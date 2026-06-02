"""
Stock-specific data providers:
  - Fundamentals:  Alpha Vantage OVERVIEW (P/E, EPS, Market Cap, Beta, etc.)
  - Earnings:      Finnhub /stock/earnings (last 4 quarters) + /calendar/earnings (next date)
  - Analyst:       Finnhub /stock/recommendation + /stock/price-target
  - Insider:       Finnhub /stock/insider-transactions
  - History:       Yahoo Finance 5Y weekly vs SPY (1M/3M/6M/1Y/2Y/5Y returns)
Run directly: python -m app.providers.stock_info
"""
import asyncio
from datetime import datetime, timedelta

import httpx

from app.config import (
    ALPHA_VANTAGE_KEY, FINNHUB_KEY,
    AV_BASE, FINNHUB_BASE, YAHOO_BASE,
)

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
