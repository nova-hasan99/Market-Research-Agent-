"""
Timeframe definitions and interval mappings.
Supports all standard trading timeframes from 1-minute scalping to monthly investing.
"""

# ── Timeframe definitions ─────────────────────────────────────────────────────
TIMEFRAMES: dict[str, dict] = {
    "1m":  {"label": "1m",  "name": "1 Minute",  "desc": "Scalping",         "trade_type": "Scalping (seconds to minutes)",      "minutes": 1},
    "5m":  {"label": "5m",  "name": "5 Minutes", "desc": "Scalping",         "trade_type": "Scalping (5-30 minutes)",            "minutes": 5},
    "15m": {"label": "15m", "name": "15 Minutes","desc": "Short-term",       "trade_type": "Short-term (15-90 minutes)",         "minutes": 15},
    "1h":  {"label": "1H",  "name": "1 Hour",    "desc": "Intraday",         "trade_type": "Intraday (1-8 hours)",               "minutes": 60},
    "4h":  {"label": "4H",  "name": "4 Hours",   "desc": "Intraday Swing",   "trade_type": "Intraday swing (hours to 2 days)",   "minutes": 240},
    "8h":  {"label": "8H",  "name": "8 Hours",   "desc": "Short Swing",      "trade_type": "Short swing (1-5 days)",             "minutes": 480},
    "1d":  {"label": "1D",  "name": "Daily",     "desc": "Swing Trade",      "trade_type": "Swing trading (days to weeks)",      "minutes": 1440},
    "1w":  {"label": "1W",  "name": "Weekly",    "desc": "Position Trade",   "trade_type": "Position trading (weeks to months)", "minutes": 10080},
    "1mo": {"label": "1M",  "name": "Monthly",   "desc": "Long Term",        "trade_type": "Long-term investing (months+)",      "minutes": 43200},
}

DEFAULT_TF = "1d"

# ── Timeframe relationships ────────────────────────────────────────────────────
# Secondary = one level lower (used for entry timing / finer S/R)
_SECONDARY: dict[str, str] = {
    "1m":  "1m",
    "5m":  "1m",
    "15m": "5m",
    "1h":  "15m",
    "4h":  "1h",
    "8h":  "4h",
    "1d":  "1h",
    "1w":  "1d",
    "1mo": "1w",
}

# Context = one level higher (used for big-picture trend)
_CONTEXT: dict[str, str] = {
    "1m":  "15m",
    "5m":  "1h",
    "15m": "4h",
    "1h":  "1d",
    "4h":  "1w",
    "8h":  "1w",
    "1d":  "1w",
    "1w":  "1mo",
    "1mo": "1mo",
}

# ── Provider interval strings ─────────────────────────────────────────────────
# TwelveData (primary provider — broadest interval support)
_TWELVE: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "1h":  "1h",
    "4h":  "4h",
    "8h":  "8h",
    "1d":  "1day",
    "1w":  "1week",
    "1mo": "1month",
}

# AlphaVantage (fallback — no 4h/8h, use 1h and aggregate)
_ALPHA: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "1h":  "60min",
    "4h":  "60min",    # AV doesn't have 4h; provider will aggregate
    "8h":  "60min",
    "1d":  "daily",
    "1w":  "weekly",
    "1mo": "monthly",
}

# Yahoo Finance (used in correlation provider)
_YAHOO: dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "4h":  "1h",       # YF has no 4h; caller should aggregate
    "8h":  "1h",
    "1d":  "1d",
    "1w":  "1wk",
    "1mo": "1mo",
}


# ── Public helpers ─────────────────────────────────────────────────────────────

def validate(tf: str) -> str:
    """Return tf if valid, else DEFAULT_TF."""
    return tf if tf in TIMEFRAMES else DEFAULT_TF


def get_intervals(tf: str) -> tuple[str, str, str]:
    """
    Return (primary, secondary, context) TwelveData interval strings for a
    given timeframe key.
    primary   = selected TF (main analysis)
    secondary = one TF lower (entry timing, finer S/R)
    context   = one TF higher (big-picture trend)
    """
    tf  = validate(tf)
    sec = _SECONDARY.get(tf, "1h")
    ctx = _CONTEXT.get(tf, "1d")
    return _TWELVE[tf], _TWELVE[sec], _TWELVE[ctx]


def get_label(tf: str) -> str:
    return TIMEFRAMES.get(validate(tf), TIMEFRAMES[DEFAULT_TF])["name"]


def get_info(tf: str) -> dict:
    return TIMEFRAMES.get(validate(tf), TIMEFRAMES[DEFAULT_TF])
