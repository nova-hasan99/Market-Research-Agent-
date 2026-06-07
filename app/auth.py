"""
Authentication utilities for MarketLens.
Reads/writes the 'sb_access_token' and 'sb_refresh_token' cookies.
"""
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

from app.db import get_client, get_admin_client


def _profile_from_supabase(user_obj) -> dict:
    """Build a user dict from the Supabase user object and metadata."""
    uid   = user_obj.id
    email = user_obj.email or ""
    meta  = user_obj.user_metadata or {}
    name  = meta.get("name") or email.split("@")[0]
    return {
        "id":        uid,
        "email":     email,
        "name":      name,
        "is_admin":  False,
        "is_active": True,
    }


async def get_current_user(request: Request) -> dict | None:
    """
    Reads 'sb_access_token' cookie, verifies the token with Supabase,
    enriches it with profile data (is_admin, is_active) and returns a dict.
    Returns None on any failure or if not logged in.
    """
    token = request.cookies.get("sb_access_token")
    if not token:
        return None
    try:
        client   = get_client()
        response = client.auth.get_user(token)
        if not response or not response.user:
            return None
        user = _profile_from_supabase(response.user)

        # Fetch profile row for is_admin / is_active
        # Must use admin client (service key) to bypass RLS on the profiles table
        try:
            admin = get_admin_client()
            prof = (
                admin.table("profiles")
                .select("is_admin,is_active,name")
                .eq("id", user["id"])
                .maybe_single()
                .execute()
            )
            if prof and prof.data:
                user["is_admin"]  = bool(prof.data.get("is_admin", False))
                user["is_active"] = bool(prof.data.get("is_active", True))
                if prof.data.get("name"):
                    user["name"] = prof.data["name"]
            else:
                import logging
                logging.getLogger(__name__).warning(
                    "No profile row found for user %s — defaulting is_active=True", user["id"]
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Profile fetch FAILED for %s: %s — defaulting is_active=True", user["id"], e
            )

        # Fallback: if ADMIN_EMAIL is set in config and matches, grant admin
        # This ensures the super admin always has access even if the profiles
        # table is missing or the is_admin column isn't set.
        try:
            from app.config import ADMIN_EMAIL
            if ADMIN_EMAIL and user["email"].lower() == ADMIN_EMAIL.lower():
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


def set_auth_cookie(response, access_token: str, refresh_token: str) -> None:
    """Set http-only auth cookies."""
    response.set_cookie(
        "sb_access_token",
        access_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,   # 7 days
        secure=False,                 # set True in production with HTTPS
    )
    response.set_cookie(
        "sb_refresh_token",
        refresh_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days
        secure=False,
    )


def clear_auth_cookies(response) -> None:
    """Clear auth cookies."""
    response.delete_cookie("sb_access_token")
    response.delete_cookie("sb_refresh_token")
