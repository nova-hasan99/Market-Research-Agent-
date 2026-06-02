"""
Economic calendar via Finnhub — upcoming high/medium impact events.
Run directly: python -m app.providers.calendar
"""
import asyncio
from datetime import datetime, timezone

import httpx

from app.config import FINNHUB_KEY, FINNHUB_BASE


async def fetch_events(client: httpx.AsyncClient) -> list[dict]:
    """
    Returns up to 12 upcoming high/medium-impact economic events sorted by time.
    Always returns a list — never raises.
    """
    if not FINNHUB_KEY:
        return []
    try:
        r    = await client.get(f"{FINNHUB_BASE}/calendar/economic",
                                params={"token": FINNHUB_KEY}, timeout=15)
        data = r.json()
        events = data.get("economicCalendar", []) if isinstance(data, dict) else []
        now    = datetime.now(timezone.utc)
        result = []
        for ev in events:
            impact = str(ev.get("impact", "")).lower()
            if impact not in ("high", "3", "medium", "2"):
                continue
            raw_time = ev.get("time")
            try:
                ev_time = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if ev_time < now:
                    continue
            except (ValueError, TypeError):
                pass
            result.append({
                "event":    ev.get("event"),
                "country":  ev.get("country"),
                "impact":   impact,
                "time":     raw_time,
                "estimate": ev.get("estimate"),
                "actual":   ev.get("actual"),
            })
        result.sort(key=lambda e: e.get("time") or "")
        return result[:12]
    except Exception:
        return []


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        async with httpx.AsyncClient() as c:
            events = await fetch_events(c)
            print(f"Got {len(events)} events")
            for e in events[:3]:
                print(e)
    asyncio.run(_test())
