"""
Authentication routes: /login, /register, /logout
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import get_current_user, set_auth_cookie, clear_auth_cookies
from app.db import get_client
from app.deps import templates

router = APIRouter()


# ─── GET /login ───────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_current_user(request)
    if user:
        next_url = request.query_params.get("next", "/dashboard")
        return RedirectResponse(next_url, status_code=302)
    error    = request.query_params.get("error", "")
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(
        request, "login.html",
        {"user": None, "error": error, "next": next_url},
    )


# ─── POST /login ──────────────────────────────────────────────────────────────
@router.post("/login")
async def login_submit(
    request:  Request,
    email:    str = Form(...),
    password: str = Form(...),
    next_url: str = Form(""),
):
    try:
        client   = get_client()
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        session  = response.session
        if not session:
            suffix = f"&next={next_url}" if next_url else ""
            return RedirectResponse(f"/login?error=Invalid+credentials{suffix}", status_code=302)

        dest = next_url if (next_url and next_url.startswith("/")) else "/dashboard"
        redirect = RedirectResponse(dest, status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect
    except Exception as exc:
        msg    = str(exc).replace(" ", "+")
        suffix = f"&next={next_url}" if next_url else ""
        if "Invalid" in str(exc) or "credentials" in str(exc).lower():
            msg = "Invalid+email+or+password"
        return RedirectResponse(f"/login?error={msg}{suffix}", status_code=302)


# ─── GET /register ────────────────────────────────────────────────────────────
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(request, "register.html", {"user": None, "error": error})


# ─── POST /register ───────────────────────────────────────────────────────────
@router.post("/register")
async def register_submit(
    request:  Request,
    name:     str  = Form(...),
    email:    str  = Form(...),
    password: str  = Form(...),
    phone:    str  = Form(""),
    country:  str  = Form(""),
):
    meta: dict = {"name": name}
    if phone.strip():
        meta["phone"] = phone.strip()
    if country.strip():
        meta["country"] = country.strip()

    try:
        client   = get_client()
        response = client.auth.sign_up({
            "email":    email,
            "password": password,
            "options":  {"data": meta},
        })
        session = response.session
        if not session:
            # Email confirmation required
            return templates.TemplateResponse(
                request, "register.html",
                {"user": None, "error": "", "info": "Check your email to confirm your account."},
            )
        redirect = RedirectResponse("/dashboard", status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect
    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        if "already" in str(exc).lower():
            msg = "Email+already+registered.+Try+logging+in."
        return RedirectResponse(f"/register?error={msg}", status_code=302)


# ─── GET /logout ──────────────────────────────────────────────────────────────
@router.get("/logout")
async def logout(request: Request):
    redirect = RedirectResponse("/", status_code=302)
    clear_auth_cookies(redirect)
    return redirect
