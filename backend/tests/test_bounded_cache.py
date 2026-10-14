"""Size and TTL bounds of the in-process caches (review finding N14).

Cache keys come from user input, so a long-lived instance must not keep every
key it ever saw.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future

import pandas as pd
import pytest
import yfinance as yf

import cache as cache_mod
import fx
import market_data
from cache import BoundedTTLCache, cache_clear, ttl_cache


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cache_mod.time, "monotonic", lambda: now[0])
    return now


class TestBoundedTTLCache:
    def test_size_is_capped_and_oldest_is_evicted(self):
        c = BoundedTTLCache(3)
        for i in range(5):
            c[i] = i
        assert len(c) == 3
        assert [i in c for i in range(5)] == [False, False, True, True, True]

    def test_eviction_is_least_recently_used(self):
        c = BoundedTTLCache(3)
        c["a"], c["b"], c["c"] = 1, 2, 3
        assert c.get("a") == 1  # touch: "b" is now the oldest
        c["d"] = 4
        assert "b" not in c
        assert all(k in c for k in ("a", "c", "d"))

    def test_rewriting_a_key_refreshes_its_position(self):
        c = BoundedTTLCache(2)
        c["a"], c["b"] = 1, 2
        c["a"] = 10
        c["c"] = 3
        assert c.get("a") == 10
        assert "b" not in c

    def test_entries_expire_after_ttl(self, clock):
        c = BoundedTTLCache(10, ttl=60)
        c["a"] = 1
        clock[0] += 59
        assert c.get("a") == 1
        clock[0] += 2
        assert c.get("a", "gone") == "gone"
        assert "a" not in c
        assert len(c) == 0  # reading an expired entry removes it

    def test_per_entry_ttl_overrides_default(self, clock):
        c = BoundedTTLCache(10, ttl=60)
        c.set("short", 1, ttl=5)
        c.set("forever", 2, ttl=None)
        clock[0] += 3600
        assert "short" not in c
        assert c.get("forever") == 2

    def test_expired_entries_are_pruned_on_write(self, clock):
        c = BoundedTTLCache(100, ttl=10, prune_interval=0)
        for i in range(20):
            c[i] = i
        clock[0] += 11
        c["fresh"] = 1
        assert len(c) == 1  # the 20 stale ones are gone, not just hidden

    def test_prune_is_throttled_but_size_cap_still_holds(self, clock):
        c = BoundedTTLCache(5, ttl=10, prune_interval=1000)
        for i in range(50):
            c[i] = i
            clock[0] += 1
        assert len(c) <= 5

    def test_expiry_beats_lru_when_pruning(self, clock):
        c = BoundedTTLCache(2, ttl=None, prune_interval=0)
        c.set("old", 1, ttl=5)
        c.set("keep", 2, ttl=None)
        c.get("old")  # most recently used, but about to expire
        clock[0] += 10
        c["new"] = 3
        assert "old" not in c
        assert c.get("keep") == 2 and c.get("new") == 3

    def test_pop_and_getitem(self, clock):
        c = BoundedTTLCache(3, ttl=5)
        c["a"] = 1
        assert c["a"] == 1
        assert c.pop("a") == 1
        assert c.pop("a", "x") == "x"
        with pytest.raises(KeyError):
            c["a"]
        with pytest.raises(KeyError):
            c.pop("a")
        c["b"] = 2
        clock[0] += 10
        assert c.pop("b", None) is None  # expired counts as absent

    def test_none_is_a_cacheable_value(self):
        c = BoundedTTLCache(3)
        c["a"] = None
        assert "a" in c
        assert c.get("a", "miss") is None

    def test_maxsize_must_be_positive(self):
        with pytest.raises(ValueError):
            BoundedTTLCache(0)

    def test_concurrent_writers_never_exceed_the_cap(self):
        c = BoundedTTLCache(50, ttl=60, prune_interval=0)
        errors = []

        def work(n):
            try:
                for i in range(500):
                    k = (n, i % 80)
                    c[k] = i
                    c.get((n, (i * 7) % 80))
                    assert len(c) <= 50
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert not errors
        assert len(c) <= 50


class TestTtlCacheDecorator:
    def setup_method(self):
        cache_clear()

    def test_distinct_arguments_are_bounded_by_maxsize(self):
        calls = []

        @ttl_cache(60, maxsize=3)
        def f(x):
            calls.append(x)
            return x

        for i in range(10):
            f(i)
        assert len(f.cache) == 3
        f(9)  # still cached
        assert calls.count(9) == 1
        f(0)  # evicted long ago, computed again
        assert calls.count(0) == 2

    def test_lru_order_across_calls(self):
        calls = []

        @ttl_cache(60, maxsize=2)
        def f(x):
            calls.append(x)
            return x

        f("a"), f("b"), f("a"), f("c")  # "b" is evicted, "a" survives
        f("a")
        assert calls == ["a", "b", "c"]
        f("b")
        assert calls == ["a", "b", "c", "b"]

    def test_expiry_frees_the_entry(self, clock):
        calls = []

        @ttl_cache(10)
        def f(x):
            calls.append(x)
            return x

        f(1)
        clock[0] += 11
        f(1)
        assert calls == [1, 1]

    def test_exceptions_are_not_cached(self):
        calls = []

        @ttl_cache(60, maxsize=4)
        def f(x):
            calls.append(x)
            if len(calls) == 1:
                raise ValueError("boom")
            return x

        with pytest.raises(ValueError):
            f(1)
        assert len(f.cache) == 0
        assert f(1) == 1
        assert f(1) == 1
        assert calls == [1, 1]

    def test_none_result_is_cached(self):
        calls = []

        @ttl_cache(60)
        def f():
            calls.append(1)

        f(), f()
        assert calls == [1]

    def test_async_variant_is_bounded_and_skips_exceptions(self):
        calls = []

        @ttl_cache(60, maxsize=2)
        async def f(x):
            calls.append(x)
            if x == "bad" and calls.count("bad") == 1:
                raise RuntimeError("boom")
            return x * 2

        async def run():
            with pytest.raises(RuntimeError):
                await f("bad")
            assert await f("bad") == "badbad"
            assert await f("a") == "aa"
            assert await f("a") == "aa"
            assert await f("b") == "bb"  # evicts "bad"
            return len(f.cache)

        assert asyncio.run(run()) == 2
        assert calls == ["bad", "bad", "a", "b"]

    def test_cache_clear_empties_every_decorated_function(self):
        @ttl_cache(60)
        def f(x):
            return x

        @ttl_cache(60)
        async def g(x):
            return x

        f(1)
        asyncio.run(g(1))
        cache_clear()
        assert len(f.cache) == 0 and len(g.cache) == 0

    def test_same_name_functions_do_not_share_entries(self):
        def make(value):
            @ttl_cache(60)
            def get(x):
                return value
            return get

        assert make("one")(1) == "one"
        assert make("two")(1) == "two"

    def test_concurrent_calls_stay_bounded(self):
        @ttl_cache(60, maxsize=10)
        def f(x):
            return x * x

        def work(n):
            for i in range(300):
                assert f((n * 1000 + i) % 97) == ((n * 1000 + i) % 97) ** 2

        threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert len(f.cache) <= 10


class TestMarketDataCaches:
    @pytest.fixture(autouse=True)
    def _clean(self):
        market_data.clear_shared_caches()
        market_data._cache.clear()
        market_data._inflight.clear()
        yield
        market_data.clear_shared_caches()
        market_data._cache.clear()
        market_data._inflight.clear()

    def test_info_cache_is_bounded(self, monkeypatch):
        monkeypatch.setattr(market_data, "_cache", BoundedTTLCache(5, ttl=300))
        monkeypatch.setattr(market_data, "_raw_info", lambda sym: {"symbol": sym})
        symbols = [f"T{i}" for i in range(20)]

        out = market_data.get_infos(symbols, timeout=5)

        assert len(market_data._cache) <= 5
        # a batch bigger than the cache still returns every result
        assert all(out[s] == {"symbol": s} for s in symbols)

    def test_abandoned_futures_expire_and_are_bounded(self, clock, monkeypatch):
        inflight = BoundedTTLCache(4, ttl=market_data._INFLIGHT_TTL, prune_interval=0)
        monkeypatch.setattr(market_data, "_inflight", inflight)
        for i in range(10):
            inflight[f"T{i}"] = Future()  # never collected
        assert len(inflight) <= 4

        clock[0] += market_data._INFLIGHT_TTL + 1
        inflight["fresh"] = Future()
        assert len(inflight) == 1

    def test_download_cache_is_bounded(self, monkeypatch):
        monkeypatch.setattr(market_data, "_download_cache", BoundedTTLCache(3))
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame({"Close": [1.0]}))

        for i in range(10):
            market_data.download(f"T{i}", period="2d")

        assert len(market_data._download_cache) == 3

    def test_empty_download_uses_the_short_ttl(self, clock, monkeypatch):
        calls = []
        monkeypatch.setattr(yf, "download", lambda *a, **k: calls.append(1) or pd.DataFrame())

        market_data.download("X", period="2d")
        clock[0] += market_data._EMPTY_TTL + 1
        market_data.download("X", period="2d")

        assert len(calls) == 2

    def test_ticker_attr_cache_is_bounded_and_expires(self, clock, monkeypatch):
        monkeypatch.setattr(market_data, "_attr_cache", BoundedTTLCache(4))

        class T:
            def __init__(self, symbol):
                self.symbol = symbol

            @property
            def dividends(self):
                return self.symbol

        monkeypatch.setattr(yf, "Ticker", T)
        symbols = [f"S{i}" for i in range(12)]
        out = market_data.ticker_attrs(symbols, "dividends", ttl=100)

        assert out == {s: s for s in symbols}
        assert len(market_data._attr_cache) <= 4

        market_data.ticker_attrs(["S11"], "dividends", ttl=100)
        clock[0] += 101
        assert ("S11", "dividends") not in market_data._attr_cache


class TestFxCache:
    def test_daily_cache_is_bounded(self, monkeypatch):
        monkeypatch.setattr(fx, "_DAILY_CACHE", BoundedTTLCache(3, ttl=3600))
        idx = pd.to_datetime(["2025-12-30", "2026-01-02"])
        monkeypatch.setattr(
            market_data, "download", lambda *a, **k: pd.DataFrame({"Close": [21.0, 22.0]}, index=idx)
        )

        from datetime import date, timedelta

        for i in range(10):
            assert fx.fetch_fx_to_czk("USD", date(2026, 1, 2) + timedelta(days=i)) == 22.0

        assert len(fx._DAILY_CACHE) == 3

    def test_repeat_lookup_hits_the_cache(self, monkeypatch):
        monkeypatch.setattr(fx, "_DAILY_CACHE", BoundedTTLCache(8, ttl=3600))
        calls = []
        idx = pd.to_datetime(["2025-12-30", "2026-01-02"])

        def download(*a, **k):
            calls.append(1)
            return pd.DataFrame({"Close": [21.0, 22.0]}, index=idx)

        monkeypatch.setattr(market_data, "download", download)
        from datetime import date

        fx.fetch_fx_to_czk("EUR", date(2026, 1, 2))
        fx.fetch_fx_to_czk("EUR", date(2026, 1, 2))
        assert len(calls) == 1
