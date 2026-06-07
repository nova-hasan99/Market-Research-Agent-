"""
All HTTP routes for the Market Research Platform.
Registered on an APIRouter and included into the main FastAPI app.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.ai import generate_ai_summary
from app.analysis import compute_alignment, compute_stock_alignment, compute_trade_levels
from app.config import (
    TWELVE_DATA_KEY, ALPHA_VANTAGE_KEY, FINNHUB_KEY, POLYGON_KEY,
    GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    NEWSAPI_KEY, FINNHUB_BASE,
    OANDA_API_KEY, IG_API_KEY, TRADINGECONOMICS_KEY,
    SUPABASE_URL, SMTP_HOST, SMTP_USER,
)
from app.auth import get_current_user
from app.db import get_admin_client
from app.deps import templates
from app.indicators import analyze_timeframe, volatility_regime, get_session_info
from app.models import AnalyzeRequest
from app.timeframes import get_intervals, get_info as tf_info, validate as tf_validate
from app.providers.calendar import fetch_events
from app.patterns import analyze_patterns
from app.providers.correlation import (
    fetch_correlation, fetch_best_retail_sentiment, fetch_stock_correlation,
)
from app.providers.cot import fetch_cot
from app.providers.intermarket import fetch_usd_strength
from app.providers.price import fetch_ohlcv
from app.providers.sentiment import fetch_sentiment
from app.providers.stock_info import (
    fetch_stock_fundamentals, fetch_stock_earnings,
    fetch_stock_analyst, fetch_stock_insider, fetch_stock_history,
    fetch_short_interest, fetch_institutional_ownership,
    fetch_options_sentiment, fetch_sector_performance, get_sector_pe,
)
from app.providers.yields import fetch_yield_differential

router = APIRouter()

# ── Forex pair normalisation ──────────────────────────────────────────────────
# Standard market convention: higher-priority currency is always the BASE.
# If user enters USD/EUR, we analyse EUR/USD and invert the result.
_FX_PRIORITY: dict[str, int] = {
    "EUR": 9, "GBP": 8, "AUD": 7, "NZD": 6,
    "USD": 5, "CAD": 4, "CHF": 3, "JPY": 2,
    # All others get 0 — alphabetical default
}


def _normalize_fx(base: str, quote: str) -> tuple[str, str, bool]:
    """
    Returns (std_base, std_quote, is_inverted).
    is_inverted=True when the user's pair is the inverse of the standard pair.
    Example: USD/EUR → returns ('EUR', 'USD', True)
             EUR/USD → returns ('EUR', 'USD', False)
             USD/JPY → returns ('USD', 'JPY', False)  # USD has higher priority than JPY
    """
    bp = _FX_PRIORITY.get(base,  0)
    qp = _FX_PRIORITY.get(quote, 0)
    if bp >= qp:
        return base, quote, False
    return quote, base, True


def _inv(p: float) -> float:
    """Invert a price (e.g., EUR/USD 1.1616 → USD/EUR 0.8609)."""
    return round(1.0 / p, 6) if p and p != 0 else 0.0


def _flip_dir(d: str) -> str:
    return "up" if d == "down" else ("down" if d == "up" else d)


def _invert_tf(tf: dict) -> dict:
    """
    Invert all directional signals in one timeframe analysis dict.
    Called when the user requested the inverse of the standard pair.
    """
    if not tf:
        return tf
    tf = dict(tf)
    lp = tf.get("last_price", 0)
    if lp:
        tf["last_price"] = _inv(lp)
    # Invert RSI (RSI of inverse series ≈ 100 - RSI)
    tf["rsi"]          = round(100.0 - tf.get("rsi", 50.0), 2)
    tf["stoch_rsi_k"]  = round(100.0 - tf.get("stoch_rsi_k", 50.0), 2)
    tf["stoch_rsi_d"]  = round(100.0 - tf.get("stoch_rsi_d", 50.0), 2)
    # Negate slope (rising on EUR/USD = falling on USD/EUR)
    tf["rsi_slope"]    = round(-tf.get("rsi_slope", 0.0), 4)
    # Flip directional signals
    tf["direction"]    = _flip_dir(tf.get("direction",  "neutral"))
    tf["trend"]        = _flip_dir(tf.get("trend",      "neutral"))
    tf["divergence"]   = _flip_dir(tf.get("divergence", "none"))
    tf["macd_above_signal"] = not tf.get("macd_above_signal", False)
    tf["ma20_above_ma50"]   = not tf.get("ma20_above_ma50",   False)
    # Negate MACD histogram
    tf["macd_histogram"] = round(-tf.get("macd_histogram", 0.0), 6)
    # Invert support/resistance (support becomes resistance and vice-versa)
    sup = tf.get("support",    0)
    res = tf.get("resistance", 0)
    tf["support"]    = _inv(res) if res else 0.0
    tf["resistance"] = _inv(sup) if sup else 0.0
    # ATR pct stays approximately the same (% moves are symmetric)
    atr_abs = tf.get("atr_absolute", 0)
    if atr_abs and lp:
        tf["atr_absolute"] = round(atr_abs / (lp ** 2), 6)
    # Ichimoku: invert prices, flip direction
    ichi = tf.get("ichimoku", {})
    if ichi and ichi.get("available"):
        ichi = dict(ichi)
        for key in ("tenkan", "kijun", "cloud_top", "cloud_bottom"):
            if ichi.get(key):
                ichi[key] = _inv(ichi[key])
        ichi["cloud_position"] = _flip_dir(ichi.get("cloud_position", "neutral"))
        ichi["tk_cross"]       = _flip_dir(ichi.get("tk_cross", "neutral"))
        ichi["direction"]      = _flip_dir(ichi.get("direction", "neutral"))
        tf["ichimoku"] = ichi
    # Volume: flip divergence signal
    vol = tf.get("volume", {})
    if vol and vol.get("available"):
        vol = dict(vol)
        vol["direction"]  = _flip_dir(vol.get("direction", "neutral"))
        vol["signal"]     = _flip_dir(vol.get("signal", "neutral"))
        vol["divergence"] = _flip_dir(vol.get("divergence", "none"))
        tf["volume"] = vol
    # Fibonacci: invert price levels
    fibs = tf.get("fibonacci", {})
    if fibs:
        fibs = dict(fibs)
        sh = fibs.get("swing_high", 0)
        sl_f = fibs.get("swing_low", 0)
        if sh and sl_f:
            fibs["swing_high"] = _inv(sl_f)
            fibs["swing_low"]  = _inv(sh)
        tf["fibonacci"] = fibs
    return tf


def _invert_trade_levels(tl: dict) -> dict:
    """Invert all price levels in a trade_levels dict."""
    if not tl:
        return tl
    tl = dict(tl)
    entry = _inv(tl.get("entry", 0))
    sl    = _inv(tl.get("sl",    0))
    tp1   = _inv(tl.get("tp1",   0))
    tp2   = _inv(tl.get("tp2",   0))
    risk  = abs(entry - sl)
    rr1   = round(abs(tp1 - entry) / risk, 2) if risk else 0.0
    rr2   = round(abs(tp2 - entry) / risk, 2) if risk else 0.0
    kijun = tl.get("kijun_ref")
    return {
        **tl,
        "bias":           _flip_dir(tl.get("bias", "unclear")),
        "entry":          entry,
        "sl":             sl,
        "tp1":            tp1,
        "tp2":            tp2,
        "risk":           round(risk, 6),
        "rr1":            rr1,
        "rr2":            rr2,
        "kijun_ref":      _inv(kijun) if kijun else None,
        "sl_description": tl.get("sl_description", ""),
    }


def _invert_forex_response(response: dict, user_display: str) -> dict:
    """
    Post-process a forex analysis response to invert all signals
    when the user requested a non-standard pair (e.g., USD/EUR instead of EUR/USD).
    """
    response = dict(response)

    # Core signals
    response["bias"]       = _flip_dir(response.get("bias", "unclear"))
    response["last_price"] = _inv(response.get("last_price", 0))
    response["asset"]      = user_display

    # Timeframes
    tfs = response.get("timeframes", {})
    response["timeframes"] = {k: _invert_tf(v) for k, v in tfs.items()}

    # Weekly
    if response.get("weekly"):
        response["weekly"] = _invert_tf(response["weekly"])

    # Trade levels
    if response.get("trade_levels"):
        response["trade_levels"] = _invert_trade_levels(response["trade_levels"])

    # Key signal direction
    ks = response.get("key_signal")
    if isinstance(ks, dict):
        ks = dict(ks)
        ks["direction"] = _flip_dir(ks.get("direction", "neutral"))
        response["key_signal"] = ks

    # Score breakdown: flip component directions (scores stay same — they measure strength)
    comps = response.get("components") or response.get("breakdown", {})
    if isinstance(comps, dict):
        flipped = {}
        for k, v in comps.items():
            if isinstance(v, dict) and "direction" in v:
                v = dict(v)
                v["direction"] = _flip_dir(v["direction"])
            flipped[k] = v
        # Store in whichever key exists
        if "components" in response:
            response["components"] = flipped
        if "breakdown" in response:
            response["breakdown"] = flipped

    # Add a note so the UI can show "Analysed as EUR/USD (standard form)"
    response["pair_note"] = f"Non-standard pair — analysed as {response.get('inverted_from', '')} with inverted signals"
    response["is_inverted_pair"] = True

    return response

_EMPTY_COT  = {"net": 0, "direction": "neutral", "label": "No Data",
               "weeks_trend": "unknown", "available": False}
_EMPTY_YLD  = {"available": False, "direction": "neutral", "label": "Unavailable",
               "us10y": None, "de10y": None, "differential": None}
_EMPTY_IM   = {"dollar": "n/a", "eurusd_trend": "n/a", "usdjpy_trend": "n/a"}
_EMPTY_FUND = {"available": False}
_EMPTY_EARN = {"quarters": [], "next_date": None, "beats": 0, "misses": 0, "available": False}
_EMPTY_ANA  = {"available": False, "consensus": "No Data", "total": 0}
_EMPTY_INS  = {"available": False, "transactions": [], "buy_count": 0, "sell_count": 0}
_EMPTY_HIST = {"available": False, "direction": "neutral", "label": "Unavailable"}
_EMPTY_SI   = {"short_percent": None, "days_to_cover": None, "signal": "unknown", "squeeze_risk": False, "available": False}
_EMPTY_INST = {"top_holders": [], "buy_count": 0, "sell_count": 0, "signal": "neutral", "available": False}
_EMPTY_OPT  = {"put_oi": None, "call_oi": None, "ratio": None, "signal": "neutral", "label": "No Data", "available": False}
_EMPTY_SECT = {"etf": "N/A", "etf_1m": None, "signal": "neutral", "label": "Unavailable", "available": False}


# ── Helper: Detect SPA requests ─────────────────────────────────────────────
def _is_spa_request(request: Request) -> bool:
    """Check if request is from SPA router (AJAX)"""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


# ── Pages ─────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    from app.auth import get_current_user
    user = await get_current_user(request)
    if _is_spa_request(request):
        # Return only the hero/content for SPA
        return templates.TemplateResponse(request, "index.html", {"user": user, "spa_mode": True})
    return templates.TemplateResponse(request, "index.html", {"user": user})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    from app.auth import get_current_user
    user = await get_current_user(request)
    if _is_spa_request(request):
        return templates.TemplateResponse(request, "privacy.html", {"user": user, "spa_mode": True})
    return templates.TemplateResponse(request, "privacy.html", {"user": user})


@router.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login?next=/research", status_code=302)
    if _is_spa_request(request):
        return templates.TemplateResponse(request, "research.html", {"user": user, "spa_mode": True})
    return templates.TemplateResponse(request, "research.html", {"user": user})


# ── API: stock search ─────────────────────────────────────────────────────────
@router.get("/api/search-stock")
async def search_stock(request: Request, q: str = ""):
    if not await get_current_user(request):
        raise HTTPException(status_code=401, detail="Login required")
    if not q or len(q.strip()) < 1:
        return {"results": []}
    if not FINNHUB_KEY:
        return {"results": []}
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(
                f"{FINNHUB_BASE}/search",
                params={"q": q.strip(), "token": FINNHUB_KEY},
            )
            r.raise_for_status()
            data = r.json()
            results = [
                {
                    "symbol": item.get("displaySymbol") or item.get("symbol", ""),
                    "name":   item.get("description", ""),
                    "type":   item.get("type", ""),
                }
                for item in (data.get("result") or [])
                if item.get("type") in ("Common Stock", "ETP", "ADR", "REIT")
                and item.get("displaySymbol")
            ][:10]
            return {"results": results}
        except Exception:
            return {"results": []}


# ── API: provider status ──────────────────────────────────────────────────────
@router.get("/api/providers")
def api_providers():
    """Raw JSON — kept for backward compat."""
    return _build_provider_status()


def _build_provider_status() -> dict:
    from app.config import (
        OANDA_API_KEY, IG_API_KEY, TRADINGECONOMICS_KEY,
        SMTP_HOST, SMTP_USER,
    )
    return {
        "price_data": [
            {"name": "TwelveData",    "key": "TWELVE_DATA_KEY",   "enabled": bool(TWELVE_DATA_KEY),   "priority": 1, "note": "Primary OHLCV provider — supports all timeframes & pairs"},
            {"name": "AlphaVantage",  "key": "ALPHA_VANTAGE_KEY", "enabled": bool(ALPHA_VANTAGE_KEY), "priority": 2, "note": "Fallback OHLCV + fundamental data"},
            {"name": "Yahoo Finance", "key": "—",                 "enabled": True,                    "priority": 3, "note": "No key required — free fallback"},
            {"name": "Polygon.io",    "key": "POLYGON_KEY",       "enabled": bool(POLYGON_KEY),       "priority": 4, "note": "Stocks only"},
        ],
        "ai_summary": [
            {"name": "Google Gemini", "key": "GEMINI_API_KEY",    "enabled": bool(GEMINI_API_KEY),    "priority": 1, "note": "Primary AI summary"},
            {"name": "Groq (LLaMA)",  "key": "GROQ_API_KEY",      "enabled": bool(GROQ_API_KEY),      "priority": 2, "note": "Fast fallback"},
            {"name": "OpenAI GPT",    "key": "OPENAI_API_KEY",    "enabled": bool(OPENAI_API_KEY),    "priority": 3, "note": "Fallback"},
            {"name": "Anthropic",     "key": "ANTHROPIC_API_KEY", "enabled": bool(ANTHROPIC_API_KEY), "priority": 4, "note": "Fallback"},
            {"name": "Rule-Based",    "key": "—",                 "enabled": True,                    "priority": 5, "note": "Always available — no AI key needed"},
        ],
        "market_data": [
            {"name": "Finnhub",          "key": "FINNHUB_KEY",       "enabled": bool(FINNHUB_KEY),       "note": "Economic calendar + COT data"},
            {"name": "NewsAPI",          "key": "NEWSAPI_KEY",       "enabled": bool(NEWSAPI_KEY),       "note": "News sentiment scoring"},
            {"name": "CFTC COT",         "key": "—",                 "enabled": True,                    "note": "Institutional positioning — free"},
            {"name": "OANDA Sentiment",  "key": "OANDA_API_KEY",     "enabled": bool(OANDA_API_KEY),     "note": "Retail long/short positioning"},
            {"name": "IG Sentiment",     "key": "IG_API_KEY",        "enabled": bool(IG_API_KEY),        "note": "Retail positioning fallback"},
            {"name": "TradingEconomics", "key": "TRADINGECONOMICS_KEY", "enabled": bool(TRADINGECONOMICS_KEY), "note": "Enhanced macro indicators"},
        ],
        "infrastructure": [
            {"name": "Supabase Auth",  "key": "SUPABASE_*",       "enabled": bool(SUPABASE_URL),      "note": "Authentication + database"},
            {"name": "SMTP Email",     "key": "SMTP_HOST",        "enabled": bool(SMTP_HOST and SMTP_USER), "note": "Welcome + reset emails"},
        ],
    }


@router.get("/admin/api-status", response_class=HTMLResponse)
async def admin_api_status(request: Request):
    """Admin-only API status dashboard."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login?next=/admin/api-status", status_code=302)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    status = _build_provider_status()
    return templates.TemplateResponse(
        request, "admin_api_status.html",
        {"user": user, "status": status},
    )


# ── Background save helper ────────────────────────────────────────────────────
async def _save_analysis_bg(user_id: str, data: dict):
    try:
        from app.db import get_admin_client
        client = get_admin_client()
        client.table("analyses").insert({
            "user_id":    user_id,
            "asset_type": data["asset_type"],
            "asset":      data["asset"],
            "score":      data["score"],
            "bias":       data["bias"],
            "last_price": str(data.get("last_price", "")),
            "data":       data,
        }).execute()
    except Exception:
        pass


# ── API: analyse ─────────────────────────────────────────────────────────────
@router.post("/api/analyze")
async def analyze(req: AnalyzeRequest, request: Request):
    # Require login — unauthenticated requests get 401
    from app.auth import get_current_user as _gcu
    _user = await _gcu(request)
    if not _user:
        raise HTTPException(
            status_code=401,
            detail="Login required. Please sign in to use the analysis feature.",
        )

    # Check if user is suspended (analysis blocked)
    if not _user.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Your account access is temporarily limited due to high traffic and API rate limits. Please try again later or contact support at hasan@latticecode.pro for assistance.",
        )

    # Build symbols
    if req.asset_type == "forex":
        req_base  = req.symbol.upper()
        req_quote = (req.quote or "USD").upper()
        # Normalise to standard market pair ordering (e.g. USD/EUR → EUR/USD)
        std_base, std_quote, is_inverted = _normalize_fx(req_base, req_quote)
        symbol    = f"{std_base}/{std_quote}"
        news_tick = f"FOREX:{std_base}{std_quote}"
        display   = f"{req_base}/{req_quote}"   # user's notation for UI
    else:
        symbol    = req.symbol.upper()
        news_tick = symbol
        display   = symbol
        is_inverted = False

    # ── Resolve timeframe intervals ───────────────────────────────────────────
    tf_key              = tf_validate(req.timeframe)
    primary_iv, secondary_iv, context_iv = get_intervals(tf_key)
    tf_meta             = tf_info(tf_key)

    # ── Fetch all data concurrently ───────────────────────────────────────────
    async with httpx.AsyncClient(timeout=45) as client:

        if req.asset_type == "forex":
            # ── FOREX path ────────────────────────────────────────────────
            # Fetch secondary (entry TF), primary (analysis TF), context (trend TF)
            ohlcv_results = await asyncio.gather(
                fetch_ohlcv(client, symbol, secondary_iv, "forex"),
                fetch_ohlcv(client, symbol, primary_iv,   "forex"),
                fetch_ohlcv(client, symbol, context_iv,   "forex"),
                return_exceptions=True,
            )
            (hourly_df, h_prov) = ohlcv_results[0] if not isinstance(ohlcv_results[0], Exception) else (None, "None")
            (daily_df,  d_prov) = ohlcv_results[1] if not isinstance(ohlcv_results[1], Exception) else (None, "None")
            weekly_result       = ohlcv_results[2]

            # If required timeframes failed, raise
            if hourly_df is None:
                raise ohlcv_results[0]
            if daily_df is None:
                raise ohlcv_results[1]

            sec = await asyncio.gather(
                fetch_sentiment(client, news_tick),
                fetch_events(client),
                fetch_cot(client, symbol, "forex"),
                fetch_usd_strength(client),
                fetch_yield_differential(client),
                fetch_correlation(client, symbol),
                fetch_best_retail_sentiment(client, symbol),
                return_exceptions=True,
            )
            def _ok(i):
                return not isinstance(sec[i], Exception) if i < len(sec) else False

            sentiment    = sec[0] if _ok(0) else {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}
            events       = sec[1] if _ok(1) else []
            cot          = sec[2] if _ok(2) else _EMPTY_COT
            intermarket  = sec[3] if _ok(3) else _EMPTY_IM
            yield_diff   = sec[4] if _ok(4) else _EMPTY_YLD
            correlation  = sec[5] if _ok(5) else {"available": False}
            retail_sent  = sec[6] if _ok(6) else {"available": False}

            hourly = analyze_timeframe(hourly_df)
            daily  = analyze_timeframe(daily_df)
            regime = volatility_regime(daily_df)

            # Weekly timeframe (optional - graceful fallback)
            weekly = None
            weekly_bias = "neutral"
            try:
                if not isinstance(weekly_result, Exception):
                    weekly_df, _ = weekly_result
                    weekly = analyze_timeframe(weekly_df)
                    weekly_bias = weekly.get("direction", "neutral")
            except Exception:
                weekly = None
                weekly_bias = "neutral"

            session_info = get_session_info()
            patterns     = analyze_patterns(daily_df)

            scored = compute_alignment(
                hourly, daily, intermarket, sentiment, cot, events, "forex",
                ichimoku=daily.get("ichimoku"),
                volume=daily.get("volume"),
                weekly_bias=weekly_bias,
                symbol=symbol,
            )

            response: dict = {
                "asset":             display,
                "asset_type":        "forex",
                "generated_at_utc":  datetime.now(timezone.utc).isoformat(),
                "score":             scored["alignment_score"],
                "bias":              scored["bias"],
                "last_price":        daily["last_price"],
                "timeframe":         tf_key,
                "timeframe_label":   tf_meta["name"],
                "timeframe_desc":    tf_meta["trade_type"],
                "timeframes":        {"hourly": hourly, "daily": daily},
                "breakdown":         scored["components"],
                "key_signal":        scored["key_signal"],
                "main_risk":         scored["main_risk"],
                "conflicts":         scored["conflicts"],
                "volatility_regime": regime,
                "upcoming_events":   events,
                "sentiment":         sentiment,
                "intermarket":       intermarket,
                "cot":               cot,
                "yield_diff":        yield_diff,
                "fundamentals":      None,
                "earnings":          None,
                "analyst":           None,
                "insider":           None,
                "history":           None,
                "short_interest":    None,
                "institutional":     None,
                "options_sentiment": None,
                "weekly":            weekly,
                "session":           session_info,
                "correlation":       correlation,
                "retail_sentiment":  retail_sent,
                "patterns":          patterns,
                "providers_used":    {"hourly_data": h_prov, "daily_data": d_prov},
                "trade_levels":      compute_trade_levels(
                                         daily, hourly,
                                         scored["bias"], scored["alignment_score"],
                                         regime,
                                     ),
            }

            # ── Invert response if user requested non-standard pair ────────
            if is_inverted:
                response["inverted_from"] = f"{std_base}/{std_quote}"
                response = _invert_forex_response(response, display)

        else:
            # ── STOCK path ─────────────────────────────────────────────────
            # Phase 1: OHLCV (required; propagate failures as 500)
            ohlcv_results_s = await asyncio.gather(
                fetch_ohlcv(client, symbol, secondary_iv, "stock"),
                fetch_ohlcv(client, symbol, primary_iv,   "stock"),
                fetch_ohlcv(client, symbol, context_iv,   "stock"),
                return_exceptions=True,
            )
            (hourly_df, h_prov) = ohlcv_results_s[0] if not isinstance(ohlcv_results_s[0], Exception) else (None, "None")
            (daily_df,  d_prov) = ohlcv_results_s[1] if not isinstance(ohlcv_results_s[1], Exception) else (None, "None")
            weekly_result_s     = ohlcv_results_s[2]

            if hourly_df is None:
                raise ohlcv_results_s[0]
            if daily_df is None:
                raise ohlcv_results_s[1]

            # Phase 2: supplemental data (all optional; exceptions return fallbacks)
            (sentiment, events, fundamentals, earnings, insider, history,
             short_interest, institutional, options_sentiment) = await asyncio.gather(
                fetch_sentiment(client, news_tick),
                fetch_events(client),
                fetch_stock_fundamentals(client, symbol),
                fetch_stock_earnings(client, symbol),
                fetch_stock_insider(client, symbol),
                fetch_stock_history(client, symbol),
                fetch_short_interest(client, symbol),
                fetch_institutional_ownership(client, symbol),
                fetch_options_sentiment(client, symbol),
                return_exceptions=True,
            )

            def _safe(val, fallback):
                return val if not isinstance(val, Exception) else fallback

            sentiment         = _safe(sentiment,         {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []})
            events            = _safe(events,            [])
            fundamentals      = _safe(fundamentals,      _EMPTY_FUND)
            earnings          = _safe(earnings,          _EMPTY_EARN)
            insider           = _safe(insider,           _EMPTY_INS)
            history           = _safe(history,           _EMPTY_HIST)
            short_interest    = _safe(short_interest,    _EMPTY_SI)
            institutional     = _safe(institutional,     _EMPTY_INST)
            options_sentiment = _safe(options_sentiment, _EMPTY_OPT)

            # Phase 3: compute technicals, then fetch analyst + sector perf (need price + sector)
            hourly = analyze_timeframe(hourly_df)
            daily  = analyze_timeframe(daily_df)
            regime = volatility_regime(daily_df)

            # Weekly timeframe (optional - graceful fallback)
            weekly_s    = None
            weekly_bias_s = "neutral"
            try:
                if not isinstance(weekly_result_s, Exception):
                    weekly_df_s, _ = weekly_result_s
                    weekly_s = analyze_timeframe(weekly_df_s)
                    weekly_bias_s = weekly_s.get("direction", "neutral")
            except Exception:
                weekly_s    = None
                weekly_bias_s = "neutral"

            session_info_s = get_session_info()
            patterns_s     = analyze_patterns(daily_df)

            analyst, sector_perf = await asyncio.gather(
                fetch_stock_analyst(client, symbol),
                fetch_sector_performance(client, fundamentals.get("sector")),
                return_exceptions=True,
            )
            analyst     = _safe(analyst,     _EMPTY_ANA)
            sector_perf = _safe(sector_perf, _EMPTY_SECT)

            # Stock benchmark correlation (after sector_perf so we can pass etf ticker)
            try:
                stock_corr = await fetch_stock_correlation(
                    client, symbol,
                    sector_etf=sector_perf.get("etf") if isinstance(sector_perf, dict) else None,
                )
            except Exception:
                stock_corr = {"available": False}

            # Compute analyst price-target upside now that we have the current price
            if analyst.get("available") and analyst.get("price_target_mean") and daily["last_price"]:
                try:
                    price = float(daily["last_price"])
                    pt    = float(analyst["price_target_mean"])
                    analyst["upside_pct"] = round((pt - price) / price * 100, 1)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Annotate fundamentals with sector PE comparison
            if isinstance(fundamentals, dict) and fundamentals.get("available"):
                sp_avg = get_sector_pe(fundamentals.get("sector"))
                pe     = fundamentals.get("pe_ratio")
                fundamentals["sector_pe_avg"]    = sp_avg
                fundamentals["pe_vs_sector_pct"] = (
                    round((pe - sp_avg) / sp_avg * 100, 1) if pe is not None else None
                )

            # Attach sector 1M return to history for frontend display
            if isinstance(history, dict) and isinstance(sector_perf, dict):
                history["sector_etf"]  = sector_perf.get("etf")
                history["sector_1m"]   = sector_perf.get("etf_1m")
                stock_1m = history.get("returns", {}).get("1M")
                etf_1m   = sector_perf.get("etf_1m")
                history["vs_sector_1m"] = (
                    round(stock_1m - etf_1m, 1)
                    if stock_1m is not None and etf_1m is not None else None
                )

            scored = compute_stock_alignment(
                hourly, daily, sentiment, fundamentals, analyst, earnings, history, events,
                insider=insider,
                institutional=institutional,
                short_interest=short_interest,
                options_sentiment=options_sentiment,
                ichimoku=daily.get("ichimoku"),
                volume=daily.get("volume"),
                weekly_bias=weekly_bias_s,
                symbol=symbol,
            )

            response: dict = {
                "asset":             display,
                "asset_type":        "stock",
                "generated_at_utc":  datetime.now(timezone.utc).isoformat(),
                "score":             scored["alignment_score"],
                "bias":              scored["bias"],
                "last_price":        daily["last_price"],
                "timeframe":         tf_key,
                "timeframe_label":   tf_meta["name"],
                "timeframe_desc":    tf_meta["trade_type"],
                "timeframes":        {"hourly": hourly, "daily": daily},
                "breakdown":         scored["components"],
                "key_signal":        scored["key_signal"],
                "main_risk":         scored["main_risk"],
                "conflicts":         scored["conflicts"],
                "volatility_regime": regime,
                "upcoming_events":   events,
                "sentiment":         sentiment,
                "intermarket":       None,
                "cot":               None,
                "yield_diff":        None,
                "fundamentals":      fundamentals,
                "earnings":          earnings,
                "analyst":           analyst,
                "insider":           insider,
                "history":           history,
                "short_interest":    short_interest,
                "institutional":     institutional,
                "options_sentiment": options_sentiment,
                "weekly":            weekly_s,
                "session":           session_info_s,
                "patterns":          patterns_s,
                "correlation":       stock_corr,
                "retail_sentiment":  None,
                "providers_used":    {"hourly_data": h_prov, "daily_data": d_prov},
                "trade_levels":      compute_trade_levels(
                                         daily, hourly,
                                         scored["bias"], scored["alignment_score"],
                                         regime,
                                     ),
            }

    # ── Generate AI summary ───────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=20) as ai_client:
        ai_text, ai_prov = await generate_ai_summary(ai_client, response)

    response["ai_summary"] = {"text": ai_text, "provider": ai_prov}

    # ── Auto-save (fire-and-forget) ───────────────────────────────────────────
    asyncio.create_task(_save_analysis_bg(_user["id"], response))

    return response


# ── User Preferences ──────────────────────────────────────────────────────────

@router.post("/api/preferences")
async def save_preference(request: Request) -> dict:
    """
    Save user preferences (e.g. preferred timeframe) to Supabase user metadata.
    Silent fail — frontend uses localStorage as primary, this is just DB sync.
    """
    user = await get_current_user(request)
    if not user:
        return {"ok": False, "reason": "not_logged_in"}
    try:
        body = await request.json()
        tf   = tf_validate(body.get("timeframe", "1d"))
        admin = get_admin_client()
        admin.auth.admin.update_user_by_id(
            user["id"],
            {"user_metadata": {"preferred_tf": tf}},
        )
        return {"ok": True, "timeframe": tf}
    except Exception:
        return {"ok": False, "reason": "db_error"}


@router.get("/api/preferences")
async def load_preference(request: Request) -> dict:
    """Load user preferences from Supabase. Returns defaults if not logged in."""
    user = await get_current_user(request)
    if not user:
        return {"timeframe": "1d"}
    try:
        from supabase import create_client
        from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY
        admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        data  = admin.auth.admin.get_user_by_id(user["id"])
        meta  = data.user.user_metadata or {}
        tf    = tf_validate(meta.get("preferred_tf", "1d"))
        return {"timeframe": tf}
    except Exception:
        return {"timeframe": "1d"}
