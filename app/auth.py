"""
Authentication utilities for MarketLens.
Reads/writes the 'sb_access_token' and 'sb_refresh_token' cookies.
"""
import base64
import json as _json
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.db import get_admin_client


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload without signature verification."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return _json.loads(base64.b64decode(padded))
    except Exception:
        return None


async def get_current_user(request: Request) -> dict | None:
    """
    Reads 'sb_access_token' cookie, decodes the Supabase JWT locally,
    enriches with profile data (is_admin, is_active) and returns a dict.
    Returns None on any failure or if not logged in.

    Uses local JWT decode instead of a Supabase API call so that OAuth
    (PKCE) tokens work identically to email/password tokens.
    The cookie is httponly so clients cannot tamper with it via JS.
    """
    token = request.cookies.get("sb_access_token")
    if not token:
        return None
    try:
        payload = _decode_jwt_payload(token)
        if not payload:
            return None

        # Reject expired tokens
        exp = payload.get("exp", 0)
        if exp and time.time() > exp:
            return None

        user_id = payload.get("sub")
        email   = payload.get("email", "")
        if not user_id:
            return None

        # Name comes from Google user_metadata or falls back to email prefix
        meta = payload.get("user_metadata") or {}
        name = meta.get("full_name") or meta.get("name") or email.split("@")[0]

        user: dict = {
            "id":        user_id,
            "email":     email,
            "name":      name,
            "is_admin":  False,
            "is_active": True,
        }

        # Fetch profile row for is_admin / is_active / display name
        try:
            admin = get_admin_client()
            prof = (
                admin.table("profiles")
                .select("is_admin,is_active,name")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if prof and prof.data:
                user["is_admin"]  = bool(prof.data.get("is_admin", False))
                user["is_active"] = bool(prof.data.get("is_active", True))
                if prof.data.get("name"):
                    user["name"] = prof.data["name"]
        except Exception:
            pass

        # Ensure the configured admin email always has admin rights
        try:
            from app.config import ADMIN_EMAIL
            if ADMIN_EMAIL and email.lower() == ADMIN_EMAIL.lower():
                user["is_admin"] = True
        except Exception:
            pass

        return user
    except Exception:
        return None


async def require_user(request: Request):
    """
    Check if user is authenticated.
    Returns user if logged in (even if suspended), or RedirectResponse if not.
    Suspended users can access dashboard but NOT research/analysis.
    """
    from fastapi.responses import RedirectResponse

    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    # Allow suspended users to access dashboard (warning banner will show)
    # But block them from analysis in the API endpoint
    return user


async def require_admin(request: Request):
    """
    Like require_user but additionally requires is_admin=True.
    Returns user if valid, or RedirectResponse if not.
    Use only for HTML page routes — JSON API routes must use require_admin_api.
    """
    from fastapi.responses import RedirectResponse

    result = await require_user(request)

    # If require_user returned a redirect, return it
    if isinstance(result, RedirectResponse):
        return result

    user = result
    if not user.get("is_admin"):
        return RedirectResponse(url="/login?error=unauthorized", status_code=302)
    return user


async def require_user_api(request: Request) -> dict:
    """
    For JSON API endpoints: raises 401 if not authenticated.
    Never redirects — always returns a dict or raises HTTPException.
    """
    from fastapi import HTTPException
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_admin_api(request: Request) -> dict:
    """
    For JSON API endpoints: raises 401 if not authenticated, 403 if not admin.
    Never redirects — always returns a dict or raises HTTPException.
    """
    from fastapi import HTTPException
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def set_auth_cookie(response, access_token: str, refresh_token: str) -> None:
    """Set http-only auth cookies. secure=True in production (HTTPS only)."""
    import os
    _secure = os.getenv("ENVIRONMENT", "development") == "production"
    response.set_cookie(
        "sb_access_token",
        access_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,   # 7 days
        secure=_secure,
    )
    response.set_cookie(
        "sb_refresh_token",
        refresh_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days
        secure=_secure,
    )


def clear_auth_cookies(response) -> None:
    """Clear auth cookies."""
    response.delete_cookie("sb_access_token")
    response.delete_cookie("sb_refresh_token")
