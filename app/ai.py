"""
AI-powered market summary with automatic provider fallback.
Priority: Gemini → Groq → OpenAI → Anthropic → Rule-based (always works).
Run directly: python -m app.ai
"""
import asyncio

import httpx

from app.config import (
    GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    GEMINI_URL, GROQ_URL, OPENAI_URL, ANTHROPIC_URL,
)


def _build_prompt(data: dict) -> str:
    d          = data["timeframes"]["daily"]
    h          = data["timeframes"]["hourly"]
    b          = data["breakdown"]
    asset_type = data.get("asset_type", "forex")
    ev         = data.get("upcoming_events", [])[:5]
    key_signal = data.get("key_signal") or {}
    main_risk  = data.get("main_risk", "N/A")
    conflicts  = data.get("conflicts") or {}
    regime     = data.get("volatility_regime") or {}
    yield_diff = data.get("yield_diff") or {}
    cot        = data.get("cot") or {}
    inst       = b.get("institutional", {})

    ev_str = "\n".join(
        f"  {e.get('event','?')} ({e.get('country','?')}, {e.get('impact','?')}, {e.get('time','?')})"
        for e in ev
    ) or "  None scheduled"

    cot_str = "N/A (stocks)"
    if asset_type == "forex":
        cot_str = (
            f"{cot.get('label','No Data')} | Weekly trend: {cot.get('weeks_trend','unknown')}"
            if cot.get("available") else "Data unavailable"
        )

    yd_str = "N/A"
    if yield_diff.get("available"):
        yd_str = (
            f"US10Y {yield_diff['us10y']}% vs DE10Y {yield_diff['de10y']}%"
            f" | Spread {yield_diff['differential']:+.2f}% | {yield_diff['label']}"
        )

    regime_str = (
        f"{regime.get('regime','?').upper()} | ADX {regime.get('adx','?')}"
        f" | BB {'expanding' if regime.get('bb_expanding') else 'contracting'}"
    ) if regime else "N/A"

    conflict_str = (
        ", ".join(c["label"] for c in conflicts.get("badges", []))
        or "None"
    )

    headlines = b.get("sentiment", {}).get("headlines", [])
    hl_str = "\n".join(f"  - {hl['title']} ({hl.get('source','')})" for hl in headlines[:3]) \
             or "  None available"

    return f"""You are a professional market analyst. A trader needs your expert opinion on {data['asset']}.

FULL ANALYSIS DATA
Asset: {data['asset']} | Price: {data['last_price']} | Type: {asset_type.upper()}
Alignment Score: {data['score']}/100 | Overall Bias: {data['bias'].upper()}
Key Signal Detected: {key_signal.get('text','N/A')} ({key_signal.get('direction','?')})
Main Risk: {main_risk}
Signal Conflicts: {conflict_str}

TECHNICALS
Daily:  RSI {d['rsi']} | MACD {'above' if d['macd_above_signal'] else 'below'} signal | Trend {d['trend']} | MA20>MA50: {d['ma20_above_ma50']} | ATR% {d['volatility_atr_pct']}
Hourly: RSI {h['rsi']} | MACD {'above' if h['macd_above_signal'] else 'below'} signal | Trend {h['trend']}
Daily levels: Support {d['support']} / Resistance {d['resistance']}
Hourly levels: Support {h['support']} / Resistance {h['resistance']}

SCORE BREAKDOWN
Daily Technical  {b['daily_technical']['points']:.0f}/25 ({b['daily_technical']['direction'].upper()})
Hourly Technical {b['hourly_technical']['points']:.0f}/20 ({b['hourly_technical']['direction'].upper()})
Intermarket      {b['intermarket']['points']:.0f}/18  (USD {b['intermarket'].get('dollar','n/a')})
Institutional    {inst.get('points',0):.0f}/15  ({inst.get('label','No Data')} | {inst.get('weeks_trend','unknown')} trend)
Sentiment        {b['sentiment']['points']:.0f}/12  ({b['sentiment']['label'].upper()} | {b['sentiment']['articles']} articles)
Event Clarity    {b['event_clarity']['points']:.0f}/10  ({b['event_clarity']['high_impact']} high-impact events)

MACRO DATA
Institutional Positioning: {cot_str}
Yield Differential (US-DE 10Y): {yd_str}
Volatility Regime: {regime_str}

RECENT HEADLINES
{hl_str}

UPCOMING EVENTS
{ev_str}

---
Write a professional market analysis for this specific asset using ALL the data above.

Structure your response as:
1. VERDICT (1 sentence): state the directional bias and why, in plain language
2. KEY DRIVERS (3 bullet points): the most important factors explaining the current setup -- be specific to the actual numbers
3. WHAT TO WATCH (1-2 sentences): the main risk or catalyst that could change the thesis

Rules:
- Be specific to THIS data, not generic
- If technicals conflict with macro (e.g. MACD bullish but COT bearish), highlight the conflict and explain which matters more right now
- If the score is below 50, say the setup is LOW CONVICTION
- If the regime is Ranging, warn about false breakouts
- Max 220 words. No specific entry/exit prices. Not financial advice."""


def _build_stock_prompt(data: dict) -> str:
    d          = data["timeframes"]["daily"]
    h          = data["timeframes"]["hourly"]
    b          = data["breakdown"]
    asset      = data["asset"]
    fund       = data.get("fundamentals") or {}
    earnings   = data.get("earnings") or {}
    analyst    = data.get("analyst") or {}
    insider    = data.get("insider") or {}
    history    = data.get("history") or {}
    key_signal = data.get("key_signal") or {}
    main_risk  = data.get("main_risk", "N/A")
    conflicts  = data.get("conflicts") or {}
    regime     = data.get("volatility_regime") or {}
    sentiment  = data.get("sentiment") or {}

    # Fundamentals block
    pe      = fund.get("pe_ratio")
    fpe     = fund.get("forward_pe")
    eps     = fund.get("eps")
    mktcap  = fund.get("market_cap", "N/A")
    beta    = fund.get("beta")
    rev_g   = fund.get("revenue_growth")
    pm      = fund.get("profit_margin")
    roe     = fund.get("roe")
    hi52    = fund.get("week52_high")
    lo52    = fund.get("week52_low")
    sector  = fund.get("sector", "N/A")

    fund_str = (
        f"P/E: {pe:.1f}x" if pe else "P/E: N/A"
    ) + (
        f" | Fwd P/E: {fpe:.1f}x" if fpe else ""
    ) + (
        f" | EPS: ${eps:.2f}" if eps else ""
    ) + (
        f" | Market Cap: {mktcap}"
    ) + (
        f" | Beta: {beta:.2f}" if beta else ""
    ) + (
        f" | Revenue Growth: {rev_g * 100:.1f}%" if rev_g is not None else ""
    ) + (
        f" | Profit Margin: {pm * 100:.1f}%" if pm is not None else ""
    ) + (
        f" | ROE: {roe * 100:.1f}%" if roe is not None else ""
    ) + (
        f" | 52W Range: ${lo52:.2f} - ${hi52:.2f}" if lo52 and hi52 else ""
    )

    # Earnings block
    quarters  = earnings.get("quarters", [])
    beats     = earnings.get("beats",    0)
    misses    = earnings.get("misses",   0)
    next_date = earnings.get("next_date")
    q_str     = " | ".join(
        f"{q['period']}: Actual {q['actual']} vs Est {q['estimate']} "
        f"({'Beat' if q['beat'] else 'Miss'} {q['surprise_pct']:+.1f}%)"
        for q in quarters if q.get("actual") is not None
    ) or "N/A"
    earn_str = f"Record: {beats} beats / {misses} misses (last 4Q) | {q_str}"
    if next_date:
        earn_str += f" | Next earnings: {next_date}"

    # Analyst block
    consensus = analyst.get("consensus", "No Data")
    sb = analyst.get("strong_buy", 0); b_ = analyst.get("buy", 0)
    h_ = analyst.get("hold", 0);       s  = analyst.get("sell", 0); ss = analyst.get("strong_sell", 0)
    pt_mean = analyst.get("price_target_mean")
    upside  = analyst.get("upside_pct")
    ana_str = (
        f"{consensus} ({sb} Strong Buy / {b_} Buy / {h_} Hold / {s} Sell / {ss} Strong Sell)"
    )
    if pt_mean:
        ana_str += f" | Mean target: ${pt_mean:.2f}"
    if upside is not None:
        ana_str += f" | Upside: {upside:+.1f}%"

    # Insider block
    transactions = insider.get("transactions", [])[:4]
    bc = insider.get("buy_count",  0)
    sc = insider.get("sell_count", 0)
    ins_str = f"{bc} buys / {sc} sells (recent) | " + (
        " | ".join(
            f"{t['name']}: {t['type']} {t['shares']:,} shares @ ${t['price']:.2f} ({t['date']})"
            for t in transactions if t.get("price")
        ) or "No open-market transactions"
    )

    # Historical returns block
    rets  = history.get("returns",     {})
    spy_r = history.get("spy_returns", {})
    vs    = history.get("vs_spy",      {})
    hist_str = " | ".join(
        f"{p}: {rets.get(p, 'N/A'):+.1f}% (SPY {spy_r.get(p, 'N/A'):+.1f}%, vs {vs.get(p, 'N/A'):+.1f}%)"
        for p in ("1M", "3M", "6M", "1Y", "2Y", "5Y")
        if rets.get(p) is not None
    ) or "N/A"

    # Technicals block
    regime_str = (
        f"{regime.get('regime','?').upper()} | ADX {regime.get('adx','?')}"
        f" | BB {'expanding' if regime.get('bb_expanding') else 'contracting'}"
    ) if regime else "N/A"

    conflict_str = ", ".join(c["label"] for c in conflicts.get("badges", [])) or "None"

    headlines = sentiment.get("headlines", [])
    hl_str = "\n".join(f"  - {hl['title']} ({hl.get('source','')})" for hl in headlines[:3]) \
             or "  None available"

    # Score breakdown
    bk = b
    bd_str = "\n".join([
        f"  Daily Technical   {bk.get('daily_technical',{}).get('points',0):.0f}/25",
        f"  Hourly Technical  {bk.get('hourly_technical',{}).get('points',0):.0f}/20",
        f"  Fundamental Score {bk.get('fundamental',{}).get('points',0):.0f}/15",
        f"  Analyst Consensus {bk.get('analyst_consensus',{}).get('points',0):.0f}/12",
        f"  News Sentiment    {bk.get('sentiment',{}).get('points',0):.0f}/10",
        f"  Historical vs SPY {bk.get('historical_trend',{}).get('points',0):.0f}/10",
        f"  Earnings Quality  {bk.get('earnings_quality',{}).get('points',0):.0f}/8",
    ])

    return f"""You are a professional equity analyst. A trader needs your expert opinion on {asset} stock.

FULL ANALYSIS DATA
Asset: {asset} | Price: ${data['last_price']} | Sector: {sector}
Alignment Score: {data['score']}/100 | Overall Bias: {data['bias'].upper()}
Key Signal: {key_signal.get('text','N/A')} ({key_signal.get('direction','?')})
Main Risk: {main_risk}
Signal Conflicts: {conflict_str}

FUNDAMENTALS
{fund_str}

EARNINGS HISTORY
{earn_str}

ANALYST CONSENSUS
{ana_str}

INSIDER ACTIVITY (last 6 months)
{ins_str}

HISTORICAL PERFORMANCE vs SPY
{hist_str}

TECHNICALS
Daily:  RSI {d['rsi']} | MACD {'above' if d['macd_above_signal'] else 'below'} signal | Trend {d['trend']} | ATR% {d['volatility_atr_pct']}
Hourly: RSI {h['rsi']} | MACD {'above' if h['macd_above_signal'] else 'below'} signal | Trend {h['trend']}
Support {d['support']} / Resistance {d['resistance']}
Regime: {regime_str}

SCORE BREAKDOWN
{bd_str}

RECENT HEADLINES
{hl_str}

---
Write a professional equity research note using ALL the data above.

Structure your response as:
1. VERDICT (1 sentence): directional bias and the single most important reason
2. KEY DRIVERS (3 bullet points): the most impactful factors -- be specific to the actual numbers
3. WHAT TO WATCH (1-2 sentences): the main risk or catalyst that could change the thesis

Rules:
- Be specific to THIS data, not generic commentary
- If technicals conflict with fundamentals or analyst view, highlight it and explain which matters more
- If score is below 50, say the setup is LOW CONVICTION
- If P/E is extreme (above 40 or below 8), mention valuation risk or opportunity explicitly
- If insider selling is heavy, flag it
- Max 220 words. No specific entry/exit prices. Not financial advice."""


def _rule_based_summary(data: dict) -> str:
    """Always-available fallback — no AI key required."""
    score    = data["score"]
    bias     = data["bias"]
    asset    = data["asset"]
    d        = data["timeframes"]["daily"]
    h        = data["timeframes"]["hourly"]
    b        = data.get("breakdown", {})
    cot      = data.get("cot") or {}
    yd       = data.get("yield_diff") or {}
    regime   = data.get("volatility_regime") or {}
    key_sig  = (data.get("key_signal") or {}).get("text", "")
    main_risk = data.get("main_risk", "")
    conflicts = (data.get("conflicts") or {}).get("badges", [])

    strength = "strong" if score >= 65 else "moderate" if score >= 45 else "weak"
    conviction = "LOW CONVICTION -- wait for score above 50 before trading." if score < 45 else ""

    rsi_note = (
        f"overbought RSI at {d['rsi']:.0f}" if d["rsi"] > 70 else
        f"oversold RSI at {d['rsi']:.0f}"   if d["rsi"] < 30 else
        f"neutral RSI at {d['rsi']:.0f}"
    )

    verdict = (
        f"{asset} shows {strength} {bias} bias with an alignment score of {score}/100. "
        f"Daily trend is {d['trend']}, hourly trend is {h['trend']}, {rsi_note}. {conviction}"
    ).strip()

    bullets = [
        f"- MACD {'above' if d['macd_above_signal'] else 'below'} signal line on daily chart "
        f"({'bullish' if d['macd_above_signal'] else 'bearish'} short-term momentum)",
        f"- MA20 {'above' if d['ma20_above_ma50'] else 'below'} MA50 "
        f"({'uptrend aligned' if d['ma20_above_ma50'] else 'downtrend alignment'})",
    ]
    if cot.get("available"):
        bullets.append(
            f"- Institutional COT: {cot.get('label','N/A')} "
            f"(weekly trend {cot.get('weeks_trend','unknown')}) -- macro confirmation"
        )
    else:
        bullets.append(f"- Daily Support {d['support']} | Resistance {d['resistance']}")

    if yd.get("available"):
        bullets.append(f"- Yield spread: {yd['label']} (US10Y {yd['us10y']}% vs DE10Y {yd['de10y']}%)")

    regime_note = ""
    if regime.get("regime") == "ranging":
        regime_note = f" Market is in a Ranging regime (ADX {regime.get('adx','?')}) -- beware of false breakouts."
    elif regime.get("regime") == "trending":
        regime_note = f" Trending regime confirmed (ADX {regime.get('adx','?')}) -- trend-following signals are more reliable."

    conflict_note = ""
    if conflicts:
        labels = " and ".join(c["label"] for c in conflicts)
        conflict_note = f" Note: {labels} detected -- reduce position size."

    risk_line = f"Main risk to watch: {main_risk}." if main_risk else ""
    p3 = (
        f"ATR volatility at {d['volatility_atr_pct']:.2f}%.{regime_note}{conflict_note} "
        f"{risk_line} This is signal-alignment analysis, not financial advice."
    ).strip()

    return f"{verdict}\n\n" + "\n".join(bullets) + f"\n\n{p3}"


async def generate_ai_summary(client: httpx.AsyncClient, data: dict) -> tuple[str, str]:
    """
    Returns (summary_text, provider_name).
    Tries AI providers top-to-bottom; falls back to rule-based text.
    """
    prompt = _build_stock_prompt(data) if data.get("asset_type") == "stock" else _build_prompt(data)
    errors: list[str] = []

    # ── Gemini 2.0 Flash (free tier) ────────────────────────────────────────
    if GEMINI_API_KEY:
        try:
            r = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": 600, "temperature": 0.4}},
                timeout=15,
            )
            r.raise_for_status()
            body = r.json()
            candidates = body.get("candidates")
            if not candidates:
                raise ValueError(f"No candidates: {body.get('promptFeedback', body)}")
            text = candidates[0]["content"]["parts"][0]["text"]
            return text.strip(), "Gemini 2.0 Flash"
        except Exception as exc:
            errors.append(f"Gemini: {exc}")

    # ── Groq — Llama 3.3 70B (free tier, very fast) ─────────────────────────
    if GROQ_API_KEY:
        try:
            r = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 600,
                      "temperature": 0.4,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=15,
            )
            text = r.json()["choices"][0]["message"]["content"]
            return text.strip(), "Groq (Llama 3.3 70B)"
        except Exception as exc:
            errors.append(f"Groq: {exc}")

    # ── OpenAI GPT-4o-mini ───────────────────────────────────────────────────
    if OPENAI_API_KEY:
        try:
            r = await client.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": "gpt-4o-mini", "max_tokens": 600, "temperature": 0.4,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=15,
            )
            text = r.json()["choices"][0]["message"]["content"]
            return text.strip(), "OpenAI GPT-4o-mini"
        except Exception as exc:
            errors.append(f"OpenAI: {exc}")

    # ── Anthropic Claude Haiku ───────────────────────────────────────────────
    if ANTHROPIC_API_KEY:
        try:
            r = await client.post(
                ANTHROPIC_URL,
                headers={"x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 600,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=15,
            )
            text = r.json()["content"][0]["text"]
            return text.strip(), "Anthropic Claude Haiku"
        except Exception as exc:
            errors.append(f"Anthropic: {exc}")

    # ── Rule-based fallback (always works) ───────────────────────────────────
    note = " | ".join(errors) if errors else "no AI keys configured"
    return _rule_based_summary(data), f"Rule-based ({note})"


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dummy = {
        "asset": "EUR/USD", "last_price": 1.0843, "score": 72, "bias": "up",
        "timeframes": {
            "daily":  {"rsi": 55.0, "macd_above_signal": True, "ma20_above_ma50": True,
                       "trend": "up", "volatility_atr_pct": 0.35, "support": 1.07, "resistance": 1.10},
            "hourly": {"rsi": 60.0, "macd_above_signal": True, "trend": "up"},
        },
        "breakdown": {
            "daily_technical":  {"points": 22, "direction": "up"},
            "hourly_technical": {"points": 19, "direction": "up"},
            "intermarket":      {"points": 20, "direction": "up", "dollar": "weakening"},
            "sentiment":        {"points": 8,  "direction": "up", "label": "bullish", "articles": 12},
            "event_clarity":    {"points": 7,  "high_impact": 1},
        },
        "upcoming_events": [],
    }
    async def _test():
        async with httpx.AsyncClient() as c:
            text, provider = await generate_ai_summary(c, dummy)
            print(f"Provider: {provider}\n\n{text}")
    asyncio.run(_test())
