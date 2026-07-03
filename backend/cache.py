"""Tiny thread-safe TTL cache for the expensive yfinance-backed endpoints.

The /market/* endpoints are pure functions of their inputs (ticker, period,
query) but every call fans out into many slow Yahoo requests — `fundamentals`
alone pulls info, four statement frames, their quarterly variants, analyst
estimates, ownership and insider tables. Without caching, the frontend
auto-loader (which prefetches every holding's detail page) plus ordinary
navigation would re-hit Yahoo on each page reload, which is both slow and a
fast route to getting rate-limited.

This caches successful return values in-process for a configurable TTL. It is
deliberately minimal: no eviction beyond TTL expiry and the whole thing is lost
on restart — the same contract the existing `_SECTOR_CACHE` already relies on.
Exceptions are never cached, so a transient Yahoo failure can be retried on the
next request rather than being remembered for the full TTL.
"""
from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Callable

# key -> (expires_at_monotonic, value)
_store: dict = {}
_lock = threading.Lock()


def _make_key(name: str, args: tuple, kwargs: dict):
    return (name, args, tuple(sorted(kwargs.items())))


def ttl_cache(seconds: float) -> Callable:
    """Memoise a function's successful results for `seconds`.

    Keyed on the call's positional and keyword arguments, so distinct
    tickers / periods are cached independently. Thread-safe: the wrapped
    function runs OUTSIDE the lock, so a slow Yahoo call for one key never
    blocks a cache hit (or a different key's call) on another thread.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = _make_key(fn.__name__, args, kwargs)
            now = time.monotonic()
            with _lock:
                entry = _store.get(key)
                if entry is not None and entry[0] > now:
                    return entry[1]
            result = fn(*args, **kwargs)
            with _lock:
                _store[key] = (now + seconds, result)
            return result

        return wrapper

    return decorator


def cache_clear() -> None:
    """Drop every cached entry (used by tests / manual invalidation)."""
    with _lock:
        _store.clear()
