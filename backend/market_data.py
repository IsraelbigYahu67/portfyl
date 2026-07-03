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
            pending[key] = _executor.submit(_raw_info, yf_symbol(tk))

    if pending:
        deadline = time.time() + timeout
        for key, fut in pending.items():
            remaining = max(0.1, deadline - time.time())
            try:
                info = fut.result(timeout=remaining) or {}
            except Exception:
                info = {}
            _cache[key] = (time.time(), info)

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


def run_bounded(fn, *args, timeout: float = INFO_TIMEOUT, default=None):
    """Run ``fn(*args)`` in a worker thread, returning ``default`` if it raises
    or doesn't finish within ``timeout``. For one-off blocking yfinance calls
    (e.g. the autocomplete search) that aren't ``.info`` but can still stall."""
    fut = _executor.submit(fn, *args)
    try:
        return fut.result(timeout=timeout)
    except Exception:
        return default
