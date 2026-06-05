"""
Price OHLCV data — four providers tried in priority order.
Each provider requests the CORRECT number of bars for the selected timeframe
so that all indicators (RSI-14, MACD-26, Ichimoku-52, MA-50, Fibonacci-60)
have sufficient history regardless of timeframe.

Required minimum bars per indicator:
  MA50:       50 bars
  Ichimoku:   52 bars (Span B uses 52-period range)
  Fibonacci:  60 bars (to identify meaningful swing highs/lows)
  RSI:        28 bars (2x period for warm-up)
  MACD:       52 bars (2x slowest EMA period)
  ATR:        28 bars

Target: 300 bars for all timeframes (ensures all indicators are reliable).
Shorter timeframes require more bars to cover the same wall-clock period.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import httpx
import pandas as pd
from fastapi import HTTPException

from app.config import (
    TWELVE_DATA_KEY, ALPHA_VANTAGE_KEY, POLYGON_KEY,
    TD_BASE, AV_BASE, YAHOO_BASE, POLYGON_BASE,
)


# ── How many bars to request per interval ────────────────────────────────────
# Formula: enough bars so all indicators are reliable.
# Ichimoku needs 52 bars min; we ask for 300 to also cover Fibonacci swing detection.
_BARS: dict[str, int] = {
    "1min":   500,   # 500 min  = ~8h  of 1m data
    "5min":   400,   # 400 × 5  = ~33h of 5m data
    "15min":  300,   # 300 × 15 = ~75h of 15m data
    "30min":  300,
    "1h":     300,   # 300h     = ~12 days
    "4h":     300,   # 300 × 4h = ~50 days
    "8h":     250,   # 250 × 8h = ~83 days
    "1day":   300,   # 300 trading days ≈ 14 months
    "1week":  200,   # 200 weeks = ~3.8 years
    "1month": 120,   # 120 months = 10 years
}

# ── Yahoo Finance interval map (Yahoo doesn't support 4h/8h natively) ────────
# For 4h/8h we fetch 1h data and resample.
_YAHOO_INTERVAL: dict[str, str] = {
    "1min":   "1m",
    "5min":   "5m",
    "15min":  "15m",
    "30min":  "30m",
    "1h":     "1h",
    "4h":     "1h",    # fetch 1h, resample → 4h
    "8h":     "1h",    # fetch 1h, resample → 8h
    "1day":   "1d",
    "1week":  "1wk",
    "1month": "1mo",
}

# Yahoo range to get enough bars at each interval
_YAHOO_RANGE: dict[str, str] = {
    "1min":   "7d",     # Yahoo cap: 7 days for 1m
    "5min":   "60d",    # Yahoo cap: 60 days for 5m
    "15min":  "60d",
    "30min":  "60d",
    "1h":     "2y",     # 2 years → ~3500 hourly bars
    "4h":     "2y",     # fetch 1h/2y then resample → ~875 4h bars
    "8h":     "2y",     # fetch 1h/2y then resample → ~437 8h bars
    "1day":   "5y",     # 5 years → ~1250 daily bars
    "1week":  "max",    # max → 20+ years of weekly bars
    "1month": "max",
}

# How many source-interval bars make one target-interval bar
_RESAMPLE_FACTOR: dict[str, int] = {
    "4h": 4,   # 4 × 1h = 1 4h bar
    "8h": 8,   # 8 × 1h = 1 8h bar
}

# AlphaVantage interval strings (limited intraday support)
_AV_INTERVAL: dict[str, str] = {
    "1min":  "1min",
    "5min":  "5min",
    "15min": "15min",
    "30min": "30min",
    "1h":    "60min",
    "4h":    "60min",   # no native 4h — resample from 1h
    "8h":    "60min",   # no native 8h — resample from 1h
}

# Polygon multiplier + timespan for each interval
_POLYGON_SPAN: dict[str, tuple[int, str]] = {
    "1min":   (1,  "minute"),
    "5min":   (5,  "minute"),
    "15min":  (15, "minute"),
    "30min":  (30, "minute"),
    "1h":     (1,  "hour"),
    "4h":     (4,  "hour"),
    "8h":     (8,  "hour"),
    "1day":   (1,  "day"),
    "1week":  (1,  "week"),
    "1month": (1,  "month"),
}

# Polygon lookback in days per interval
_POLYGON_DAYS: dict[str, int] = {
    "1min": 10, "5min": 30, "15min": 60, "30min": 90,
    "1h": 60, "4h": 180, "8h": 365,
    "1day": 800, "1week": 2000, "1month": 4000,
}


# ── OHLCV resampler (1h → 4h or 8h) ──────────────────────────────────────────

def _resample(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    """
    Resample a 1h OHLCV DataFrame into `factor`-hour bars.
    Groups consecutive rows into OHLC blocks of `factor` rows each.
    """
    if factor <= 1 or len(df) < factor:
        return df
    rows = []
    for i in range(0, len(df) - factor + 1, factor):
        chunk = df.iloc[i: i + factor]
        rows.append({
            "ts":    chunk.iloc[0]["ts"],
            "open":  float(chunk.iloc[0]["open"]),
            "high":  float(chunk["high"].max()),
            "low":   float(chunk["low"].min()),
            "close": float(chunk.iloc[-1]["close"]),
        })
        # Carry volume if present
        if "volume" in chunk.columns:
            rows[-1]["volume"] = float(chunk["volume"].sum())
    return pd.DataFrame(rows).reset_index(drop=True)


# ── Provider 1: Twelve Data ───────────────────────────────────────────────────

async def _td_ohlcv(client: httpx.AsyncClient,
                    symbol: str, interval: str) -> pd.DataFrame:
    if not TWELVE_DATA_KEY:
        raise ValueError("TWELVE_DATA_KEY not configured")
    outputsize = _BARS.get(interval, 300)
    params = {
        "symbol":     symbol,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     TWELVE_DATA_KEY,
        "timezone":   "UTC",
    }
    r    = await client.get(TD_BASE, params=params, timeout=20)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise ValueError(data.get("message", "TwelveData error"))
    rows = [
        {
            "ts":    v["datetime"],
            "open":  float(v["open"]),
            "high":  float(v["high"]),
            "low":   float(v["low"]),
            "close": float(v["close"]),
            "volume": float(v.get("volume", 0) or 0),
        }
        for v in data["values"]
    ]
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    return df


# ── Provider 2: Alpha Vantage ─────────────────────────────────────────────────

async def _av_ohlcv(client: httpx.AsyncClient,
                    symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    if not ALPHA_VANTAGE_KEY:
        raise ValueError("ALPHA_VANTAGE_KEY not configured")

    av_interval = _AV_INTERVAL.get(interval, "60min")
    is_intraday = av_interval in ("1min", "5min", "15min", "30min", "60min")

    if asset_type == "forex":
        base, quote = symbol.split("/")
        if is_intraday:
            params  = {"function": "FX_INTRADAY", "from_symbol": base,
                       "to_symbol": quote, "interval": av_interval,
                       "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY}
            ts_key  = f"Time Series FX ({av_interval})"
        else:
            params  = {"function": "FX_DAILY", "from_symbol": base,
                       "to_symbol": quote, "outputsize": "full",
                       "apikey": ALPHA_VANTAGE_KEY}
            ts_key  = "Time Series FX (Daily)"
    else:
        if is_intraday:
            params = {"function": "TIME_SERIES_INTRADAY", "symbol": symbol,
                      "interval": av_interval, "outputsize": "full",
                      "apikey": ALPHA_VANTAGE_KEY}
            ts_key = f"Time Series ({av_interval})"
        else:
            params = {"function": "TIME_SERIES_DAILY", "symbol": symbol,
                      "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY}
            ts_key = "Time Series (Daily)"

    r    = await client.get(AV_BASE, params=params, timeout=20)
    data = r.json()
    ts   = data.get(ts_key, {})
    if not ts:
        raise ValueError(f"AlphaVantage: no data (keys={list(data.keys())[:3]})")
    rows = [
        {
            "ts":     dt,
            "open":   float(v.get("1. open",  0)),
            "high":   float(v.get("2. high",  0)),
            "low":    float(v.get("3. low",   0)),
            "close":  float(v.get("4. close", 0)),
            "volume": float(v.get("5. volume", 0) or 0),
        }
        for dt, v in ts.items()
    ]
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)

    # Resample if needed (AV has no 4h/8h native)
    factor = _RESAMPLE_FACTOR.get(interval, 1)
    if factor > 1:
        df = _resample(df, factor)

    return df


# ── Provider 3: Yahoo Finance (no key required) ───────────────────────────────

async def _yahoo_ohlcv(client: httpx.AsyncClient,
                       symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    yf_sym = (symbol.replace("/", "") + "=X") if asset_type == "forex" else symbol

    # Map our interval to Yahoo's interval string and range
    yf_interval = _YAHOO_INTERVAL.get(interval, "1d")
    yf_range    = _YAHOO_RANGE.get(interval, "2y")

    r = await client.get(
        f"{YAHOO_BASE}/{yf_sym}",
        params={"interval": yf_interval, "range": yf_range},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    data   = r.json()
    result = data.get("chart", {}).get("result", [])
    if not result:
        raise ValueError(f"Yahoo: no result for {yf_sym}")

    res = result[0]
    q   = res.get("indicators", {}).get("quote", [{}])[0]
    df  = pd.DataFrame({
        "ts":     [str(t) for t in res.get("timestamp", [])],
        "open":   q.get("open",   []),
        "high":   q.get("high",   []),
        "low":    q.get("low",    []),
        "close":  q.get("close",  []),
        "volume": q.get("volume", [0] * len(res.get("timestamp", []))),
    }).dropna(subset=["open", "high", "low", "close"]).sort_values("ts").reset_index(drop=True)

    if df.empty:
        raise ValueError("Yahoo: empty dataframe after dropna")

    # Resample 1h → 4h or 8h if needed
    factor = _RESAMPLE_FACTOR.get(interval, 1)
    if factor > 1:
        df = _resample(df, factor)

    return df


# ── Provider 4: Polygon.io (stocks + forex on paid tier) ─────────────────────

async def _polygon_ohlcv(client: httpx.AsyncClient,
                          symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    if not POLYGON_KEY or asset_type == "forex":
        raise ValueError("Polygon: no key or forex not supported on free tier")

    span_info = _POLYGON_SPAN.get(interval, (1, "day"))
    multiplier, timespan = span_info
    lookback_days = _POLYGON_DAYS.get(interval, 730)

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    bars  = _BARS.get(interval, 300)
    url   = (f"{POLYGON_BASE}/{symbol}/range/{multiplier}/{timespan}/"
             f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}")
    r     = await client.get(url, params={"apiKey": POLYGON_KEY, "limit": bars}, timeout=20)
    data  = r.json()
    items = data.get("results", [])
    if not items:
        raise ValueError("Polygon: no results")
    df = pd.DataFrame([
        {"ts": str(i["t"]), "open": i["o"], "high": i["h"],
         "low": i["l"], "close": i["c"], "volume": float(i.get("v", 0) or 0)}
        for i in items
    ])
    return df.sort_values("ts").reset_index(drop=True)


# ── Public fallback chain ─────────────────────────────────────────────────────

async def fetch_ohlcv(
    client: httpx.AsyncClient, symbol: str, interval: str, asset_type: str
) -> tuple[pd.DataFrame, str]:
    """
    Try providers in priority order. Returns (dataframe, provider_name).
    Minimum required bars: 100 (enough for Ichimoku, MA50, Fibonacci).
    Raises HTTPException 502 if all providers fail or return too few bars.
    """
    required = max(100, min(_BARS.get(interval, 100), 100))  # hard minimum = 100
    errors: list[str] = []
    chain = [
        ("TwelveData",   _td_ohlcv(client, symbol, interval)),
        ("AlphaVantage", _av_ohlcv(client, symbol, interval, asset_type)),
        ("Yahoo",        _yahoo_ohlcv(client, symbol, interval, asset_type)),
        ("Polygon",      _polygon_ohlcv(client, symbol, interval, asset_type)),
    ]
    for name, coro in chain:
        try:
            df = await coro
            if len(df) >= required:
                return df, name
            errors.append(f"{name}: only {len(df)} rows (need {required})")
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:120]}")
    raise HTTPException(502, f"All price providers failed — {'; '.join(errors)}")


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        tests = [
            ("EUR/USD", "1h",   "forex"),
            ("EUR/USD", "4h",   "forex"),
            ("EUR/USD", "1day", "forex"),
            ("AAPL",    "1h",   "stock"),
            ("AAPL",    "1day", "stock"),
        ]
        async with httpx.AsyncClient() as c:
            for sym, iv, at in tests:
                try:
                    df, src = await fetch_ohlcv(c, sym, iv, at)
                    print(f"OK  {sym} {iv:6s} [{at}]: {len(df)} bars from {src}")
                except Exception as e:
                    print(f"ERR {sym} {iv:6s}: {e}")
    asyncio.run(_test())
