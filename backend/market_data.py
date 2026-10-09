"""Bounded, cached access to yfinance ``.info``.

yfinance's ``Ticker.info`` can hang for ~10 minutes on a delisted / thin ticker
(see the project's yfinance fail-fast note). Every lookup routed through this
module is therefore:

  * **gated** on a short ``history()`` probe — a ticker with no recent history is
    treated as "no data" instead of dragging ``.info`` into a long stall;
  * **bounded** by a hard wall-clock timeout via a worker thread. We use a
    thread (not ``signal.alarm``) because SIGALRM is Unix-only and unusable on
    Windows, which is the dev platform here;
  * **cached** with a short TTL so the same symbol isn't refetched within a burst
    of requests or across back-to-back page loads. This cache is what lets
    ``/portfolio/summary`` and ``/portfolio/holdings`` share one set of quotes
    instead of each independently paying the yfinance cost.

Batched lookups (:func:`get_infos`) run concurrently and share a single
deadline, so N tickers cost ~one timeout in the worst case rather than N.
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import yfinance as yf

from ticker_map import yf_symbol

# Per-batch wall-clock bound for resolving ``.info``.
INFO_TIMEOUT = 8.0
# Successful lookups live longer than empty ones, so a briefly-unavailable
# ticker can recover without being pinned to "no data" for the full window.
_OK_TTL = 300.0
_EMPTY_TTL = 60.0

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yf-info")
# broker-ticker(upper) -> (fetched_at, info_dict)
_cache: dict[str, tuple[float, dict]] = {}
# broker-ticker(upper) -> Future still running past a caller's deadline. Kept so
# a later call collects the eventual result instead of resubmitting — and so a
# deadline miss is never cached as "no data" (that once poisoned USDCZK=X for
# 60s and every position rendered at ≈ -95%).
_inflight: dict[str, Future] = {}


def _ttl(info: dict) -> float:
    return _OK_TTL if info else _EMPTY_TTL


def _raw_info(symbol: str) -> dict:
    """Fetch ``.info`` behind a short ``history()`` fail-fast gate.

    Runs in a worker thread; if the caller's deadline passes this may keep
    running in the background, but it never blocks the request past the
    deadline.
    """
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist is None or hist.empty:
            return {}
        return t.info or {}
    except Exception:
        return {}


def get_infos(tickers, timeout: float = INFO_TIMEOUT) -> dict[str, dict]:
    """Resolve many tickers' ``.info`` concurrently under a shared deadline.

    Broker symbols are mapped via :func:`yf_symbol`; results are cached and
    keyed by the original (broker) ticker. Always returns an entry for every
    requested ticker (``{}`` when unavailable).
    """
    out: dict[str, dict] = {}
    pending: dict[str, Future] = {}
    now = time.time()
    for tk in tickers:
        key = (tk or "").upper()
        if not key:
            out[tk] = {}
            continue
        cached = _cache.get(key)
        if cached and now - cached[0] < _ttl(cached[1]):
            out[tk] = cached[1]
        elif key not in pending:
            fut = _inflight.get(key)
            if fut is None:
                fut = _executor.submit(_raw_info, yf_symbol(tk))
                _inflight[key] = fut
            pending[key] = fut

    if pending:
        deadline = time.time() + timeout
        for key, fut in pending.items():
            remaining = max(0.1, deadline - time.time())
            try:
                info = fut.result(timeout=remaining) or {}
            except TimeoutError:
                # Still running — leave it in _inflight for a later call to
                # collect; caching {} here would pin "no data" for _EMPTY_TTL.
                continue
            except Exception:
                info = {}
            _cache[key] = (time.time(), info)
            _inflight.pop(key, None)

    for tk in tickers:
        if tk not in out:
            out[tk] = _cache.get((tk or "").upper(), (0.0, {}))[1]
    return out


def get_info(ticker: str, timeout: float = INFO_TIMEOUT) -> dict:
    """Bounded, cached ``.info`` for a single ticker (``{}`` when unavailable)."""
    return get_infos([ticker], timeout=timeout).get(ticker, {})


def quote(info: dict, fallback: str) -> tuple[float, str, str]:
    """Extract ``(price, name, currency)`` from an info dict with safe fallbacks."""
    raw = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
        or 0
    )
    try:
        price = float(raw or 0)
    except (TypeError, ValueError):
        price = 0.0
    name = info.get("shortName") or info.get("longName") or fallback
    ccy = info.get("currency") or "USD"
    return price, name, ccy


PRICE_SOURCE = "Yahoo Finance"
# A close older than this is stale: it covers a long weekend plus a holiday,
# so only a delisted, suspended or broken symbol crosses it.
STALE_AFTER = timedelta(days=5)


def price_freshness(info: dict, price: float, now: datetime | None = None) -> dict:
    """When ``price`` was set and whether it can be trusted.

    ``price_status`` is one of ``missing`` (no usable price, valued as 0),
    ``stale`` (older than :data:`STALE_AFTER`), ``live`` / ``delayed`` (market
    open), ``closed`` (last close), or ``unknown`` (Yahoo sent no quote time).
    """
    now = now or datetime.now(timezone.utc)
    try:
        as_of = datetime.fromtimestamp(int(info["regularMarketTime"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        as_of = None
    delay = None
    if as_of is not None:
        if "real time" in str(info.get("quoteSourceName") or "").lower():
            delay = 0
        else:
            try:
                delay = int(info.get("exchangeDataDelayedBy") or 0)
            except (TypeError, ValueError):
                delay = 0

    if not price or price <= 0:
        status = "missing"
    elif as_of is None:
        status = "unknown"
    elif now - as_of > STALE_AFTER:
        status = "stale"
    elif info.get("marketState") == "REGULAR":
        status = "delayed" if delay else "live"
    else:
        status = "closed"

    return {
        "price_status": status,
        "price_as_of": as_of.isoformat().replace("+00:00", "Z") if as_of else None,
        "price_delay_minutes": delay,
        "price_source": PRICE_SOURCE,
    }


def run_bounded(fn, *args, timeout: float = INFO_TIMEOUT, default=None):
    """Run ``fn(*args)`` in a worker thread, returning ``default`` if it raises
    or doesn't finish within ``timeout``. For one-off blocking yfinance calls
    (e.g. the autocomplete search) that aren't ``.info`` but can still stall."""
    fut = _executor.submit(fn, *args)
    try:
        return fut.result(timeout=timeout)
    except Exception:
        return default
