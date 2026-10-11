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

import threading
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


def _release_db() -> None:
    """Hand the current request's DB connection back before waiting on Yahoo.

    Imported lazily so this module keeps working where no database is
    configured (scripts, the market-data unit tests).
    """
    from database import release_request_connections

    release_request_connections()


def ticker(symbol: str):
    """``yf.Ticker`` for request code: frees the request's DB connection first.

    The Ticker's network calls happen when its attributes are read, so call
    this after the last database read that precedes them.
    """
    _release_db()
    return yf.Ticker(symbol)


# Shared across requests. One dashboard load used to fetch the same Yahoo
# data several times: the 2-day closes of every holding three times
# (summary, heatmap, movers), the price history twice (performance, risk
# metrics), and per-ticker dividends / calendar / earnings dates one ticker
# after another, on every load.
DOWNLOAD_TTL = 300.0
_DOWNLOAD_CACHE_MAX = 128
TICKER_ATTR_TTL = 6 * 3600.0
_shared_lock = threading.Lock()
# key -> (stored_at, ttl, result)
_download_cache: dict[tuple, tuple[float, float, object]] = {}
_download_inflight: dict[tuple, Future] = {}
# (symbol, attribute) -> (stored_at, ttl, value)
_attr_cache: dict[tuple[str, str], tuple[float, float, object]] = {}
_attr_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yf-attr")


def clear_shared_caches() -> None:
    with _shared_lock:
        _download_cache.clear()
        _download_inflight.clear()
        _attr_cache.clear()


def _freeze(value):
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    return value


def _private_copy(value):
    return value.copy() if hasattr(value, "copy") else value


def download(*args, **kwargs):
    """``yf.download`` for request code: frees the request's DB connection
    first, and shares the result with identical calls for DOWNLOAD_TTL.

    Concurrent identical calls wait for the first one instead of asking Yahoo
    again. Every caller gets its own copy, so mutating it is safe. A failure
    is never cached, and an empty result (yfinance's answer to most errors)
    only for _EMPTY_TTL."""
    _release_db()
    key = (_freeze(args), _freeze(kwargs))
    with _shared_lock:
        hit = _download_cache.get(key)
        if hit and time.monotonic() - hit[0] < hit[1]:
            return _private_copy(hit[2])
        pending = _download_inflight.get(key)
        if pending is None:
            pending = _download_inflight[key] = Future()
            owner = True
        else:
            owner = False
    if not owner:
        return _private_copy(pending.result())
    try:
        result = yf.download(*args, **kwargs)
    except BaseException as exc:
        with _shared_lock:
            _download_inflight.pop(key, None)
        pending.set_exception(exc)
        raise
    ttl = _EMPTY_TTL if getattr(result, "empty", False) else DOWNLOAD_TTL
    with _shared_lock:
        _download_inflight.pop(key, None)
        _download_cache[key] = (time.monotonic(), ttl, result)
        if len(_download_cache) > _DOWNLOAD_CACHE_MAX:
            oldest = min(_download_cache, key=lambda k: _download_cache[k][0])
            del _download_cache[oldest]
    pending.set_result(result)
    return _private_copy(result)


def _fetch_attr(symbol: str, attr: str):
    try:
        return getattr(yf.Ticker(symbol), attr), True
    except Exception:
        return None, False


def ticker_attrs(symbols, attr: str, ttl: float = TICKER_ATTR_TTL) -> dict:
    """``{symbol: yf.Ticker(symbol).<attr>}`` for slow per-ticker lookups
    (dividends, calendar, earnings_dates), fetched in parallel and cached for
    ``ttl``. A lookup that raises maps to None and is retried after
    _EMPTY_TTL. Values are shared between callers: do not mutate them."""
    out: dict = {}
    missing: list[str] = []
    now = time.monotonic()
    with _shared_lock:
        for symbol in dict.fromkeys(symbols):
            hit = _attr_cache.get((symbol, attr))
            if hit and now - hit[0] < hit[1]:
                out[symbol] = hit[2]
            else:
                missing.append(symbol)
    if missing:
        _release_db()
        futures = {s: _attr_executor.submit(_fetch_attr, s, attr) for s in missing}
        for symbol, future in futures.items():
            value, ok = future.result()
            out[symbol] = value
            with _shared_lock:
                _attr_cache[(symbol, attr)] = (time.monotonic(), ttl if ok else _EMPTY_TTL, value)
    return out


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
            if not pending:
                # Before the first submit: the worker may reach Yahoo at once.
                _release_db()
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
