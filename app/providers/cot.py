"""
CFTC Commitments of Traders (COT) institutional positioning.
Free weekly data via CFTC Socrata API, no API key required.
Run directly: python -m app.providers.cot
"""
import asyncio

import httpx

_SOCRATA_URL = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"

_COT_CODES: dict[str, str] = {
    "EUR": "099741",
    "GBP": "096742",
    "JPY": "097741",
    "AUD": "232741",
    "NZD": "112741",
    "CAD": "090741",
    "CHF": "092741",
}

_EMPTY = {
    "net":         0,
    "direction":   "neutral",
    "label":       "No Data",
    "weeks_trend": "unknown",
    "available":   False,
}


def _parse_pair(symbol: str) -> tuple[str, str]:
    if "/" in symbol:
        parts = symbol.upper().split("/")
        return parts[0], parts[1]
    s = symbol.upper()
    return s[:3], s[3:]


def _cot_currency(base: str, quote: str) -> tuple[str, bool]:
    """
    Returns (currency_to_lookup, should_invert).
    should_invert = True when positive net COT means the pair goes DOWN.
    """
    if quote == "USD" and base in _COT_CODES:
        return base, False          # EUR/USD: long EUR = pair UP
    if base == "USD" and quote in _COT_CODES:
        return quote, True          # USD/JPY: long JPY = pair DOWN
    if base in _COT_CODES:
        return base, False          # Cross: use base direction
    if quote in _COT_CODES:
        return quote, False
    return "", False


async def fetch_cot(
    client: httpx.AsyncClient, symbol: str, asset_type: str
) -> dict:
    """Returns COT data dict. Always returns a valid dict, never raises."""
    if asset_type != "forex":
        return _EMPTY

    base, quote = _parse_pair(symbol)
    currency, invert = _cot_currency(base, quote)
    code = _COT_CODES.get(currency)
    if not code:
        return _EMPTY

    try:
        r = await client.get(
            _SOCRATA_URL,
            params={
                "cftc_contract_market_code": code,
                "$order":  "report_date_as_yyyy_mm_dd DESC",
                "$limit":  "2",
                "$select": (
                    "report_date_as_yyyy_mm_dd,"
                    "noncomm_positions_long_all,"
                    "noncomm_positions_short_all"
                ),
            },
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return _EMPTY

        cur    = rows[0]
        longs  = int(cur.get("noncomm_positions_long_all",  0) or 0)
        shorts = int(cur.get("noncomm_positions_short_all", 0) or 0)
        net    = longs - shorts

        weeks_trend = "unknown"
        if len(rows) >= 2:
            prev     = rows[1]
            prev_net = (
                int(prev.get("noncomm_positions_long_all",  0) or 0) -
                int(prev.get("noncomm_positions_short_all", 0) or 0)
            )
            delta = net - prev_net
            weeks_trend = "increasing" if delta > 2000 else "decreasing" if delta < -2000 else "flat"

        effective_net = -net if invert else net
        direction     = "up" if effective_net > 0 else "down" if effective_net < 0 else "neutral"
        pos_label     = "Net Long" if net > 0 else "Net Short"
        label         = f"{pos_label} {currency} ({net:+,})"

        return {
            "net":           net,
            "effective_net": effective_net,
            "direction":     direction,
            "label":         label,
            "currency":      currency,
            "weeks_trend":   weeks_trend,
            "available":     True,
        }
    except Exception as exc:
        return {**_EMPTY, "error": str(exc)[:120]}


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            for sym, at in [("EUR/USD","forex"),("USD/JPY","forex"),("AAPL","stock")]:
                print(sym, await fetch_cot(c, sym, at))
    asyncio.run(_test())
