"""
Login rate limiter — in-memory, no external dependencies.
Policy: 5 failed attempts per IP within a 10-minute sliding window → 429 lockout.
Thread-safe; old entries are evicted lazily on each access.
"""
import time
import threading
from collections import defaultdict

WINDOW   = 600  # seconds (10 min)
MAX_FAIL = 5


_lock:  threading.Lock          = threading.Lock()
_store: dict[str, list[float]]  = defaultdict(list)


def get_client_ip(request) -> str:
    """
    Extract the real client IP.
    Trusts X-Forwarded-For (set by Render / Heroku / nginx proxies).
    """
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(request.client, "host", "unknown")


def _evict(ip: str, now: float) -> list[float]:
    """Return only in-window timestamps and update store in-place (call under lock)."""
    recent = [t for t in _store[ip] if now - t < WINDOW]
    _store[ip] = recent
    return recent


def is_blocked(ip: str) -> tuple[bool, int]:
    """
    Returns (blocked, retry_after_seconds).
    retry_after is 0 when not blocked.
    """
    now = time.monotonic()
    with _lock:
        recent = _evict(ip, now)
        if len(recent) >= MAX_FAIL:
            # Oldest timestamp that is still "counting"
            oldest = sorted(recent)[len(recent) - MAX_FAIL]
            secs   = int(WINDOW - (now - oldest)) + 1
            return True, max(1, secs)
        return False, 0


def record_failure(ip: str) -> int:
    """Record a failed attempt. Returns current in-window failure count."""
    now = time.monotonic()
    with _lock:
        _store[ip].append(now)
        return len(_evict(ip, now))


def clear(ip: str) -> None:
    """Clear all failures on successful login."""
    with _lock:
        _store.pop(ip, None)
