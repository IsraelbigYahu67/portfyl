"""Tiny thread-safe, size-bounded TTL cache for the expensive yfinance-backed endpoints.

The /market/* endpoints are pure functions of their inputs (ticker, period,
query) but every call fans out into many slow Yahoo requests — `fundamentals`
alone pulls info, four statement frames, their quarterly variants, analyst
estimates, ownership and insider tables. Without caching, the frontend
auto-loader (which prefetches every holding's detail page) plus ordinary
navigation would re-hit Yahoo on each page reload, which is both slow and a
fast route to getting rate-limited.

This caches successful return values in-process for a configurable TTL. Keys
come from user input (ticker, query, period, view), so every cache is also
capped at `maxsize` entries: expired entries are pruned on write and, when
the cache is still full, the least recently used entry is evicted. A
long-lived Cloud Run instance therefore cannot grow without bound. The whole
thing is lost on restart. Exceptions are never cached, so a transient Yahoo
failure can be retried on the next request rather than being remembered for
the full TTL.

`BoundedTTLCache` is also the building block for the hand-rolled module-level
caches in `market_data`, `fx` and `routers/market`.
"""
from __future__ import annotations

import asyncio
import threading
import time
import weakref
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable

DEFAULT_MAXSIZE = 256
# Expired entries are swept at most this often by writes (an O(n) pass); a
# full cache falls back to LRU eviction in between.
DEFAULT_PRUNE_INTERVAL = 30.0

_MISSING = object()
_UNSET = object()


class BoundedTTLCache:
    """Thread-safe LRU cache with a TTL, capped at ``maxsize`` entries.

    * ``ttl`` is the default lifetime in seconds (``None`` = never expires);
      :meth:`set` can override it per entry.
    * Reading a live entry marks it most recently used; reading an expired one
      removes it.
    * Writing first sweeps expired entries (at most once per
      ``prune_interval``), then evicts least recently used ones until the cache
      fits ``maxsize``.

    The mapping protocol subset (``[]``, ``in``, ``get``, ``pop``, ``clear``,
    ``len``) matches ``dict``, so it can replace a module-level dict without
    touching its call sites. ``len`` may still count expired entries that have
    not been swept yet. The clock is looked up as ``time.monotonic`` on every
    call so tests can patch it.
    """

    def __init__(self, maxsize: int, ttl: float | None = None, *,
                 prune_interval: float = DEFAULT_PRUNE_INTERVAL):
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self.maxsize = maxsize
        self.ttl = ttl
        self._prune_interval = prune_interval
        self._next_prune = 0.0
        # key -> (expires_at_monotonic or None, value), least recently used first
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return default
            expires, value = item
            if expires is not None and expires <= time.monotonic():
                del self._data[key]
                return default
            self._data.move_to_end(key)
            return value

    def set(self, key, value, ttl: Any = _UNSET) -> None:
        ttl = self.ttl if ttl is _UNSET else ttl
        now = time.monotonic()
        expires = None if ttl is None else now + ttl
        with self._lock:
            self._data[key] = (expires, value)
            self._data.move_to_end(key)
            if now >= self._next_prune:
                self._prune_expired(now)
                self._next_prune = now + self._prune_interval
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def pop(self, key, default=_MISSING):
        with self._lock:
            item = self._data.pop(key, None)
        if item is None or (item[0] is not None and item[0] <= time.monotonic()):
            if default is _MISSING:
                raise KeyError(key)
            return default
        return item[1]

    def prune(self) -> None:
        """Drop every expired entry now."""
        with self._lock:
            self._prune_expired(time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _prune_expired(self, now: float) -> None:
        expired = [k for k, (exp, _) in self._data.items() if exp is not None and exp <= now]
        for k in expired:
            del self._data[k]

    def __getitem__(self, key):
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value) -> None:
        self.set(key, value)

    def __contains__(self, key) -> bool:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return False
            return item[0] is None or item[0] > time.monotonic()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


# Every cache a `ttl_cache` decorator created, so `cache_clear()` can drop them
# all. Weak, so a decorated function that goes away takes its cache with it.
_registry: "weakref.WeakSet[BoundedTTLCache]" = weakref.WeakSet()
_registry_lock = threading.Lock()


def _make_key(args: tuple, kwargs: dict):
    return (args, tuple(sorted(kwargs.items())))


def ttl_cache(seconds: float, maxsize: int = DEFAULT_MAXSIZE) -> Callable:
    """Memoise a function's successful results for `seconds`, keeping at most
    `maxsize` distinct argument combinations (least recently used go first).

    Keyed on the call's positional and keyword arguments, so distinct
    tickers / periods are cached independently. Thread-safe: the wrapped
    function runs OUTSIDE the lock, so a slow Yahoo call for one key never
    blocks a cache hit (or a different key's call) on another thread.
    Exceptions are never cached.
    """

    def decorator(fn):
        cache = BoundedTTLCache(maxsize, seconds)
        with _registry_lock:
            _registry.add(cache)

        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                key = _make_key(args, kwargs)
                hit = cache.get(key, _MISSING)
                if hit is not _MISSING:
                    return hit
                result = await fn(*args, **kwargs)
                cache.set(key, result)
                return result

            async_wrapper.cache = cache
            return async_wrapper

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            hit = cache.get(key, _MISSING)
            if hit is not _MISSING:
                return hit
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache
        return wrapper

    return decorator


def cache_clear() -> None:
    """Drop every `ttl_cache` entry (used by tests / manual invalidation)."""
    with _registry_lock:
        caches = list(_registry)
    for cache in caches:
        cache.clear()


def tenant_cache_key(workspace_id, resource_public_id, *rest) -> tuple:
    """Build a cache key for a per-process, per-resource cache that isn't
    already covered by `ttl_cache`'s own arg-based keying (e.g. a hand-rolled
    module-level dict).

    A resource's internal integer primary key is NOT safe to key on alone:
    the SQLite-to-PostgreSQL owner importer preserves each migrated owner's
    original row ids verbatim (see migrations/sqlite_to_postgres.py), so two
    different workspaces can end up with rows sharing the same legacy integer
    id. Leading the key with `(workspace_id, resource_public_id)` -- both
    tenant-unique -- means a cache collision between two workspaces is
    impossible regardless of what the underlying integer ids happen to be.
    """
    return (workspace_id, resource_public_id, *rest)
