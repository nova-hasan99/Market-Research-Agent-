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
