"""
Setup script for MarketLens Supabase database.
Run from project root:  python scripts/setup_db.py

Steps:
  1. Apply 001_schema.sql via Supabase Management API
  2. Create admin user via Auth Admin API (service key)
  3. Set is_admin=true on the admin profile row

Requires .env with:
  VITE_SUPABASE_URL, SUPABASE_SERVICE_KEY,
  SUPABASE_ACCESS_TOKEN (Management API Personal Access Token),
  VITE_ADMIN_EMAIL, VITE_ADMIN_PASSWORD
"""
import os
import sys
import pathlib

import httpx
from dotenv import load_dotenv

# ─── config ───────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SUPABASE_URL          = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_SERVICE_KEY  = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN", "")
ADMIN_EMAIL           = os.getenv("VITE_ADMIN_EMAIL", "")
ADMIN_PASS            = os.getenv("VITE_ADMIN_PASSWORD", "")

# httpx client shared across helpers (proper User-Agent bypasses Cloudflare 1010)
_HEADERS_BASE = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; MarketLens-Setup/1.0)",
}


# ─── low-level request helper ─────────────────────────────────────────────────
def _req(method: str, url: str, token: str,
         payload: dict | None = None,
         extra_headers: dict | None = None) -> dict:
    """Make an HTTP request; always returns a dict (errors in '__error' key)."""
    headers = {
        **_HEADERS_BASE,
        "Authorization": f"Bearer {token}",
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as c:
            r = c.request(method, url, json=payload, headers=headers)
            if r.status_code in (200, 201, 204):
                try:
                    return r.json()
                except Exception:
                    return {}          # 204 No Content
            return {"__error": f"HTTP {r.status_code}: {r.text[:600]}"}
    except Exception as exc:
        return {"__error": str(exc)}


# ─── print helpers ────────────────────────────────────────────────────────────
def ok(msg: str)                  -> None: print(f"  [OK]   {msg}")
def fail(msg: str, detail: str = "") -> None:
    print(f"  [FAIL] {msg}" + (f"\n         {detail}" if detail else ""))


# ─── step 1: schema migration ─────────────────────────────────────────────────
def apply_schema() -> bool:
    print("\n[1/3] Applying schema migration ...")

    if not SUPABASE_URL:
        fail("SUPABASE_URL / VITE_SUPABASE_URL not set in .env")
        return False
    if not SUPABASE_ACCESS_TOKEN:
        fail("SUPABASE_ACCESS_TOKEN not set",
             "Get your Personal Access Token at: https://app.supabase.com/account/tokens")
        return False

    try:
        project_ref = SUPABASE_URL.rstrip("/").split("//")[1].split(".")[0]
    except Exception:
        fail("Cannot parse project ref from SUPABASE_URL", SUPABASE_URL)
        return False

    sql_path = ROOT / "supabase" / "migrations" / "001_schema.sql"
    if not sql_path.exists():
        fail(f"Migration file not found: {sql_path}")
        return False

    sql_text = sql_path.read_text(encoding="utf-8")
    url      = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    result   = _req("POST", url, SUPABASE_ACCESS_TOKEN, {"query": sql_text})

    if "__error" in result:
        fail("Management API call failed", result["__error"])
        print()
        print("  Tip: The SUPABASE_ACCESS_TOKEN must be a Personal Access Token (PAT),")
        print("       NOT the service role key or anon key.")
        print(f"       Generate one at: https://app.supabase.com/account/tokens")
        print()
        print("  Manual fallback: paste the SQL into the Supabase SQL editor:")
        print(f"       https://app.supabase.com/project/{project_ref}/sql/new")
        print(f"       File: {sql_path}")
        return False

    ok(f"Schema applied to project '{project_ref}'")
    return True


# ─── step 2: create admin user ────────────────────────────────────────────────
def create_admin_user() -> str | None:
    print("\n[2/3] Creating admin user ...")

    if not SUPABASE_URL:
        fail("SUPABASE_URL not set"); return None
    if not SUPABASE_SERVICE_KEY:
        fail("SUPABASE_SERVICE_KEY not set",
             "Copy the 'service_role' key from Supabase -> Settings -> API"); return None

    url    = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
    result = _req(
        "POST", url, SUPABASE_SERVICE_KEY,
        payload={
            "email":         ADMIN_EMAIL,
            "password":      ADMIN_PASS,
            "email_confirm": True,
            "user_metadata": {"name": "Super Admin"},
        },
        # Supabase Auth Admin API requires BOTH Authorization AND apikey headers
        extra_headers={"apikey": SUPABASE_SERVICE_KEY},
    )

    if "__error" in result:
        err = result["__error"]
        # 422 = user already registered — that is fine
        if "already" in err.lower() or "422" in err:
            ok(f"Admin user already exists ({ADMIN_EMAIL})")
            return _find_user_id()
        fail("Admin user creation failed", err)
        return None

    user_id = result.get("id")
    if not user_id:
        fail("Unexpected response (no id)", str(result)[:200])
        return None

    ok(f"Admin user created: {ADMIN_EMAIL}  id={user_id}")
    return user_id


def _find_user_id() -> str | None:
    """Look up admin user id by email from the users list."""
    url    = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users?page=1&per_page=100"
    result = _req("GET", url, SUPABASE_SERVICE_KEY,
                  extra_headers={"apikey": SUPABASE_SERVICE_KEY})

    if "__error" in result:
        fail("Could not list users to find existing admin", result["__error"])
        return None

    for u in (result.get("users") or []):
        if (u.get("email") or "").lower() == ADMIN_EMAIL.lower():
            return u.get("id")
    return None


# ─── step 3: flag profile row as admin ────────────────────────────────────────
def set_admin_flag(user_id: str) -> bool:
    """
    Use the Management API (direct SQL) instead of PostgREST REST API.
    PostgREST schema cache can lag after a fresh schema migration (PGRST205),
    so bypassing it entirely is the most reliable approach.
    """
    print("\n[3/3] Setting is_admin=true on profile ...")

    if not SUPABASE_ACCESS_TOKEN:
        fail("SUPABASE_ACCESS_TOKEN not set — cannot run SQL via Management API")
        return False

    try:
        project_ref = SUPABASE_URL.rstrip("/").split("//")[1].split(".")[0]
    except Exception:
        fail("Cannot parse project ref from SUPABASE_URL")
        return False

    # Use UPSERT so it works whether the trigger already created the row or not
    sql = f"""
INSERT INTO public.profiles (id, name, email, is_admin)
VALUES (
  '{user_id}',
  'Super Admin',
  '{ADMIN_EMAIL}',
  true
)
ON CONFLICT (id) DO UPDATE SET is_admin = true;
"""
    url    = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    result = _req("POST", url, SUPABASE_ACCESS_TOKEN, {"query": sql})

    if "__error" in result:
        fail("Could not set is_admin via SQL", result["__error"])
        return False

    ok(f"is_admin=true set for user {user_id}")
    return True


# ─── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 58)
    print("  MarketLens DB Setup")
    print("=" * 58)

    # Validate required credentials from .env
    missing = [k for k, v in {
        "VITE_ADMIN_EMAIL":    ADMIN_EMAIL,
        "VITE_ADMIN_PASSWORD": ADMIN_PASS,
    }.items() if not v]
    if missing:
        print(f"\n[ERROR] Missing env vars: {', '.join(missing)}")
        print("  Add them to your .env and re-run.")
        return 1

    schema_ok = apply_schema()
    user_id   = create_admin_user()

    if user_id:
        flag_ok = set_admin_flag(user_id)
    else:
        print("\n[3/3] Skipped (admin user id unavailable)")
        flag_ok = False

    print("\n" + "=" * 58)
    if schema_ok and user_id and flag_ok:
        print("  Setup complete!")
        print("  Run:  uvicorn main:app --reload")
    else:
        print("  Setup finished with issues. See output above.")
        if not schema_ok:
            print("  Schema: use the manual SQL fallback shown above.")
        if not user_id:
            print("  Admin:  check SUPABASE_SERVICE_KEY in .env.")
    print("=" * 58)
    return 0 if (schema_ok and user_id and flag_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
