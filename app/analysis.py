"""
Alignment score computation -- v2.
Weights (forex): daily(25) + hourly(20) + intermarket(18) + institutional(15) + sentiment(12) + events(10) = 100
Stocks omit intermarket and institutional; raw max = 67, scaled to 100.
Run directly: python -m app.analysis
"""


def _vote(d: str) -> int:
    return 1 if d == "up" else -1 if d == "down" else 0


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

def _find_main_risk(events: list, daily: dict, sentiment: dict, cot: dict) -> str:
    # Imminent high-impact event
    hi = [e for e in events if str(e.get("impact", "")).lower() in ("high", "3")]
    if hi:
        e = hi[0]
        return f"High-impact {e.get('event', 'event')} ({e.get('country', '')})"

    # Extreme RSI
    if daily["rsi"] > 75:
        return f"Daily RSI Extreme Overbought ({daily['rsi']:.0f}) -- reversal risk"
    if daily["rsi"] < 25:
        return f"Daily RSI Extreme Oversold ({daily['rsi']:.0f}) -- reversal risk"

    # COT reducing
    if (cot.get("available") and cot.get("weeks_trend") == "decreasing"
            and abs(cot.get("net", 0)) > 30000):
        return "Institutional positioning reducing -- potential trend shift"

    # Sentiment vs technical divergence
    sent_lbl = sentiment.get("label", "neutral") if isinstance(sentiment, dict) else "neutral"
    if sent_lbl == "bearish" and daily["direction"] == "up":
        return "Bearish news sentiment conflicts with bullish technical bias"
    if sent_lbl == "bullish" and daily["direction"] == "down":
        return "Bullish news sentiment conflicts with bearish technical bias"

    return "Monitor economic calendar for volatility triggers"


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
    hourly:      dict,
    daily:       dict,
    intermarket: dict,
    sentiment:   dict,
    cot:         dict,
    events:      list,
    asset_type:  str,
) -> dict:
    """
    Point allocation (forex):
        Daily technical   25 pts
        Hourly technical  20 pts
        Intermarket       18 pts  (forex only)
        Institutional COT 15 pts  (forex only)
        Sentiment         12 pts
        Event clarity     10 pts
        Total            100 pts

    Stocks: max_raw = 67, rescaled to 100.
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

    # Direction vote (weighted)
    inter_w = 18 if asset_type == "forex" else 0
    cot_w   = 15 if asset_type == "forex" else 0
    net = (
        _vote(daily["direction"])  * 25 +
        _vote(hourly["direction"]) * 20 +
        _vote(inter_dir)           * inter_w +
        _vote(cot_dir)             * cot_w +
        _vote(sent_dir)            * 12
    )
    bias = "up" if net > 5 else "down" if net < -5 else "unclear"

    # Normalise
    raw     = daily_pts + hourly_pts + inter_pts + cot_pts + sent_pts + event_pts
    max_pts = 100.0 if asset_type == "forex" else 67.0
    score   = min(int(round(raw / max_pts * 100)), 100)

    # Key signal, main risk, conflicts
    key_signal = _find_key_signal(daily, hourly, ct, snt)
    main_risk  = _find_main_risk(events, daily, snt, ct)
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
        },
    }


# ── Stock scoring helpers ─────────────────────────────────────────────────────

def _score_fundamentals(fund: dict) -> tuple[float, str]:
    """Returns (points 0-15, direction) from P/E, revenue growth, profit margin."""
    if not fund.get("available"):
        return 7.5, "neutral"   # half points when data unavailable

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
        return 7.5, "neutral"

    avg = sum(signals) / len(signals)
    pts = max(0.0, min(15.0, (avg + 1.0) / 2.0 * 15.0))
    direction = "up" if avg > 0.15 else "down" if avg < -0.15 else "neutral"
    return round(pts, 1), direction


def _score_analyst_consensus(analyst: dict) -> tuple[float, str]:
    """Returns (points 0-12, direction) from buy/hold/sell ratio."""
    if not analyst.get("available") or not analyst.get("total"):
        return 0.0, "neutral"

    total    = analyst["total"]
    buy_pct  = (analyst.get("strong_buy", 0) + analyst.get("buy",        0)) / total
    sell_pct = (analyst.get("strong_sell",0) + analyst.get("sell",       0)) / total
    score    = buy_pct - sell_pct              # range [-1, 1]
    pts      = max(0.0, min(12.0, (score + 1.0) / 2.0 * 12.0))
    direction = "up" if score > 0.1 else "down" if score < -0.1 else "neutral"
    return round(pts, 1), direction


def _score_historical_trend(history: dict) -> tuple[float, str]:
    """Returns (points 0-10, direction) from 1Y performance vs SPY."""
    if not history.get("available"):
        return 5.0, "neutral"   # neutral when data unavailable

    vs_1y = history.get("vs_spy", {}).get("1Y")
    ret_1y = history.get("returns", {}).get("1Y")

    # Prefer vs-SPY; fall back to absolute 1Y return
    val = vs_1y if vs_1y is not None else ret_1y
    if val is None:
        return 5.0, "neutral"

    if   val > 20:  pts, direction = 10.0, "up"
    elif val > 10:  pts, direction =  8.0, "up"
    elif val > 3:   pts, direction =  6.5, "up"
    elif val > -3:  pts, direction =  5.0, "neutral"
    elif val > -10: pts, direction =  3.0, "down"
    elif val > -20: pts, direction =  1.5, "down"
    else:           pts, direction =  0.0, "down"
    return pts, direction


def _score_earnings_quality(earnings: dict) -> tuple[float, str]:
    """Returns (points 0-8, direction) from EPS beat/miss record."""
    if not earnings.get("available"):
        return 4.0, "neutral"

    beats  = earnings.get("beats",  0)
    misses = earnings.get("misses", 0)
    total  = beats + misses
    if total == 0:
        return 4.0, "neutral"

    beat_ratio = beats / total
    if   beat_ratio >= 1.0: pts, direction = 8.0, "up"
    elif beat_ratio >= 0.75: pts, direction = 6.0, "up"
    elif beat_ratio >= 0.5:  pts, direction = 4.0, "neutral"
    elif beat_ratio >= 0.25: pts, direction = 2.0, "down"
    else:                    pts, direction = 0.0, "down"
    return pts, direction


# ── Stock-specific helpers ────────────────────────────────────────────────────

def _find_stock_key_signal(
    daily: dict, hourly: dict, sentiment: dict,
    analyst: dict, earnings: dict, history: dict,
) -> dict:
    candidates: list[dict] = []

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
                "text":      f"Analyst {consensus}" + (f" ({upside:+.0f}% upside)" if upside else ""),
                "direction": "up", "strength": 3,
            })
        elif consensus in ("Strong Sell", "Sell"):
            candidates.append({
                "text": f"Analyst {consensus}", "direction": "down", "strength": 3,
            })

    # Consistent earnings beats
    beats  = earnings.get("beats",  0)
    misses = earnings.get("misses", 0)
    total  = beats + misses
    if total >= 3 and beats == total:
        candidates.append({
            "text": f"Earnings Beat {beats}/{total} Quarters", "direction": "up", "strength": 2,
        })
    elif total >= 3 and misses == total:
        candidates.append({
            "text": f"Earnings Miss {misses}/{total} Quarters", "direction": "down", "strength": 2,
        })

    # Strong historical outperformance vs SPY
    vs_1y = history.get("vs_spy", {}).get("1Y")
    if vs_1y is not None:
        if vs_1y > 20:
            candidates.append({"text": f"Outperforming SPY by {vs_1y:+.0f}% (1Y)", "direction": "up", "strength": 2})
        elif vs_1y < -20:
            candidates.append({"text": f"Underperforming SPY by {abs(vs_1y):.0f}% (1Y)", "direction": "down", "strength": 2})

    # MACD aligned on both TFs
    if daily["macd_above_signal"] and hourly["macd_above_signal"]:
        candidates.append({"text": "MACD Bullish on Daily + Hourly", "direction": "up", "strength": 2})
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
        candidates.append({"text": f"Strong Bullish News Sentiment ({score:.2f})", "direction": "up", "strength": 1})
    elif score < -0.3:
        candidates.append({"text": f"Strong Bearish News Sentiment ({score:.2f})", "direction": "down", "strength": 1})

    if not candidates:
        return {"text": "No dominant signal", "direction": "neutral"}
    best = max(candidates, key=lambda x: x["strength"])
    return {"text": best["text"], "direction": best["direction"]}


def _find_stock_main_risk(
    daily: dict, earnings: dict, fundamentals: dict, insider: dict, events: list,
) -> str:
    # Upcoming earnings date (high uncertainty)
    next_date = earnings.get("next_date")
    if next_date:
        try:
            from datetime import date
            days_away = (date.fromisoformat(next_date) - date.today()).days
            if 0 <= days_away <= 21:
                return f"Earnings report due {next_date} ({days_away}d away) -- expect volatility"
        except ValueError:
            pass

    # Extreme valuation
    pe = fundamentals.get("pe_ratio")
    if pe is not None and pe > 45:
        return f"Extreme valuation: P/E ratio is {pe:.0f}x (high reversal risk)"

    # Revenue decline
    rev = fundamentals.get("revenue_growth")
    if rev is not None and rev < -0.05:
        return f"Revenue declining {rev * 100:.1f}% YoY -- fundamental deterioration"

    # RSI extreme
    if daily["rsi"] > 75:
        return f"Daily RSI Extreme Overbought ({daily['rsi']:.0f}) -- reversal risk"
    if daily["rsi"] < 25:
        return f"Daily RSI Extreme Oversold ({daily['rsi']:.0f}) -- reversal risk"

    # Heavy insider selling
    sc = insider.get("sell_count", 0)
    bc = insider.get("buy_count",  0)
    if sc >= 3 and sc > bc * 2:
        return f"Heavy insider selling detected ({sc} sell transactions)"

    # High-impact event
    hi = [e for e in events if str(e.get("impact", "")).lower() in ("high", "3")]
    if hi:
        e = hi[0]
        return f"High-impact event: {e.get('event', '')} ({e.get('country', '')})"

    return "Monitor earnings calendar and macro news for unexpected catalysts"


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
    hourly:       dict,
    daily:        dict,
    sentiment:    dict,
    fundamentals: dict,
    analyst:      dict,
    earnings:     dict,
    history:      dict,
    events:       list,
    insider:      dict | None = None,
) -> dict:
    """
    Stock scoring (total 100 pts):
        Daily Technical   25 pts
        Hourly Technical  20 pts
        Fundamental Score 15 pts  (P/E, revenue growth, profit margin)
        Analyst Consensus 12 pts  (buy/hold/sell ratio)
        News Sentiment    10 pts
        Historical vs SPY 10 pts  (1Y return vs SPY)
        Earnings Quality   8 pts  (beat/miss record last 4Q)
    """
    daily_pts  = daily["strength"]  * 25
    hourly_pts = hourly["strength"] * 20

    fund_pts,    fund_dir    = _score_fundamentals(fundamentals)
    analyst_pts, analyst_dir = _score_analyst_consensus(analyst)
    hist_pts,    hist_dir    = _score_historical_trend(history)
    earn_pts,    earn_dir    = _score_earnings_quality(earnings)

    snt      = sentiment if isinstance(sentiment, dict) else {}
    s        = snt.get("score", 0.0)
    sent_dir = "up" if s > 0 else "down" if s < 0 else "neutral"
    sent_pts = min(abs(s) / 0.5, 1.0) * 10

    # Direction vote (weighted)
    net = (
        _vote(daily["direction"])  * 25 +
        _vote(hourly["direction"]) * 20 +
        _vote(fund_dir)            * 15 +
        _vote(analyst_dir)         * 12 +
        _vote(sent_dir)            * 10 +
        _vote(hist_dir)            * 10 +
        _vote(earn_dir)            *  8
    )
    bias = "up" if net > 8 else "down" if net < -8 else "unclear"

    raw   = daily_pts + hourly_pts + fund_pts + analyst_pts + sent_pts + hist_pts + earn_pts
    score = min(int(round(raw)), 100)

    ins_data   = insider if isinstance(insider, dict) else {}
    key_signal = _find_stock_key_signal(daily, hourly, snt, analyst, earnings, history)
    main_risk  = _find_stock_main_risk(daily, earnings, fundamentals, ins_data, events)
    conflicts  = _detect_stock_conflicts(daily, hourly, snt, analyst, fundamentals)

    return {
        "alignment_score": score,
        "bias":            bias,
        "key_signal":      key_signal,
        "main_risk":       main_risk,
        "conflicts":       conflicts,
        "components": {
            "daily_technical":  {"points": round(daily_pts, 1),  "max": 25, "direction": daily["direction"]},
            "hourly_technical": {"points": round(hourly_pts, 1), "max": 20, "direction": hourly["direction"]},
            "fundamental":      {
                "points": fund_pts, "max": 15, "direction": fund_dir,
                "pe_ratio":       fundamentals.get("pe_ratio"),
                "revenue_growth": fundamentals.get("revenue_growth"),
                "profit_margin":  fundamentals.get("profit_margin"),
                "available":      fundamentals.get("available", False),
            },
            "analyst_consensus": {
                "points":    analyst_pts, "max": 12, "direction": analyst_dir,
                "consensus": analyst.get("consensus", "No Data"),
                "upside_pct":analyst.get("upside_pct"),
                "available": analyst.get("available", False),
            },
            "sentiment": {
                "points":    round(sent_pts, 1), "max": 10,
                "direction": sent_dir,
                "label":     snt.get("label", "neutral"),
                "articles":  snt.get("article_count", 0),
                "headlines": snt.get("headlines", []),
            },
            "historical_trend": {
                "points":    hist_pts, "max": 10, "direction": hist_dir,
                "vs_spy_1y": history.get("vs_spy", {}).get("1Y"),
                "return_1y": history.get("returns", {}).get("1Y"),
                "label":     history.get("label", "N/A"),
                "available": history.get("available", False),
            },
            "earnings_quality": {
                "points":    earn_pts, "max": 8, "direction": earn_dir,
                "beats":     earnings.get("beats",  0),
                "misses":    earnings.get("misses", 0),
                "available": earnings.get("available", False),
            },
        },
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
