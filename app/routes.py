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
from app.analysis import compute_alignment, compute_stock_alignment
from app.config import (
    TWELVE_DATA_KEY, ALPHA_VANTAGE_KEY, FINNHUB_KEY, POLYGON_KEY,
    GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    NEWSAPI_KEY, FINNHUB_BASE,
)
from app.deps import templates
from app.indicators import analyze_timeframe, volatility_regime
from app.models import AnalyzeRequest
from app.providers.calendar import fetch_events
from app.providers.cot import fetch_cot
from app.providers.intermarket import fetch_usd_strength
from app.providers.price import fetch_ohlcv
from app.providers.sentiment import fetch_sentiment
from app.providers.stock_info import (
    fetch_stock_fundamentals, fetch_stock_earnings,
    fetch_stock_analyst, fetch_stock_insider, fetch_stock_history,
)
from app.providers.yields import fetch_yield_differential

router = APIRouter()

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


# ── Pages ─────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    return templates.TemplateResponse(request, "research.html")


# ── API: stock search ─────────────────────────────────────────────────────────
@router.get("/api/search-stock")
async def search_stock(q: str = ""):
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
    return {
        "price_data": {
            "twelve_data":   {"enabled": bool(TWELVE_DATA_KEY),   "priority": 1},
            "alpha_vantage": {"enabled": bool(ALPHA_VANTAGE_KEY), "priority": 2},
            "yahoo_finance": {"enabled": True, "priority": 3, "note": "no key required"},
            "polygon":       {"enabled": bool(POLYGON_KEY),       "priority": 4, "note": "stocks only"},
        },
        "supplemental": {
            "newsapi_sentiment":       {"enabled": bool(NEWSAPI_KEY)},
            "alphavantage_sentiment":  {"enabled": bool(ALPHA_VANTAGE_KEY), "note": "fallback"},
            "cftc_cot":                {"enabled": True, "note": "no key required"},
            "finnhub_calendar":        {"enabled": bool(FINNHUB_KEY)},
            "twelve_data_yields":      {"enabled": bool(TWELVE_DATA_KEY)},
        },
        "ai_summary": {
            "gemini":     {"enabled": bool(GEMINI_API_KEY),    "priority": 1},
            "groq":       {"enabled": bool(GROQ_API_KEY),      "priority": 2},
            "openai":     {"enabled": bool(OPENAI_API_KEY),    "priority": 3},
            "anthropic":  {"enabled": bool(ANTHROPIC_API_KEY), "priority": 4},
            "rule_based": {"enabled": True,                    "priority": 5},
        },
    }


# ── API: analyse ─────────────────────────────────────────────────────────────
@router.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    # Build symbols
    if req.asset_type == "forex":
        quote     = (req.quote or "USD").upper()
        symbol    = f"{req.symbol.upper()}/{quote}"
        news_tick = f"FOREX:{req.symbol.upper()}{quote}"
        display   = symbol
    else:
        symbol    = req.symbol.upper()
        news_tick = symbol
        display   = symbol

    # ── Fetch all data concurrently ───────────────────────────────────────────
    async with httpx.AsyncClient(timeout=45) as client:

        if req.asset_type == "forex":
            # ── FOREX path ────────────────────────────────────────────────
            (hourly_df, h_prov), (daily_df, d_prov) = await asyncio.gather(
                fetch_ohlcv(client, symbol, "1h",   "forex"),
                fetch_ohlcv(client, symbol, "1day", "forex"),
            )
            sec = await asyncio.gather(
                fetch_sentiment(client, news_tick),
                fetch_events(client),
                fetch_cot(client, symbol, "forex"),
                fetch_usd_strength(client),
                fetch_yield_differential(client),
                return_exceptions=True,
            )
            def _ok(i):
                return not isinstance(sec[i], Exception) if i < len(sec) else False

            sentiment   = sec[0] if _ok(0) else {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}
            events      = sec[1] if _ok(1) else []
            cot         = sec[2] if _ok(2) else _EMPTY_COT
            intermarket = sec[3] if _ok(3) else _EMPTY_IM
            yield_diff  = sec[4] if _ok(4) else _EMPTY_YLD

            hourly = analyze_timeframe(hourly_df)
            daily  = analyze_timeframe(daily_df)
            regime = volatility_regime(daily_df)

            scored = compute_alignment(
                hourly, daily, intermarket, sentiment, cot, events, "forex"
            )

            response: dict = {
                "asset":             display,
                "asset_type":        "forex",
                "generated_at_utc":  datetime.now(timezone.utc).isoformat(),
                "score":             scored["alignment_score"],
                "bias":              scored["bias"],
                "last_price":        daily["last_price"],
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
                "providers_used":    {"hourly_data": h_prov, "daily_data": d_prov},
            }

        else:
            # ── STOCK path ─────────────────────────────────────────────────
            # Phase 1: OHLCV (required; propagate failures as 500)
            (hourly_df, h_prov), (daily_df, d_prov) = await asyncio.gather(
                fetch_ohlcv(client, symbol, "1h",   "stock"),
                fetch_ohlcv(client, symbol, "1day", "stock"),
            )

            # Phase 2: supplemental data (all optional; exceptions return fallbacks)
            sentiment, events, fundamentals, earnings, insider, history = await asyncio.gather(
                fetch_sentiment(client, news_tick),
                fetch_events(client),
                fetch_stock_fundamentals(client, symbol),
                fetch_stock_earnings(client, symbol),
                fetch_stock_insider(client, symbol),
                fetch_stock_history(client, symbol),
                return_exceptions=True,
            )

            def _safe(val, fallback):
                return val if not isinstance(val, Exception) else fallback

            sentiment    = _safe(sentiment,    {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []})
            events       = _safe(events,       [])
            fundamentals = _safe(fundamentals, _EMPTY_FUND)
            earnings     = _safe(earnings,     _EMPTY_EARN)
            insider      = _safe(insider,      _EMPTY_INS)
            history      = _safe(history,      _EMPTY_HIST)

            # Phase 2: compute technicals, then fetch analyst with current price
            hourly = analyze_timeframe(hourly_df)
            daily  = analyze_timeframe(daily_df)
            regime = volatility_regime(daily_df)

            analyst = await fetch_stock_analyst(client, symbol)
            analyst = _safe(analyst, _EMPTY_ANA)

            # Compute price-target upside now that we have the price
            if analyst.get("available") and analyst.get("price_target_mean") and daily["last_price"]:
                try:
                    price = float(daily["last_price"])
                    pt    = float(analyst["price_target_mean"])
                    analyst["upside_pct"] = round((pt - price) / price * 100, 1)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            scored = compute_stock_alignment(
                hourly, daily, sentiment, fundamentals, analyst, earnings, history, events,
                insider=insider,
            )

            response: dict = {
                "asset":             display,
                "asset_type":        "stock",
                "generated_at_utc":  datetime.now(timezone.utc).isoformat(),
                "score":             scored["alignment_score"],
                "bias":              scored["bias"],
                "last_price":        daily["last_price"],
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
                "providers_used":    {"hourly_data": h_prov, "daily_data": d_prov},
            }

    # ── Generate AI summary ───────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=20) as ai_client:
        ai_text, ai_prov = await generate_ai_summary(ai_client, response)

    response["ai_summary"] = {"text": ai_text, "provider": ai_prov}
    return response
