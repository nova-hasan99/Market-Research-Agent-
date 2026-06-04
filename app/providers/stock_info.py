"""
Stock-specific data providers:
  - Fundamentals:       Alpha Vantage OVERVIEW (P/E, EPS, Market Cap, Beta, etc.)
  - Earnings:           Finnhub /stock/earnings + /calendar/earnings
  - Analyst:            Finnhub /stock/recommendation + /stock/price-target
  - Insider:            Finnhub /stock/insider-transactions
  - History:            Yahoo Finance 5Y weekly vs SPY (1M/3M/6M/1Y/2Y/5Y returns)
  - Short Interest:     Finnhub /stock/short-interest
  - Institutional:      Finnhub /institutional/ownership
  - Options Sentiment:  Finnhub /stock/option-chain (put/call OI ratio)
  - Sector Performance: Yahoo Finance sector ETF 1M return
Run directly: python -m app.providers.stock_info
"""
import asyncio
from datetime import datetime, timedelta

import httpx

from app.config import (
    ALPHA_VANTAGE_KEY, FINNHUB_KEY,
    AV_BASE, FINNHUB_BASE, YAHOO_BASE,
)

# ── Sector constants ──────────────────────────────────────────────────────────

SECTOR_ETF_MAP: dict[str, str] = {
    "Technology":             "XLK",
    "Consumer Discretionary": "XLY",
    "Health Care":            "XLV",
    "Healthcare":             "XLV",
    "Financials":             "XLF",
    "Energy":                 "XLE",
    "Communication Services": "XLC",
    "Industrials":            "XLI",
    "Materials":              "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Consumer Staples":       "XLP",
}

SECTOR_PE_AVG: dict[str, float] = {
    "Technology":             28.0,
    "Consumer Discretionary": 24.0,
    "Health Care":            22.0,
    "Healthcare":             22.0,
    "Financials":             14.0,
    "Energy":                 12.0,
    "Communication Services": 18.0,
    "Industrials":            20.0,
    "Materials":              16.0,
    "Utilities":              17.0,
    "Real Estate":            30.0,
    "Consumer Staples":       20.0,
}


def get_sector_etf(sector: str | None) -> str:
    """Map sector name to its benchmark ETF ticker; fall back to SPY."""
    if not sector:
        return "SPY"
    su = sector.upper()
    for key, etf in SECTOR_ETF_MAP.items():
        if key.upper() in su or su in key.upper():
            return etf
    return "SPY"


def get_sector_pe(sector: str | None) -> float:
    """Return typical P/E for the sector; default 20.0."""
    if not sector:
        return 20.0
    su = sector.upper()
    for key, pe in SECTOR_PE_AVG.items():
        if key.upper() in su or su in key.upper():
            return pe
    return 20.0


# ── Empty / fallback dicts ────────────────────────────────────────────────────

_EMPTY_FUNDAMENTALS = {
    "pe_ratio": None, "forward_pe": None, "eps": None,
    "market_cap": None, "market_cap_raw": None,
    "beta": None, "week52_high": None, "week52_low": None,
    "dividend_yield": None, "revenue_growth": None,
    "profit_margin": None, "roe": None,
    "sector": None, "industry": None, "description": None,
    "available": False,
}

_EMPTY_EARNINGS = {
    "quarters": [], "next_date": None,
    "beats": 0, "misses": 0, "available": False,
}

_EMPTY_ANALYST = {
    "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0,
    "total": 0, "consensus": "No Data",
    "price_target_mean": None, "price_target_high": None, "price_target_low": None,
    "upside_pct": None, "available": False,
}

_EMPTY_INSIDER = {
    "transactions": [], "buy_count": 0, "sell_count": 0,
    "net_shares": 0, "available": False,
}

_EMPTY_HISTORY = {
    "returns": {}, "spy_returns": {}, "vs_spy": {},
    "direction": "neutral", "label": "Unavailable", "available": False,
}

_EMPTY_SHORT_INTEREST = {
    "short_percent": None, "days_to_cover": None,
    "signal": "unknown", "squeeze_risk": False, "available": False,
}

_EMPTY_INSTITUTIONAL = {
    "top_holders": [], "buy_count": 0, "sell_count": 0,
    "signal": "neutral", "available": False,
}

_EMPTY_OPTIONS_SENT = {
    "put_oi": None, "call_oi": None, "ratio": None,
    "signal": "neutral", "label": "No Data", "available": False,
}

_EMPTY_SECTOR_PERF = {
    "etf": "N/A", "etf_1m": None, "signal": "neutral",
    "label": "Unavailable", "available": False,
}


# ── Fundamentals (Alpha Vantage OVERVIEW) ─────────────────────────────────────

async def fetch_stock_fundamentals(client: httpx.AsyncClient, symbol: str) -> dict:
    """P/E, EPS, Market Cap, Beta, sector, growth metrics from Alpha Vantage."""
    if not ALPHA_VANTAGE_KEY:
        return _EMPTY_FUNDAMENTALS

    try:
        r = await client.get(
            AV_BASE,
            params={"function": "OVERVIEW", "symbol": symbol, "apikey": ALPHA_VANTAGE_KEY},
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()
        if not d or "Symbol" not in d:
            return _EMPTY_FUNDAMENTALS

        def _f(key):
            v = d.get(key)
            try:
                return float(v) if v not in (None, "None", "N/A", "-", "") else None
            except (ValueError, TypeError):
                return None

        def _fmt_cap(v):
            if v is None: return None
            if v >= 1e12: return f"${v / 1e12:.2f}T"
            if v >= 1e9:  return f"${v / 1e9:.2f}B"
            if v >= 1e6:  return f"${v / 1e6:.2f}M"
            return f"${v:,.0f}"

        cap = _f("MarketCapitalization")
        return {
            "pe_ratio":       _f("PERatio"),
            "forward_pe":     _f("ForwardPE"),
            "eps":            _f("EPS"),
            "market_cap":     _fmt_cap(cap),
            "market_cap_raw": cap,
            "beta":           _f("Beta"),
            "week52_high":    _f("52WeekHigh"),
            "week52_low":     _f("52WeekLow"),
            "dividend_yield": _f("DividendYield"),
            "revenue_growth": _f("QuarterlyRevenueGrowthYOY"),
            "profit_margin":  _f("ProfitMargin"),
            "roe":            _f("ReturnOnEquityTTM"),
            "sector":         d.get("Sector") or None,
            "industry":       d.get("Industry") or None,
            "description":    (d.get("Description") or "")[:280] or None,
            "available":      True,
        }
    except Exception:
        return _EMPTY_FUNDAMENTALS


# ── Earnings (Finnhub) ─────────────────────────────────────────────────────────

async def fetch_stock_earnings(client: httpx.AsyncClient, symbol: str) -> dict:
    """Last 4 quarterly EPS beats/misses and next earnings date from Finnhub."""
    if not FINNHUB_KEY:
        return _EMPTY_EARNINGS

    try:
        hist_r, cal_r = await asyncio.gather(
            client.get(
                f"{FINNHUB_BASE}/stock/earnings",
                params={"symbol": symbol, "limit": 4, "token": FINNHUB_KEY},
                timeout=12,
            ),
            client.get(
                f"{FINNHUB_BASE}/calendar/earnings",
                params={"symbol": symbol, "from": _today(), "to": _date_plus(120), "token": FINNHUB_KEY},
                timeout=12,
            ),
        )
        hist  = hist_r.json() if hist_r.status_code == 200 else []
        cdata = cal_r.json()  if cal_r.status_code  == 200 else {}

        quarters: list[dict] = []
        beats = misses = 0
        for q in (hist or [])[:4]:
            actual   = q.get("actual")
            estimate = q.get("estimate")
            if actual is not None and estimate is not None and estimate != 0:
                try:
                    surprise_pct = round((actual - estimate) / abs(estimate) * 100, 1)
                    beat = actual >= estimate
                    if beat: beats  += 1
                    else:    misses += 1
                except (ZeroDivisionError, TypeError):
                    surprise_pct = None
                    beat = None
            else:
                surprise_pct = None
                beat = None

            quarters.append({
                "period":       q.get("period", ""),
                "actual":       actual,
                "estimate":     estimate,
                "surprise_pct": surprise_pct,
                "beat":         beat,
            })

        next_date = None
        cal_items = (cdata.get("earningsCalendar") or [])
        if cal_items:
            next_date = cal_items[0].get("date")

        return {
            "quarters":  quarters,
            "next_date": next_date,
            "beats":     beats,
            "misses":    misses,
            "available": len(quarters) > 0,
        }
    except Exception:
        return _EMPTY_EARNINGS


# ── Analyst Consensus (Finnhub) ───────────────────────────────────────────────

async def fetch_stock_analyst(client: httpx.AsyncClient, symbol: str) -> dict:
    """Buy/hold/sell rating counts and mean price target from Finnhub."""
    if not FINNHUB_KEY:
        return _EMPTY_ANALYST

    try:
        rec_r, pt_r = await asyncio.gather(
            client.get(
                f"{FINNHUB_BASE}/stock/recommendation",
                params={"symbol": symbol, "token": FINNHUB_KEY},
                timeout=12,
            ),
            client.get(
                f"{FINNHUB_BASE}/stock/price-target",
                params={"symbol": symbol, "token": FINNHUB_KEY},
                timeout=12,
            ),
        )
        recs = rec_r.json() if rec_r.status_code == 200 else []
        pt   = pt_r.json()  if pt_r.status_code  == 200 else {}

        if not recs:
            return _EMPTY_ANALYST

        latest = recs[0]
        sb = int(latest.get("strongBuy",   0) or 0)
        b  = int(latest.get("buy",         0) or 0)
        h  = int(latest.get("hold",        0) or 0)
        s  = int(latest.get("sell",        0) or 0)
        ss = int(latest.get("strongSell",  0) or 0)
        total = sb + b + h + s + ss
        if total == 0:
            return _EMPTY_ANALYST

        buy_pct  = (sb + b) / total
        sell_pct = (s + ss) / total
        consensus = (
            "Strong Buy" if buy_pct >= 0.6  else
            "Buy"        if buy_pct >= 0.4  else
            "Sell"       if sell_pct >= 0.4 else
            "Strong Sell"if sell_pct >= 0.6 else
            "Hold"
        )

        return {
            "strong_buy":        sb,
            "buy":               b,
            "hold":              h,
            "sell":              s,
            "strong_sell":       ss,
            "total":             total,
            "consensus":         consensus,
            "price_target_mean": pt.get("targetMean"),
            "price_target_high": pt.get("targetHigh"),
            "price_target_low":  pt.get("targetLow"),
            "upside_pct":        None,   # filled by route after price is known
            "period":            latest.get("period", ""),
            "available":         True,
        }
    except Exception:
        return _EMPTY_ANALYST


# ── Insider Transactions (Finnhub) ────────────────────────────────────────────

async def fetch_stock_insider(client: httpx.AsyncClient, symbol: str) -> dict:
    """Most recent insider buy/sell transactions from Finnhub (last 6 months)."""
    if not FINNHUB_KEY:
        return _EMPTY_INSIDER

    try:
        r = await client.get(
            f"{FINNHUB_BASE}/stock/insider-transactions",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json() or {}
        raw  = data.get("data") or []
        if not raw:
            return _EMPTY_INSIDER

        # Filter to only open-market purchases (P) and sales (S); sort newest first
        filtered = [
            x for x in raw
            if (x.get("transactionCode") or "").upper() in ("P", "S")
        ]
        filtered.sort(key=lambda x: x.get("transactionDate", ""), reverse=True)

        transactions: list[dict] = []
        buy_count = sell_count = net_shares = 0

        for tx in filtered[:6]:
            shares  = int(tx.get("share", 0) or 0)
            p_raw   = tx.get("transactionPrice")
            try: price = float(p_raw) if p_raw else None
            except (ValueError, TypeError): price = None
            value   = round(shares * price) if price and shares else None
            is_buy  = (tx.get("transactionCode") or "").upper() == "P"
            tx_type = "BUY" if is_buy else "SELL"

            if is_buy:  buy_count  += 1; net_shares += shares
            else:       sell_count += 1; net_shares -= shares

            transactions.append({
                "name":   tx.get("name", "Unknown"),
                "title":  (tx.get("officerTitle") or "")[:30],
                "type":   tx_type,
                "shares": shares,
                "price":  price,
                "value":  value,
                "date":   tx.get("transactionDate", ""),
            })

        return {
            "transactions": transactions,
            "buy_count":    buy_count,
            "sell_count":   sell_count,
            "net_shares":   net_shares,
            "available":    len(transactions) > 0,
        }
    except Exception:
        return _EMPTY_INSIDER


# ── Historical Returns vs SPY (Yahoo Finance) ─────────────────────────────────

async def fetch_stock_history(client: httpx.AsyncClient, symbol: str) -> dict:
    """5Y weekly prices from Yahoo Finance; computes 1M/3M/6M/1Y/2Y/5Y returns vs SPY."""
    try:
        stock_r, spy_r = await asyncio.gather(
            client.get(
                f"{YAHOO_BASE}/{symbol}",
                params={"interval": "1wk", "range": "5y"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            ),
            client.get(
                f"{YAHOO_BASE}/SPY",
                params={"interval": "1wk", "range": "5y"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            ),
        )

        stock_closes = _extract_closes(stock_r.json())
        spy_closes   = _extract_closes(spy_r.json())

        if len(stock_closes) < 10 or len(spy_closes) < 10:
            return _EMPTY_HISTORY

        def _ret(closes, n_weeks):
            if len(closes) < n_weeks + 1:
                return None
            start = closes[-(n_weeks + 1)]
            end   = closes[-1]
            if not start:
                return None
            return round((end - start) / abs(start) * 100, 1)

        periods = {"1M": 4, "3M": 13, "6M": 26, "1Y": 52, "2Y": 104, "5Y": 260}
        returns     = {k: _ret(stock_closes, v) for k, v in periods.items()}
        spy_returns = {k: _ret(spy_closes,   v) for k, v in periods.items()}
        vs_spy = {
            k: round(returns[k] - spy_returns[k], 1)
            if (returns[k] is not None and spy_returns[k] is not None) else None
            for k in periods
        }

        one_yr_vs = vs_spy.get("1Y")
        direction = (
            "up"   if (one_yr_vs is not None and one_yr_vs > 5)  else
            "down" if (one_yr_vs is not None and one_yr_vs < -5) else
            "neutral"
        )
        y1r = returns.get("1Y")
        if one_yr_vs is not None:
            label = (
                f"Outperforming SPY by {one_yr_vs:+.1f}% over 1Y"  if one_yr_vs > 0
                else f"Underperforming SPY by {abs(one_yr_vs):.1f}% over 1Y"
            )
        elif y1r is not None:
            label = f"1Y return: {y1r:+.1f}%"
        else:
            label = "Historical data available"

        return {
            "returns":     returns,
            "spy_returns": spy_returns,
            "vs_spy":      vs_spy,
            "direction":   direction,
            "label":       label,
            "available":   True,
        }
    except Exception:
        return _EMPTY_HISTORY


# ── Yahoo Finance base URLs + crumb-aware session helper ──────────────────────
_YF_SUMMARY  = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"
_YF_OPTIONS  = "https://query2.finance.yahoo.com/v7/finance/options"
_YF_HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://finance.yahoo.com",
    "Referer":         "https://finance.yahoo.com/",
}

# Module-level crumb cache — fetched once per process and reused across requests.
# Prevents race conditions when multiple providers run in parallel.
_YF_SESSION: dict[str, str | None] = {"crumb": None, "cookie": None}
_YF_SESSION_LOCK = asyncio.Lock()


async def _yf_ensure_session(client: httpx.AsyncClient) -> bool:
    """
    Fetch and cache Yahoo Finance crumb + cookie string once per process.
    Uses asyncio.Lock so parallel callers wait rather than all hitting fc.yahoo.com.
    Returns True if a valid session is now available.
    """
    if _YF_SESSION["crumb"]:
        return True

    async with _YF_SESSION_LOCK:
        if _YF_SESSION["crumb"]:   # re-check inside lock
            return True
        try:
            r1 = await client.get(
                "https://fc.yahoo.com",
                headers=_YF_HEADERS,
                follow_redirects=True,
                timeout=8,
            )
            # Merge cookies from response + client jar into a plain string
            merged = {**dict(client.cookies), **dict(r1.cookies)}
            cookie_str = "; ".join(f"{k}={v}" for k, v in merged.items())

            r2 = await client.get(
                "https://query2.finance.yahoo.com/v1/test/getcrumb",
                headers={**_YF_HEADERS, "Cookie": cookie_str},
                timeout=8,
            )
            if r2.status_code == 200 and r2.text.strip():
                _YF_SESSION["crumb"]  = r2.text.strip()
                _YF_SESSION["cookie"] = cookie_str
                return True
        except Exception:
            pass
    return False


async def _yf_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
) -> httpx.Response | None:
    """
    Fetch a Yahoo Finance URL with automatic crumb auth.
    Pass 1 – no crumb (still works on many IPs / endpoints).
    Pass 2 – full crumb + cookie session (required since 2024 for quoteSummary).
    The session is fetched once and cached at module level; no race conditions.
    """
    params = params or {}

    # ── Pass 1: plain request ────────────────────────────────────────────────
    try:
        r = await client.get(url, params=params, headers=_YF_HEADERS, timeout=12)
        if r.status_code == 200:
            data  = r.json()
            qs    = data.get("quoteSummary", {})
            oc    = data.get("optionChain",  {})
            has_data  = bool(qs.get("result") or oc.get("result"))
            has_error = bool(qs.get("error")  or oc.get("error"))
            if has_data and not has_error:
                return r
    except Exception:
        pass

    # ── Pass 2: crumb session ────────────────────────────────────────────────
    if not await _yf_ensure_session(client):
        return None
    try:
        r = await client.get(
            url,
            params={**params, "crumb": _YF_SESSION["crumb"]},
            headers={**_YF_HEADERS, "Cookie": _YF_SESSION["cookie"]},
            timeout=12,
        )
        return r if r.status_code == 200 else None
    except Exception:
        return None


# ── Short Interest  (Finnhub → Yahoo Finance) ─────────────────────────────────

def _si_build(pct: float, dtc: float | None, source: str) -> dict:
    signal = "high" if pct > 20 else "moderate" if pct > 10 else "low"
    return {
        "short_percent": pct,
        "days_to_cover": dtc,
        "signal":        signal,
        "squeeze_risk":  pct > 20,
        "source":        source,
        "available":     True,
    }


async def _si_finnhub(client: httpx.AsyncClient, symbol: str) -> dict:
    if not FINNHUB_KEY:
        return _EMPTY_SHORT_INTEREST
    try:
        r = await client.get(
            f"{FINNHUB_BASE}/stock/short-interest",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=12,
        )
        if r.status_code != 200:
            return _EMPTY_SHORT_INTEREST
        items = (r.json() or {}).get("data") or []
        if not items:
            return _EMPTY_SHORT_INTEREST

        latest = items[0]
        def _n(k):
            v = latest.get(k)
            try: return float(v) if v is not None else None
            except: return None

        pct = _n("shortPercent")
        if pct is not None and pct <= 1.0:
            pct = round(pct * 100, 2)
        if pct is None:
            return _EMPTY_SHORT_INTEREST

        dtc = _n("daysToCover") or _n("daysTocover")
        return _si_build(pct, dtc, "Finnhub")
    except Exception:
        return _EMPTY_SHORT_INTEREST


async def _si_yahoo(client: httpx.AsyncClient, symbol: str) -> dict:
    try:
        r = await _yf_get(
            client, f"{_YF_SUMMARY}/{symbol}",
            {"modules": "defaultKeyStatistics"},
        )
        if r is None:
            return _EMPTY_SHORT_INTEREST
        stats = (
            (r.json() or {})
            .get("quoteSummary", {})
            .get("result", [{}])[0]
            .get("defaultKeyStatistics", {})
        )

        def _rv(k):
            v = stats.get(k, {})
            raw = v.get("raw") if isinstance(v, dict) else v
            try: return float(raw) if raw is not None else None
            except: return None

        pct = _rv("shortPercentOfFloat")
        if pct is not None:
            pct = round(pct * 100, 2)   # decimal → %
        if pct is None:
            return _EMPTY_SHORT_INTEREST

        dtc = _rv("shortRatio")         # Yahoo "short ratio" = days to cover
        return _si_build(pct, dtc, "Yahoo Finance")
    except Exception:
        return _EMPTY_SHORT_INTEREST


async def fetch_short_interest(client: httpx.AsyncClient, symbol: str) -> dict:
    """Short % float and days-to-cover. Waterfall: Finnhub → Yahoo Finance."""
    if FINNHUB_KEY:
        r = await _si_finnhub(client, symbol)
        if r.get("available"):
            return r
    return await _si_yahoo(client, symbol)


# ── Institutional Ownership  (Finnhub → Yahoo Finance) ───────────────────────

async def _inst_finnhub(client: httpx.AsyncClient, symbol: str) -> dict:
    if not FINNHUB_KEY:
        return _EMPTY_INSTITUTIONAL
    try:
        r = await client.get(
            f"{FINNHUB_BASE}/institutional/ownership",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=12,
        )
        if r.status_code != 200:
            return _EMPTY_INSTITUTIONAL
        raw = (r.json() or {}).get("ownership") or []
        if not raw:
            return _EMPTY_INSTITUTIONAL

        raw.sort(key=lambda x: float(x.get("percent") or 0), reverse=True)
        top20      = raw[:20]
        buy_count  = sum(1 for h in top20 if (h.get("change") or 0) > 0)
        sell_count = sum(1 for h in top20 if (h.get("change") or 0) < 0)

        signal = (
            "accumulation" if buy_count > sell_count * 1.5 else
            "distribution" if sell_count > buy_count * 1.5 else
            "neutral"
        )
        top3 = [
            {
                "name":    (h.get("holder") or "Unknown")[:40],
                "percent": float(h.get("percent") or 0),
                "change":  int(h.get("change") or 0),
            }
            for h in raw[:3]
        ]
        return {
            "top_holders": top3,
            "buy_count":   buy_count,
            "sell_count":  sell_count,
            "signal":      signal,
            "source":      "Finnhub",
            "available":   True,
        }
    except Exception:
        return _EMPTY_INSTITUTIONAL


async def _inst_yahoo(client: httpx.AsyncClient, symbol: str) -> dict:
    """
    Yahoo Finance institutionOwnership gives current holdings only (no QoQ change).
    buy_count/sell_count cannot be determined; signal defaults to 'neutral'.
    """
    try:
        r = await _yf_get(
            client, f"{_YF_SUMMARY}/{symbol}",
            {"modules": "institutionOwnership"},
        )
        if r is None:
            return _EMPTY_INSTITUTIONAL
        owners = (
            (r.json() or {})
            .get("quoteSummary", {})
            .get("result", [{}])[0]
            .get("institutionOwnership", {})
            .get("ownershipList") or []
        )
        if not owners:
            return _EMPTY_INSTITUTIONAL

        def _rv(obj, k):
            v = obj.get(k, {})
            return v.get("raw") if isinstance(v, dict) else v

        # Sort by pctHeld descending
        owners.sort(key=lambda x: float(_rv(x, "pctHeld") or 0), reverse=True)

        top3 = [
            {
                "name":    (o.get("organization") or "Unknown")[:40],
                "percent": round(float(_rv(o, "pctHeld") or 0) * 100, 2),
                "change":  0,  # not available from Yahoo
            }
            for o in owners[:3]
        ]
        return {
            "top_holders": top3,
            "buy_count":   0,
            "sell_count":  0,
            "signal":      "neutral",   # direction unknown without change data
            "source":      "Yahoo Finance",
            "available":   True,
        }
    except Exception:
        return _EMPTY_INSTITUTIONAL


async def fetch_institutional_ownership(client: httpx.AsyncClient, symbol: str) -> dict:
    """Top institutional holders. Waterfall: Finnhub → Yahoo Finance."""
    if FINNHUB_KEY:
        r = await _inst_finnhub(client, symbol)
        if r.get("available"):
            return r
    return await _inst_yahoo(client, symbol)


# ── Options Sentiment / Put-Call Ratio  (Finnhub → Yahoo Finance) ─────────────

def _opt_build(total_put: int, total_call: int, source: str) -> dict:
    if total_call == 0:
        return _EMPTY_OPTIONS_SENT
    ratio = round(total_put / total_call, 2)
    if ratio >= 1.5:
        signal, label = "extreme_fear", "Extreme Fear (>1.5)"
    elif ratio >= 1.0:
        signal, label = "bearish",      "Bearish (1.0-1.5)"
    elif ratio >= 0.7:
        signal, label = "neutral",      "Neutral (0.7-1.0)"
    else:
        signal, label = "bullish",      "Bullish (<0.7)"
    return {
        "put_oi":   total_put,
        "call_oi":  total_call,
        "ratio":    ratio,
        "signal":   signal,
        "label":    label,
        "source":   source,
        "available": True,
    }


async def _opt_finnhub(client: httpx.AsyncClient, symbol: str) -> dict:
    if not FINNHUB_KEY:
        return _EMPTY_OPTIONS_SENT
    try:
        r = await client.get(
            f"{FINNHUB_BASE}/stock/option-chain",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=15,
        )
        if r.status_code != 200:
            return _EMPTY_OPTIONS_SENT
        expirations = (r.json() or {}).get("data") or []
        if not expirations:
            return _EMPTY_OPTIONS_SENT

        total_call = total_put = 0
        for exp in expirations:
            opts = exp.get("options") or {}
            for c in (opts.get("CALL") or []):
                total_call += int(c.get("openInterest") or 0)
            for p in (opts.get("PUT") or []):
                total_put  += int(p.get("openInterest") or 0)

        return _opt_build(total_put, total_call, "Finnhub")
    except Exception:
        return _EMPTY_OPTIONS_SENT


async def _opt_yahoo(client: httpx.AsyncClient, symbol: str) -> dict:
    """
    Yahoo Finance /v7/finance/options.
    openInterest is often 0 on Yahoo (removed 2024); falls back to volume.
    Put/call volume ratio is equally valid (used by CBOE for their daily P/C index).
    Fetches nearest expiry + up to 5 monthly expirations for a broader sample.
    """
    def _sum_chain(options_list: list[dict]) -> tuple[int, int]:
        """Sum options activity: prefer openInterest, fall back to volume."""
        calls = puts = 0
        for grp in options_list:
            for c in (grp.get("calls") or []):
                oi  = int(c.get("openInterest") or 0)
                vol = int(c.get("volume")       or 0)
                calls += oi if oi > 0 else vol
            for p in (grp.get("puts") or []):
                oi  = int(p.get("openInterest") or 0)
                vol = int(p.get("volume")       or 0)
                puts += oi if oi > 0 else vol
        return calls, puts

    try:
        r = await _yf_get(client, f"{_YF_OPTIONS}/{symbol}")
        if r is None:
            return _EMPTY_OPTIONS_SENT
        result = (r.json() or {}).get("optionChain", {}).get("result", [{}])[0]
        if not result:
            return _EMPTY_OPTIONS_SENT

        total_call, total_put = _sum_chain(result.get("options") or [])

        # Fetch up to 5 additional expirations (skip first already fetched)
        extra_dates = (result.get("expirationDates") or [])[1:6]
        if extra_dates:
            tasks = [
                _yf_get(client, f"{_YF_OPTIONS}/{symbol}", {"date": str(ts)})
                for ts in extra_dates
            ]
            resps = await asyncio.gather(*tasks, return_exceptions=True)
            for resp in resps:
                if not resp or isinstance(resp, Exception):
                    continue
                sub = (resp.json() or {}).get("optionChain", {}).get("result", [{}])[0]
                c, p = _sum_chain(sub.get("options") or [])
                total_call += c
                total_put  += p

        return _opt_build(total_put, total_call, "Yahoo Finance")
    except Exception:
        return _EMPTY_OPTIONS_SENT


async def fetch_options_sentiment(client: httpx.AsyncClient, symbol: str) -> dict:
    """Put/call OI ratio. Waterfall: Finnhub → Yahoo Finance."""
    if FINNHUB_KEY:
        r = await _opt_finnhub(client, symbol)
        if r.get("available"):
            return r
    return await _opt_yahoo(client, symbol)


# ── Sector Relative Performance (Yahoo Finance) ───────────────────────────────

async def fetch_sector_performance(client: httpx.AsyncClient, sector: str | None) -> dict:
    """1-month return for the corresponding sector ETF from Yahoo Finance."""
    etf = get_sector_etf(sector)
    try:
        r = await client.get(
            f"{YAHOO_BASE}/{etf}",
            params={"interval": "1d", "range": "2mo"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        closes = _extract_closes(r.json())
        if len(closes) < 5:
            return {**_EMPTY_SECTOR_PERF, "etf": etf}

        n = min(21, len(closes) - 1)   # ~1 month trading days
        start = closes[-(n + 1)]
        end   = closes[-1]
        etf_1m = round((end - start) / abs(start) * 100, 1) if start else None

        return {
            "etf":      etf,
            "etf_1m":   etf_1m,
            "signal":   "neutral",
            "label":    f"{etf}: {etf_1m:+.1f}% (1M)" if etf_1m is not None else f"{etf}: N/A",
            "available": etf_1m is not None,
        }
    except Exception:
        return {**_EMPTY_SECTOR_PERF, "etf": etf}


def _extract_closes(data: dict) -> list[float]:
    try:
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]
    except (KeyError, IndexError, TypeError):
        return []


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _date_plus(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            sym = "AAPL"
            fund, earn, ana, ins, hist = await asyncio.gather(
                fetch_stock_fundamentals(c, sym),
                fetch_stock_earnings(c, sym),
                fetch_stock_analyst(c, sym),
                fetch_stock_insider(c, sym),
                fetch_stock_history(c, sym),
            )
            import json
            for name, val in [("Fundamentals", fund), ("Earnings", earn),
                               ("Analyst", ana), ("Insider", ins), ("History", hist)]:
                print(f"\n{'='*40}\n{name}:\n{json.dumps(val, indent=2)}")
    asyncio.run(_test())
