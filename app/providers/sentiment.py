"""
News sentiment via NewsAPI.org (primary) or Alpha Vantage (fallback).
Returns score, label, article_count, and top-3 headlines.
Run directly: python -m app.providers.sentiment
"""
import asyncio
import re

import httpx

from app.config import NEWSAPI_KEY, NEWSAPI_URL, ALPHA_VANTAGE_KEY, AV_BASE

_BULLISH = {
    "rally", "rallies", "surge", "surges", "surged", "gain", "gains", "gained",
    "bullish", "rise", "rises", "rose", "strong", "strength", "positive",
    "growth", "recover", "recovery", "increase", "increases", "upside",
    "advance", "advances", "advanced", "outperform", "beat", "beats", "exceed",
    "breakout", "momentum", "buying", "soar", "soars", "soared", "rebound",
}

_BEARISH = {
    "fall", "falls", "fell", "drop", "drops", "dropped", "decline", "declines",
    "declined", "bearish", "weak", "weakness", "down", "downside", "negative",
    "crash", "crashes", "decrease", "decreases", "selloff", "sell-off",
    "concern", "concerns", "miss", "misses", "disappoint", "disappoints",
    "breakdown", "pressure", "risk", "risks", "warning", "slump", "slumps",
    "tumble", "tumbles", "tumbled", "plunge", "plunges", "plunged",
}


def _score_text(text: str) -> float:
    words = re.findall(r"\b[a-z]+\b", text.lower())
    if not words:
        return 0.0
    bull  = sum(1 for w in words if w in _BULLISH)
    bear  = sum(1 for w in words if w in _BEARISH)
    total = bull + bear
    return (bull - bear) / total if total else 0.0


async def fetch_sentiment(client: httpx.AsyncClient, ticker: str) -> dict:
    """
    Returns: score (float), label (str), article_count (int), headlines (list).
    ticker format: 'FOREX:EURUSD' for forex, 'AAPL' for stocks.
    Always returns a valid dict.
    """
    if NEWSAPI_KEY:
        return await _fetch_newsapi(client, ticker)
    if ALPHA_VANTAGE_KEY:
        return await _fetch_alphavantage(client, ticker)
    return {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}


async def _fetch_newsapi(client: httpx.AsyncClient, ticker: str) -> dict:
    if ticker.startswith("FOREX:"):
        pair  = ticker[6:]
        query = f"{pair[:3]}/{pair[3:]} forex currency"
    else:
        query = f"{ticker} stock market"

    try:
        r = await client.get(
            NEWSAPI_URL,
            params={
                "q":        query,
                "language": "en",
                "pageSize": "20",
                "sortBy":   "publishedAt",
                "apiKey":   NEWSAPI_KEY,
            },
            timeout=15,
        )
        r.raise_for_status()
        data     = r.json()
        articles = data.get("articles", [])
        if not articles:
            return {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}

        scores:    list[float] = []
        headlines: list[dict]  = []
        for art in articles:
            title = art.get("title") or ""
            desc  = art.get("description") or ""
            scores.append(_score_text(f"{title} {desc}"))
            if len(headlines) < 3 and title and art.get("url"):
                headlines.append({
                    "title":  title,
                    "url":    art["url"],
                    "source": (art.get("source") or {}).get("name", ""),
                })

        avg   = sum(scores) / len(scores) if scores else 0.0
        label = "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral"
        return {
            "score":         round(avg, 4),
            "label":         label,
            "article_count": len(articles),
            "headlines":     headlines,
        }
    except Exception:
        return {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}


async def _fetch_alphavantage(client: httpx.AsyncClient, ticker: str) -> dict:
    try:
        r    = await client.get(
            AV_BASE,
            params={"function": "NEWS_SENTIMENT", "tickers": ticker,
                    "apikey": ALPHA_VANTAGE_KEY, "limit": "50"},
            timeout=15,
        )
        data = r.json()
        feed = data.get("feed", [])
        if not feed:
            return {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}

        scores:    list[float] = []
        headlines: list[dict]  = []
        for item in feed:
            for ts in item.get("ticker_sentiment", []):
                if ts.get("ticker") == ticker:
                    scores.append(float(ts.get("ticker_sentiment_score", 0)))
            if len(headlines) < 3 and item.get("title") and item.get("url"):
                headlines.append({
                    "title":  item["title"],
                    "url":    item["url"],
                    "source": item.get("source", ""),
                })
        if not scores:
            scores = [float(i.get("overall_sentiment_score", 0)) for i in feed]

        avg   = sum(scores) / len(scores) if scores else 0.0
        label = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
        return {
            "score":         round(avg, 4),
            "label":         label,
            "article_count": len(feed),
            "headlines":     headlines,
        }
    except Exception:
        return {"score": 0.0, "label": "neutral", "article_count": 0, "headlines": []}


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            print(await fetch_sentiment(c, "FOREX:EURUSD"))
            print(await fetch_sentiment(c, "AAPL"))
    asyncio.run(_test())
