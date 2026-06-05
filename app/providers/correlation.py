"""
Global correlation provider.
Works for ANY forex pair and ANY stock globally.

For forex: dynamically finds correlated pairs based on shared currencies,
commodity linkages, and safe-haven relationships.
For stocks: fetches sector ETF and index benchmark.

Retail sentiment via OANDA API (optional, requires key).
"""
import asyncio
import httpx
from app.config import OANDA_API_KEY, IG_API_KEY, TRADINGECONOMICS_KEY

_YF_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

# ── Global currency universe ──────────────────────────────────────────────────
# Every major/minor/some-exotic pair supported by Yahoo Finance
_ALL_FX_PAIRS = [
    # G7 majors
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD", "NZD/USD",
    # EUR crosses
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/CAD", "EUR/AUD", "EUR/NZD",
    # GBP crosses
    "GBP/JPY", "GBP/CHF", "GBP/CAD", "GBP/AUD", "GBP/NZD",
    # JPY crosses
    "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY",
    # Other minors
    "AUD/CAD", "AUD/CHF", "AUD/NZD", "CAD/CHF", "NZD/CAD", "NZD/CHF",
    # Exotics (partial)
    "USD/TRY", "USD/ZAR", "USD/MXN", "USD/SEK", "USD/NOK", "USD/DKK",
    "USD/SGD", "USD/HKD", "USD/CNY", "USD/INR", "USD/BRL",
    "EUR/TRY", "EUR/SEK", "EUR/NOK", "EUR/PLN", "EUR/HUF", "EUR/CZK",
]

# ── Commodity-currency relationships ─────────────────────────────────────────
# Fetch these Yahoo Finance tickers for commodity currencies
_COMMODITY_TICKERS: dict[str, tuple[str, str]] = {
    "AUD": ("GC=F",  "Gold"),          # AUD strongly correlated with gold
    "NZD": ("GC=F",  "Gold"),          # NZD also gold-sensitive
    "CAD": ("CL=F",  "WTI Oil"),       # CAD tracks oil
    "NOK": ("BZ=F",  "Brent Oil"),     # NOK tracks Brent
    "RUB": ("CL=F",  "WTI Oil"),       # RUB tracks oil
    "ZAR": ("GC=F",  "Gold"),          # ZAR tracks gold/platinum
    "CLP": ("HG=F",  "Copper"),        # Chilean peso tracks copper
}

# ── Safe-haven pairs ──────────────────────────────────────────────────────────
_SAFE_HAVENS = {"JPY", "CHF", "USD"}

# ── Stock benchmark map (sector ETF / index) ─────────────────────────────────
# For any stock we map its exchange/country to the right benchmark
_EXCHANGE_BENCHMARKS: dict[str, tuple[str, str]] = {
    "US":  ("^GSPC",  "S&P 500"),
    "NASDAQ": ("^IXIC", "NASDAQ"),
    "NYSE": ("^GSPC",  "S&P 500"),
    "UK":  ("^FTSE",  "FTSE 100"),
    "DE":  ("^GDAXI", "DAX"),
    "FR":  ("^FCHI",  "CAC 40"),
    "JP":  ("^N225",  "Nikkei 225"),
    "HK":  ("^HSI",   "Hang Seng"),
    "CN":  ("000001.SS", "Shanghai"),
    "IN":  ("^BSESN",  "BSE Sensex"),
    "AU":  ("^AXJO",   "ASX 200"),
    "CA":  ("^GSPTSE", "TSX"),
    "BR":  ("^BVSP",   "Bovespa"),
    "DEFAULT": ("^GSPC", "S&P 500"),
}


# ── Core OHLCV fetch ──────────────────────────────────────────────────────────

async def _yf_ohlcv(client: httpx.AsyncClient, ticker: str,
                     interval: str = "1d", bars: str = "5d") -> dict:
    """Fetch OHLCV from Yahoo Finance. Returns dict with closes list."""
    try:
        r = await client.get(
            f"{_YF_BASE}/{ticker}",
            params={"interval": interval, "range": bars},
            timeout=9,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return {}
        result = r.json().get("chart", {}).get("result", [{}])[0]
        quote  = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in (quote.get("close") or []) if c is not None]
        return {"closes": closes, "meta": result.get("meta", {})}
    except Exception:
        return {}


# ── Forex correlation ─────────────────────────────────────────────────────────

def _get_correlated_pairs(symbol: str) -> list[str]:
    """
    Dynamically compute the most relevant correlated pairs for ANY forex symbol.
    Logic:
      1. Pairs sharing the base currency (same direction)
      2. Pairs sharing the quote currency (inverse direction for inverted pairs)
      3. Classic inversions: EUR/USD vs USD/CHF (strong negative correlation)
    Returns up to 4 most relevant pairs (excluding the symbol itself).
    """
    parts = symbol.upper().split("/")
    if len(parts) != 2:
        return []
    base, quote = parts[0], parts[1]

    primary: list[str]   = []  # Share base OR quote
    secondary: list[str] = []  # Classic macro correlations

    for pair in _ALL_FX_PAIRS:
        if pair.upper() == symbol.upper():
            continue
        p = pair.upper().split("/")
        if len(p) != 2:
            continue
        pb, pq = p[0], p[1]
        if pb == base or pq == quote or pb == quote or pq == base:
            primary.append(pair)

    # Prioritise: pairs that share the LESS common currency first
    # e.g. for EUR/GBP → EUR crosses and GBP crosses are equally relevant
    # Sort: pairs containing both currencies first, then base, then quote
    def _score(p: str) -> int:
        pb, pq = p.upper().split("/")
        shared = (pb in (base, quote)) + (pq in (base, quote))
        return -shared   # most shared first

    primary.sort(key=_score)

    # Remove duplicates, limit to 4
    seen = set()
    result = []
    for p in primary:
        if p not in seen:
            seen.add(p)
            result.append(p)
        if len(result) >= 4:
            break
    return result


async def _pair_change(client: httpx.AsyncClient, pair: str) -> dict | None:
    """Fetch 3-day % change for a forex pair."""
    ticker = pair.replace("/", "") + "=X"
    data   = await _yf_ohlcv(client, ticker, "1d", "5d")
    closes = data.get("closes", [])
    if len(closes) < 2:
        return None
    chg = (closes[-1] - closes[0]) / closes[0] * 100
    return {
        "symbol":     pair,
        "change_pct": round(chg, 3),
        "direction":  "up" if chg > 0 else "down",
        "price":      round(closes[-1], 5),
    }


async def fetch_dxy(client: httpx.AsyncClient) -> dict:
    """Dollar Index — relevant when USD is in the pair."""
    data   = await _yf_ohlcv(client, "DX-Y.NYB", "1d", "5d")
    closes = data.get("closes", [])
    if len(closes) < 2:
        return {"available": False}
    chg = (closes[-1] - closes[-2]) / closes[-2] * 100
    return {
        "available":  True,
        "value":      round(closes[-1], 2),
        "change_pct": round(chg, 3),
        "direction":  ("strengthening" if chg > 0.05
                       else "weakening" if chg < -0.05 else "neutral"),
    }


async def _commodity_data(client: httpx.AsyncClient,
                           ticker: str, name: str) -> dict | None:
    """Fetch latest commodity price change."""
    data   = await _yf_ohlcv(client, ticker, "1d", "5d")
    closes = data.get("closes", [])
    if len(closes) < 2:
        return None
    chg = (closes[-1] - closes[-2]) / closes[-2] * 100
    return {
        "name":       name,
        "ticker":     ticker,
        "price":      round(closes[-1], 2),
        "change_pct": round(chg, 3),
        "direction":  "up" if chg > 0.05 else "down" if chg < -0.05 else "neutral",
    }


async def fetch_correlation(client: httpx.AsyncClient, symbol: str) -> dict:
    """
    Fetch correlation data for ANY forex pair.
    - Always: DXY (if USD in pair) or EUR index (if EUR in pair)
    - Always: up to 4 dynamically chosen correlated pairs
    - If commodity currency: relevant commodity (gold, oil, etc.)
    """
    parts = symbol.upper().split("/")
    base  = parts[0] if len(parts) == 2 else ""
    quote = parts[1] if len(parts) == 2 else ""

    corr_pairs = _get_correlated_pairs(symbol)
    has_usd    = "USD" in (base, quote)

    # Build task list
    tasks: list = [fetch_dxy(client)]
    tasks += [_pair_change(client, p) for p in corr_pairs]

    # Commodity correlation if applicable
    commodity_key = _COMMODITY_TICKERS.get(base) or _COMMODITY_TICKERS.get(quote)
    if commodity_key:
        tasks.append(_commodity_data(client, commodity_key[0], commodity_key[1]))
    else:
        tasks.append(asyncio.coroutine(lambda: None)() if False else _noop())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    dxy       = results[0] if isinstance(results[0], dict) else {"available": False}
    pairs_raw = results[1:1 + len(corr_pairs)]
    pairs     = [p for p in pairs_raw if isinstance(p, dict) and p]

    commodity = None
    if commodity_key and isinstance(results[-1], dict):
        commodity = results[-1]

    return {
        "available":  True,
        "symbol":     symbol,
        "dxy":        dxy,
        "pairs":      pairs,
        "commodity":  commodity,
        "has_usd":    has_usd,
    }


async def _noop() -> None:
    return None


# ── Stock correlation ─────────────────────────────────────────────────────────

async def fetch_stock_correlation(client: httpx.AsyncClient,
                                   symbol: str,
                                   sector_etf: str | None = None) -> dict:
    """
    Benchmark correlation for ANY stock globally.
    Fetches S&P 500 (or regional index) + sector ETF if available.
    """
    # Primary benchmark: S&P 500 for US stocks, regional index otherwise
    benchmark_ticker, benchmark_name = _EXCHANGE_BENCHMARKS["DEFAULT"]

    tasks = [_yf_ohlcv(client, benchmark_ticker, "1d", "5d")]
    if sector_etf:
        tasks.append(_yf_ohlcv(client, sector_etf, "1d", "5d"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    def _to_chg(res) -> dict | None:
        if not isinstance(res, dict):
            return None
        closes = res.get("closes", [])
        if len(closes) < 2:
            return None
        chg = (closes[-1] - closes[0]) / closes[0] * 100
        return {"change_pct": round(chg, 3),
                "direction": "up" if chg > 0 else "down",
                "price": round(closes[-1], 2)}

    benchmark_chg = _to_chg(results[0])
    sector_chg    = _to_chg(results[1]) if len(results) > 1 else None

    return {
        "available":      True,
        "benchmark_name": benchmark_name,
        "benchmark":      benchmark_chg,
        "sector_etf":     sector_etf,
        "sector":         sector_chg,
    }


# ── Retail sentiment (OANDA — optional) ──────────────────────────────────────

async def fetch_retail_sentiment(client: httpx.AsyncClient, symbol: str) -> dict:
    """
    OANDA order book — retail trader positioning (contrarian indicator).
    Works for any OANDA-supported forex instrument.
    Rule: >70% retail long = bearish signal (fade the crowd).
          >70% retail short = bullish signal.
    Requires OANDA_API_KEY in .env.
    """
    if not OANDA_API_KEY:
        return {"available": False}

    # OANDA instrument format: EUR/USD -> EUR_USD
    instrument = symbol.replace("/", "_").upper()

    try:
        r = await client.get(
            f"https://api-fxtrade.oanda.com/v3/instruments/{instrument}/orderBook",
            headers={
                "Authorization": f"Bearer {OANDA_API_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return {"available": False, "source": "OANDA"}

        buckets   = r.json().get("orderBook", {}).get("buckets", [])
        long_sum  = sum(float(b.get("longCountPercent",  0)) for b in buckets)
        short_sum = sum(float(b.get("shortCountPercent", 0)) for b in buckets)
        total     = (long_sum + short_sum) or 1.0
        long_pct  = round(long_sum  / total * 100, 1)
        short_pct = round(short_sum / total * 100, 1)

        # Contrarian signal
        if long_pct > 70:
            signal = "bearish"     # Most retail long → fade them
            note   = f"{long_pct}% retail long - contrarian bearish"
        elif short_pct > 70:
            signal = "bullish"     # Most retail short → fade them
            note   = f"{short_pct}% retail short - contrarian bullish"
        else:
            signal = "neutral"
            note   = "Retail positioning mixed"

        return {
            "available":  True,
            "source":     "OANDA",
            "long_pct":   long_pct,
            "short_pct":  short_pct,
            "signal":     signal,
            "note":       note,
            "contrarian": True,
        }
    except Exception:
        return {"available": False, "source": "OANDA"}


# ── IG Sentiment (optional) ───────────────────────────────────────────────────

async def fetch_ig_sentiment(client: httpx.AsyncClient, symbol: str) -> dict:
    """
    IG Client Sentiment — retail positioning from IG Group.
    Requires IG_API_KEY in .env (IG REST API v1).
    Currently a placeholder — returns available=False until key is configured.
    When configured, provides live retail long/short % for any IG instrument.
    """
    if not IG_API_KEY:
        return {"available": False, "source": "IG", "reason": "IG_API_KEY not configured"}

    # IG REST API endpoint (placeholder — implement when key available)
    # Reference: https://labs.ig.com/rest-trading-api-reference
    try:
        r = await client.get(
            "https://api.ig.com/gateway/deal/clientsentiment",
            params={"marketIds": symbol.replace("/", "")},
            headers={
                "X-IG-API-KEY": IG_API_KEY,
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json; charset=UTF-8",
                "Version": "1",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return {"available": False, "source": "IG"}

        data      = r.json().get("clientSentiments", [{}])[0]
        long_pct  = float(data.get("longPositionPercentage",  50))
        short_pct = float(data.get("shortPositionPercentage", 50))

        if long_pct > 70:
            signal = "bearish"
            note   = f"{long_pct:.0f}% IG clients long - contrarian bearish"
        elif short_pct > 70:
            signal = "bullish"
            note   = f"{short_pct:.0f}% IG clients short - contrarian bullish"
        else:
            signal = "neutral"
            note   = "IG client sentiment mixed"

        return {
            "available":  True,
            "source":     "IG",
            "long_pct":   round(long_pct, 1),
            "short_pct":  round(short_pct, 1),
            "signal":     signal,
            "note":       note,
            "contrarian": True,
        }
    except Exception:
        return {"available": False, "source": "IG"}


# ── TradingEconomics (optional) ───────────────────────────────────────────────

async def fetch_economic_indicators(client: httpx.AsyncClient,
                                     country: str = "united states") -> dict:
    """
    TradingEconomics API — real-time economic indicators and forecasts.
    Requires TRADINGECONOMICS_KEY in .env.
    Currently a placeholder — returns available=False until key is configured.
    When configured, provides: GDP, inflation, interest rates, employment data.
    Reference: https://tradingeconomics.com/api
    """
    if not TRADINGECONOMICS_KEY:
        return {"available": False, "source": "TradingEconomics",
                "reason": "TRADINGECONOMICS_KEY not configured"}

    try:
        r = await client.get(
            "https://api.tradingeconomics.com/indicators",
            params={
                "c":       TRADINGECONOMICS_KEY,
                "country": country,
                "category": "inflation rate,interest rate,gdp growth rate",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return {"available": False, "source": "TradingEconomics"}

        data = r.json()
        indicators = []
        for item in (data if isinstance(data, list) else [])[:6]:
            indicators.append({
                "category": item.get("Category", ""),
                "value":    item.get("LatestValue"),
                "previous": item.get("PreviousValue"),
                "unit":     item.get("Unit", ""),
                "country":  item.get("Country", ""),
            })

        return {
            "available":   True,
            "source":      "TradingEconomics",
            "indicators":  indicators,
            "country":     country,
        }
    except Exception:
        return {"available": False, "source": "TradingEconomics"}


# ── Best-available sentiment aggregator ──────────────────────────────────────

async def fetch_best_retail_sentiment(client: httpx.AsyncClient,
                                       symbol: str) -> dict:
    """
    Try OANDA first, fall back to IG, return available=False if neither configured.
    This is the function routes.py should call - never breaks regardless of which
    APIs are configured.
    """
    # Try OANDA
    if OANDA_API_KEY:
        result = await fetch_retail_sentiment(client, symbol)
        if result.get("available"):
            return result

    # Try IG
    if IG_API_KEY:
        result = await fetch_ig_sentiment(client, symbol)
        if result.get("available"):
            return result

    # Neither configured or both failed - return graceful empty
    return {
        "available": False,
        "reason":    "No retail sentiment API configured (OANDA_API_KEY or IG_API_KEY)",
        "hint":      "Add OANDA_API_KEY or IG_API_KEY to .env to enable retail positioning data",
    }
