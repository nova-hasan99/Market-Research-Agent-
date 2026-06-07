"""
Authentication routes: /login  /register  /logout
                       /forgot-password  /reset-password
"""
import smtplib
import asyncio
import secrets
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import get_current_user, set_auth_cookie, clear_auth_cookies
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SITE_URL,
)
from app.db import get_client, get_admin_client
from app.deps import templates

router = APIRouter()


# ── Email helper ──────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, html: str) -> None:
    """Send an email via SMTP. Silently skips if SMTP is not configured."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM or SMTP_USER
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.sendmail(SMTP_FROM or SMTP_USER, [to], msg.as_string())
    except Exception:
        pass   # Never break registration if email fails


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _welcome_google_email_html(name: str, email: str, password: str) -> str:
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:auto;
                background:#0d1117;color:#f0f6fc;border-radius:12px;padding:2rem">
      <h2 style="color:#3b82f6;margin-top:0">Welcome to MarketLens</h2>
      <p>Hi <strong>{name}</strong>, your account is ready.</p>
      <p style="color:#8b949e;font-size:0.875rem">
        You signed up with Google. We also created an email &amp; password login for you:
      </p>
      <table style="border-collapse:collapse;width:100%;margin:1.5rem 0">
        <tr>
          <td style="padding:0.5rem 1rem;background:#161b22;border-radius:6px 6px 0 0;
                     color:#8b949e;font-size:0.8rem;font-weight:600;
                     text-transform:uppercase;letter-spacing:0.05em">Email</td>
          <td style="padding:0.5rem 1rem;background:#161b22">{email}</td>
        </tr>
        <tr>
          <td style="padding:0.5rem 1rem;background:#1c2128;
                     color:#8b949e;font-size:0.8rem;font-weight:600;
                     text-transform:uppercase;letter-spacing:0.05em">Password</td>
          <td style="padding:0.5rem 1rem;background:#1c2128;font-family:monospace">{password}</td>
        </tr>
      </table>
      <p style="color:#8b949e;font-size:0.875rem">
        You can sign in with Google <strong>or</strong> directly with email + password.<br>
        You can change your password anytime via
        <a href="{SITE_URL}/forgot-password" style="color:#3b82f6">Forgot Password</a>.
      </p>
      <a href="{SITE_URL}/research" style="display:inline-block;margin-top:1rem;
         padding:0.65rem 1.5rem;background:#3b82f6;color:#fff;border-radius:8px;
         text-decoration:none;font-weight:700">Open MarketLens</a>
    </div>"""


def _welcome_email_html(name: str, email: str, password: str) -> str:
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:auto;
                background:#0d1117;color:#f0f6fc;border-radius:12px;padding:2rem">
      <h2 style="color:#3b82f6;margin-top:0">Welcome to MarketLens</h2>
      <p>Hi <strong>{name}</strong>, your account is ready.</p>
      <table style="border-collapse:collapse;width:100%;margin:1.5rem 0">
        <tr>
          <td style="padding:0.5rem 1rem;background:#161b22;border-radius:6px 6px 0 0;
                     color:#8b949e;font-size:0.8rem;font-weight:600;
                     text-transform:uppercase;letter-spacing:0.05em">Email</td>
          <td style="padding:0.5rem 1rem;background:#161b22;border-radius:0 0 0 0">{email}</td>
        </tr>
        <tr>
          <td style="padding:0.5rem 1rem;background:#1c2128;
                     color:#8b949e;font-size:0.8rem;font-weight:600;
                     text-transform:uppercase;letter-spacing:0.05em">Password</td>
          <td style="padding:0.5rem 1rem;background:#1c2128">{password}</td>
        </tr>
      </table>
      <p style="color:#8b949e;font-size:0.875rem">
        Keep this email safe. You can change your password any time via the
        <a href="{SITE_URL}/forgot-password" style="color:#3b82f6">Forgot Password</a> page.
      </p>
      <a href="{SITE_URL}/research" style="display:inline-block;margin-top:1rem;
         padding:0.65rem 1.5rem;background:#3b82f6;color:#fff;border-radius:8px;
         text-decoration:none;font-weight:700">Open MarketLens</a>
    </div>"""


# ── GET /login ────────────────────────────────────────────────────────────────
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


# ── POST /login ───────────────────────────────────────────────────────────────
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


# ── GET /register ─────────────────────────────────────────────────────────────
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(request, "register.html", {"user": None, "error": error})


# ── POST /register ────────────────────────────────────────────────────────────
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
        client = get_client()
        # 1. Sign up (may require email confirmation in Supabase settings)
        response = client.auth.sign_up({
            "email":    email,
            "password": password,
            "options":  {"data": meta},
        })

        if not response.user:
            return RedirectResponse("/register?error=Registration+failed", status_code=302)

        user_id = response.user.id

        # 2. Auto-confirm the email via admin API (bypasses email confirmation)
        try:
            admin = get_admin_client()
            admin.auth.admin.update_user_by_id(user_id, {"email_confirm": True})
        except Exception:
            pass   # If admin confirm fails, try to sign in anyway

        # 3. Sign in immediately to get a valid session
        sign_in = client.auth.sign_in_with_password({"email": email, "password": password})
        session = sign_in.session

        if not session:
            # Fallback: email confirmation still pending — show friendly message
            return templates.TemplateResponse(
                request, "register.html",
                {"user": None, "error": "",
                 "info": "Account created! Please check your email to confirm before signing in."},
            )

        # 4. Send welcome email in the background (non-blocking)
        asyncio.get_event_loop().run_in_executor(
            None, _send_email, email,
            "Welcome to MarketLens — Your Account Details",
            _welcome_email_html(name, email, password),
        )

        # 5. Redirect straight to dashboard
        redirect = RedirectResponse("/dashboard", status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect

    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        if "already" in str(exc).lower():
            msg = "Email+already+registered.+Try+logging+in."
        return RedirectResponse(f"/register?error={msg}", status_code=302)


# ── GET /logout ───────────────────────────────────────────────────────────────
@router.get("/logout")
async def logout(request: Request):
    redirect = RedirectResponse("/", status_code=302)
    clear_auth_cookies(redirect)
    return redirect


# ── GET /forgot-password ─────────────────────────────────────────────────────
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    sent  = request.query_params.get("sent",  "")
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(
        request, "forgot_password.html",
        {"user": None, "sent": sent, "error": error},
    )


# ── POST /forgot-password ────────────────────────────────────────────────────
@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    email:   str = Form(...),
):
    try:
        client = get_client()
        reset_url = f"{SITE_URL}/reset-password"
        client.auth.reset_password_for_email(email, {"redirect_to": reset_url})
        return RedirectResponse(
            "/forgot-password?sent=1",
            status_code=302,
        )
    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        return RedirectResponse(f"/forgot-password?error={msg}", status_code=302)


# ── GET /reset-password ──────────────────────────────────────────────────────
@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    error        = request.query_params.get("error", "")
    access_token = ""
    refresh_token = ""

    # PKCE flow: Supabase redirects with ?code=xxx
    code = request.query_params.get("code", "")
    if code:
        try:
            client   = get_client()
            response = client.auth.exchange_code_for_session({"auth_code": code})
            if response and response.session:
                access_token  = response.session.access_token or ""
                refresh_token = response.session.refresh_token or ""
        except Exception:
            error = "Invalid or expired reset link. Please request a new one."

    return templates.TemplateResponse(
        request, "reset_password.html",
        {"user": None, "error": error,
         "access_token": access_token, "refresh_token": refresh_token},
    )


# ── POST /reset-password ─────────────────────────────────────────────────────
@router.post("/reset-password")
async def reset_password_submit(
    request:       Request,
    access_token:  str = Form(...),
    refresh_token: str = Form(""),
    new_password:  str = Form(...),
):
    if len(new_password) < 6:
        return RedirectResponse("/reset-password?error=Password+must+be+at+least+6+characters", status_code=302)
    try:
        client = get_client()
        # Restore the session from the reset link tokens
        client.auth.set_session(access_token, refresh_token)
        client.auth.update_user({"password": new_password})

        # Sign out all other sessions for security
        try:
            client.auth.sign_out()
        except Exception:
            pass

        return RedirectResponse("/login?error=Password+updated.+Please+sign+in+with+your+new+password.", status_code=302)
    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        return RedirectResponse(f"/reset-password?error={msg}", status_code=302)


# ── GET /auth/google ──────────────────────────────────────────────────────────
@router.get("/auth/google")
async def auth_google(request: Request):
    """Initiate Google OAuth — redirects to Google consent screen via Supabase."""
    try:
        client   = get_client()
        response = client.auth.sign_in_with_oauth({
            "provider": "google",
            "options":  {"redirect_to": f"{SITE_URL}/auth/callback"},
        })
        return RedirectResponse(response.url, status_code=302)
    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        return RedirectResponse(f"/login?error={msg}", status_code=302)


# ── GET /auth/callback ────────────────────────────────────────────────────────
@router.get("/auth/callback")
async def auth_callback(request: Request):
    """Supabase redirects here after Google OAuth with ?code=xxx."""
    from datetime import datetime, timezone

    code = request.query_params.get("code", "")
    if not code:
        return RedirectResponse("/login?error=OAuth+authentication+failed", status_code=302)

    try:
        client   = get_client()
        response = client.auth.exchange_code_for_session({"auth_code": code})

        if not response or not response.session:
            return RedirectResponse("/login?error=Could+not+create+session", status_code=302)

        session = response.session
        user    = response.user

        # For brand-new Google accounts: generate a password so they can also
        # sign in with email + password, then send welcome email with credentials.
        if user and user.email:
            try:
                created_at = user.created_at
                if created_at:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    diff = (datetime.now(timezone.utc) - created_at).total_seconds()
                    if diff < 30:
                        meta      = user.user_metadata or {}
                        name      = meta.get("full_name") or meta.get("name") or user.email.split("@")[0]
                        auto_pass = _generate_password()
                        # Set the generated password via admin API
                        try:
                            admin = get_admin_client()
                            admin.auth.admin.update_user_by_id(
                                user.id, {"password": auto_pass}
                            )
                        except Exception:
                            pass
                        asyncio.get_event_loop().run_in_executor(
                            None, _send_email, user.email,
                            "Welcome to MarketLens — Your Account Details",
                            _welcome_google_email_html(name, user.email, auto_pass),
                        )
            except Exception:
                pass

        redirect = RedirectResponse("/dashboard", status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect

    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        return RedirectResponse(f"/login?error={msg}", status_code=302)
