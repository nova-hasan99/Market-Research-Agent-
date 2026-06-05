"""
Dashboard routes for MarketLens.
Handles user analysis history, admin panel, and export.
"""
import io
import json
import csv as csv_mod
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.auth import get_current_user, require_user, require_admin
from app.db import get_admin_client
from app.deps import templates

router = APIRouter()


# ─── helpers ──────────────────────────────────────────────────────────────────
def _admin_client():
    return get_admin_client()


def _fetch_user_analyses(user_id: str) -> list:
    client = _admin_client()
    result = (
        client.table("analyses")
        .select("id,asset_type,asset,score,bias,last_price,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ─── GET /dashboard ───────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await require_user(request)

    # Support admin viewing another user's dashboard
    view_user_id = request.query_params.get("user_id", user["id"])
    if view_user_id != user["id"] and not user.get("is_admin"):
        view_user_id = user["id"]

    analyses = _fetch_user_analyses(view_user_id)

    forex_analyses = [a for a in analyses if a.get("asset_type") == "forex"]
    stock_analyses = [a for a in analyses if a.get("asset_type") == "stock"]

    return templates.TemplateResponse(request, "dashboard.html", {
        "user":            user,
        "forex_analyses":  forex_analyses,
        "stock_analyses":  stock_analyses,
        "view_user_id":    view_user_id,
    })


# ─── GET /admin/users — dedicated Super Admin user-management page ────────────
@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login?next=/admin/users", status_code=302)
    if not user.get("is_admin"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "admin_users.html", {"user": user})


# ─── GET /dashboard/view/{id} — full-page analysis viewer ────────────────────
@router.get("/dashboard/view/{analysis_id}", response_class=HTMLResponse)
async def view_analysis_page(request: Request, analysis_id: str):
    user = await require_user(request)
    client = _admin_client()
    result = (
        client.table("analyses")
        .select("*")
        .eq("id", analysis_id)
        .maybe_single()
        .execute()
    )
    row = result.data
    if not row:
        raise HTTPException(404, "Analysis not found")
    if row["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    analysis_data = row.get("data") or {}
    return templates.TemplateResponse(request, "analysis_view.html", {
        "user":               user,
        "analysis":           row,
        "analysis_data_json": json.dumps(analysis_data, default=str),
    })


# ─── GET /dashboard/analysis/{id} — JSON API for JS ──────────────────────────
@router.get("/dashboard/analysis/{analysis_id}")
async def get_analysis(request: Request, analysis_id: str):
    user = await require_user(request)
    client = _admin_client()

    result = (
        client.table("analyses")
        .select("*")
        .eq("id", analysis_id)
        .maybe_single()
        .execute()
    )
    row = result.data
    if not row:
        raise HTTPException(404, "Analysis not found")
    if row["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    # Return the full data dict for JS renderResults()
    data = row.get("data") or {}
    return JSONResponse(data)


# ─── POST /api/dashboard/save ─────────────────────────────────────────────────
@router.post("/api/dashboard/save")
async def save_analysis(request: Request):
    user = await require_user(request)
    body = await request.json()

    client = _admin_client()
    result = (
        client.table("analyses")
        .insert({
            "user_id":    user["id"],
            "asset_type": body.get("asset_type", ""),
            "asset":      body.get("asset", ""),
            "score":      body.get("score"),
            "bias":       body.get("bias", ""),
            "last_price": str(body.get("last_price", "")),
            "data":       body,
        })
        .execute()
    )
    rows = result.data or []
    new_id = rows[0]["id"] if rows else None
    return {"ok": True, "id": new_id}


# ─── DELETE /api/dashboard/analyses/{id} ──────────────────────────────────────
@router.delete("/api/dashboard/analyses/{analysis_id}")
async def delete_analysis(request: Request, analysis_id: str):
    user = await require_user(request)
    client = _admin_client()

    row = (
        client.table("analyses")
        .select("user_id")
        .eq("id", analysis_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        raise HTTPException(404, "Not found")
    if row["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    client.table("analyses").delete().eq("id", analysis_id).execute()
    return {"ok": True}


# ─── DELETE /api/dashboard/analyses (bulk) ────────────────────────────────────
@router.delete("/api/dashboard/analyses")
async def delete_analyses_bulk(request: Request):
    user = await require_user(request)
    body = await request.json()
    ids  = body.get("ids", [])
    if not ids:
        return {"ok": True, "deleted": 0}

    client = _admin_client()
    # Only delete rows that belong to the user (or admin)
    q = client.table("analyses").delete().in_("id", ids)
    if not user.get("is_admin"):
        q = q.eq("user_id", user["id"])
    q.execute()
    return {"ok": True, "deleted": len(ids)}


# ─── GET /api/dashboard/export ────────────────────────────────────────────────
@router.get("/api/dashboard/export")
async def export_analyses(
    request:    Request,
    format:     str = "csv",
    ids:        Optional[str] = None,
    asset_type: Optional[str] = None,
):
    user = await require_user(request)
    client = _admin_client()

    q = client.table("analyses").select("*").eq("user_id", user["id"])
    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
        q = q.in_("id", id_list)
    if asset_type:
        q = q.eq("asset_type", asset_type)

    rows = (q.order("created_at", desc=True).execute()).data or []

    if format == "xlsx":
        return _export_xlsx(rows)
    # default: csv
    return _export_csv(rows)


def _flat_row(row: dict) -> dict:
    data = row.get("data") or {}
    return {
        "id":         row.get("id", ""),
        "asset_type": row.get("asset_type", ""),
        "asset":      row.get("asset", ""),
        "score":      row.get("score", ""),
        "bias":       row.get("bias", ""),
        "last_price": row.get("last_price", ""),
        "created_at": row.get("created_at", ""),
        "ai_summary": (data.get("ai_summary") or {}).get("text", ""),
        "key_signal": (data.get("key_signal") or {}).get("text", ""),
        "main_risk":  data.get("main_risk", ""),
    }


def _export_csv(rows: list) -> StreamingResponse:
    output = io.StringIO()
    fields = ["id", "asset_type", "asset", "score", "bias", "last_price",
              "created_at", "ai_summary", "key_signal", "main_risk"]
    writer = csv_mod.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(_flat_row(row))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analyses.csv"},
    )


def _export_xlsx(rows: list):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(500, "openpyxl not installed")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analyses"

    headers = ["ID", "Type", "Asset", "Score", "Bias", "Last Price",
               "Date/Time", "AI Summary", "Key Signal", "Main Risk"]
    keys    = ["id", "asset_type", "asset", "score", "bias", "last_price",
               "created_at", "ai_summary", "key_signal", "main_risk"]

    header_fill = PatternFill("solid", fgColor="0F1923")
    header_font = Font(bold=True, color="E8EDF5")

    for col_idx, hdr in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=hdr)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, row in enumerate(rows, 2):
        flat = _flat_row(row)
        for col_idx, key in enumerate(keys, 1):
            ws.cell(row=row_idx, column=col_idx, value=flat.get(key, ""))

    # Auto-fit column widths
    for col in ws.columns:
        max_len = 0
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=analyses.xlsx"},
    )


# ─── Admin: GET /api/admin/users ──────────────────────────────────────────────
@router.get("/api/admin/users")
async def admin_get_users(request: Request):
    await require_admin(request)
    client = _admin_client()

    profiles = (
        client.table("profiles")
        .select("id,name,email,is_admin,is_active,created_at,last_seen")
        .execute()
    ).data or []

    # Get analysis counts per user
    counts_raw = (
        client.table("analyses")
        .select("user_id")
        .execute()
    ).data or []

    count_map: dict = {}
    for row in counts_raw:
        uid = row["user_id"]
        count_map[uid] = count_map.get(uid, 0) + 1

    for p in profiles:
        p["analysis_count"] = count_map.get(p["id"], 0)

    return profiles


# ─── Email helper (reuse from routes_auth) ───────────────────────────────────
def _notify_user(email: str, name: str, subject: str, html: str) -> None:
    from app.routes_auth import _send_email
    _send_email(email, subject, html)


def _deactivate_email_html(name: str) -> str:
    from app.config import SITE_URL
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:auto;
                background:#0d1117;color:#f0f6fc;border-radius:12px;padding:2rem">
      <h2 style="color:#ef4444;margin-top:0">Account Suspended</h2>
      <p>Hi <strong>{name}</strong>,</p>
      <p>Your MarketLens account has been temporarily <strong>deactivated</strong> by an administrator.
         You will not be able to log in or use any features until your account is reinstated.</p>
      <p>If you believe this is an error, please contact support.</p>
      <p style="color:#6b7280;font-size:0.85rem;margin-top:1.5rem">— The MarketLens Team</p>
    </div>"""


def _activate_email_html(name: str) -> str:
    from app.config import SITE_URL
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:auto;
                background:#0d1117;color:#f0f6fc;border-radius:12px;padding:2rem">
      <h2 style="color:#10b981;margin-top:0">Account Reinstated</h2>
      <p>Hi <strong>{name}</strong>,</p>
      <p>Your MarketLens account has been <strong>reactivated</strong>.
         You can now log in and use all features as normal.</p>
      <a href="{SITE_URL}/login" style="display:inline-block;margin-top:1rem;
         padding:0.65rem 1.5rem;background:#10b981;color:#fff;border-radius:8px;
         text-decoration:none;font-weight:700">Sign In Now</a>
      <p style="color:#6b7280;font-size:0.85rem;margin-top:1.5rem">— The MarketLens Team</p>
    </div>"""


def _get_user_profile(uid: str) -> dict:
    """Fetch user profile (name + email) for email notifications."""
    try:
        client = _admin_client()
        rows = client.table("profiles").select("name,email").eq("id", uid).execute().data
        return rows[0] if rows else {}
    except Exception:
        return {}


# ─── Admin: POST /api/admin/users/{uid}/deactivate ───────────────────────────
@router.post("/api/admin/users/{uid}/deactivate")
async def admin_deactivate_user(request: Request, uid: str):
    await require_admin(request)
    client = _admin_client()
    client.table("profiles").update({"is_active": False}).eq("id", uid).execute()
    # Also ban via Supabase Auth so active sessions are invalidated
    try:
        client.auth.admin.update_user_by_id(uid, {"ban_duration": "876600h"})  # ~100 years
    except Exception:
        pass
    # Email notification (non-blocking)
    profile = _get_user_profile(uid)
    if profile.get("email"):
        import asyncio
        asyncio.get_event_loop().run_in_executor(
            None, _notify_user,
            profile["email"], profile.get("name", "User"),
            "Your MarketLens Account Has Been Suspended",
            _deactivate_email_html(profile.get("name", "User")),
        )
    return {"ok": True}


# ─── Admin: POST /api/admin/users/{uid}/activate ─────────────────────────────
@router.post("/api/admin/users/{uid}/activate")
async def admin_activate_user(request: Request, uid: str):
    await require_admin(request)
    client = _admin_client()
    client.table("profiles").update({"is_active": True}).eq("id", uid).execute()
    # Unban in Supabase Auth
    try:
        client.auth.admin.update_user_by_id(uid, {"ban_duration": "none"})
    except Exception:
        pass
    # Email notification
    profile = _get_user_profile(uid)
    if profile.get("email"):
        import asyncio
        asyncio.get_event_loop().run_in_executor(
            None, _notify_user,
            profile["email"], profile.get("name", "User"),
            "Your MarketLens Account Has Been Reinstated",
            _activate_email_html(profile.get("name", "User")),
        )
    return {"ok": True}


# ─── Admin: DELETE /api/admin/users/{uid} ────────────────────────────────────
@router.delete("/api/admin/users/{uid}")
async def admin_delete_user(request: Request, uid: str):
    """
    Permanently delete a user and ALL their data:
      1. Delete all analyses from the analyses table
      2. Delete profile row
      3. Delete from Supabase Auth (revokes all sessions)
    """
    await require_admin(request)
    # Prevent self-deletion
    me = await require_admin(request)
    if me["id"] == uid:
        raise HTTPException(400, "Cannot delete your own account")

    client = _admin_client()
    # 1. Delete all analyses
    try:
        client.table("analyses").delete().eq("user_id", uid).execute()
    except Exception:
        pass
    # 2. Delete profile row
    try:
        client.table("profiles").delete().eq("id", uid).execute()
    except Exception:
        pass
    # 3. Delete from Supabase Auth
    try:
        client.auth.admin.delete_user(uid)
    except Exception as e:
        raise HTTPException(500, f"Auth deletion failed: {e}")

    return {"ok": True, "deleted": uid}


# ─── Admin: GET /api/admin/users/{uid}/analyses ──────────────────────────────
@router.get("/api/admin/users/{uid}/analyses")
async def admin_get_user_analyses(request: Request, uid: str):
    await require_admin(request)
    rows = _fetch_user_analyses(uid)
    return rows
