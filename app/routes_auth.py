"""
Authentication routes: /login  /register  /logout
                       /forgot-password  /reset-password
"""
import smtplib
import asyncio
import secrets
import string
import hashlib
import base64
import os
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import get_current_user, set_auth_cookie, clear_auth_cookies
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SITE_URL,
    SUPABASE_URL, BREVO_API_KEY, BREVO_FROM_NAME, BREVO_FROM_EMAIL,
)
from app.db import get_client, get_admin_client
from app.deps import templates

router = APIRouter()


# ── Email helper ──────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, html: str) -> None:
    """Send email — tries SMTP first, falls back to Resend HTTP API."""

    # ── Attempt 1: SMTP (works on localhost / platforms that allow SMTP) ───────
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
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
            return  # sent successfully
        except Exception:
            pass    # SMTP blocked (e.g. Render free plan) → try Resend

    # ── Attempt 2: Brevo REST API (HTTP — never blocked by hosting platforms) ───
    if BREVO_API_KEY:
        try:
            import json as _json
            payload = _json.dumps({
                "sender":      {"name": BREVO_FROM_NAME, "email": BREVO_FROM_EMAIL},
                "to":          [{"email": to}],
                "subject":     subject,
                "htmlContent": html,
            }).encode()
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=payload,
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass    # Never break registration if email fails


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _base_email(name: str, email: str, password: str, via_google: bool) -> str:
    google_note = (
        "<p style='margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7'>"
        "You signed up via <strong style='color:#111827'>Google</strong>. "
        "We also created an email&nbsp;+&nbsp;password login so you can always access your account:"
        "</p>"
    ) if via_google else (
        "<p style='margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7'>"
        "Your account is active. Save your login details below &mdash; you'll need them every time you sign in."
        "</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'Segoe UI',Inter,Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:40px 16px">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">

  <!-- HEADER -->
  <tr><td style="background:#1d4ed8;border-radius:14px 14px 0 0;padding:24px 36px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <span style="display:inline-block;background:rgba(255,255,255,0.2);border-radius:8px;
                     padding:5px 10px;font-size:17px;font-weight:800;color:#fff">&#9670;</span>
        <span style="font-size:18px;font-weight:700;color:#fff;vertical-align:middle;margin-left:10px">
          MarketLens
        </span>
      </td>
      <td align="right">
        <span style="font-size:12px;color:rgba(255,255,255,0.7);font-weight:500">AI Market Analysis</span>
      </td>
    </tr></table>
  </td></tr>

  <!-- HERO -->
  <tr><td style="background:#ffffff;padding:36px 36px 28px">
    <h1 style="margin:0 0 10px;font-size:26px;font-weight:800;color:#111827;line-height:1.25">
      Welcome aboard, {name}! &#127881;
    </h1>
    <p style="margin:0 0 6px;font-size:15px;color:#6b7280">Your MarketLens account is ready to use.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
    {google_note}
  </td></tr>

  <!-- CREDENTIALS CARD -->
  <tr><td style="background:#ffffff;padding:0 36px 32px">
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-radius:10px;border:1px solid #e5e7eb;overflow:hidden">
      <tr><td colspan="2"
              style="background:#1d4ed8;padding:12px 20px">
        <span style="font-size:12px;font-weight:700;color:#fff;
                     text-transform:uppercase;letter-spacing:0.08em">&#128274;&nbsp; Your Login Details</span>
      </td></tr>
      <tr style="background:#f9fafb">
        <td style="padding:14px 20px;font-size:12px;font-weight:700;color:#6b7280;
                   text-transform:uppercase;letter-spacing:0.06em;width:100px;
                   border-bottom:1px solid #e5e7eb">Email</td>
        <td style="padding:14px 20px;font-size:14px;color:#111827;
                   border-bottom:1px solid #e5e7eb">{email}</td>
      </tr>
      <tr style="background:#ffffff">
        <td style="padding:14px 20px;font-size:12px;font-weight:700;color:#6b7280;
                   text-transform:uppercase;letter-spacing:0.06em">Password</td>
        <td style="padding:14px 20px;font-size:15px;color:#1d4ed8;
                   font-family:'Courier New',monospace;font-weight:700;
                   letter-spacing:0.06em">{password}</td>
      </tr>
    </table>
    <p style="margin:12px 0 0;font-size:13px;color:#9ca3af;line-height:1.6">
      Keep this email safe. Change your password anytime via
      <a href="{SITE_URL}/forgot-password" style="color:#1d4ed8;text-decoration:none;font-weight:600">Forgot Password</a>.
    </p>
  </td></tr>

  <!-- DIVIDER -->
  <tr><td style="background:#ffffff;padding:0 36px">
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:0">
  </td></tr>

  <!-- FEATURES -->
  <tr><td style="background:#ffffff;padding:28px 36px">
    <p style="margin:0 0 18px;font-size:12px;font-weight:700;color:#9ca3af;
              text-transform:uppercase;letter-spacing:0.1em">What you can do</p>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="50%" style="padding:0 6px 12px 0;vertical-align:top">
          <div style="background:#f0f9ff;border-radius:10px;padding:16px;border:1px solid #bae6fd">
            <div style="font-size:20px;margin-bottom:8px">&#128200;</div>
            <div style="font-size:13px;font-weight:700;color:#0c4a6e;margin-bottom:4px">Live Market Analysis</div>
            <div style="font-size:12px;color:#0369a1;line-height:1.5">Real-time signals for Forex, Stocks &amp; Crypto</div>
          </div>
        </td>
        <td width="50%" style="padding:0 0 12px 6px;vertical-align:top">
          <div style="background:#f0fdf4;border-radius:10px;padding:16px;border:1px solid #bbf7d0">
            <div style="font-size:20px;margin-bottom:8px">&#129302;</div>
            <div style="font-size:13px;font-weight:700;color:#14532d;margin-bottom:4px">AI Trade Guidance</div>
            <div style="font-size:12px;color:#15803d;line-height:1.5">Stop loss, take profit &amp; confidence score</div>
          </div>
        </td>
      </tr>
      <tr>
        <td width="50%" style="padding:0 6px 0 0;vertical-align:top">
          <div style="background:#fff7ed;border-radius:10px;padding:16px;border:1px solid #fed7aa">
            <div style="font-size:20px;margin-bottom:8px">&#128240;</div>
            <div style="font-size:13px;font-weight:700;color:#7c2d12;margin-bottom:4px">News Sentiment</div>
            <div style="font-size:12px;color:#c2410c;line-height:1.5">Market-moving news with sentiment scoring</div>
          </div>
        </td>
        <td width="50%" style="padding:0 0 0 6px;vertical-align:top">
          <div style="background:#faf5ff;border-radius:10px;padding:16px;border:1px solid #e9d5ff">
            <div style="font-size:20px;margin-bottom:8px">&#128337;</div>
            <div style="font-size:13px;font-weight:700;color:#581c87;margin-bottom:4px">Multi-Timeframe</div>
            <div style="font-size:12px;color:#7e22ce;line-height:1.5">1H · 4H · 8H · Daily analysis in one view</div>
          </div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="background:#ffffff;border-radius:0 0 14px 14px;padding:0 36px 40px;text-align:center">
    <a href="{SITE_URL}/research"
       style="display:inline-block;padding:15px 44px;background:#1d4ed8;
              color:#fff;text-decoration:none;border-radius:10px;font-size:15px;
              font-weight:700;letter-spacing:0.02em">
      Start Analyzing Markets &#8594;
    </a>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="padding:24px 36px;text-align:center">
    <p style="margin:0 0 6px;font-size:12px;color:#9ca3af">
      &copy; 2025 MarketLens &mdash; AI-Powered Market Analysis
    </p>
    <p style="margin:0 0 6px;font-size:12px;color:#d1d5db">
      Sent to <span style="color:#6b7280">{email}</span> because you created an account.
    </p>
    <p style="margin:0;font-size:11px;color:#d1d5db">Not financial advice. Always manage your risk.</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def _welcome_google_email_html(name: str, email: str, password: str) -> str:
    return _base_email(name, email, password, via_google=True)


def _welcome_email_html(name: str, email: str, password: str) -> str:
    return _base_email(name, email, password, via_google=False)


# ── GET /login ────────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_current_user(request)
    if user:
        next_url = request.query_params.get("next", "/dashboard")
        return RedirectResponse(next_url, status_code=302)
    error       = request.query_params.get("error", "")
    next_url    = request.query_params.get("next", "")
    blocked     = request.query_params.get("blocked", "")
    try:
        retry_after = int(request.query_params.get("retry_after", "0") or "0")
    except ValueError:
        retry_after = 0
    return templates.TemplateResponse(
        request, "login.html",
        {"user": None, "error": error, "next": next_url,
         "blocked": blocked, "retry_after": retry_after},
    )


# ── POST /login ───────────────────────────────────────────────────────────────
@router.post("/login")
async def login_submit(
    request:  Request,
    email:    str = Form(...),
    password: str = Form(...),
    next_url: str = Form(""),
):
    from app.rate_limit import get_client_ip, is_blocked, record_failure, clear as rl_clear

    ip     = get_client_ip(request)
    suffix = f"&next={next_url}" if next_url else ""

    # ── Pre-check: already blocked? ────────────────────────────────────────────
    blocked, retry_after = is_blocked(ip)
    if blocked:
        return RedirectResponse(
            f"/login?blocked=1&retry_after={retry_after}{suffix}",
            status_code=302,
        )

    # ── Attempt authentication ─────────────────────────────────────────────────
    try:
        client   = get_client()
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        session  = response.session
        if not session:
            record_failure(ip)
            blocked2, retry_after2 = is_blocked(ip)
            if blocked2:
                return RedirectResponse(
                    f"/login?blocked=1&retry_after={retry_after2}{suffix}",
                    status_code=302,
                )
            return RedirectResponse(f"/login?error=Invalid+email+or+password{suffix}", status_code=302)

        # ── Success: clear the failure counter ─────────────────────────────────
        rl_clear(ip)
        dest     = next_url if (next_url and next_url.startswith("/")) else "/dashboard"
        redirect = RedirectResponse(dest, status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        return redirect

    except Exception as exc:
        record_failure(ip)
        blocked2, retry_after2 = is_blocked(ip)
        if blocked2:
            return RedirectResponse(
                f"/login?blocked=1&retry_after={retry_after2}{suffix}",
                status_code=302,
            )
        msg = "Invalid+email+or+password" if (
            "Invalid" in str(exc) or "credentials" in str(exc).lower()
        ) else str(exc).replace(" ", "+")
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


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier  = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ── GET /auth/google ──────────────────────────────────────────────────────────
@router.get("/auth/google")
async def auth_google(request: Request):
    """Initiate Google OAuth with PKCE.
    Verifier is stored in BOTH the redirect_to URL param (primary) and a
    short-lived cookie (fallback) so it survives the cross-domain redirect chain.
    """
    verifier, challenge = _pkce_pair()
    # Primary: embed verifier in callback URL — Supabase appends &code=... to it
    callback_url = f"{SITE_URL}/auth/callback?cv={verifier}"
    qs = urllib.parse.urlencode({
        "provider":              "google",
        "redirect_to":           callback_url,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    resp = RedirectResponse(f"{SUPABASE_URL}/auth/v1/authorize?{qs}", status_code=302)
    # Fallback: also store verifier in a short-lived httponly cookie
    resp.set_cookie(
        "pkce_verifier", verifier,
        httponly=True, samesite="lax", secure=False, max_age=600,
    )
    return resp


# ── GET /auth/callback ────────────────────────────────────────────────────────
@router.get("/auth/callback")
async def auth_callback(request: Request):
    """Supabase redirects here after Google OAuth with ?code=xxx&cv=<verifier>."""
    from datetime import datetime, timezone

    code = request.query_params.get("code", "")
    # Primary: verifier embedded in the redirect_to URL by /auth/google
    # Fallback: short-lived cookie set by /auth/google as a backup
    code_verifier = (
        request.query_params.get("cv", "")
        or request.cookies.get("pkce_verifier", "")
    )

    if not code:
        return RedirectResponse("/login?error=OAuth+authentication+failed", status_code=302)
    if not code_verifier:
        return RedirectResponse("/login?error=Invalid+OAuth+state.+Please+try+again.", status_code=302)

    try:
        client   = get_client()
        response = client.auth.exchange_code_for_session({
            "auth_code":     code,
            "code_verifier": code_verifier,
        })

        if not response or not response.session:
            return RedirectResponse("/login?error=Could+not+create+session", status_code=302)

        session = response.session
        user    = response.user

        # Ensure profile row exists for this Google user
        if user:
            try:
                admin = get_admin_client()
                meta  = user.user_metadata or {}
                name  = meta.get("full_name") or meta.get("name") or (user.email or "").split("@")[0]
                existing = (
                    admin.table("profiles")
                    .select("id")
                    .eq("id", user.id)
                    .maybe_single()
                    .execute()
                )
                if not existing or not existing.data:
                    admin.table("profiles").insert({
                        "id":        user.id,
                        "email":     user.email,
                        "name":      name,
                        "is_admin":  False,
                        "is_active": True,
                    }).execute()
            except Exception:
                pass

        # For brand-new Google accounts: generate a password + send welcome email
        if user and user.email:
            try:
                created_at = user.created_at
                if created_at:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - created_at).total_seconds() < 30:
                        meta      = user.user_metadata or {}
                        name      = meta.get("full_name") or meta.get("name") or user.email.split("@")[0]
                        auto_pass = _generate_password()
                        try:
                            admin = get_admin_client()
                            admin.auth.admin.update_user_by_id(user.id, {"password": auto_pass})
                        except Exception:
                            pass
                        asyncio.get_event_loop().run_in_executor(
                            None, _send_email, user.email,
                            "Welcome to MarketLens — Your Account Details",
                            _welcome_google_email_html(name, user.email, auto_pass),
                        )
            except Exception:
                pass

        redirect = RedirectResponse("/research", status_code=302)
        set_auth_cookie(redirect, session.access_token, session.refresh_token)
        redirect.delete_cookie("pkce_verifier")
        return redirect

    except Exception as exc:
        msg = str(exc).replace(" ", "+")
        return RedirectResponse(f"/login?error={msg}", status_code=302)
