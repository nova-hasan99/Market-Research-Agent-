"""
Yield differential: US10Y minus DE10Y via FRED (St. Louis Fed) -- no API key needed.
Rising spread = USD bullish / EUR bearish.
Run directly: python -m app.providers.yields
"""
import asyncio
import io

import httpx

_FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_US10Y_ID = "DGS10"           # US Treasury 10-year constant maturity
_DE10Y_ID = "IRLTLT01DEM156N" # Germany 10-year government bond yield (OECD/FRED)

_EMPTY = {
    "us10y":        None,
    "de10y":        None,
    "differential": None,
    "direction":    "neutral",
    "label":        "Unavailable",
    "available":    False,
}


def _parse_csv(text: str) -> list[float]:
    """Parse FRED CSV and return the last two non-null close values."""
    values: list[float] = []
    for line in text.strip().split("\n")[1:]:   # skip header
        parts = line.strip().split(",")
        if len(parts) >= 2 and parts[1] not in ("", "."):
            try:
                values.append(float(parts[1]))
            except ValueError:
                pass
    return values


async def fetch_yield_differential(client: httpx.AsyncClient) -> dict:
    """Returns yield differential dict. Always returns a valid dict."""
    try:
        us_r, de_r = await asyncio.gather(
            client.get(_FRED_URL, params={"id": _US10Y_ID}, timeout=15),
            client.get(_FRED_URL, params={"id": _DE10Y_ID}, timeout=15),
        )
        us_vals = _parse_csv(us_r.text)
        de_vals = _parse_csv(de_r.text)

        if len(us_vals) < 2 or len(de_vals) < 2:
            return _EMPTY

        us10y_now  = us_vals[-1]
        de10y_now  = de_vals[-1]
        us10y_prev = us_vals[-2]
        de10y_prev = de_vals[-2]

        diff_now  = us10y_now  - de10y_now
        diff_prev = us10y_prev - de10y_prev
        change    = diff_now - diff_prev

        if change > 0.02:
            direction = "down"   # widening: USD stronger, EUR/USD bearish
            label = f"Spread widening ({diff_now:+.2f}%): USD bullish"
        elif change < -0.02:
            direction = "up"     # narrowing: USD weaker, EUR/USD bullish
            label = f"Spread narrowing ({diff_now:+.2f}%): EUR bullish"
        else:
            direction = "neutral"
            label = f"Spread stable ({diff_now:+.2f}%)"

        return {
            "us10y":        round(us10y_now, 3),
            "de10y":        round(de10y_now, 3),
            "differential": round(diff_now, 3),
            "direction":    direction,
            "label":        label,
            "available":    True,
        }
    except Exception:
        return _EMPTY


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            print(await fetch_yield_differential(c))
    asyncio.run(_test())
