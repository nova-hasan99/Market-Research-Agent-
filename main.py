"""
Market Research Backend - FastAPI
=================================
This service does all the real-time numeric work:
  1. Fetches real market data from the internet (Alpha Vantage / Finnhub)
  2. Computes technical indicators (RSI, MACD, MA, ATR)
  3. Produces a deterministic score (0-100) without any LLM
  4. Returns structured JSON, which the n8n AI Agent later turns into a readable message

Core principles:
  - The score means "how aligned the signals are", NOT "probability the price will rise".
  - All numeric work happens here in code, never via an LLM.

Supports two asset types:
  - forex : currency pairs like EUR/USD (macro / events matter most)
  - stock : tickers like META, GOOGL, TSLA (company fundamentals matter most)
"""

import os
from datetime import datetime, timezone
from typing import Optional, Literal

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load variables from a local .env file (if present) into the environment.
# On a hosting platform like Render, you set these as real env vars instead,
# so there is no .env file there and load_dotenv() simply does nothing.
load_dotenv()

app = FastAPI(title="Market Research Backend", version="1.2")

# ---- API keys are read from environment variables (never hardcode them) ----
# These come from the .env file locally, or from the platform's env vars in prod.
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")

AV_BASE = "https://www.alphavantage.co/query"
FINNHUB_BASE = "https://finnhub.io/api/v1"


# ----------------------------- Request model -----------------------------
class AnalyzeRequest(BaseModel):
    asset_type: Literal["forex", "stock"]
    # forex -> symbol="EUR", quote="USD"
    # stock -> symbol="META" (quote is ignored)
    symbol: str
    quote: Optional[str] = "USD"
    horizon_hours: int = Field(default=6, ge=1, le=72)  # how many hours to keep on watch


# ------------------- Technical indicators (pure pandas) -------------------
def rsi(series: pd.Series, period: int = 14) -> float:
    """Relative Strength Index. Returns 50 (neutral) if not computable."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    val = 100 - (100 / (1 + rs))
    last = val.iloc[-1]
    return float(last) if not pd.isna(last) else 50.0


def macd(series: pd.Series):
    """Returns (macd_line, signal_line) using standard 12/26/9 EMAs."""
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return float(macd_line.iloc[-1]), float(signal.iloc[-1])


def moving_averages(series: pd.Series):
    """Returns (fast MA 20, slow MA 50)."""
    ma_fast = float(series.rolling(20).mean().iloc[-1])
    ma_slow = float(series.rolling(50).mean().iloc[-1])
    return ma_fast, ma_slow


def atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range as a percentage of price. Useful as a volatility / risk gauge."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    last_close = close.iloc[-1]
    return float(atr / last_close * 100) if last_close else 0.0


# ----------------------------- Data fetching -----------------------------
async def fetch_forex_ohlcv(symbol: str, quote: str) -> pd.DataFrame:
    """
    Fetch daily forex data from Alpha Vantage.
    NOTE: FX_DAILY is on the free tier. FX_INTRADAY is a premium endpoint,
    so we use daily candles here to stay free.
    """
    if not ALPHA_VANTAGE_KEY:
        raise HTTPException(500, "ALPHA_VANTAGE_KEY is not set")
    params = {
        "function": "FX_DAILY",
        "from_symbol": symbol,
        "to_symbol": quote,
        "outputsize": "compact",
        "apikey": ALPHA_VANTAGE_KEY,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(AV_BASE, params=params)
    data = r.json()
    key = next((k for k in data if "Time Series" in k), None)
    if not key:
        # Alpha Vantage returns a "Note" or "Information" message when rate-limited
        msg = data.get("Note") or data.get("Information") or data
        raise HTTPException(502, f"Forex data unavailable: {msg}")
    rows = data[key]
    df = pd.DataFrame(
        [
            {
                "ts": ts,
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
            }
            for ts, v in rows.items()
        ]
    ).sort_values("ts").reset_index(drop=True)
    return df


async def fetch_stock_ohlcv(symbol: str) -> pd.DataFrame:
    """
    Fetch daily stock data from Alpha Vantage.
    NOTE: TIME_SERIES_DAILY is on the free tier; intraday is premium.
    """
    if not ALPHA_VANTAGE_KEY:
        raise HTTPException(500, "ALPHA_VANTAGE_KEY is not set")
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": ALPHA_VANTAGE_KEY,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(AV_BASE, params=params)
    data = r.json()
    key = next((k for k in data if "Time Series" in k), None)
    if not key:
        msg = data.get("Note") or data.get("Information") or data
        raise HTTPException(502, f"Stock data unavailable: {msg}")
    rows = data[key]
    df = pd.DataFrame(
        [
            {
                "ts": ts,
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
            }
            for ts, v in rows.items()
        ]
    ).sort_values("ts").reset_index(drop=True)
    return df


async def fetch_news_sentiment(symbol: str) -> dict:
    """
    Alpha Vantage NEWS_SENTIMENT endpoint. Returns an average sentiment score.
    Falls back to neutral on any failure so the pipeline never breaks.
    """
    if not ALPHA_VANTAGE_KEY:
        return {"score": 0.0, "label": "neutral", "article_count": 0}
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "apikey": ALPHA_VANTAGE_KEY,
        "limit": "50",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(AV_BASE, params=params)
        data = r.json()
        feed = data.get("feed", [])
        if not feed:
            return {"score": 0.0, "label": "neutral", "article_count": 0}
        scores = []
        for item in feed:
            for ts in item.get("ticker_sentiment", []):
                if ts.get("ticker") == symbol:
                    scores.append(float(ts.get("ticker_sentiment_score", 0)))
        if not scores:
            # fall back to the overall article sentiment if no per-ticker score
            scores = [float(item.get("overall_sentiment_score", 0)) for item in feed]
        avg = float(np.mean(scores)) if scores else 0.0
        label = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
        return {"score": round(avg, 4), "label": label, "article_count": len(feed)}
    except Exception:
        return {"score": 0.0, "label": "neutral", "article_count": 0}


async def fetch_economic_calendar() -> list:
    """
    Finnhub economic calendar - upcoming medium/high impact events.
    Returns an empty list if no key is set (important for forex, minor for stocks).
    Only events from now onward are kept (past events are not "upcoming risk").
    """
    if not FINNHUB_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{FINNHUB_BASE}/calendar/economic", params={"token": FINNHUB_KEY}
            )
        data = r.json()
        events = data.get("economicCalendar", []) if isinstance(data, dict) else []
        now = datetime.now(timezone.utc)
        upcoming = []
        for ev in events:
            impact = str(ev.get("impact", "")).lower()
            if impact not in ("high", "3", "medium", "2"):
                continue
            # keep only events that are still in the future
            raw_time = ev.get("time")
            try:
                # Finnhub time looks like "2026-05-22 06:00:00" (UTC)
                ev_time = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                if ev_time < now:
                    continue
            except (ValueError, TypeError):
                # if the time can't be parsed, keep it rather than silently drop
                pass
            upcoming.append(
                {
                    "event": ev.get("event"),
                    "country": ev.get("country"),
                    "impact": impact,
                    "time": raw_time,
                }
            )
        # soonest events first
        upcoming.sort(key=lambda e: e.get("time") or "")
        return upcoming[:10]
    except Exception:
        return []


# ------------------- Scoring logic (deterministic) -------------------
def compute_score(df: pd.DataFrame, sentiment: dict, events: list, asset_type: str) -> dict:
    """
    100 points = technical(40) + sentiment(30) + event risk(30)
    Each component votes up/down. alignment_score = how one-directional the
    signals are (NOT a probability of being correct).
    """
    close = df["close"]
    _rsi = rsi(close)
    macd_line, macd_signal = macd(close)
    ma_fast, ma_slow = moving_averages(close)
    vol = atr_pct(df)

    # ---- Technical votes (-1 bearish .. +1 bullish) ----
    tech_votes = []
    tech_votes.append(1 if _rsi < 30 else -1 if _rsi > 70 else (1 if _rsi > 50 else -1))
    tech_votes.append(1 if macd_line > macd_signal else -1)
    tech_votes.append(1 if ma_fast > ma_slow else -1)
    tech_net = float(np.mean(tech_votes))           # -1 .. +1
    tech_points = abs(tech_net) * 40                 # 0..40 (how one-directional)
    tech_dir = "up" if tech_net > 0 else "down"

    # ---- Sentiment vote ----
    s = sentiment.get("score", 0.0)
    sent_dir = "up" if s > 0 else "down"
    sent_points = min(abs(s) / 0.5, 1.0) * 30        # 0..30

    # ---- Event risk: a nearby event lowers certainty, so it lowers points ----
    high_impact_count = sum(
        1 for e in events if str(e.get("impact", "")).lower() in ("high", "3")
    )
    # events matter a lot for forex, much less for stocks
    weight = 1.0 if asset_type == "forex" else 0.4
    event_penalty = min(high_impact_count * weight, 3) / 3
    event_points = (1 - event_penalty) * 30          # no events -> 30, many -> 0

    # ---- Net direction: technical + sentiment vote together ----
    dir_votes = tech_net + (s * 2)  # sentiment given a slightly lower weight
    net_direction = "up" if dir_votes > 0 else "down" if dir_votes < 0 else "neutral"

    alignment_score = round(tech_points + sent_points + event_points)

    return {
        "net_direction": net_direction,
        "alignment_score": int(alignment_score),  # 0-100
        "components": {
            "technical": {
                "points": round(tech_points, 1),
                "direction": tech_dir,
                "rsi": round(_rsi, 1),
                "macd_above_signal": macd_line > macd_signal,
                "ma20_above_ma50": ma_fast > ma_slow,
            },
            "sentiment": {
                "points": round(sent_points, 1),
                "direction": sent_dir,
                "score": s,
                "label": sentiment.get("label"),
                "articles": sentiment.get("article_count"),
            },
            "event_risk": {
                "points": round(event_points, 1),
                "high_impact_events": high_impact_count,
            },
        },
        "volatility_atr_pct": round(vol, 3),
        "last_price": round(float(close.iloc[-1]), 5),
    }


# ----------------------------- Endpoints -----------------------------
@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "market-research-backend",
        "keys_configured": {
            "alpha_vantage": bool(ALPHA_VANTAGE_KEY),
            "finnhub": bool(FINNHUB_KEY),
        },
    }


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if req.asset_type == "forex":
        quote = (req.quote or "USD").upper()
        df = await fetch_forex_ohlcv(req.symbol.upper(), quote)
        news_symbol = f"{req.symbol.upper()}{quote}"
        display = f"{req.symbol.upper()}/{quote}"
    else:
        df = await fetch_stock_ohlcv(req.symbol.upper())
        news_symbol = req.symbol.upper()
        display = req.symbol.upper()

    if len(df) < 50:
        raise HTTPException(422, "Not enough data points to compute indicators")

    sentiment = await fetch_news_sentiment(news_symbol)
    events = await fetch_economic_calendar() if req.asset_type == "forex" else []
    result = compute_score(df, sentiment, events, req.asset_type)

    return {
        "asset": display,
        "asset_type": req.asset_type,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "horizon_hours": req.horizon_hours,
        "score": result["alignment_score"],
        "direction": result["net_direction"],
        "volatility_atr_pct": result["volatility_atr_pct"],
        "last_price": result["last_price"],
        "breakdown": result["components"],
        "upcoming_events": events,
        # The AI Agent must keep this note in the readable message
        "interpretation_note": (
            "Score reflects how aligned the current signals are, not a "
            "guarantee about the future. Markets can move unexpectedly at any time."
        ),
    }
    
    
# ----------------------------- Run directly -----------------------------
# Lets you start the server with: python main.py
# (handy for local dev and tunneling through ngrok)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)