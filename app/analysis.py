"""
Alignment score computation -- v3.
Weights (forex): daily(25) + hourly(20) + intermarket(18) + institutional(15) + sentiment(12) + events(10) = 100
Weights (stock): daily(22) + hourly(18) + fundamental(14) + analyst(11) + institutional_ownership(8)
                 + sentiment(9) + historical(9) + earnings(9) = 100
                 plus short-interest modifier +-3 pts (clamped to 100).
Run directly: python -m app.analysis
"""
from datetime import date as _date


def _vote(d: str) -> int:
    return 1 if d == "up" else -1 if d == "down" else 0


# ── Asset-to-country mapping ──────────────────────────────────────────────────
# Maps currency codes to the Finnhub country codes used in economic calendar events.
# Finnhub uses ISO 3166-1 alpha-2 codes (US, GB, DE, JP, etc.).
# EUR covers all major Eurozone economies since any ECB / EU-wide event
# can be filed under any of these country codes.

_CURRENCY_COUNTRIES: dict[str, list[str]] = {
    "USD": ["US"],
    "EUR": ["EU", "DE", "FR", "IT", "ES", "PT", "NL", "BE", "AT", "GR", "FI", "IE", "LU"],
    "GBP": ["GB", "UK"],
    "JPY": ["JP"],
    "CHF": ["CH"],
    "CAD": ["CA"],
    "AUD": ["AU"],
    "NZD": ["NZ"],
    "CNY": ["CN"],
    "HKD": ["HK"],
    "SGD": ["SG"],
    "SEK": ["SE"],
    "NOK": ["NO"],
    "DKK": ["DK"],
    "MXN": ["MX"],
    "ZAR": ["ZA"],
    "TRY": ["TR"],
    "BRL": ["BR"],
    "INR": ["IN"],
    "RUB": ["RU"],
    "PLN": ["PL"],
    "HUF": ["HU"],
    "CZK": ["CZ"],
    "KRW": ["KR"],
    "TWD": ["TW"],
    "THB": ["TH"],
    "IDR": ["ID"],
    "MYR": ["MY"],
    "PHP": ["PH"],
    "CLP": ["CL"],
    "COP": ["CO"],
    "ARS": ["AR"],
    "PEN": ["PE"],
    "ILS": ["IL"],
    "SAR": ["SA"],
    "AED": ["AE"],
    "QAR": ["QA"],
}

# Stock exchanges mapped to their country code(s)
_EXCHANGE_COUNTRIES: dict[str, list[str]] = {
    "NASDAQ": ["US"],
    "NYSE":   ["US"],
    "US":     ["US"],
    "LSE":    ["GB", "UK"],
    "XETRA":  ["DE"],
    "EURONEXT": ["FR", "NL", "BE", "PT"],
    "TSE":    ["JP"],
    "SSE":    ["CN"],
    "SZSE":   ["CN"],
    "BSE":    ["IN"],
    "NSE":    ["IN"],
    "ASX":    ["AU"],
    "TSX":    ["CA"],
    "HKEX":   ["HK"],
    "KRX":    ["KR"],
    "DEFAULT": ["US"],
}

# Event priority score — higher = more market-moving
# Used to pick the SINGLE most critical risk from the filtered list.
_EVENT_PRIORITY: dict[str, int] = {
    # Tier 1 — Monetary policy (most market-moving)
    "interest rate":      100,
    "rate decision":      100,
    "central bank":       100,
    "fed funds":          100,
    "fomc":               100,
    "ecb":                95,
    "boe":                95,
    "rba":                95,
    "rbnz":               95,
    "boj":                95,
    "snb":                95,
    "boc":                95,
    "monetary policy":    90,

    # Tier 2 — Inflation & Labour (second most market-moving)
    "cpi":                85,
    "consumer price":     85,
    "pce":                85,
    "inflation":          82,
    "non-farm":           85,
    "nonfarm":            85,
    "employment change":  80,
    "unemployment rate":  78,
    "jobs":               75,
    "labour":             75,
    "labor":              75,
    "payroll":            80,

    # Tier 3 — Growth
    "gdp":                75,
    "gross domestic":     75,

    # Tier 4 — Activity indicators
    "retail sales":       60,
    "industrial production": 58,
    "manufacturing":      55,
    "pmi":                55,
    "ism":                55,
    "trade balance":      50,
    "current account":    48,
    "housing":            45,
    "building permits":   43,
    "consumer confidence": 42,
    "business confidence": 40,
    "sentiment":          38,
}


def _event_priority_score(event_name: str) -> int:
    """Return the priority score for an event name (higher = more critical)."""
    name_lower = (event_name or "").lower()
    best = 0
    for keyword, score in _EVENT_PRIORITY.items():
        if keyword in name_lower and score > best:
            best = score
    return best


def _asset_countries(symbol: str, asset_type: str) -> set[str]:
    """
    Return the set of relevant Finnhub country codes for the given asset.
    For forex: map both currencies.
    For stocks: default to US (can be extended with exchange detection).
    """
    if asset_type == "forex":
        parts = symbol.upper().replace("-", "/").split("/")
        codes: set[str] = set()
        for currency in parts:
            for country in _CURRENCY_COUNTRIES.get(currency, []):
                codes.add(country.upper())
        return codes
    else:
        # For stocks we default to US; caller can pass exchange info via symbol prefix
        return set(_EXCHANGE_COUNTRIES.get("DEFAULT", ["US"]))


def _filter_and_rank_events(events: list, relevant_countries: set[str]) -> list[dict]:
    """
    1. Discard events from countries NOT in relevant_countries.
    2. Among remaining events, sort by: impact level first, then priority score.
    Returns filtered + ranked list.
    """
    filtered = []
    for ev in events:
        country = str(ev.get("country") or "").upper().strip()
        if country not in relevant_countries:
            continue
        priority = _event_priority_score(ev.get("event", ""))
        impact   = str(ev.get("impact", "")).lower()
        impact_w = 1000 if impact in ("high", "3") else 500 if impact in ("medium", "2") else 0
        filtered.append({**ev, "_sort_key": impact_w + priority})

    filtered.sort(key=lambda x: x["_sort_key"], reverse=True)
    return filtered


# ── Key signal finder ─────────────────────────────────────────────────────────

def _find_key_signal(daily: dict, hourly: dict, cot: dict, sentiment: dict) -> dict:
    candidates: list[dict] = []

    # RSI extremes (strongest signal)
    if daily["rsi"] < 30:
        candidates.append({"text": f"Daily RSI Oversold ({daily['rsi']:.0f})", "direction": "up", "strength": 3})
    elif daily["rsi"] > 70:
        candidates.append({"text": f"Daily RSI Overbought ({daily['rsi']:.0f})", "direction": "down", "strength": 3})

    # MACD aligned across both timeframes
    if daily["macd_above_signal"] and hourly["macd_above_signal"]:
        candidates.append({"text": "MACD Bullish on Daily + Hourly", "direction": "up", "strength": 2})
    elif not daily["macd_above_signal"] and not hourly["macd_above_signal"]:
        candidates.append({"text": "MACD Bearish on Daily + Hourly", "direction": "down", "strength": 2})

    # Large COT positioning
    if cot.get("available") and abs(cot.get("net", 0)) > 40000:
        eff  = cot.get("effective_net", cot.get("net", 0))
        pos  = "Long" if cot["net"] > 0 else "Short"
        cur  = cot.get("currency", "")
        candidates.append({
            "text":      f"Institutions {pos} {cur} ({cot['net']:+,})",
            "direction": "up" if eff > 0 else "down",
            "strength":  2,
        })

    # Trend aligned on both timeframes
    if daily["trend"] == hourly["trend"] and daily["trend"] != "neutral":
        candidates.append({
            "text":      f"Trend Aligned {daily['trend'].upper()} (Daily + Hourly)",
            "direction": daily["trend"],
            "strength":  1,
        })

    # Strong sentiment
    score = sentiment.get("score", 0.0) if isinstance(sentiment, dict) else 0.0
    if score > 0.3:
        candidates.append({"text": f"Strong Bullish Sentiment ({score:.2f})", "direction": "up", "strength": 1})
    elif score < -0.3:
        candidates.append({"text": f"Strong Bearish Sentiment ({score:.2f})", "direction": "down", "strength": 1})

    if not candidates:
        return {"text": "No dominant signal", "direction": "neutral"}
    return {"text": best["text"], "direction": best["direction"]} if (best := max(candidates, key=lambda x: x["strength"])) else {"text": "No dominant signal", "direction": "neutral"}


# ── Main risk finder ──────────────────────────────────────────────────────────

def _find_main_risk(
    events: list,
    daily: dict,
    sentiment: dict,
    cot: dict,
    symbol: str = "",
    asset_type: str = "forex",
) -> str:
    """
    Identify the single most critical risk for this specific asset.

    Step 1: Map asset to relevant countries (e.g. EUR/USD -> EU countries + US only).
    Step 2: Discard ALL events from other countries (strict exclusion).
    Step 3: From filtered events, pick the highest-priority one.
    Step 4: Fall back to technical/macro risks if no relevant event found.
    """
    # Determine which countries are relevant for this asset
    relevant = _asset_countries(symbol, asset_type)

    # Filter and rank events by relevance + priority
    ranked = _filter_and_rank_events(events, relevant)

    # Use the top-ranked event if it's high-impact
    if ranked:
        top = ranked[0]
        impact = str(top.get("impact", "")).lower()
        name   = top.get("event", "event")
        cc     = top.get("country", "")
        if impact in ("high", "3"):
            return f"{name} ({cc})"
        # Medium-impact only if it scores highly (central bank, CPI, GDP)
        if top.get("_sort_key", 0) >= 500 + 75:
            return f"{name} ({cc})"

    # No calendar risk — fall back to technical / positioning warnings
    if daily["rsi"] > 75:
        return f"Daily RSI Extreme Overbought ({daily['rsi']:.0f}) -- reversal risk"
    if daily["rsi"] < 25:
        return f"Daily RSI Extreme Oversold ({daily['rsi']:.0f}) -- reversal risk"

    if (cot.get("available") and cot.get("weeks_trend") == "decreasing"
            and abs(cot.get("net", 0)) > 30000):
        return "Institutional positioning reducing -- potential trend shift"

    sent_lbl = sentiment.get("label", "neutral") if isinstance(sentiment, dict) else "neutral"
    if sent_lbl == "bearish" and daily["direction"] == "up":
        return "Bearish news sentiment conflicts with bullish technical bias"
    if sent_lbl == "bullish" and daily["direction"] == "down":
        return "Bullish news sentiment conflicts with bearish technical bias"

    if relevant and ranked:
        # There are medium-impact events for this pair
        top = ranked[0]
        return f"{top.get('event', 'event')} ({top.get('country', '')}) -- medium impact"

    return "No major macroeconomic risk detected for this asset"


# ── Conflict detector ─────────────────────────────────────────────────────────

def _detect_conflicts(daily: dict, hourly: dict, sentiment: dict, cot: dict) -> dict:
    # Timeframe conflict
    tf_conflict = (
        daily["direction"] != "neutral" and
        hourly["direction"] != "neutral" and
        daily["direction"] != hourly["direction"]
    )

    # Macro vs technical conflict
    tech_dir = daily["direction"]
    sent_lbl = sentiment.get("label", "neutral") if isinstance(sentiment, dict) else "neutral"
    sent_dir = "up" if sent_lbl == "bullish" else "down" if sent_lbl == "bearish" else "neutral"
    cot_dir  = cot.get("direction", "neutral") if isinstance(cot, dict) else "neutral"

    macro_conflict = (
        (sent_dir != "neutral" and tech_dir != "neutral" and sent_dir != tech_dir) or
        (cot_dir  != "neutral" and tech_dir != "neutral" and cot_dir  != tech_dir)
    )

    badges: list[dict] = []
    if tf_conflict:
        badges.append({
            "label": "TF Conflict",
            "type":  "warning",
            "tip":   f"Daily trend is {daily['direction'].upper()} but Hourly trend is {hourly['direction'].upper()}. Mixed signals -- lower confidence.",
        })
    if macro_conflict:
        badges.append({
            "label": "Macro Conflict",
            "type":  "warning",
            "tip":   "News sentiment or institutional positioning contradicts the technical direction. Extra caution advised.",
        })

    return {
        "timeframe_conflict":      tf_conflict,
        "macro_technical_conflict": macro_conflict,
        "badges":                  badges,
    }


# ── Main function ─────────────────────────────────────────────────────────────

def compute_alignment(
    hourly:       dict,
    daily:        dict,
    intermarket:  dict,
    sentiment:    dict,
    cot:          dict,
    events:       list,
    asset_type:   str,
    ichimoku:     dict | None = None,
    volume:       dict | None = None,
    weekly_bias:  str = "neutral",
    symbol:       str = "",
) -> dict:
    """
    Point allocation (forex):
        Daily technical   25 pts
        Hourly technical  20 pts
        Intermarket       18 pts  (forex only)
        Institutional COT 15 pts  (forex only)
        Sentiment         12 pts
        Event clarity     10 pts
        Ichimoku          10 pts
        Volume confirm     5 pts
        Weekly bias        8 pts (direction vote only)
        Total            113 pts (forex), 80 pts (stock)

    Stocks: max_raw = 80, rescaled to 100.
    """
    daily_pts  = daily["strength"]  * 25
    hourly_pts = hourly["strength"] * 20

    # Intermarket direction (forex only)
    im = intermarket if isinstance(intermarket, dict) else {}
    dollar = im.get("dollar", "n/a")
    if dollar == "weakening":
        inter_dir = "up"
    elif dollar == "strengthening":
        inter_dir = "down"
    else:
        inter_dir = "neutral"
    inter_pts = 18.0 if asset_type == "forex" and inter_dir != "neutral" else 0.0

    # COT institutional (forex only)
    ct      = cot if isinstance(cot, dict) else {}
    cot_dir = ct.get("direction", "neutral")
    cot_pts = 15.0 if (asset_type == "forex" and ct.get("available") and cot_dir != "neutral") else 0.0

    # Sentiment
    snt      = sentiment if isinstance(sentiment, dict) else {}
    s        = snt.get("score", 0.0)
    sent_dir = "up" if s > 0 else "down" if s < 0 else "neutral"
    sent_pts = min(abs(s) / 0.5, 1.0) * 12

    # Event clarity
    high_ev   = sum(1 for e in events if str(e.get("impact", "")).lower() in ("high", "3"))
    weight    = 1.0 if asset_type == "forex" else 0.4
    event_pts = (1 - min(high_ev * weight, 3) / 3) * 10

    # Ichimoku (replaces/supplements intermarket for direction voting)
    ichi     = ichimoku if isinstance(ichimoku, dict) else {}
    ichi_dir = ichi.get("direction", "neutral")
    ichi_str = float(ichi.get("strength", 0))
    ichi_pts = ichi_str * 10 if asset_type == "forex" else ichi_str * 8   # 0-10 pts

    # Volume confirmation (modifier)
    vol_data = volume if isinstance(volume, dict) else {}
    vol_sig  = vol_data.get("signal", "neutral")
    vol_pts  = 0.0

    # Determine bias direction for volume confirmation check
    _inter_w = 18 if asset_type == "forex" else 0
    _cot_w   = 15 if asset_type == "forex" else 0
    _net_prelim = (
        _vote(daily["direction"])  * 25 +
        _vote(hourly["direction"]) * 20 +
        _vote(inter_dir)           * _inter_w +
        _vote(cot_dir)             * _cot_w +
        _vote(sent_dir)            * 12
    )
    _bias_prelim = "up" if _net_prelim > 5 else "down" if _net_prelim < -5 else "unclear"

    if vol_data.get("available"):
        if vol_sig == "bullish" and _vote(_bias_prelim) > 0:
            vol_pts = 5.0
        elif vol_sig == "bearish" and _vote(_bias_prelim) < 0:
            vol_pts = 5.0
        elif vol_data.get("divergence") != "none":
            vol_pts = 2.0

    # Direction vote (weighted)
    inter_w = 18 if asset_type == "forex" else 0
    cot_w   = 15 if asset_type == "forex" else 0
    net = (
        _vote(daily["direction"])  * 25 +
        _vote(hourly["direction"]) * 20 +
        _vote(inter_dir)           * inter_w +
        _vote(cot_dir)             * cot_w +
        _vote(sent_dir)            * 12 +
        _vote(ichi_dir)            * 10 +
        _vote(vol_sig)             *  5 +
        _vote(weekly_bias)         *  8
    )
    bias = "up" if net > 5 else "down" if net < -5 else "unclear"

    # Normalise
    raw     = daily_pts + hourly_pts + inter_pts + cot_pts + sent_pts + event_pts + ichi_pts + vol_pts
    max_pts = 113.0 if asset_type == "forex" else 80.0
    score   = min(int(round(raw / max_pts * 100)), 100)

    # Key signal, main risk, conflicts
    key_signal = _find_key_signal(daily, hourly, ct, snt)
    main_risk  = _find_main_risk(events, daily, snt, ct, symbol=symbol, asset_type=asset_type)
    conflicts  = _detect_conflicts(daily, hourly, snt, ct)

    return {
        "alignment_score": score,
        "bias":            bias,
        "key_signal":      key_signal,
        "main_risk":       main_risk,
        "conflicts":       conflicts,
        "components": {
            "daily_technical":  {"points": round(daily_pts, 1),  "max": 25, "direction": daily["direction"]},
            "hourly_technical": {"points": round(hourly_pts, 1), "max": 20, "direction": hourly["direction"]},
            "intermarket":      {
                "points": round(inter_pts, 1), "max": 18,
                "direction": inter_dir, "dollar": dollar,
            },
            "institutional":    {
                "points":      round(cot_pts, 1), "max": 15,
                "direction":   cot_dir,
                "net":         ct.get("net", 0),
                "label":       ct.get("label", "No Data"),
                "weeks_trend": ct.get("weeks_trend", "unknown"),
                "available":   ct.get("available", False),
            },
            "sentiment":        {
                "points":        round(sent_pts, 1), "max": 12,
                "direction":     sent_dir,
                "label":         snt.get("label", "neutral"),
                "articles":      snt.get("article_count", 0),
                "headlines":     snt.get("headlines", []),
            },
            "event_clarity":    {"points": round(event_pts, 1), "max": 10, "high_impact": high_ev},
            "ichimoku":         {
                "points":         round(ichi_pts, 1), "max": 10, "direction": ichi_dir,
                "cloud_position": ichi.get("cloud_position"),
                "tk_cross":       ichi.get("tk_cross"),
                "available":      ichi.get("available", False),
            },
            "volume_confirmation": {
                "points":    round(vol_pts, 1), "max": 5,
                "signal":    vol_sig,
                "divergence": vol_data.get("divergence", "none"),
                "vol_ratio": vol_data.get("vol_ratio"),
                "available": vol_data.get("available", False),
            },
        },
    }


# ── Stock scoring helpers ─────────────────────────────────────────────────────

def _score_fundamentals(fund: dict) -> tuple[float, str]:
    """Returns (points 0-14, direction) from P/E, revenue growth, profit margin."""
    if not fund.get("available"):
        return 7.0, "neutral"

    signals: list[float] = []

    pe = fund.get("pe_ratio")
    if pe is not None and pe > 0:
        if   pe < 12:  signals.append( 1.0)
        elif pe < 20:  signals.append( 0.6)
        elif pe < 30:  signals.append( 0.1)
        elif pe < 40:  signals.append(-0.3)
        else:          signals.append(-0.6)

    rev = fund.get("revenue_growth")
    if rev is not None:
        if   rev > 0.20:  signals.append( 1.0)
        elif rev > 0.08:  signals.append( 0.5)
        elif rev > 0.00:  signals.append( 0.15)
        elif rev > -0.05: signals.append(-0.2)
        else:             signals.append(-0.8)

    pm = fund.get("profit_margin")
    if pm is not None:
        if   pm > 0.20:  signals.append( 1.0)
        elif pm > 0.10:  signals.append( 0.5)
        elif pm > 0.00:  signals.append( 0.1)
        else:            signals.append(-0.7)

    if not signals:
        return 7.0, "neutral"

    avg = sum(signals) / len(signals)
    pts = max(0.0, min(14.0, (avg + 1.0) / 2.0 * 14.0))
    direction = "up" if avg > 0.15 else "down" if avg < -0.15 else "neutral"
    return round(pts, 1), direction


def _score_analyst_consensus(analyst: dict) -> tuple[float, str]:
    """Returns (points 0-11, direction) from buy/hold/sell ratio."""
    if not analyst.get("available") or not analyst.get("total"):
        return 0.0, "neutral"

    total    = analyst["total"]
    buy_pct  = (analyst.get("strong_buy", 0) + analyst.get("buy",        0)) / total
    sell_pct = (analyst.get("strong_sell",0) + analyst.get("sell",       0)) / total
    score    = buy_pct - sell_pct
    pts      = max(0.0, min(11.0, (score + 1.0) / 2.0 * 11.0))
    direction = "up" if score > 0.1 else "down" if score < -0.1 else "neutral"
    return round(pts, 1), direction


def _score_historical_trend(history: dict) -> tuple[float, str]:
    """Returns (points 0-9, direction) from 1Y performance vs SPY."""
    if not history.get("available"):
        return 4.5, "neutral"

    vs_1y  = history.get("vs_spy",    {}).get("1Y")
    ret_1y = history.get("returns",   {}).get("1Y")
    val    = vs_1y if vs_1y is not None else ret_1y
    if val is None:
        return 4.5, "neutral"

    if   val > 20:  pts, direction = 9.0, "up"
    elif val > 10:  pts, direction = 7.2, "up"
    elif val > 3:   pts, direction = 5.9, "up"
    elif val > -3:  pts, direction = 4.5, "neutral"
    elif val > -10: pts, direction = 2.7, "down"
    elif val > -20: pts, direction = 1.4, "down"
    else:           pts, direction = 0.0, "down"
    return pts, direction


def _score_earnings_quality(earnings: dict) -> tuple[float, str]:
    """Returns (points 0-9, direction) from EPS beat/miss record."""
    if not earnings.get("available"):
        return 4.5, "neutral"

    beats  = earnings.get("beats",  0)
    misses = earnings.get("misses", 0)
    total  = beats + misses
    if total == 0:
        return 4.5, "neutral"

    beat_ratio = beats / total
    if   beat_ratio >= 1.0:  pts, direction = 9.0, "up"
    elif beat_ratio >= 0.75: pts, direction = 6.8, "up"
    elif beat_ratio >= 0.5:  pts, direction = 4.5, "neutral"
    elif beat_ratio >= 0.25: pts, direction = 2.3, "down"
    else:                    pts, direction = 0.0, "down"
    return pts, direction


def _score_institutional_ownership(institutional: dict) -> tuple[float, str]:
    """Returns (points 0-8, direction) from institutional accumulation/distribution."""
    if not institutional.get("available"):
        return 4.0, "neutral"

    buy_ct  = institutional.get("buy_count",  0)
    sell_ct = institutional.get("sell_count", 0)
    total   = buy_ct + sell_ct
    if total == 0:
        return 4.0, "neutral"

    buy_pct = buy_ct / total
    if   buy_pct >= 0.70: return 8.0, "up"
    elif buy_pct >= 0.55: return 6.0, "up"
    elif buy_pct >= 0.45: return 4.0, "neutral"
    elif buy_pct >= 0.30: return 2.0, "down"
    else:                 return 0.0, "down"


def _short_interest_modifier(short_interest: dict, daily_direction: str) -> float:
    """Returns +-3 pts modifier based on short interest and price direction."""
    if not short_interest.get("available"):
        return 0.0
    pct = short_interest.get("short_percent")
    if pct is None or pct <= 20:
        return 0.0
    # High short (>20%): squeeze catalyst if upward, bearish confirmation otherwise
    return 3.0 if daily_direction == "up" else -3.0


# ── Stock-specific helpers ────────────────────────────────────────────────────

def _find_stock_key_signal(
    daily: dict, hourly: dict, sentiment: dict,
    analyst: dict, earnings: dict, history: dict,
    institutional: dict | None = None,
    short_interest: dict | None = None,
    fundamentals:   dict | None = None,
) -> dict:
    inst_data = institutional  if isinstance(institutional,  dict) else {}
    si_data   = short_interest if isinstance(short_interest, dict) else {}
    fund_data = fundamentals   if isinstance(fundamentals,   dict) else {}

    candidates: list[dict] = []

    # Smart money aligned: institutions accumulating + analyst consensus buy
    if (inst_data.get("available") and inst_data.get("signal") == "accumulation"
            and analyst.get("available")
            and analyst.get("consensus") in ("Strong Buy", "Buy")):
        candidates.append({
            "text": "Smart Money Aligned: Institutions Accumulating + Analyst Buy",
            "direction": "up", "strength": 4,
        })

    # Short squeeze setup: >20% float short + price heading up
    si_pct = si_data.get("short_percent")
    if si_pct is not None and si_pct > 20 and daily.get("direction") == "up":
        candidates.append({
            "text": f"Short Squeeze Setup: {si_pct:.1f}% Float Short + Upward Momentum",
            "direction": "up", "strength": 4,
        })

    # Near 52W high breakout (within 3%)
    try:
        last_price  = float(daily.get("last_price", 0))
        week52_high = float(fund_data.get("week52_high") or 0)
        if week52_high > 0 and last_price > 0 and (week52_high - last_price) / week52_high < 0.03:
            candidates.append({
                "text": f"Near 52W High Breakout (within 3% of ${week52_high:.2f})",
                "direction": "up", "strength": 3,
            })
    except (ValueError, TypeError):
        pass

    # RSI extremes
    if daily["rsi"] < 30:
        candidates.append({"text": f"Daily RSI Oversold ({daily['rsi']:.0f})", "direction": "up", "strength": 3})
    elif daily["rsi"] > 70:
        candidates.append({"text": f"Daily RSI Overbought ({daily['rsi']:.0f})", "direction": "down", "strength": 3})

    # Strong analyst consensus with upside
    if analyst.get("available"):
        consensus = analyst.get("consensus", "")
        upside    = analyst.get("upside_pct")
        if consensus in ("Strong Buy", "Buy") and (upside is None or upside > 10):
            candidates.append({
                "text": f"Analyst {consensus}" + (f" ({upside:+.0f}% upside)" if upside else ""),
                "direction": "up", "strength": 3,
            })
        elif consensus in ("Strong Sell", "Sell"):
            candidates.append({"text": f"Analyst {consensus}", "direction": "down", "strength": 3})

    # Consistent earnings beats
    beats  = earnings.get("beats",  0)
    misses = earnings.get("misses", 0)
    total  = beats + misses
    if total >= 3 and beats == total:
        candidates.append({"text": f"Earnings Beat {beats}/{total} Quarters", "direction": "up",   "strength": 2})
    elif total >= 3 and misses == total:
        candidates.append({"text": f"Earnings Miss {misses}/{total} Quarters", "direction": "down", "strength": 2})

    # Strong historical outperformance vs SPY
    vs_1y = history.get("vs_spy", {}).get("1Y")
    if vs_1y is not None:
        if vs_1y > 20:
            candidates.append({"text": f"Outperforming SPY by {vs_1y:+.0f}% (1Y)", "direction": "up",   "strength": 2})
        elif vs_1y < -20:
            candidates.append({"text": f"Underperforming SPY by {abs(vs_1y):.0f}% (1Y)", "direction": "down", "strength": 2})

    # MACD aligned on both TFs
    if daily["macd_above_signal"] and hourly["macd_above_signal"]:
        candidates.append({"text": "MACD Bullish on Daily + Hourly", "direction": "up",   "strength": 2})
    elif not daily["macd_above_signal"] and not hourly["macd_above_signal"]:
        candidates.append({"text": "MACD Bearish on Daily + Hourly", "direction": "down", "strength": 2})

    # Trend aligned
    if daily["trend"] == hourly["trend"] and daily["trend"] != "neutral":
        candidates.append({
            "text": f"Trend Aligned {daily['trend'].upper()} (Daily + Hourly)",
            "direction": daily["trend"], "strength": 1,
        })

    # Sentiment
    score = sentiment.get("score", 0.0) if isinstance(sentiment, dict) else 0.0
    if score > 0.3:
        candidates.append({"text": f"Strong Bullish News Sentiment ({score:.2f})", "direction": "up",   "strength": 1})
    elif score < -0.3:
        candidates.append({"text": f"Strong Bearish News Sentiment ({score:.2f})", "direction": "down", "strength": 1})

    if not candidates:
        return {"text": "No dominant signal", "direction": "neutral"}
    best = max(candidates, key=lambda x: x["strength"])
    return {"text": best["text"], "direction": best["direction"]}


def _find_stock_main_risk(
    daily: dict, earnings: dict, fundamentals: dict, insider: dict, events: list,
    short_interest: dict | None = None, institutional: dict | None = None,
) -> str:
    si_data   = short_interest if isinstance(short_interest, dict) else {}
    inst_data = institutional  if isinstance(institutional,  dict) else {}

    # Earnings proximity (always surfaces at <=14 days)
    next_date = earnings.get("next_date")
    days_away = None
    if next_date:
        try:
            days_away = (_date.fromisoformat(next_date) - _date.today()).days
        except ValueError:
            days_away = None

    if days_away is not None and 0 <= days_away <= 14:
        return f"Earnings in {days_away} days ({next_date}) - expect sharp price movement"

    # Extreme PE premium vs sector (>50% above sector avg)
    pe_vs = fundamentals.get("pe_vs_sector_pct")
    if pe_vs is not None and pe_vs > 50:
        pe      = fundamentals.get("pe_ratio")
        sec_pe  = fundamentals.get("sector_pe_avg", 20)
        return (
            f"Extreme valuation: P/E {pe:.0f}x is {pe_vs:.0f}% above sector avg "
            f"({sec_pe:.0f}x)"
        )

    # Double red flag: insider selling + institutional distribution
    sc = insider.get("sell_count", 0)
    bc = insider.get("buy_count",  0)
    if sc > bc * 2 and inst_data.get("signal") == "distribution":
        return "Double red flag: insider selling and institutional distribution detected"

    # High short without upward momentum
    si_pct = si_data.get("short_percent")
    if si_pct is not None and si_pct > 20 and daily["direction"] != "up":
        return f"High short interest ({si_pct:.1f}%) with no upward momentum - bearish conviction"

    # Revenue decline
    rev = fundamentals.get("revenue_growth")
    if rev is not None and rev < -0.05:
        return f"Revenue declining {rev * 100:.1f}% YoY - fundamental deterioration"

    # RSI extreme
    if daily["rsi"] > 75:
        return f"Daily RSI Extreme Overbought ({daily['rsi']:.0f}) - reversal risk"
    if daily["rsi"] < 25:
        return f"Daily RSI Extreme Oversold ({daily['rsi']:.0f}) - reversal risk"

    # Heavy insider selling
    if sc >= 3 and sc > bc * 2:
        return f"Heavy insider selling detected ({sc} sell transactions)"

    # High-impact event (US-only for stocks unless symbol says otherwise)
    relevant = _asset_countries("", "stock")   # defaults to US
    ranked   = _filter_and_rank_events(events, relevant)
    if ranked:
        top    = ranked[0]
        impact = str(top.get("impact", "")).lower()
        if impact in ("high", "3") or top.get("_sort_key", 0) >= 500 + 75:
            return f"High-impact event: {top.get('event', '')} ({top.get('country', '')})"

    # Earnings in 15-30 days (secondary warning)
    if days_away is not None and 15 <= days_away <= 30:
        return f"Earnings in {days_away} days ({next_date}) - monitor for volatility"

    return "No major macroeconomic risk detected"


def _detect_stock_conflicts(
    daily: dict, hourly: dict, sentiment: dict,
    analyst: dict, fundamentals: dict,
) -> dict:
    # TF conflict
    tf_conflict = (
        daily["direction"] != "neutral" and
        hourly["direction"] != "neutral" and
        daily["direction"] != hourly["direction"]
    )

    # Analyst vs technical conflict
    tech_dir = daily["direction"]
    consensus = analyst.get("consensus", "No Data") if analyst.get("available") else "No Data"
    analyst_dir = (
        "up"   if consensus in ("Strong Buy", "Buy") else
        "down" if consensus in ("Strong Sell", "Sell") else
        "neutral"
    )
    analyst_conflict = (
        analyst_dir != "neutral" and tech_dir != "neutral" and
        analyst_dir != tech_dir and analyst.get("available", False)
    )

    # Fundamental vs technical conflict
    pe = fundamentals.get("pe_ratio")
    rev = fundamentals.get("revenue_growth")
    fund_bearish = (pe is not None and pe > 40) or (rev is not None and rev < -0.05)
    fund_conflict = fund_bearish and tech_dir == "up"

    badges: list[dict] = []
    if tf_conflict:
        badges.append({
            "label": "TF Conflict",
            "type":  "warning",
            "tip":   f"Daily trend is {daily['direction'].upper()} but Hourly trend is {hourly['direction'].upper()}. Mixed signals - lower confidence.",
        })
    if analyst_conflict:
        badges.append({
            "label": "Analyst Conflict",
            "type":  "warning",
            "tip":   f"Analyst consensus ({consensus}) contradicts the technical direction ({tech_dir.upper()}). Extra caution advised.",
        })
    if fund_conflict:
        badges.append({
            "label": "Valuation Risk",
            "type":  "warning",
            "tip":   "Technical signals are bullish but fundamentals show elevated valuation or declining revenue. Consider the long-term risk.",
        })

    return {
        "timeframe_conflict":      tf_conflict,
        "analyst_conflict":        analyst_conflict,
        "fundamental_conflict":    fund_conflict,
        "badges":                  badges,
    }


# ── Stock alignment ───────────────────────────────────────────────────────────

def compute_stock_alignment(
    hourly:            dict,
    daily:             dict,
    sentiment:         dict,
    fundamentals:      dict,
    analyst:           dict,
    earnings:          dict,
    history:           dict,
    events:            list,
    insider:           dict | None = None,
    institutional:     dict | None = None,
    short_interest:    dict | None = None,
    options_sentiment: dict | None = None,
    ichimoku:          dict | None = None,
    volume:            dict | None = None,
    weekly_bias:       str = "neutral",
    symbol:            str = "",
) -> dict:
    """
    Stock scoring (total 100 pts, plus +-3 modifier):
        Daily Technical         22 pts
        Hourly Technical        18 pts
        Fundamental Score       14 pts  (P/E, revenue growth, profit margin)
        Analyst Consensus       11 pts  (buy/hold/sell ratio)
        Institutional Ownership  8 pts  (accumulation vs distribution)
        News Sentiment           9 pts
        Historical vs SPY        9 pts  (1Y return vs SPY)
        Earnings Quality         9 pts  (beat/miss record last 4Q)
        Short Interest modifier +-3 pts (squeeze risk or bearish conviction)
    """
    daily_pts  = daily["strength"]  * 22
    hourly_pts = hourly["strength"] * 18

    fund_pts,    fund_dir    = _score_fundamentals(fundamentals)
    analyst_pts, analyst_dir = _score_analyst_consensus(analyst)
    hist_pts,    hist_dir    = _score_historical_trend(history)
    earn_pts,    earn_dir    = _score_earnings_quality(earnings)

    inst_data = institutional if isinstance(institutional, dict) else {}
    si_data   = short_interest if isinstance(short_interest, dict) else {}

    inst_pts,  inst_dir = _score_institutional_ownership(inst_data)
    si_mod              = _short_interest_modifier(si_data, daily["direction"])

    snt      = sentiment if isinstance(sentiment, dict) else {}
    s        = snt.get("score", 0.0)
    sent_dir = "up" if s > 0 else "down" if s < 0 else "neutral"
    sent_pts = min(abs(s) / 0.5, 1.0) * 9

    # Ichimoku
    ichi     = ichimoku if isinstance(ichimoku, dict) else {}
    ichi_dir = ichi.get("direction", "neutral")
    ichi_str = float(ichi.get("strength", 0))
    ichi_pts = ichi_str * 8

    # Volume confirmation
    vol_data = volume if isinstance(volume, dict) else {}
    vol_sig  = vol_data.get("signal", "neutral")
    vol_pts  = 0.0
    _net_prelim = (
        _vote(daily["direction"])  * 22 +
        _vote(hourly["direction"]) * 18 +
        _vote(fund_dir)            * 14 +
        _vote(analyst_dir)         * 11
    )
    _bias_prelim = "up" if _net_prelim > 8 else "down" if _net_prelim < -8 else "unclear"
    if vol_data.get("available"):
        if vol_sig == "bullish" and _vote(_bias_prelim) > 0:
            vol_pts = 5.0
        elif vol_sig == "bearish" and _vote(_bias_prelim) < 0:
            vol_pts = 5.0
        elif vol_data.get("divergence") != "none":
            vol_pts = 2.0

    # Direction vote (weighted)
    net = (
        _vote(daily["direction"])  * 22 +
        _vote(hourly["direction"]) * 18 +
        _vote(fund_dir)            * 14 +
        _vote(analyst_dir)         * 11 +
        _vote(inst_dir)            *  8 +
        _vote(sent_dir)            *  9 +
        _vote(hist_dir)            *  9 +
        _vote(earn_dir)            *  9 +
        _vote(ichi_dir)            *  8 +
        _vote(vol_sig)             *  5 +
        _vote(weekly_bias)         *  8
    )
    bias = "up" if net > 8 else "down" if net < -8 else "unclear"

    raw   = daily_pts + hourly_pts + fund_pts + analyst_pts + inst_pts + sent_pts + hist_pts + earn_pts + ichi_pts + vol_pts
    score = max(0, min(100, int(round(raw + si_mod))))

    ins_data   = insider if isinstance(insider, dict) else {}
    key_signal = _find_stock_key_signal(
        daily, hourly, snt, analyst, earnings, history,
        institutional=inst_data, short_interest=si_data, fundamentals=fundamentals,
    )
    main_risk  = _find_stock_main_risk(
        daily, earnings, fundamentals, ins_data, events,
        short_interest=si_data, institutional=inst_data,
    )
    conflicts  = _detect_stock_conflicts(daily, hourly, snt, analyst, fundamentals)

    return {
        "alignment_score": score,
        "bias":            bias,
        "key_signal":      key_signal,
        "main_risk":       main_risk,
        "conflicts":       conflicts,
        "components": {
            "daily_technical":  {"points": round(daily_pts, 1),  "max": 22, "direction": daily["direction"]},
            "hourly_technical": {"points": round(hourly_pts, 1), "max": 18, "direction": hourly["direction"]},
            "fundamental": {
                "points": fund_pts, "max": 14, "direction": fund_dir,
                "pe_ratio":       fundamentals.get("pe_ratio"),
                "revenue_growth": fundamentals.get("revenue_growth"),
                "profit_margin":  fundamentals.get("profit_margin"),
                "available":      fundamentals.get("available", False),
            },
            "analyst_consensus": {
                "points":     analyst_pts, "max": 11, "direction": analyst_dir,
                "consensus":  analyst.get("consensus", "No Data"),
                "upside_pct": analyst.get("upside_pct"),
                "available":  analyst.get("available", False),
            },
            "institutional_ownership": {
                "points":     round(inst_pts, 1), "max": 8, "direction": inst_dir,
                "signal":     inst_data.get("signal", "neutral"),
                "buy_count":  inst_data.get("buy_count",  0),
                "sell_count": inst_data.get("sell_count", 0),
                "available":  inst_data.get("available", False),
            },
            "sentiment": {
                "points":    round(sent_pts, 1), "max": 9,
                "direction": sent_dir,
                "label":     snt.get("label", "neutral"),
                "articles":  snt.get("article_count", 0),
                "headlines": snt.get("headlines", []),
            },
            "historical_trend": {
                "points":    hist_pts, "max": 9, "direction": hist_dir,
                "vs_spy_1y": history.get("vs_spy",    {}).get("1Y"),
                "return_1y": history.get("returns",   {}).get("1Y"),
                "label":     history.get("label", "N/A"),
                "available": history.get("available", False),
            },
            "earnings_quality": {
                "points":    earn_pts, "max": 9, "direction": earn_dir,
                "beats":     earnings.get("beats",  0),
                "misses":    earnings.get("misses", 0),
                "available": earnings.get("available", False),
            },
            "ichimoku": {
                "points":         round(ichi_pts, 1), "max": 8, "direction": ichi_dir,
                "cloud_position": ichi.get("cloud_position"),
                "tk_cross":       ichi.get("tk_cross"),
                "available":      ichi.get("available", False),
            },
            "volume_confirmation": {
                "points":    round(vol_pts, 1), "max": 5,
                "signal":    vol_sig,
                "divergence": vol_data.get("divergence", "none"),
                "vol_ratio": vol_data.get("vol_ratio"),
                "available": vol_data.get("available", False),
            },
        },
    }


# ── Dynamic Trade Levels (TP/SL) ─────────────────────────────────────────────

def compute_trade_levels(
    daily:  dict,
    hourly: dict,
    bias:   str,
    score:  int,
    regime: dict | None = None,
) -> dict | None:
    """
    Calculate Stop Loss and Take Profit levels using proper market structure.

    SL Algorithm (priority order):
        1. Kijun-sen (Ichimoku 26-period base line) + ATR buffer
           -- Kijun is the most reliable structural level: price almost always
              retraces to test it in a trending move, so SL must be BEYOND it.
        2. Ichimoku cloud edge + ATR buffer (if Kijun not available)
        3. Swing S/R level + ATR buffer (fallback)
        4. 2.0x ATR projection (last resort)
        SL is capped at 3.0x ATR so it never becomes absurdly wide.

    TP Algorithm (priority order):
        1. Fibonacci extensions (127.2%, 161.8%, 200%) from recent swing
        2. Structural S/R levels on the target side
        3. R:R projection from risk distance
        TP1 >= 1.5:1, TP2 >= 2.5:1 AND >= 0.8x risk separation from TP1
        (prevents TP1 and TP2 being only a few pips apart).
    """
    if bias not in ("up", "down"):
        return None

    price = float(daily.get("last_price", 0))
    atr   = float(daily.get("atr_absolute", 0))

    if price <= 0:
        return None

    # Derive ATR if missing
    if atr <= 0:
        atr = price * float(daily.get("volatility_atr_pct", 0.5)) / 100
    if atr <= 0:
        return None

    # Regime-based SL buffer (fraction of ATR added beyond the structural level)
    regime_label = (regime or {}).get("regime", "transitioning")
    buf = 0.8 if regime_label == "trending" else 0.5 if regime_label == "ranging" else 0.6

    # ── Ichimoku levels ────────────────────────────────────────────────────────
    ichi         = daily.get("ichimoku") or {}
    kijun        = ichi.get("kijun")
    tenkan       = ichi.get("tenkan")
    cloud_top    = ichi.get("cloud_top")
    cloud_bottom = ichi.get("cloud_bottom")

    # ── Swing S/R levels ──────────────────────────────────────────────────────
    d_sup = float(daily.get("support",    price * 0.990))
    d_res = float(daily.get("resistance", price * 1.010))
    h_sup = float(hourly.get("support",   price * 0.995))
    h_res = float(hourly.get("resistance",price * 1.005))

    # ── Fibonacci data ─────────────────────────────────────────────────────────
    fibs      = daily.get("fibonacci") or {}
    ext_up    = fibs.get("extensions_up",   {})
    ext_down  = fibs.get("extensions_down", {})

    def _fib_levels_above(min_dist: float) -> list[float]:
        """All Fibonacci extension levels above price by at least min_dist."""
        out = []
        for v in ext_up.values():
            try:
                fv = float(v)
                if fv > price + min_dist:
                    out.append(fv)
            except (ValueError, TypeError):
                pass
        return sorted(out)

    def _fib_levels_below(min_dist: float) -> list[float]:
        """All Fibonacci extension levels below price by at least min_dist."""
        out = []
        for v in ext_down.values():
            try:
                fv = float(v)
                if fv < price - min_dist:
                    out.append(fv)
            except (ValueError, TypeError):
                pass
        return sorted(out, reverse=True)   # nearest first

    # ── SL calculation ─────────────────────────────────────────────────────────
    sl_method = "structure"

    if bias == "down":
        # SELL: SL must be ABOVE current price
        # Collect candidate SL levels (all must be > price)
        sl_candidates: list[tuple[str, float]] = []

        # Kijun above price → SL just above it
        if kijun and float(kijun) > price:
            sl_candidates.append(("kijun",     float(kijun) + atr * buf))

        # Cloud top above price → SL just above it
        if cloud_top and float(cloud_top) > price:
            sl_candidates.append(("cloud_top", float(cloud_top) + atr * buf))

        # Tenkan above price → shorter-term reference
        if tenkan and float(tenkan) > price:
            sl_candidates.append(("tenkan",    float(tenkan) + atr * buf))

        # Swing resistance
        if d_res > price:
            sl_candidates.append(("d_res",     d_res + atr * buf))
        if h_res > price:
            sl_candidates.append(("h_res",     h_res + atr * buf))

        # Filter: must clear price by at least 0.5x ATR, cap at 3x ATR
        valid = [(lbl, sl) for lbl, sl in sl_candidates
                 if sl - price >= atr * 0.5 and sl - price <= atr * 3.0]

        if valid:
            # Prefer Kijun if available; otherwise use nearest valid SL
            kijun_sl = next(((l, s) for l, s in valid if l == "kijun"), None)
            if kijun_sl:
                sl_method, raw_sl = kijun_sl
            else:
                # Pick smallest (nearest to price) among valid structural levels
                sl_method, raw_sl = min(valid, key=lambda x: x[1])
        else:
            # Fallback: 2x ATR above price
            raw_sl   = price + atr * 2.0
            sl_method = "atr_2x"

        risk = raw_sl - price

    else:
        # BUY: SL must be BELOW current price
        sl_candidates = []

        if kijun and float(kijun) < price:
            sl_candidates.append(("kijun",        float(kijun) - atr * buf))

        if cloud_bottom and float(cloud_bottom) < price:
            sl_candidates.append(("cloud_bottom", float(cloud_bottom) - atr * buf))

        if tenkan and float(tenkan) < price:
            sl_candidates.append(("tenkan",       float(tenkan) - atr * buf))

        if d_sup < price:
            sl_candidates.append(("d_sup",        d_sup - atr * buf))
        if h_sup < price:
            sl_candidates.append(("h_sup",        h_sup - atr * buf))

        valid = [(lbl, sl) for lbl, sl in sl_candidates
                 if price - sl >= atr * 0.5 and price - sl <= atr * 3.0]

        if valid:
            kijun_sl = next(((l, s) for l, s in valid if l == "kijun"), None)
            if kijun_sl:
                sl_method, raw_sl = kijun_sl
            else:
                sl_method, raw_sl = max(valid, key=lambda x: x[1])
        else:
            raw_sl    = price - atr * 2.0
            sl_method = "atr_2x"

        risk = price - raw_sl

    if risk <= 0:
        return None

    # ── TP calculation ─────────────────────────────────────────────────────────
    # Rules:
    #   TP1 distance >= risk * 1.5 (1.5:1 R:R minimum)
    #   TP2 distance >= risk * 2.5 (2.5:1 R:R minimum)
    #   TP2 must also be >= risk * 0.8 BEYOND TP1 (meaningful separation)

    MIN_RR1   = 1.5
    MIN_RR2   = 2.5
    MIN_SEP   = 0.8   # TP2 must be at least 0.8x risk away from TP1

    if bias == "down":
        # Targets below price
        tp1_min_dist = risk * MIN_RR1
        tp2_min_dist = risk * MIN_RR2

        # TP1: nearest Fibonacci below price respecting min distance
        fib_below = _fib_levels_below(tp1_min_dist)
        struct_below = sorted(
            [lvl for lvl in [h_sup, d_sup] if price - lvl >= tp1_min_dist],
            key=lambda x: price - x,
        )

        tp1 = (fib_below[0]   if fib_below  else
               struct_below[0] if struct_below else
               price - risk * MIN_RR1)

        # TP2: must satisfy both R:R and separation from TP1
        tp2_floor = min(price - tp2_min_dist, tp1 - risk * MIN_SEP)

        fib_tp2 = [f for f in fib_below if f <= tp2_floor]
        struct_tp2 = sorted(
            [lvl for lvl in [d_sup, h_sup] if lvl <= tp2_floor],
            key=lambda x: tp2_floor - x,
        )

        tp2 = (fib_tp2[0]    if fib_tp2   else
               struct_tp2[0]  if struct_tp2 else
               tp2_floor)

        # Final sanity
        if tp2 >= tp1:
            tp2 = tp1 - risk * MIN_SEP
        if tp1 >= price:
            tp1 = price - risk * MIN_RR1
        if tp2 >= price:
            tp2 = price - risk * MIN_RR2

    else:
        # Targets above price
        tp1_min_dist = risk * MIN_RR1
        tp2_min_dist = risk * MIN_RR2

        fib_above = _fib_levels_above(tp1_min_dist)
        struct_above = sorted(
            [lvl for lvl in [h_res, d_res] if lvl - price >= tp1_min_dist],
            key=lambda x: x - price,
        )

        tp1 = (fib_above[0]   if fib_above   else
               struct_above[0] if struct_above else
               price + risk * MIN_RR1)

        tp2_floor = max(price + tp2_min_dist, tp1 + risk * MIN_SEP)

        fib_tp2 = [f for f in fib_above if f >= tp2_floor]
        struct_tp2 = sorted(
            [lvl for lvl in [d_res, h_res] if lvl >= tp2_floor],
            key=lambda x: x - tp2_floor,
        )

        tp2 = (fib_tp2[0]    if fib_tp2    else
               struct_tp2[0]  if struct_tp2  else
               tp2_floor)

        if tp2 <= tp1:
            tp2 = tp1 + risk * MIN_SEP
        if tp1 <= price:
            tp1 = price + risk * MIN_RR1
        if tp2 <= price:
            tp2 = price + risk * MIN_RR2

    rr1 = round(abs(tp1 - price) / risk, 2)
    rr2 = round(abs(tp2 - price) / risk, 2)

    # Human-readable SL description for UI
    _sl_desc = {
        "kijun":        f"SL beyond Kijun-sen (Ichimoku base line: {round(float(kijun), 5) if kijun else '-'})",
        "cloud_top":    f"SL above Ichimoku cloud top ({round(float(cloud_top), 5) if cloud_top else '-'})",
        "cloud_bottom": f"SL below Ichimoku cloud bottom ({round(float(cloud_bottom), 5) if cloud_bottom else '-'})",
        "tenkan":       f"SL beyond Tenkan-sen ({round(float(tenkan), 5) if tenkan else '-'})",
        "d_res":        "SL beyond daily resistance",
        "h_res":        "SL beyond hourly resistance",
        "d_sup":        "SL beyond daily support",
        "h_sup":        "SL beyond hourly support",
        "atr_2x":       f"SL at 2x ATR (no structural level nearby)",
        "structure":    "SL beyond structural S/R level",
    }

    if score >= 70:
        size_hint = "Standard position size. Strong alignment."
    elif score >= 55:
        size_hint = "Reduced position size (50-75%). Moderate alignment."
    elif score >= 40:
        size_hint = "Minimal position size (25-50%). Weak alignment."
    else:
        size_hint = "No trade recommended. Conflicting signals."

    return {
        "bias":           bias,
        "entry":          round(price,  6),
        "sl":             round(raw_sl, 6),
        "tp1":            round(tp1,    6),
        "tp2":            round(tp2,    6),
        "risk":           round(risk,   6),
        "atr":            round(atr,    6),
        "rr1":            rr1,
        "rr2":            rr2,
        "regime":         regime_label,
        "atr_sl_buf":     buf,
        "sl_method":      sl_method,
        "sl_description": _sl_desc.get(sl_method, sl_method),
        "kijun_ref":      round(float(kijun), 6) if kijun else None,
        "size_hint":      size_hint,
    }


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dummy_tf = {
        "direction": "up", "strength": 0.75, "rsi": 55.0,
        "macd_above_signal": True, "ma20_above_ma50": True,
        "trend": "up", "support": 1.07, "resistance": 1.10,
        "volatility_atr_pct": 0.4, "last_price": 1.085,
    }
    dummy_cot = {
        "net": 55000, "effective_net": 55000, "direction": "up",
        "label": "Net Long EUR (+55,000)", "weeks_trend": "increasing",
        "available": True,
    }
    result = compute_alignment(
        hourly=dummy_tf, daily=dummy_tf,
        intermarket={"dollar": "weakening"},
        sentiment={"score": 0.25, "label": "bullish", "article_count": 12, "headlines": []},
        cot=dummy_cot,
        events=[],
        asset_type="forex",
    )
    import json
    print(json.dumps(result, indent=2))
