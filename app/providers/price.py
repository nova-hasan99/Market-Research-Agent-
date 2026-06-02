"""
Price OHLCV data — four providers tried in priority order.
Run directly to test a symbol: python -m app.providers.price
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


# ── Provider 1: Twelve Data ──────────────────────────────────────────────────
async def _td_ohlcv(client: httpx.AsyncClient, symbol: str, interval: str) -> pd.DataFrame:
    if not TWELVE_DATA_KEY:
        raise ValueError("TWELVE_DATA_KEY not configured")
    params = {
        "symbol": symbol, "interval": interval,
        "outputsize": 200, "apikey": TWELVE_DATA_KEY, "timezone": "UTC",
    }
    r    = await client.get(TD_BASE, params=params, timeout=20)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise ValueError(data.get("message", "TwelveData error"))
    rows = [
        {"ts": v["datetime"], "open": float(v["open"]), "high": float(v["high"]),
         "low": float(v["low"]), "close": float(v["close"])}
        for v in data["values"]
    ]
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


# ── Provider 2: Alpha Vantage ────────────────────────────────────────────────
async def _av_ohlcv(client: httpx.AsyncClient, symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    if not ALPHA_VANTAGE_KEY:
        raise ValueError("ALPHA_VANTAGE_KEY not configured")
    is_hourly = interval in ("1h", "60min")
    if asset_type == "forex":
        base, quote = symbol.split("/")
        if is_hourly:
            params = {"function": "FX_INTRADAY", "from_symbol": base, "to_symbol": quote,
                      "interval": "60min", "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY}
            ts_key = "Time Series FX (60min)"
        else:
            params = {"function": "FX_DAILY", "from_symbol": base, "to_symbol": quote,
                      "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY}
            ts_key = "Time Series FX (Daily)"
    else:
        if is_hourly:
            params = {"function": "TIME_SERIES_INTRADAY", "symbol": symbol,
                      "interval": "60min", "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY}
            ts_key = "Time Series (60min)"
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
        {"ts": dt, "open": float(v.get("1. open", 0)), "high": float(v.get("2. high", 0)),
         "low": float(v.get("3. low", 0)), "close": float(v.get("4. close", 0))}
        for dt, v in ts.items()
    ]
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


# ── Provider 3: Yahoo Finance (no key required) ──────────────────────────────
async def _yahoo_ohlcv(client: httpx.AsyncClient, symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    is_hourly = interval in ("1h", "60min")
    yf_sym    = (symbol.replace("/", "") + "=X") if asset_type == "forex" else symbol
    r = await client.get(
        f"{YAHOO_BASE}/{yf_sym}",
        params={"interval": "1h" if is_hourly else "1d", "range": "30d" if is_hourly else "2y"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    data   = r.json()
    result = data.get("chart", {}).get("result", [])
    if not result:
        raise ValueError(f"Yahoo: no result for {yf_sym}")
    res  = result[0]
    q    = res.get("indicators", {}).get("quote", [{}])[0]
    df   = pd.DataFrame({
        "ts":    [str(t) for t in res.get("timestamp", [])],
        "open":  q.get("open",  []),
        "high":  q.get("high",  []),
        "low":   q.get("low",   []),
        "close": q.get("close", []),
    }).dropna().sort_values("ts").reset_index(drop=True)
    if df.empty:
        raise ValueError("Yahoo: empty dataframe after dropna")
    return df


# ── Provider 4: Polygon.io (stocks only) ────────────────────────────────────
async def _polygon_ohlcv(client: httpx.AsyncClient, symbol: str, interval: str, asset_type: str) -> pd.DataFrame:
    if not POLYGON_KEY or asset_type == "forex":
        raise ValueError("Polygon: no key or forex not supported on free tier")
    is_hourly = interval in ("1h", "60min")
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=30 if is_hourly else 730)
    span  = "hour" if is_hourly else "day"
    url   = f"{POLYGON_BASE}/{symbol}/range/1/{span}/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    r     = await client.get(url, params={"apiKey": POLYGON_KEY, "limit": 300}, timeout=20)
    data  = r.json()
    items = data.get("results", [])
    if not items:
        raise ValueError("Polygon: no results")
    df = pd.DataFrame([{"ts": str(i["t"]), "open": i["o"], "high": i["h"], "low": i["l"], "close": i["c"]} for i in items])
    return df.sort_values("ts").reset_index(drop=True)


# ── Public fallback chain ────────────────────────────────────────────────────
async def fetch_ohlcv(
    client: httpx.AsyncClient, symbol: str, interval: str, asset_type: str
) -> tuple[pd.DataFrame, str]:
    """
    Try providers in priority order. Returns (dataframe, provider_name).
    Raises HTTPException 502 if all fail.
    """
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
            if len(df) >= 50:
                return df, name
            errors.append(f"{name}: only {len(df)} rows")
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:100]}")
    raise HTTPException(502, f"All price providers failed — {'; '.join(errors)}")


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            df, src = await fetch_ohlcv(c, "EUR/USD", "1h", "forex")
            print(f"Got {len(df)} rows from {src}")
            print(df.tail(3))
    asyncio.run(_test())
