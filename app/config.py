"""
All API keys and global constants loaded from .env.
Import from here everywhere — never call os.getenv() in other modules.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Price data providers ─────────────────────────────────────────────────────
TWELVE_DATA_KEY   = os.getenv("TWELVE_DATA_KEY", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
FINNHUB_KEY       = os.getenv("FINNHUB_KEY", "")
POLYGON_KEY       = os.getenv("POLYGON_KEY", "")

# ── AI summary providers ─────────────────────────────────────────────────────
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── News sentiment ───────────────────────────────────────────────────────────
NEWSAPI_KEY   = os.getenv("NEWSAPI_KEY", "")

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL          = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
SUPABASE_ANON_KEY     = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY  = os.getenv("SUPABASE_SERVICE_KEY", "")   # service role key (bypasses RLS)
SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN", "")  # Management API PAT
ADMIN_EMAIL = os.getenv("VITE_ADMIN_EMAIL", "")
ADMIN_PASS  = os.getenv("VITE_ADMIN_PASSWORD", "")

# ── SMTP ─────────────────────────────────────────────────────────────────────
# Render free plan blocks outbound SMTP env vars, so we fall back to
# hardcoded values when the environment variable is missing or empty.
# To change credentials: update the _FALLBACK_ constants below AND the .env file.
_SMTP_HOST_FALLBACK     = "smtp.gmail.com"
_SMTP_PORT_FALLBACK     = 587
_SMTP_USER_FALLBACK     = "team@latticecode.pro"
_SMTP_PASSWORD_FALLBACK = "exed dslz xmfo ibxg"
_SMTP_FROM_FALLBACK     = "MarketLens <team@latticecode.pro>"

SMTP_HOST     = os.getenv("SMTP_HOST",     "") or _SMTP_HOST_FALLBACK
SMTP_PORT     = int(os.getenv("SMTP_PORT", "") or _SMTP_PORT_FALLBACK)
SMTP_USER     = os.getenv("SMTP_USER",     "") or _SMTP_USER_FALLBACK
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "") or _SMTP_PASSWORD_FALLBACK
SMTP_FROM     = os.getenv("SMTP_FROM",     "") or _SMTP_FROM_FALLBACK
SITE_URL      = os.getenv("SITE_URL", "http://localhost:8000")

# ── Correlation & Sentiment ──────────────────────────────────────────────────
OANDA_API_KEY        = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID     = os.getenv("OANDA_ACCOUNT_ID", "")
IG_API_KEY           = os.getenv("IG_API_KEY", "")
TRADINGECONOMICS_KEY = os.getenv("TRADINGECONOMICS_KEY", "")

# ── Base URLs ────────────────────────────────────────────────────────────────
TD_BASE       = "https://api.twelvedata.com/time_series"
NEWSAPI_URL   = "https://newsapi.org/v2/everything"
AV_BASE       = "https://www.alphavantage.co/query"
FINNHUB_BASE  = "https://finnhub.io/api/v1"
YAHOO_BASE    = "https://query1.finance.yahoo.com/v8/finance/chart"
POLYGON_BASE  = "https://api.polygon.io/v2/aggs/ticker"
GEMINI_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL    = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
