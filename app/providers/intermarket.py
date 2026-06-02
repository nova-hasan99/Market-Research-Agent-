"""
USD Dollar-strength proxy using EUR/USD and USD/JPY trends.
Run directly: python -m app.providers.intermarket
"""
import asyncio

import httpx

from app.indicators import trend_direction
from app.providers.price import fetch_ohlcv


async def fetch_usd_strength(client: httpx.AsyncClient) -> dict:
    """
    Dollar strengthening  → EUR/USD falling AND USD/JPY rising.
    Dollar weakening      → EUR/USD rising  AND USD/JPY falling.
    Returns a dict with keys: dollar, eurusd_trend, usdjpy_trend.
    """
    try:
        (eurusd, _), (usdjpy, _) = await asyncio.gather(
            fetch_ohlcv(client, "EUR/USD", "1day", "forex"),
            fetch_ohlcv(client, "USD/JPY", "1day", "forex"),
        )
        eur_t = trend_direction(eurusd["close"])
        jpy_t = trend_direction(usdjpy["close"])
        score = (
            (1 if eur_t == "down" else -1 if eur_t == "up" else 0) +
            (1 if jpy_t == "up"   else -1 if jpy_t == "down" else 0)
        )
        dollar = "strengthening" if score > 0 else "weakening" if score < 0 else "mixed"
        return {"dollar": dollar, "eurusd_trend": eur_t, "usdjpy_trend": jpy_t}
    except Exception:
        return {"dollar": "unknown", "eurusd_trend": "n/a", "usdjpy_trend": "n/a"}


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            result = await fetch_usd_strength(c)
            print(result)
    asyncio.run(_test())
