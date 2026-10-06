"""Trading 212 snapshot-first synchronization.

Task 2 of docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md: make
a connected portfolio's current holdings and account value available from
`/equity/account/summary` and `/equity/positions` alone, independent of the
(much slower) full order/dividend history sync in `routers/broker.py`.

Positions are a current-value surface only. They never substitute for the
transaction ledger in historical performance, FIFO, or tax calculations --
see `broker_cash.py` for the analogous current-cash snapshot, and the plan's
§2 user-facing data contract.

NOTE: like the existing `/equity/account/summary` mapping in routers/broker.py,
the `/equity/positions` field names below (ticker, quantity, averagePrice,
currentPrice, ppl, fxPpl, initialFillDate, pieQuantity) are verified only
against Trading 212's published API docs and hand-written test fixtures, not
a live account. `/equity/positions` does not return instrument name or
currency, so `BrokerPosition.name`/`.currency` are left unset here; callers
that need them derive currency best-effort from existing ledger rows.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from fx import bulk_fetch_fx
from models import (
    BrokerConnection,
    BrokerPosition,
    BrokerSyncEvent,
    BrokerSyncRun,
    Portfolio,
    Transaction,
)
from ledger_mutation import acquire_workspace_ledger_lock
from t212_cash import CashRow, UnsupportedCash, cash_event_id, cash_event_time, map_cash_event
from t212_incremental import OVERLAP_PAGES, evaluate_page

log = logging.getLogger("portfyl.t212_sync")

T212_BASES = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}


def _t212_base(environment: str) -> str:
    return T212_BASES.get(environment, T212_BASES["live"])


def _t212_headers(api_key: str, api_secret: str = "") -> dict:
    if api_secret:
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {"Authorization": api_key}


_T212_TICKER_RENAMES = {
    "AGC": "GRAB",
    "IPOE": "SOFI",
    "IVAN": "SES",
    "IPXX": "USAR",
    "RSTN": "GIFT",
    "OAC": "HIMS",
    "LION": "SMX",
    # SPAC tickers that already de-SPAC'd into the named operating company
    "SNII": "RGTI",
    # Renamed US listings that T212 still reports under the old ticker
    "FB": "META",
    "PCLN": "BKNG",
    # Class shares — Yahoo uses dash, T212 uses underscore
    "BRK_B": "BRK-B",
    "BRK_A": "BRK-A",
    # LSE-listed UCITS ETFs whose base ticker doesn't carry a T212 exchange suffix
    "CSPX": "CSPX.L",
    "CNDX": "CNDX.L",
    "IITU": "IITU.L",
}

# T212 appends a single lowercase letter to denote the listing exchange /
# currency variant (e.g. NVDd = Nvidia on Xetra). Map each to its Yahoo
# Finance suffix.
_T212_EXCHANGE_SUFFIX = {
    "l": ".L",   # London (GBX)
    "p": ".L",   # London (GBP)
    "s": ".L",   # London (USD)
    "d": ".DE",  # Xetra / Frankfurt
    "a": ".AS",  # Euronext Amsterdam
    "m": ".MI",  # Borsa Italiana / Milan
}


def _normalize_t212_ticker(t212_ticker: str) -> str:
    ticker = t212_ticker.strip()
    for suffix in ("_US_EQ", "_EQ"):
        if ticker.endswith(suffix):
            ticker = ticker[:-len(suffix)]
            break
    if ticker in _T212_TICKER_RENAMES:
        return _T212_TICKER_RENAMES[ticker]
    # Lowercase trailing letter on an otherwise upper-case ticker = T212 exchange tag.
    if len(ticker) >= 2 and ticker[-1].islower() and ticker[:-1].isupper():
        yahoo_suffix = _T212_EXCHANGE_SUFFIX.get(ticker[-1])
        if yahoo_suffix:
            return ticker[:-1] + yahoo_suffix
    return ticker


_CANONICAL_TICKER = re.compile(r"^[A-Z0-9]+([.\-][A-Z0-9]+)?$")


def _dedup_keys(ticker: str, *parts) -> set[str]:
    """Dedup keys under the row's ticker AND its exchange-suffix-stripped base
    ('COPM.L' → 'COPM'), so API-normalized tickers match the raw tickers the
    CSV import stores. Class-share dashes (BRK-B) are left alone."""
    tail = "_".join(str(p) for p in parts)
    keys = {f"{ticker}_{tail}"}
    base = (ticker or "").split(".")[0]
    if base != ticker:
        keys.add(f"{base}_{tail}")
    return keys


SNAPSHOT_FRESH_HOURS = 25


def _fetch_positions(base: str, headers: dict) -> list[dict]:
    resp = httpx.get(f"{base}/equity/positions", headers=headers, timeout=15)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="API key is invalid or expired")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="API key cannot read positions")
    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Trading 212 rate limit reached")
    resp.raise_for_status()
    data = resp.json()
    # /equity/positions returns a bare array, unlike the paginated
    # {"items": [...]} shape of the /equity/history/* endpoints.
    return data if isinstance(data, list) else (data.get("items") or [])


def _error_detail(exc: Exception) -> str:
    return exc.detail if isinstance(exc, HTTPException) else str(exc)


@dataclass(frozen=True)
class SnapshotResult:
    """Independent outcome of one summary+positions fetch pass. Each half
    fails independently -- a positions error never discards a successful
    summary and vice versa, and callers must not persist the failed half
    (plan §5.2, §4.1: 'Each result independently preserves its previous
    snapshot on failure')."""

    summary: dict | None
    summary_error: str | None
    positions: list[dict] | None
    positions_error: str | None


def fetch_snapshot(
    base: str,
    headers: dict,
    fetch_summary: Callable[[str, dict], dict],
) -> SnapshotResult:
    """Fetch account summary and positions concurrently (plan §5.2).

    `fetch_summary` is injected (routers.broker._fetch_account_summary)
    rather than duplicated here, so there is exactly one place that maps the
    account-summary response. The two requests run concurrently via a small
    thread pool -- this codebase's HTTP layer is synchronous throughout, so a
    thread pool gets the same "don't block one call on the other" outcome as
    an async client without introducing a second concurrency model.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        summary_future = pool.submit(fetch_summary, base, headers)
        positions_future = pool.submit(_fetch_positions, base, headers)

        summary: dict | None = None
        summary_error: str | None = None
        try:
            summary = summary_future.result()
        except Exception as e:
            summary_error = _error_detail(e)

        positions: list[dict] | None = None
        positions_error: str | None = None
        try:
            positions = positions_future.result()
        except Exception as e:
            positions_error = _error_detail(e)

    return SnapshotResult(summary, summary_error, positions, positions_error)


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def _parse_t212_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def replace_positions(db: Session, portfolio: Portfolio, raw_positions: list[dict]) -> int:
    """Atomically replace this portfolio's T212 position snapshot.

    Callers must only invoke this after a successful positions fetch -- a
    successful empty response legitimately clears previous positions (the
    account holds nothing), while a failed fetch must leave the previous
    rows untouched by not calling this at all (plan §4.1).
    """
    db.query(BrokerPosition).filter(
        BrokerPosition.workspace_id == portfolio.workspace_id,
        BrokerPosition.portfolio_id == portfolio.id,
        BrokerPosition.broker == "trading212",
    ).delete(synchronize_session=False)

    now = datetime.now(timezone.utc)
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == portfolio.workspace_id,
        BrokerConnection.portfolio_id == portfolio.id,
        BrokerConnection.broker == "trading212",
    ).first()
    if connection is not None:
        connection.positions_snapshot_at = now
    inserted = 0
    for raw in raw_positions:
        instrument = raw.get("instrument") or {}
        wallet_impact = raw.get("walletImpact") or {}
        provider_ticker = str(
            instrument.get("ticker") or raw.get("ticker") or ""
        ).strip()
        quantity = raw.get("quantity")
        avg_price = raw.get("averagePricePaid")
        if avg_price is None:
            avg_price = raw.get("averagePrice")
        if not provider_ticker or quantity is None or avg_price is None:
            continue
        db.add(BrokerPosition(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="trading212",
            provider_ticker=provider_ticker,
            ticker=_normalize_t212_ticker(provider_ticker),
            name=instrument.get("name") or raw.get("name"),
            currency=instrument.get("currency") or raw.get("currency"),
            quantity=float(quantity),
            pie_quantity=_optional_float(
                raw.get("quantityInPies", raw.get("pieQuantity"))
            ),
            avg_price=float(avg_price),
            current_price=_optional_float(raw.get("currentPrice")),
            ppl=_optional_float(
                wallet_impact.get("unrealizedProfitLoss", raw.get("ppl"))
            ),
            fx_ppl=_optional_float(wallet_impact.get("fxImpact", raw.get("fxPpl"))),
            initial_fill_date=_parse_t212_datetime(
                raw.get("createdAt") or raw.get("initialFillDate")
            ),
            as_of=now,
        ))
        inserted += 1
    return inserted


def is_snapshot_fresh(as_of: datetime | None, *, now: datetime | None = None) -> bool:
    """25-hour freshness rule shared by positions and balance snapshots
    (plan §2.4): a successful snapshot stays fresh for 25 hours regardless of
    whether a later refresh attempt failed."""
    if as_of is None:
        return False
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - as_of <= timedelta(hours=SNAPSHOT_FRESH_HOURS)


# =============================================================================
# Task 3: resumable history runs
#
# A BrokerSyncRun stages raw order/dividend/cash pages into BrokerSyncEvent rows.
# Reaching state "finalizing" here means every page is staged. The background
# worker then turns staged events into Transactions and changes the run to
# "completed" in the same commit that updates the connection's sync marker.
#
# The `cash` stream (`/equity/history/transactions`: deposits, withdrawals, fees,
# interest, transfers) was added by plan 2026-10-03; its encoding is the signed-off
# docs/research/t212-cash-transaction-encoding.md and its pure mapper is t212_cash.
#
# Run modes (plan 2026-09-24, Tasks C1-C3): `initial` walks the whole history;
# `incremental` may stop early past the connection's history frontier
# (t212_incremental); `audit` re-reads everything and revises rows whose
# provider payload changed. history_run_decision picks the mode.
# =============================================================================

STREAMS = ("orders", "dividends", "cash")
TERMINAL_RUN_STATES = ("completed", "failed", "cancelled", "needs_review")
REVIEW_DETAILS_LIMIT = 50
# fill.type values finalize_run can transform (gate G1 signed off 2026-09-30,
# plan 2026-09-24 Task B3).
SUPPORTED_CORPORATE_ACTION_TYPES: frozenset[str] = frozenset({"STOCK_SPLIT"})
HISTORY_RETRY_ERROR = "Trading 212 history sync will retry automatically."
HISTORY_NEEDS_REVIEW_ERROR = (
    "Trading 212 history contains corporate actions (such as splits) that "
    "Portfyl cannot import automatically yet. No history was imported."
)

# A STOCK_SPLIT the mapper supports but could not verify (unpaired legs, unequal
# wallet values, price ratio off). Distinct from the message above so that
# review_resolution does not treat it as "mapper now supports this": retrying
# would only re-stage the same dead end on every sync.
HISTORY_SPLIT_UNVERIFIED_ERROR = (
    "Trading 212 reported a split that Portfyl could not verify automatically. "
    "No history was imported."
)

# A cash transaction the signed-off encoding (docs/research/
# t212-cash-transaction-encoding.md) does not cover: an unmapped type, a zero or
# contradictory amount, a missing currency or time. Fail closed, like splits.
HISTORY_CASH_UNSUPPORTED_ERROR = (
    "Trading 212 reported a cash transaction that Portfyl cannot import "
    "automatically yet. No history was imported."
)

DEFAULT_LEASE_SECONDS = 90
DEFAULT_MAX_PAGES_PER_STREAM = 3

_STREAM_ENDPOINT_PATH = {
    "orders": "/equity/history/orders",
    "dividends": "/equity/history/dividends",
    "cash": "/equity/history/transactions",
}
_ALLOWED_NEXT_PAGE_QUERY_KEYS = {"cursor", "limit"}
# /equity/history/transactions also documents a `time` query parameter (OpenAPI
# spec: "Retrieve transactions starting from the specified time"); the capture
# CLI already allows it.
_ALLOWED_NEXT_PAGE_QUERY_KEYS_BY_STREAM = {"cash": _ALLOWED_NEXT_PAGE_QUERY_KEYS | {"time"}}
_API_VERSION_PREFIX = "/api/v0"  # the path suffix of every T212_BASES entry


@dataclass(frozen=True)
class RateLimitState:
    remaining: int | None
    reset_at: datetime | None


RATE_LIMIT_RESET_MIN_SECONDS = 2
RATE_LIMIT_RESET_MAX_SECONDS = 120
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 60
_UNIX_TIMESTAMP_FLOOR = 1_000_000_000          # values below this are relative seconds
_UNIX_MILLISECONDS_FLOOR = 100_000_000_000     # values at or above this are milliseconds


def _reset_at_from_header(raw, now: datetime) -> datetime | None:
    """`x-ratelimit-reset` is documented as a Unix timestamp. Small values are
    still read as relative seconds, and the result is clamped so a misread value
    can never park a run for longer than RATE_LIMIT_RESET_MAX_SECONDS."""
    try:
        value = int(float(raw))
    except (TypeError, ValueError, OverflowError):
        return None
    if value >= _UNIX_MILLISECONDS_FLOOR:
        value //= 1000
    if value >= _UNIX_TIMESTAMP_FLOOR:
        reset_at = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        reset_at = now + timedelta(seconds=value)
    earliest = now + timedelta(seconds=RATE_LIMIT_RESET_MIN_SECONDS)
    latest = now + timedelta(seconds=RATE_LIMIT_RESET_MAX_SECONDS)
    return min(max(reset_at, earliest), latest)


def parse_rate_limit_headers(headers, *, now: datetime | None = None) -> RateLimitState:
    """Read T212's rate-limit response headers (plan §5.3). Per the Trading 212
    rate-limiting documentation `x-ratelimit-reset` is a Unix timestamp; the old
    "seconds until reset" reading is kept only for small values (see
    _reset_at_from_header)."""
    now = now or datetime.now(timezone.utc)
    remaining_raw = headers.get("x-ratelimit-remaining")
    reset_raw = headers.get("x-ratelimit-reset")
    try:
        remaining = int(remaining_raw) if remaining_raw is not None else None
    except (TypeError, ValueError):
        remaining = None
    reset_at = _reset_at_from_header(reset_raw, now) if reset_raw is not None else None
    return RateLimitState(remaining=remaining, reset_at=reset_at)


def validate_next_page_path(path: str | None, stream: str) -> str | None:
    """Validate a provider-returned `nextPagePath` before ever attaching an
    Authorization header to it (plan §5.3): it must be a same-origin relative
    URL (no scheme/host/userinfo/fragment) whose path is exactly this
    stream's documented history endpoint, with only known pagination query
    keys. Returns the validated path+query to follow verbatim, or None to
    reject -- rejecting silently stops that stream's pagination rather than
    risking a forged absolute URL or cross-endpoint redirect."""
    if not path:
        return None
    expected_path = _STREAM_ENDPOINT_PATH.get(stream)
    if expected_path is None:
        return None
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    # Trading 212 documents nextPagePath with the API version prefix
    # ("/api/v0/equity/history/orders?limit=50&cursor=..."), but requests are
    # built as base + path where the base already ends in that prefix. Strip it
    # once so the result stays relative to the base; a doubled or different
    # version prefix still fails the endpoint comparison below.
    relative_path = parsed.path
    if relative_path.startswith(_API_VERSION_PREFIX + "/"):
        relative_path = relative_path[len(_API_VERSION_PREFIX):]
    if relative_path != expected_path:
        return None
    query_keys = set(parse_qs(parsed.query).keys())
    allowed_keys = _ALLOWED_NEXT_PAGE_QUERY_KEYS_BY_STREAM.get(stream, _ALLOWED_NEXT_PAGE_QUERY_KEYS)
    if not query_keys <= allowed_keys:
        return None
    return relative_path + (f"?{parsed.query}" if parsed.query else "")


HISTORY_PAGINATION_ERROR = (
    "Trading 212 returned a history page link Portfyl does not recognise, so "
    "the history was not imported. Retrying will not help until Portfyl is "
    "updated; your existing data is unchanged."
)


class UnexpectedNextPagePath(Exception):
    """Trading 212 returned a nextPagePath that failed validate_next_page_path.
    Treating it as the end of the stream would store a partial history as complete."""


class RateLimitedError(Exception):
    """Raised by _fetch_stream_page on a 429. Carries the parsed rate-limit
    state so advance_run can mark just that stream waiting (plan §5.3 point
    5: 'Mark only that stream waiting when its remaining count reaches
    zero') instead of treating the whole run as failed."""

    def __init__(self, state: RateLimitState):
        super().__init__("Trading 212 rate limit reached")
        self.state = state


class LeaseLost(Exception):
    """Raised internally by advance_run when this worker's lease token no
    longer matches the persisted row -- another worker has since claimed the
    run. Progress already committed (per-page checkpoints) is never lost;
    this only stops the current worker from committing further pages."""


def _fetch_stream_page(base: str, headers: dict, stream: str, next_page_path: str | None):
    """Fetch exactly one page of `stream`. Follows the complete, validated
    `next_page_path` when present (plan §3: never reconstruct a page request
    from only the cursor) rather than the limit-only initial request."""
    endpoint = _STREAM_ENDPOINT_PATH[stream]
    if next_page_path:
        resp = httpx.get(f"{base}{next_page_path}", headers=headers, timeout=15)
    else:
        resp = httpx.get(f"{base}{endpoint}", headers=headers, params={"limit": 50}, timeout=15)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="API key is invalid or expired")
    if resp.status_code == 429:
        raise RateLimitedError(parse_rate_limit_headers(resp.headers))
    resp.raise_for_status()
    state = parse_rate_limit_headers(resp.headers)
    log.info("T212 %s page: ratelimit remaining=%s reset_at=%s", stream, state.remaining, state.reset_at)
    data = resp.json()
    items = data.get("items") or []
    raw_next = data.get("nextPagePath")
    validated_next = validate_next_page_path(raw_next, stream) if raw_next else None
    if raw_next and validated_next is None:
        # Names only (never the cursor value): enough to diagnose a new key.
        query_keys = sorted(parse_qs(urlsplit(str(raw_next)).query).keys())
        log.warning(
            "T212 %s nextPagePath rejected (path=%s, query keys=%s)",
            stream, urlsplit(str(raw_next)).path, query_keys,
        )
        raise UnexpectedNextPagePath(stream)
    return items, validated_next


def _stable_fingerprint(item: dict) -> str:
    blob = json.dumps(item, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _order_event_id(item: dict) -> str:
    """fill.id over order.id: one order may have multiple fills (plan §4.3)."""
    fill = item.get("fill") or {}
    order = item.get("order") or {}
    fill_id = fill.get("id")
    if fill_id:
        return f"fill:{fill_id}"
    order_id = order.get("id")
    if order_id:
        return f"order:{order_id}"
    return f"order-fp:{_stable_fingerprint(item)}"


def _dividend_event_id(item: dict) -> str:
    reference = item.get("reference")
    if reference:
        return f"dividend:{reference}"
    return f"dividend-fp:{_stable_fingerprint(item)}"


def _event_id(stream: str, item: dict) -> str:
    if stream == "orders":
        return _order_event_id(item)
    if stream == "cash":
        return cash_event_id(item)
    return _dividend_event_id(item)


def _extract_provider_timestamp(stream: str, item: dict) -> datetime | None:
    if stream == "orders":
        fill = item.get("fill") or {}
        order = item.get("order") or {}
        raw = fill.get("filledAt") or order.get("createdAt")
    elif stream == "cash":
        return cash_event_time(item)
    else:
        raw = item.get("paidOn") or item.get("reference")
    return _parse_t212_datetime(raw)


def stage_events(
    db: Session, run: BrokerSyncRun, stream: str, items: list[dict],
) -> int:
    """Stage unstaged events from one page into BrokerSyncEvent. Re-staging an
    already-known event is a no-op (plan §4.3: 'Re-reading a committed page
    is harmless') -- the dedup check is scoped to this run+stream, matching
    the table's unique key."""
    if not items:
        return 0
    ids = [_event_id(stream, item) for item in items]
    existing_ids = {
        row[0] for row in db.query(BrokerSyncEvent.provider_event_id).filter(
            BrokerSyncEvent.workspace_id == run.workspace_id,
            BrokerSyncEvent.run_id == run.id,
            BrokerSyncEvent.stream == stream,
            BrokerSyncEvent.provider_event_id.in_(set(ids)),
        ).all()
    }
    staged = 0
    for item, event_id in zip(items, ids):
        if event_id in existing_ids:
            continue
        db.add(BrokerSyncEvent(
            workspace_id=run.workspace_id,
            portfolio_id=run.portfolio_id,
            run_id=run.id,
            broker=run.broker,
            account_fingerprint=run.account_fingerprint,
            stream=stream,
            provider_event_id=event_id,
            provider_timestamp=_extract_provider_timestamp(stream, item),
            raw_payload=item,
        ))
        existing_ids.add(event_id)
        staged += 1
    return staged


def claim_or_create_run(
    db: Session, connection: BrokerConnection, portfolio: Portfolio, *, mode: str = "incremental",
) -> BrokerSyncRun:
    """Return this connection's active run, creating one if none exists.
    Idempotent by design (plan §4.2/§11: 'duplicate clicks return one active
    run') -- a concurrent double-insert race is caught by the database's
    partial unique index (migration 0015) and resolved by re-querying."""
    existing = (
        db.query(BrokerSyncRun)
        .filter(
            BrokerSyncRun.workspace_id == connection.workspace_id,
            BrokerSyncRun.connection_id == connection.id,
            BrokerSyncRun.state.notin_(TERMINAL_RUN_STATES),
        )
        .first()
    )
    if existing is not None:
        if existing.account_fingerprint == connection.account_fingerprint:
            return existing
        existing.state = "cancelled"
        existing.lease_token = None
        existing.lease_expires_at = None
        db.flush()

    run = BrokerSyncRun(
        workspace_id=connection.workspace_id,
        portfolio_id=portfolio.id,
        connection_id=connection.id,
        broker=connection.broker,
        account_fingerprint=connection.account_fingerprint,
        credential_generation=connection.credential_generation,
        mode=mode,
        state="pending",
    )
    db.add(run)
    try:
        db.flush()
    except Exception:
        db.rollback()
        existing = (
            db.query(BrokerSyncRun)
            .filter(
                BrokerSyncRun.workspace_id == connection.workspace_id,
                BrokerSyncRun.connection_id == connection.id,
                BrokerSyncRun.state.notin_(TERMINAL_RUN_STATES),
            )
            .first()
        )
        if existing is None:
            raise
        return existing
    return run


@dataclass(frozen=True)
class HistoryDecision:
    action: str  # "reuse" | "create" | "blocked"
    run: BrokerSyncRun | None
    mode: str = "incremental"


def _latest_run(db: Session, connection: BrokerConnection) -> BrokerSyncRun | None:
    return (
        db.query(BrokerSyncRun)
        .filter(BrokerSyncRun.workspace_id == connection.workspace_id,
                BrokerSyncRun.connection_id == connection.id)
        .order_by(BrokerSyncRun.created_at.desc(), BrokerSyncRun.id.desc())
        .first()
    )


def review_resolution(run: BrokerSyncRun, connection: BrokerConnection, portfolio: Portfolio) -> dict:
    """What would unblock a needs_review run: an authoritative CSV export that
    covers the last blocking action, or a mapper for every blocking type."""
    details = run.review_details or []
    dates = [d["date"] for d in details if d.get("date")]
    needed = max(dates) if dates else None
    coverage = _latest_csv_coverage(portfolio.t212_csv_covered_through,
                                    connection.t212_csv_covered_through)
    # _is_csv_covered compares exact event timestamps, so coverage must pass
    # the end of the action's calendar day to guarantee every leg is covered.
    csv_covers_all = bool(
        needed and coverage is not None
        and coverage >= datetime.fromisoformat(needed).replace(tzinfo=timezone.utc) + timedelta(days=1)
    )
    types = {d.get("fill_type") for d in details}
    mapper_supports_all = (
        bool(details) and types <= SUPPORTED_CORPORATE_ACTION_TYPES
        and run.last_error != HISTORY_SPLIT_UNVERIFIED_ERROR
    )
    return {"csv_covers_all": csv_covers_all, "csv_needed_through": needed,
            "mapper_supports_all": mapper_supports_all}


AUDIT_INTERVAL = timedelta(days=30)
# A reconciliation mismatch only asks for an audit when the last full read is
# older than this: a full read that just finished has already seen everything
# the provider has, and a permanent mismatch (an unsupported corporate action,
# a ticker-mapping gap, a transfer the API does not expose) must not turn
# daily incremental syncs into repeated full re-downloads.
RECONCILIATION_AUDIT_COOLDOWN = timedelta(days=7)


def last_full_read_at(connection: BrokerConnection) -> datetime | None:
    """When the connection's whole history was last read end to end: its latest
    audit, else the initial backfill (which also read everything)."""
    value = connection.last_full_audit_at or connection.history_complete_at
    return _as_utc(value) if value is not None else None


def history_run_decision(
    db: Session, connection: BrokerConnection, portfolio: Portfolio, *,
    force: bool = False, reconciliation_mismatch: bool = False,
) -> HistoryDecision:
    """Whether a sync may start a new history run, and in which mode. Only the
    connection's latest run matters: an unresolved `needs_review` would
    re-stage the full history into the same dead end, so it blocks until the
    reason changes (CSV coverage, a new mapper) or the user forces a retry.

    A new run is `initial` until a run has completed, then `audit` when the
    last full read is older than AUDIT_INTERVAL or `reconciliation_mismatch`
    says the ledger disagrees with the broker snapshot, else `incremental`
    (parent plan §7). Only the sync entry points call this, so a connection
    with auto-sync off never triggers unrequested broker access."""
    latest = _latest_run(db, connection)
    if latest is not None and latest.state not in TERMINAL_RUN_STATES:
        return HistoryDecision("reuse", latest, latest.mode)
    if latest is not None and latest.state == "needs_review" and not force:
        res = review_resolution(latest, connection, portfolio)
        if not (res["csv_covers_all"] or res["mapper_supports_all"]):
            return HistoryDecision("blocked", latest, latest.mode)
    if connection.history_complete_at is None:
        return HistoryDecision("create", None, "initial")
    last_read = last_full_read_at(connection)
    audit_due = last_read is None or datetime.now(timezone.utc) - last_read > AUDIT_INTERVAL
    return HistoryDecision(
        "create", None, "audit" if (reconciliation_mismatch or audit_due) else "incremental",
    )


def claim_lease(
    db: Session,
    run_id: int,
    workspace_id,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> BrokerSyncRun | None:
    """Claim `run_id` for this worker: `SELECT ... FOR UPDATE SKIP LOCKED`
    (plan §4.2) so a concurrent claimer never blocks on -- or double-drives --
    the same run. Returns None if the row is currently locked by another
    live worker (skipped), already leased and unexpired, or gone. Only
    meaningfully concurrent under PostgreSQL; SQLite (fast tests) has no
    row-level locking, matching the rest of this codebase's job-safety tests
    (see tests/postgres/ for the real concurrency proof)."""
    now = now or datetime.now(timezone.utc)
    row = (
        db.query(BrokerSyncRun)
        .filter(BrokerSyncRun.id == run_id, BrokerSyncRun.workspace_id == workspace_id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        return None
    if row.lease_expires_at is not None:
        expires = row.lease_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now:
            return None
    row.lease_token = uuid.uuid4()
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.flush()
    return row


@dataclass(frozen=True)
class RunAdvanceResult:
    state: str
    orders_staged: int
    dividends_staged: int
    rate_limited_streams: tuple[str, ...]
    cash_staged: int = 0


def _lease_still_held(db: Session, run: BrokerSyncRun, lease_token) -> bool:
    current = db.query(BrokerSyncRun.lease_token).filter(
        BrokerSyncRun.id == run.id, BrokerSyncRun.workspace_id == run.workspace_id,
    ).scalar()
    return current == lease_token


def _known_provider_event_ids(db: Session, run: BrokerSyncRun, stream: str) -> set[str]:
    """Provider event ids a finalization has already decided on: the portfolio's
    API ledger rows, plus every event a completed run of this connection
    staged. The latter covers events finalization settles without writing a
    t212_api row (legacy/CSV duplicates, non-trade and invalid fills), which
    would otherwise stay unknown forever and defeat the stop rule. Once
    retention purges a run's staging, those events fall back to unknown, which
    only costs a longer walk."""
    known = {
        row[0] for row in db.query(Transaction.source_event_id).filter(
            Transaction.workspace_id == run.workspace_id,
            Transaction.portfolio_id == run.portfolio_id,
            Transaction.source == "t212_api",
            Transaction.source_event_stream == stream,
            Transaction.source_event_id.isnot(None),
        )
    }
    completed_runs = db.query(BrokerSyncRun.id).filter(
        BrokerSyncRun.workspace_id == run.workspace_id,
        BrokerSyncRun.connection_id == run.connection_id,
        BrokerSyncRun.state == "completed",
        BrokerSyncRun.id != run.id,
    )
    known.update(
        row[0] for row in db.query(BrokerSyncEvent.provider_event_id).filter(
            BrokerSyncEvent.workspace_id == run.workspace_id,
            BrokerSyncEvent.stream == stream,
            BrokerSyncEvent.account_fingerprint == run.account_fingerprint,
            BrokerSyncEvent.run_id.in_(completed_runs.scalar_subquery()),
        )
    )
    return known


def _csv_cutoff_for_run(
    db: Session, run: BrokerSyncRun, connection: BrokerConnection | None,
) -> datetime | None:
    """The authoritative T212 CSV coverage cutoff finalize_run applies to this
    run's portfolio: events at or before it are settled by the CSV export."""
    portfolio_cutoff = db.query(Portfolio.t212_csv_covered_through).filter(
        Portfolio.workspace_id == run.workspace_id,
        Portfolio.id == run.portfolio_id,
    ).scalar()
    return _latest_csv_coverage(
        portfolio_cutoff,
        connection.t212_csv_covered_through if connection is not None else None,
    )


def _restart_early_stopped_streams(run: BrokerSyncRun) -> None:
    """A run that turns into an audit mid-way must have read every stream in
    full, or its audit stamp would vouch for history that was never read. A
    stream that already stopped early (its known streak reached the stop
    threshold) is rewound to its first page; re-staging is idempotent."""
    for stream in STREAMS:
        if getattr(run, f"{stream}_complete") and getattr(run, f"{stream}_known_streak") >= OVERLAP_PAGES:
            setattr(run, f"{stream}_complete", False)
            setattr(run, f"{stream}_next_page_path", None)
            setattr(run, f"{stream}_known_streak", 0)
            setattr(run, f"{stream}_last_page_oldest_at", None)


def advance_run(
    db: Session,
    run: BrokerSyncRun,
    base: str,
    headers: dict,
    *,
    max_pages_per_stream: int = DEFAULT_MAX_PAGES_PER_STREAM,
    lease_token=None,
    reassert_context: Callable[[], None] | None = None,
    connection: BrokerConnection | None = None,
) -> RunAdvanceResult:
    """Fetch a bounded number of pages per incomplete stream, staging events
    and committing a checkpoint after every page (plan §5.3/§5.4). Never
    waits for a provider rate-limit reset -- a 429 marks that stream waiting
    and returns; the background job (jobs.broker_backfill_pass) or a later
    call resumes it. `reassert_context`, when given, is invoked immediately
    after every internal commit so a caller running under forced RLS (a
    background job; see jobs._set_job_workspace_context) never issues the
    next tenant query context-less. `lease_token`, when given, is
    re-verified after every commit -- if another worker has since reclaimed
    this run, advancing stops immediately (LeaseLost) without losing any
    already-committed page progress.

    An `incremental` run stops a stream early once the stop rule in
    `t212_incremental` is satisfied against the connection's history frontier
    (plan 2026-09-24, Task C2, parent §7); any ordering doubt turns the run
    into a full `audit` instead. `connection` is looked up from the run when
    the caller does not have it at hand."""
    run.state = "fetching"
    run.last_error = None
    db.commit()
    if reassert_context:
        reassert_context()

    if connection is None:
        connection = db.query(BrokerConnection).filter(
            BrokerConnection.workspace_id == run.workspace_id,
            BrokerConnection.id == run.connection_id,
        ).first()

    staged_counts = {stream: 0 for stream in STREAMS}
    rate_limited: list[str] = []

    try:
        for stream in STREAMS:
            complete_attr = f"{stream}_complete"
            next_path_attr = f"{stream}_next_page_path"
            loaded_attr = f"{stream}_loaded"
            streak_attr = f"{stream}_known_streak"
            oldest_attr = f"{stream}_last_page_oldest_at"
            known_ids: set[str] | None = None
            csv_cutoff: datetime | None = None
            if getattr(run, complete_attr):
                continue
            for _ in range(max_pages_per_stream):
                try:
                    items, next_path = _fetch_stream_page(
                        base, headers, stream, getattr(run, next_path_attr)
                    )
                except RateLimitedError as e:
                    rate_limited.append(stream)
                    setattr(
                        run, f"{stream}_rate_limit_reset_at",
                        e.state.reset_at
                        or datetime.now(timezone.utc) + timedelta(seconds=RATE_LIMIT_DEFAULT_WAIT_SECONDS),
                    )
                    db.commit()
                    if reassert_context:
                        reassert_context()
                    if lease_token is not None and not _lease_still_held(db, run, lease_token):
                        raise LeaseLost()
                    break
                except UnexpectedNextPagePath:
                    if lease_token is not None and not _lease_still_held(db, run, lease_token):
                        raise LeaseLost()
                    run.state = "failed"
                    run.last_error = HISTORY_PAGINATION_ERROR
                    run.lease_token = None
                    run.lease_expires_at = None
                    db.commit()
                    if reassert_context:
                        reassert_context()
                    return RunAdvanceResult(
                        state="failed",
                        orders_staged=staged_counts["orders"],
                        dividends_staged=staged_counts["dividends"],
                        cash_staged=staged_counts["cash"],
                        rate_limited_streams=tuple(rate_limited),
                    )

                staged = stage_events(db, run, stream, items)
                staged_counts[stream] += staged
                setattr(run, loaded_attr, getattr(run, loaded_attr) + staged)
                run.last_progress_at = datetime.now(timezone.utc)
                stop_early = False
                frontier = getattr(connection, f"{stream}_frontier_at") if connection else None
                if run.mode == "incremental" and frontier is not None:
                    if known_ids is None:
                        known_ids = _known_provider_event_ids(db, run, stream)
                        csv_cutoff = _csv_cutoff_for_run(db, run, connection)
                    page_events = [
                        (_event_id(stream, item), _extract_provider_timestamp(stream, item))
                        for item in items
                    ]
                    # Events at or before the CSV cutoff are settled by the
                    # export and never become API rows; they are known too.
                    page_known = known_ids
                    if csv_cutoff is not None:
                        page_known = known_ids | {
                            event_id for event_id, at in page_events
                            if at is not None and _as_utc(at) <= csv_cutoff
                        }
                    previous_oldest = getattr(run, oldest_attr)
                    verdict = evaluate_page(
                        page_events=page_events,
                        known_ids=page_known,
                        frontier_at=_as_utc(frontier),
                        prior_streak=getattr(run, streak_attr),
                        previous_page_oldest=_as_utc(previous_oldest) if previous_oldest else None,
                    )
                    oldest = min((t for _, t in page_events if t is not None), default=None)
                    if oldest is not None:
                        setattr(run, oldest_attr, oldest)
                    if verdict.ordering_violation:
                        # Ordering doubt: never stop early. Walk on to the end
                        # of every stream so the run finalizes as a full audit.
                        setattr(run, streak_attr, 0)
                        run.mode = "audit"
                        _restart_early_stopped_streams(run)
                    else:
                        setattr(run, streak_attr, verdict.known_streak)
                        stop_early = verdict.stop
                if stop_early or not items or not next_path:
                    setattr(run, complete_attr, True)
                    setattr(run, next_path_attr, None)
                    db.commit()
                    if reassert_context:
                        reassert_context()
                    if lease_token is not None and not _lease_still_held(db, run, lease_token):
                        raise LeaseLost()
                    break
                setattr(run, next_path_attr, next_path)
                db.commit()
                if reassert_context:
                    reassert_context()
                if lease_token is not None and not _lease_still_held(db, run, lease_token):
                    raise LeaseLost()
    except LeaseLost:
        return RunAdvanceResult(
            state=run.state,
            orders_staged=staged_counts["orders"],
            dividends_staged=staged_counts["dividends"],
            cash_staged=staged_counts["cash"],
            rate_limited_streams=tuple(rate_limited),
        )

    if rate_limited:
        run.state = "waiting_rate_limit"
    elif all(getattr(run, f"{stream}_complete") for stream in STREAMS):
        run.state = "finalizing"
    else:
        run.state = "fetching"
    run.lease_token = None
    run.lease_expires_at = None
    db.commit()
    if reassert_context:
        reassert_context()

    return RunAdvanceResult(
        state=run.state,
        orders_staged=staged_counts["orders"],
        dividends_staged=staged_counts["dividends"],
        cash_staged=staged_counts["cash"],
        rate_limited_streams=tuple(rate_limited),
    )


# =============================================================================
# Task 4 (scoped slice): finalize staged events into ledger Transaction rows
#
# finalize_run turns a "finalizing" run's staged BrokerSyncEvent rows into
# Transaction rows, with exact settlement (when the provider gives it) and
# the actual paid dividend amount instead of a fixed withholding guess (plan
# §5.5, §5.6). It is idempotent and is invoked by the resumable background
# worker after all required streams have been staged.
#
# Explicitly NOT covered by this function (left for a later increment):
#   - corporate actions other than STOCK_SPLIT (plan §6). Same-instrument
#     STOCK_SPLIT pairs are applied by t212_corporate_actions (gate G1, plan
#     2026-09-24 Track B). Any other non-"TRADE" `fill.type` (spin-off,
#     acquisition, distribution, FOP, ...), and a STOCK_SPLIT whose pair cannot
#     be verified, that is not already covered by an authoritative CSV export
#     sends the run to terminal `needs_review` (plan §6.2.8): nothing is
#     imported, no completion or sync marker is set, and the user is told why.
#     This refuses both a mis-imported corporate-action-as-trade and an
#     unadjusted pre-split row;
#   - per-ticker latest-date heuristics. Only the account-wide authoritative
#     `t212_csv_covered_through` cutoff suppresses older provider events;
#   - cash transactions the signed-off record does not cover (currency
#     conversions, unknown types, zero or sign-contradicting amounts): they send
#     the run to `needs_review` (HISTORY_CASH_UNSUPPORTED_ERROR) like unsupported
#     corporate actions. Mapped cash events are imported (see _finalize_cash_event).
# =============================================================================


_FINALIZE_MAPPER_VERSION = "t212_finalize_v2"


@dataclass(frozen=True)
class FinalizeResult:
    orders_imported: int
    orders_skipped_duplicate: int
    orders_skipped_non_trade: int
    orders_skipped_invalid: int
    dividends_imported: int
    dividends_skipped_duplicate: int
    dividends_skipped_invalid: int
    needs_review: bool = False
    unsupported_action_types: tuple[str, ...] = ()
    revised: int = 0
    cash_imported: int = 0
    cash_skipped_duplicate: int = 0
    cash_skipped_invalid: int = 0


def _corporate_action_type(event: BrokerSyncEvent) -> str | None:
    """Provider-labelled non-TRADE fill type (split, spin-off, acquisition,
    ...), upper-cased, or None for an ordinary trade or a non-order event."""
    if event.stream != "orders":
        return None
    fill = (event.raw_payload or {}).get("fill") or {}
    fill_type = (fill.get("type") or "").upper()
    return fill_type if fill_type and fill_type != "TRADE" else None


def _is_csv_covered(event: BrokerSyncEvent, csv_covered_through: datetime | None) -> bool:
    if csv_covered_through is None:
        return False
    event_time = _staged_event_time(event)
    return event_time is not None and event_time <= csv_covered_through


def _review_details(events: list[BrokerSyncEvent]) -> list[dict]:
    """Payload-free, bounded summary of the events that blocked a run: fill
    type, normalized ticker and calendar date only -- never the raw payload."""
    seen: set[tuple] = set()
    details: list[dict] = []
    for event in events:
        if event.stream == "cash":
            when = _staged_event_time(event)
            cash_type = str((event.raw_payload or {}).get("type") or "").upper() or None
            item = {
                "fill_type": None,
                "ticker": None,
                "date": when.date().isoformat() if when else None,
                "cash_type": cash_type,
            }
            key = ("cash", item["date"], cash_type)
            if key not in seen:
                seen.add(key)
                details.append(item)
            continue
        order = (event.raw_payload or {}).get("order") or {}
        raw_ticker = (order.get("ticker") or "").strip()
        when = _staged_event_time(event)
        item = {
            "fill_type": _corporate_action_type(event),
            "ticker": _normalize_t212_ticker(raw_ticker) if raw_ticker else None,
            "date": when.date().isoformat() if when else None,
        }
        key = (item["fill_type"], item["ticker"], item["date"])
        if key not in seen:
            seen.add(key)
            details.append(item)
    details.sort(key=lambda d: (d["date"] or "", d["fill_type"] or "", d["ticker"] or ""))
    return details[:REVIEW_DETAILS_LIMIT]


def _send_run_to_needs_review(
    db: Session, run: BrokerSyncRun, events: list[BrokerSyncEvent],
    *, last_error: str = HISTORY_NEEDS_REVIEW_ERROR,
) -> FinalizeResult:
    """Terminal state for a run whose staged history holds corporate actions
    no mapper supports yet (plan §6.2.8). Nothing is written to the ledger, no
    completion or sync marker is set, and the run is not retried: importing
    only the ordinary trades would leave pre-action share counts unadjusted.
    `events` are the blocking events; only a bounded summary is persisted."""
    action_types = sorted({_corporate_action_type(e) for e in events} - {None})
    run.state = "needs_review"
    run.last_error = last_error
    run.review_details = _review_details(events)
    run.lease_token = None
    run.lease_expires_at = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return FinalizeResult(
        orders_imported=0,
        orders_skipped_duplicate=0,
        orders_skipped_non_trade=0,
        orders_skipped_invalid=0,
        dividends_imported=0,
        dividends_skipped_duplicate=0,
        dividends_skipped_invalid=0,
        needs_review=True,
        unsupported_action_types=tuple(action_types),
    )


def _parse_event_timestamp(raw) -> tuple[date | None, datetime | None]:
    """Returns (calendar date, aware datetime or None) for an order/dividend
    timestamp string, mirroring routers.broker's existing parsing."""
    if not raw:
        return None, None
    parsed = _parse_t212_datetime(raw)
    if parsed is None:
        return None, None
    return parsed.date(), parsed


def _staged_event_time(event: BrokerSyncEvent) -> datetime | None:
    payload = event.raw_payload or {}
    if event.stream == "orders":
        fill = payload.get("fill") or {}
        order = payload.get("order") or {}
        raw = fill.get("filledAt") or order.get("createdAt")
    elif event.stream == "dividends":
        raw = payload.get("paidOn") or payload.get("reference")
    elif event.stream == "cash":
        return cash_event_time(payload)
    else:
        return None
    return _parse_t212_datetime(raw) if raw else None


def _latest_csv_coverage(*values: datetime | None) -> datetime | None:
    normalized = []
    for value in values:
        if value is None:
            continue
        normalized.append(
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
    return max(normalized) if normalized else None


def _finalize_order_event(event: BrokerSyncEvent, run: BrokerSyncRun):
    """Map one staged order/fill event to a Transaction, or explain why not.
    Returns (outcome, transaction_or_none); outcome is one of "imported",
    "non_trade", "invalid"."""
    item = event.raw_payload or {}
    order_data = item.get("order") or {}
    fill_data = item.get("fill") or {}

    fill_type = (fill_data.get("type") or "").upper()
    if _corporate_action_type(event) is not None:
        return "non_trade", None

    # A cancelled or partially filled parent order can still contain a real
    # execution. Conversely, the parent's aggregate filledQuantity is not a
    # substitute for an individual fill.
    if not fill_data:
        return "invalid", None

    raw_ticker = (order_data.get("ticker") or "").strip()
    if not raw_ticker:
        return "invalid", None
    ticker = _normalize_t212_ticker(raw_ticker)

    side = (order_data.get("side") or "").upper()
    if side == "BUY":
        txn_type = "buy"
    elif side == "SELL":
        txn_type = "sell"
    else:
        return "invalid", None

    try:
        filled_qty = float(abs(fill_data.get("quantity") or 0))
        filled_price = float(fill_data.get("price") or 0)
    except (TypeError, ValueError):
        return "invalid", None
    if not (math.isfinite(filled_qty) and filled_qty > 0
            and math.isfinite(filled_price) and filled_price > 0):
        return "invalid", None

    instrument = order_data.get("instrument") or {}
    currency = (instrument.get("currency") or "USD").upper()
    name = instrument.get("name") or ticker

    raw_date = fill_data.get("filledAt") or order_data.get("createdAt")
    txn_date, executed_at = _parse_event_timestamp(raw_date)
    if txn_date is None:
        return "invalid", None

    # Exact settlement when the provider gives it (plan §5.5 point 3);
    # otherwise the same shares*price approximation the legacy sync path
    # already uses -- see this module's Task 4 section docstring on why
    # `walletImpact` is only ever an optional enhancement here.
    wallet_impact = fill_data.get("walletImpact") or {}
    native_amount = wallet_impact.get("netValue")
    native_currency = (wallet_impact.get("currency") or currency).upper()
    if native_amount is None:
        native_amount = filled_qty * filled_price
        native_currency = currency
    else:
        native_amount = abs(float(native_amount))

    txn = Transaction(
        workspace_id=run.workspace_id,
        portfolio_id=run.portfolio_id,
        ticker=ticker,
        name=name,
        type=txn_type,
        shares=filled_qty,
        price=filled_price,
        currency=currency,
        date=txn_date,
        notes=f"T212 Order #{order_data.get('id', '')}",
        source="t212_api",
        source_event_id=event.provider_event_id,
        source_event_stream="orders",
        source_account_fingerprint=run.account_fingerprint,
        source_credential_generation=run.credential_generation,
        source_instrument_id=raw_ticker,
        source_fill_type=fill_type or None,
        executed_at=executed_at,
        source_payload_hash=_stable_fingerprint(item),
        source_mapper_version=_FINALIZE_MAPPER_VERSION,
    )
    txn._native_cash_amount = native_amount
    txn._native_cash_currency = native_currency
    return "imported", txn


def _finalize_dividend_event(event: BrokerSyncEvent, run: BrokerSyncRun):
    """Map one staged dividend event to a Transaction. Returns (outcome,
    transaction_or_none); outcome is one of "imported", "invalid"."""
    item = event.raw_payload or {}
    raw_ticker = (item.get("ticker") or "").strip()
    if not raw_ticker:
        return "invalid", None
    ticker = _normalize_t212_ticker(raw_ticker)

    try:
        gross_per_share = float(item.get("grossAmountPerShare") or 0)
        quantity = float(item.get("quantity") or 0)
    except (TypeError, ValueError):
        gross_per_share = quantity = 0.0
    if not (math.isfinite(gross_per_share) and gross_per_share > 0
            and math.isfinite(quantity) and quantity > 0):
        return "invalid", None

    instrument = item.get("instrument") or {}
    currency = (instrument.get("currency") or "USD").upper()
    account_currency = (item.get("currency") or "").upper()
    if not account_currency:
        raise ValueError("Trading 212 dividend paid amount currency is unavailable")

    raw_date = item.get("paidOn") or item.get("reference")
    txn_date, executed_at = _parse_event_timestamp(raw_date)
    if txn_date is None:
        return "invalid", None

    # A missing or malformed paid amount cannot be reconstructed from a fixed
    # withholding percentage. Stop the whole finalization rather than writing
    # a fabricated receipt or silently marking this event as handled.
    raw_amount = item.get("amount")
    try:
        net_amount = round(abs(float(raw_amount)), 6)
    except (TypeError, ValueError) as exc:
        raise ValueError("Trading 212 dividend paid amount is unavailable") from exc
    if not math.isfinite(net_amount) or net_amount <= 0:
        raise ValueError("Trading 212 dividend paid amount is invalid")

    txn = Transaction(
        workspace_id=run.workspace_id,
        portfolio_id=run.portfolio_id,
        ticker=ticker,
        name=ticker,
        type="dividend",
        shares=quantity,
        price=gross_per_share,
        currency=currency,
        date=txn_date,
        notes="T212 Dividend",
        source="t212_api",
        source_event_id=event.provider_event_id,
        source_event_stream="dividends",
        source_account_fingerprint=run.account_fingerprint,
        source_credential_generation=run.credential_generation,
        source_instrument_id=raw_ticker,
        executed_at=executed_at,
        source_payload_hash=_stable_fingerprint(item),
        source_mapper_version=_FINALIZE_MAPPER_VERSION,
    )
    txn._native_cash_amount = net_amount
    txn._native_cash_currency = account_currency
    return "imported", txn


def _finalize_cash_event(event: BrokerSyncEvent, run: BrokerSyncRun):
    """Map one staged cash event to a ledger cash Transaction. Returns
    (outcome, transaction_or_none); outcome is "imported" or "unsupported"
    (finalize_run sends an unsupported event's run to review before any write)."""
    item = event.raw_payload or {}
    mapped = map_cash_event(item)
    if isinstance(mapped, UnsupportedCash):
        return "unsupported", None
    txn = Transaction(
        workspace_id=run.workspace_id,
        portfolio_id=run.portfolio_id,
        ticker=None,
        name=None,
        type=mapped.type,
        shares=0.0,
        price=0.0,
        amount=mapped.amount,
        currency=mapped.currency,
        date=mapped.date,
        notes=mapped.notes,
        source="t212_api",
        source_event_id=event.provider_event_id,
        source_event_stream="cash",
        source_account_fingerprint=run.account_fingerprint,
        source_credential_generation=run.credential_generation,
        executed_at=mapped.executed_at,
        source_payload_hash=_stable_fingerprint(item),
        source_mapper_version=_FINALIZE_MAPPER_VERSION,
    )
    # Cash rows are denominated by `amount`/`currency` like the CSV importer's;
    # they carry no separate settlement amount.
    txn._native_cash_amount = None
    txn._native_cash_currency = mapped.currency
    txn._is_cash_row = True
    return "imported", txn


_CASH_DIRECTION = {
    "deposit": "in", "cashback": "in", "withdrawal": "out", "card_debit": "out",
    "fee": "fee", "interest": "interest",
}


def _cash_match_key(txn_type: str, amount: float, currency: str, day: date) -> tuple:
    return (_CASH_DIRECTION.get(txn_type, txn_type), round(float(amount), 2),
            (currency or "").upper(), day)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _record_history_coverage(
    connection: BrokerConnection, run: BrokerSyncRun, events: list[BrokerSyncEvent],
    now: datetime,
) -> None:
    """Advance the connection's per-stream history frontiers for a run that is
    completing now (plan 2026-09-24, Task C1). An initial/audit run walked the
    whole history, so it sets each frontier outright; an incremental run only
    moves a frontier forward. Callers invoke this only on the run's first
    completion, inside its completion commit."""
    for stream in STREAMS:
        staged = [e for e in events if e.stream == stream and e.provider_timestamp is not None]
        newest = max(
            staged, key=lambda e: (_as_utc(e.provider_timestamp), e.provider_event_id),
            default=None,
        )
        if newest is None:
            continue
        current = getattr(connection, f"{stream}_frontier_at")
        if (
            run.mode in {"initial", "audit"}
            or current is None
            or _as_utc(newest.provider_timestamp) > _as_utc(current)
        ):
            setattr(connection, f"{stream}_frontier_at", newest.provider_timestamp)
            setattr(connection, f"{stream}_frontier_event_id", newest.provider_event_id)
    if run.mode in {"initial", "audit"}:
        connection.history_complete_at = now
    if run.mode == "audit":
        connection.last_full_audit_at = now


def finalize_run(db: Session, run: BrokerSyncRun, portfolio: Portfolio) -> FinalizeResult:
    """Turn `run`'s staged events into Transaction rows. Only a "finalizing"
    run (every page staged), or an already-completed run being retried, may be
    finalized. Idempotent: calling this again
    for the same run re-derives the same dedup decisions and imports
    nothing new (each event's `source_event_id` is checked against already-
    finalized rows first). The shared workspace ledger lock serializes its
    duplicate/coverage read and write set with CSV and manual mutations. See
    this module's Task 4 section docstring for what remains out of scope."""
    if run.state not in {"finalizing", "completed"}:
        raise ValueError(
            f"cannot finalize run in state {run.state!r}, expected 'finalizing' or 'completed'"
        )
    if run.workspace_id != portfolio.workspace_id or run.portfolio_id != portfolio.id:
        raise ValueError("run does not belong to the supplied portfolio")
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == run.workspace_id,
        BrokerConnection.id == run.connection_id,
    ).first()
    if (
        connection is None
        or not run.account_fingerprint
        or run.account_fingerprint != connection.account_fingerprint
        or run.account_fingerprint != portfolio.t212_account_fingerprint
        or run.credential_generation != connection.credential_generation
    ):
        raise ValueError("run account identity or credential generation is stale")

    acquire_workspace_ledger_lock(db, portfolio.workspace_id)
    csv_covered_through = _latest_csv_coverage(
        portfolio.t212_csv_covered_through,
        connection.t212_csv_covered_through,
    )
    events = (
        db.query(BrokerSyncEvent)
        .filter(
            BrokerSyncEvent.workspace_id == run.workspace_id,
            BrokerSyncEvent.run_id == run.id,
        )
        .order_by(BrokerSyncEvent.id)
        .all()
    )
    if any(event.account_fingerprint != run.account_fingerprint for event in events):
        raise ValueError("staged event account identity does not match its run")

    # A retry of an already-completed run keeps its idempotent behavior; only
    # a first finalization can be refused for unsupported corporate actions.
    if run.state == "finalizing":
        unsupported_events = [
            event for event in events
            if (action := _corporate_action_type(event)) is not None
            and action not in SUPPORTED_CORPORATE_ACTION_TYPES
            and not _is_csv_covered(event, csv_covered_through)
        ]
        if unsupported_events:
            return _send_run_to_needs_review(db, run, unsupported_events)
        unsupported_cash = [
            event for event in events
            if event.stream == "cash"
            and isinstance(map_cash_event(event.raw_payload or {}), UnsupportedCash)
            and not _is_csv_covered(event, csv_covered_through)
        ]
        if unsupported_cash:
            return _send_run_to_needs_review(
                db, run, unsupported_cash, last_error=HISTORY_CASH_UNSUPPORTED_ERROR,
            )

    # Imported here: t212_corporate_actions imports this module at load time.
    from t212_corporate_actions import (
        UnpairedSplitLeg, apply_splits, collapse_split_pairs, drop_recorded_orphan_legs,
        reapply_recorded_splits, validate_recorded_splits,
    )

    split_events = [
        e for e in events
        if _corporate_action_type(e) == "STOCK_SPLIT" and not _is_csv_covered(e, csv_covered_through)
    ]
    split_events = drop_recorded_orphan_legs(db, run=run, portfolio=portfolio, events=split_events)
    try:
        split_evidence = collapse_split_pairs(split_events)
        validate_recorded_splits(
            db, run=run, portfolio=portfolio, evidence=split_evidence,
        )
    except UnpairedSplitLeg:
        if run.state == "finalizing":
            return _send_run_to_needs_review(
                db, run, split_events, last_error=HISTORY_SPLIT_UNVERIFIED_ERROR,
            )
        raise

    existing_txns = (
        db.query(Transaction)
        .filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            or_(Transaction.ticker.isnot(None), Transaction.source_event_stream == "cash"),
        )
        .all()
    )
    # Cash rows without provider identity (manual entries, legacy rows): each can
    # settle at most one cash event, matched on direction, amount, currency, day.
    unmatched_legacy_cash: list[tuple] = [
        _cash_match_key(row.type, row.amount or 0.0, row.currency, row.date)
        for row in db.query(Transaction).filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            Transaction.ticker.is_(None),
            Transaction.source_event_id.is_(None),
            Transaction.type.in_(tuple(_CASH_DIRECTION)),
        )
    ]
    # Fuzzy matching is only for rows without provider event identity (legacy
    # sync and CSV). Consume each such row at most once: two identical fills
    # with distinct provider IDs are two trades, even on the same day.
    unmatched_legacy_keys: list[set[str]] = []
    existing_source_ids: set[tuple[str, str]] = set()
    api_rows: dict[tuple[str, str], Transaction] = {}
    for t in existing_txns:
        if t.source_event_id and t.source_event_stream:
            existing_source_ids.add((t.source_event_stream, t.source_event_id))
            if t.source == "t212_api":
                api_rows[(t.source_event_stream, t.source_event_id)] = t
            continue
        keys = _dedup_keys(t.ticker, t.date, t.type, t.shares, t.price)
        if t.type == "dividend":
            keys |= _dedup_keys(t.ticker, t.date, "dividend", round(t.shares * t.price, 6))
        unmatched_legacy_keys.append(keys)

    orders_imported = orders_dup = orders_non_trade = orders_invalid = 0
    dividends_imported = dividends_dup = dividends_invalid = 0
    cash_imported = cash_dup = cash_invalid = 0
    new_txns: list[Transaction] = []
    # Audit runs only: (existing API row, freshly mapped copy) whose provider
    # payload changed under the same event id.
    revisions: list[tuple[Transaction, Transaction]] = []

    for event in events:
        if _is_csv_covered(event, csv_covered_through):
            if event.stream == "orders":
                orders_dup += 1
            elif event.stream == "cash":
                cash_dup += 1
            else:
                dividends_dup += 1
            continue
        if event.stream == "orders":
            outcome, txn = _finalize_order_event(event, run)
            if outcome == "non_trade":
                orders_non_trade += 1
                continue
            if outcome == "invalid":
                orders_invalid += 1
                continue
        elif event.stream == "cash":
            outcome, txn = _finalize_cash_event(event, run)
            if outcome == "unsupported":
                # A first finalization sent such a run to review above; this is
                # only reachable when retrying an already-completed run.
                cash_invalid += 1
                continue
        else:
            outcome, txn = _finalize_dividend_event(event, run)
            if outcome == "invalid":
                dividends_invalid += 1
                continue

        source_key = (event.stream, event.provider_event_id)
        if run.mode == "audit" and source_key in api_rows:
            # ID equality is not proof the provider data is unchanged (parent
            # §7): compare the canonical payload hash and revise on a change.
            existing_row = api_rows[source_key]
            if existing_row.source_payload_hash != txn.source_payload_hash:
                revisions.append((existing_row, txn))
            elif event.stream == "orders":
                orders_dup += 1
            elif event.stream == "cash":
                cash_dup += 1
            else:
                dividends_dup += 1
            continue
        if event.stream == "cash":
            cash_key = _cash_match_key(txn.type, txn.amount, txn.currency, txn.date)
            cash_match = (
                unmatched_legacy_cash.index(cash_key) if cash_key in unmatched_legacy_cash else None
            )
            if source_key in existing_source_ids or cash_match is not None:
                if cash_match is not None and source_key not in existing_source_ids:
                    unmatched_legacy_cash.pop(cash_match)
                cash_dup += 1
                continue
            new_txns.append(txn)
            existing_source_ids.add(source_key)
            cash_imported += 1
            continue
        dedup_keys = (
            _dedup_keys(txn.ticker, txn.date, txn.type, txn.shares, txn.price)
            if txn.type != "dividend"
            else _dedup_keys(txn.ticker, txn.date, "dividend", round(txn._native_cash_amount, 6))
        )
        legacy_match = next((i for i, keys in enumerate(unmatched_legacy_keys)
                             if dedup_keys & keys), None)
        if source_key in existing_source_ids or legacy_match is not None:
            if legacy_match is not None and source_key not in existing_source_ids:
                unmatched_legacy_keys.pop(legacy_match)
            if event.stream == "orders":
                orders_dup += 1
            else:
                dividends_dup += 1
            continue

        new_txns.append(txn)
        existing_source_ids.add(source_key)
        if event.stream == "orders":
            orders_imported += 1
        else:
            dividends_imported += 1

    # Price/instrument FX and settled-cash FX can differ. Dividends expose
    # gross per-share value in the instrument currency but paid `amount` in
    # the account's primary currency.
    revised_copies = [mapped for _, mapped in revisions]
    fx_needed = {
        (ccy, t.date) for t in (*new_txns, *revised_copies)
        for ccy in ((t.currency or "USD").upper(), t._native_cash_currency)
        if ccy != "CZK"
    }
    fx_map = bulk_fetch_fx(fx_needed)
    for t in (*new_txns, *revised_copies):
        ccy = t._native_cash_currency
        price_ccy = (t.currency or "USD").upper()
        price_fx = 1.0 if price_ccy == "CZK" else fx_map.get((price_ccy, t.date))
        cash_fx = 1.0 if ccy == "CZK" else fx_map.get((ccy, t.date))
        if price_fx:
            t.fx_to_czk = price_fx
        if getattr(t, "_is_cash_row", False):
            continue  # denominated by amount/currency; no separate settlement
        if cash_fx:
            t.cash_amount = round(t._native_cash_amount * cash_fx, 2)
            t.cash_currency = "CZK"
        else:
            # The provider's paid/settled amount is still exact in its native
            # currency. Keep it usable without inventing a historical FX rate.
            t.cash_amount = t._native_cash_amount
            t.cash_currency = ccy
    for t in new_txns:
        db.add(t)
    # Revise in place under the ledger lock taken above. Identity and user
    # fields (ticker, type, name, notes) are left alone. Recorded split
    # ratios are re-applied to the revised rows just below.
    for existing_row, mapped in revisions:
        date_moved = mapped.date != existing_row.date
        existing_row.shares = mapped.shares
        existing_row.price = mapped.price
        existing_row.date = mapped.date
        existing_row.executed_at = mapped.executed_at
        existing_row.cash_amount = mapped.cash_amount
        existing_row.cash_currency = mapped.cash_currency
        existing_row.source_payload_hash = mapped.source_payload_hash
        existing_row.source_mapper_version = mapped.source_mapper_version
        if getattr(mapped, "_is_cash_row", False):
            existing_row.amount = mapped.amount
            existing_row.currency = mapped.currency
        if mapped.fx_to_czk is not None:
            existing_row.fx_to_czk = mapped.fx_to_czk
        elif date_moved:
            # No rate for the new date yet; the startup backfill fills it in
            # rather than leaving the old date's rate on the row.
            existing_row.fx_to_czk = None
    if revisions:
        reapply_recorded_splits(
            db, workspace_id=portfolio.workspace_id,
            rows=[row for row, mapped in revisions if not getattr(mapped, "_is_cash_row", False)],
        )
    apply_splits(db, run=run, portfolio=portfolio, evidence=split_evidence, pending=new_txns)
    if run.state != "completed":
        finalized_at = datetime.now(timezone.utc)
        run.state = "completed"
        run.completed_at = finalized_at
        run.last_error = None
        connection.last_synced_at = finalized_at
        _record_history_coverage(connection, run, events, finalized_at)
    run.lease_token = None
    run.lease_expires_at = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return FinalizeResult(
        orders_imported=orders_imported,
        orders_skipped_duplicate=orders_dup,
        orders_skipped_non_trade=orders_non_trade,
        orders_skipped_invalid=orders_invalid,
        dividends_imported=dividends_imported,
        dividends_skipped_duplicate=dividends_dup,
        dividends_skipped_invalid=dividends_invalid,
        revised=len(revisions),
        cash_imported=cash_imported,
        cash_skipped_duplicate=cash_dup,
        cash_skipped_invalid=cash_invalid,
    )
