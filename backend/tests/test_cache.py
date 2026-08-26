"""Tests for the in-process TTL cache."""

from __future__ import annotations

import asyncio
import time

import pytest

from cache import ttl_cache, cache_clear


class TestTTLCache:
    def setup_method(self):
        cache_clear()

    def test_cache_hit(self):
        """Second call with same args returns cached value."""
        call_count = 0

        @ttl_cache(seconds=60)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert call_count == 1
        assert add(1, 2) == 3
        assert call_count == 1  # still 1 — cache hit

    def test_cache_miss_different_args(self):
        """Different args → different cache keys, both call the function."""
        call_count = 0

        @ttl_cache(seconds=60)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(3, 4) == 7
        assert call_count == 2

    def test_cache_expiry(self):
        """After TTL expires, the function is called again."""
        call_count = 0

        @ttl_cache(seconds=0.05)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert call_count == 1
        time.sleep(0.15)
        assert add(1, 2) == 3
        assert call_count == 2  # expired, called again

    def test_exceptions_not_cached(self):
        """A raised exception is never stored."""
        call_count = 0

        @ttl_cache(seconds=60)
        def maybe_fail(v):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("fail")
            return v

        with pytest.raises(ValueError):
            maybe_fail(42)

        # Second call should NOT return cached exception; it re-runs.
        assert maybe_fail(42) == 42
        assert call_count == 2

    def test_cache_keyed_on_kwargs(self):
        """Keyword arguments are part of the cache key."""
        call_count = 0

        @ttl_cache(seconds=60)
        def fn(a, b=1):
            nonlocal call_count
            call_count += 1
            return a + b

        assert fn(1, b=2) == 3
        assert call_count == 1
        assert fn(1, b=2) == 3
        assert call_count == 1  # hit
        assert fn(1, b=3) == 4
        assert call_count == 2  # miss — different kwarg

    def test_clear(self):
        """cache_clear() removes all entries."""
        call_count = 0

        @ttl_cache(seconds=60)
        def fn():
            nonlocal call_count
            call_count += 1
            return 42

        assert fn() == 42
        cache_clear()
        assert fn() == 42
        assert call_count == 2

    def test_async_function_is_awaited_and_cached(self):
        """ttl_cache must detect `async def` functions and await them --
        otherwise it caches (and returns) an unawaited coroutine object,
        which is what the political-trades endpoint (an async FastAPI route)
        needs this decorator to support correctly."""
        call_count = 0

        @ttl_cache(seconds=60)
        async def fetch(a):
            nonlocal call_count
            call_count += 1
            return a * 2

        assert asyncio.run(fetch(3)) == 6
        assert call_count == 1
        assert asyncio.run(fetch(3)) == 6
        assert call_count == 1  # cache hit, not a coroutine object
        assert asyncio.run(fetch(4)) == 8
        assert call_count == 2  # different args, miss
