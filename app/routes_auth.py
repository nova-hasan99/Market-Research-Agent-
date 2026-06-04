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
        return RedirectResponse("/dashboard", status_code=302)
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": error})


# ─── POST /login ──────────────────────────────────────────────────────────────
@router.post("/login")
async def login_submit(
    request: Request,
    email:    str = Form(...),
    password: str = Form(...),
):
    try:
        client   = get_client()
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        session  = response.session
        if not session:
            return RedirectResponse("/login?error=Invalid+credentials", status_code=302)

        redirect = RedirectResponse("/dashboard", status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect
    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        if "Invalid" in str(exc) or "credentials" in str(exc).lower():
            msg = "Invalid+email+or+password"
        return RedirectResponse(f"/login?error={msg}", status_code=302)


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
