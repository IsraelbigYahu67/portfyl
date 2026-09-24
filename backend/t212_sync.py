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
        provider_ticker = str(raw.get("ticker") or "").strip()
        quantity = raw.get("quantity")
        avg_price = raw.get("averagePrice")
        if not provider_ticker or quantity is None or avg_price is None:
            continue
        db.add(BrokerPosition(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="trading212",
            provider_ticker=provider_ticker,
            ticker=_normalize_t212_ticker(provider_ticker),
            quantity=float(quantity),
            pie_quantity=_optional_float(raw.get("pieQuantity")),
            avg_price=float(avg_price),
            current_price=_optional_float(raw.get("currentPrice")),
            ppl=_optional_float(raw.get("ppl")),
            fx_ppl=_optional_float(raw.get("fxPpl")),
            initial_fill_date=_parse_t212_datetime(raw.get("initialFillDate")),
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
# A BrokerSyncRun stages raw order/dividend pages into BrokerSyncEvent rows.
# Reaching state "finalizing" here means every page is staged. The background
# worker then turns staged events into Transactions and changes the run to
# "completed" in the same commit that updates the connection's sync marker.
#
# Scope deliberately excludes, for this increment:
#   - the `/equity/history/transactions` cash-movement stream (deposits,
#     withdrawals, fees, interest) -- a new provider surface the app doesn't
#     fetch today, not "making an existing fetch resumable";
#   - audit runs (mode="audit") -- the column accepts the value, nothing
#     creates one yet.
# =============================================================================

STREAMS = ("orders", "dividends")
TERMINAL_RUN_STATES = ("completed", "failed", "cancelled", "needs_review")
REVIEW_DETAILS_LIMIT = 50
# fill.type values finalize_run can transform. Empty until gate G1 (plan
# 2026-09-24 Task A2) is signed off and Task B3 lands.
SUPPORTED_CORPORATE_ACTION_TYPES: frozenset[str] = frozenset()
HISTORY_RETRY_ERROR = "Trading 212 history sync will retry automatically."
HISTORY_NEEDS_REVIEW_ERROR = (
    "Trading 212 history contains corporate actions (such as splits) that "
    "Portfyl cannot import automatically yet. No history was imported."
)

DEFAULT_LEASE_SECONDS = 90
DEFAULT_MAX_PAGES_PER_STREAM = 3

_STREAM_ENDPOINT_PATH = {
    "orders": "/equity/history/orders",
    "dividends": "/equity/history/dividends",
}
_ALLOWED_NEXT_PAGE_QUERY_KEYS = {"cursor", "limit"}


@dataclass(frozen=True)
class RateLimitState:
    remaining: int | None
    reset_at: datetime | None


def parse_rate_limit_headers(headers, *, now: datetime | None = None) -> RateLimitState:
    """Read T212's rate-limit response headers (plan §5.3). `x-ratelimit-reset`
    is treated as seconds-until-reset (consistent with the codebase's existing
    "verified only against docs/fixtures, not a live account" caveat for T212
    response shapes -- see this module's top-level docstring)."""
    now = now or datetime.now(timezone.utc)
    remaining_raw = headers.get("x-ratelimit-remaining")
    reset_raw = headers.get("x-ratelimit-reset")
    try:
        remaining = int(remaining_raw) if remaining_raw is not None else None
    except (TypeError, ValueError):
        remaining = None
    reset_at = None
    if reset_raw is not None:
        try:
            reset_at = now + timedelta(seconds=int(reset_raw))
        except (TypeError, ValueError):
            reset_at = None
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
    if parsed.path != expected_path:
        return None
    query_keys = set(parse_qs(parsed.query).keys())
    if not query_keys <= _ALLOWED_NEXT_PAGE_QUERY_KEYS:
        return None
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


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
    data = resp.json()
    items = data.get("items") or []
    raw_next = data.get("nextPagePath")
    validated_next = validate_next_page_path(raw_next, stream) if raw_next else None
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
    return _order_event_id(item) if stream == "orders" else _dividend_event_id(item)


def _extract_provider_timestamp(stream: str, item: dict) -> datetime | None:
    if stream == "orders":
        fill = item.get("fill") or {}
        order = item.get("order") or {}
        raw = fill.get("filledAt") or order.get("createdAt")
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


def _lease_still_held(db: Session, run: BrokerSyncRun, lease_token) -> bool:
    current = db.query(BrokerSyncRun.lease_token).filter(
        BrokerSyncRun.id == run.id, BrokerSyncRun.workspace_id == run.workspace_id,
    ).scalar()
    return current == lease_token


def advance_run(
    db: Session,
    run: BrokerSyncRun,
    base: str,
    headers: dict,
    *,
    max_pages_per_stream: int = DEFAULT_MAX_PAGES_PER_STREAM,
    lease_token=None,
    reassert_context: Callable[[], None] | None = None,
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
    already-committed page progress."""
    run.state = "fetching"
    run.last_error = None
    db.commit()
    if reassert_context:
        reassert_context()

    staged_counts = {"orders": 0, "dividends": 0}
    rate_limited: list[str] = []

    try:
        for stream in STREAMS:
            complete_attr = f"{stream}_complete"
            next_path_attr = f"{stream}_next_page_path"
            loaded_attr = f"{stream}_loaded"
            if getattr(run, complete_attr):
                continue
            for _ in range(max_pages_per_stream):
                try:
                    items, next_path = _fetch_stream_page(
                        base, headers, stream, getattr(run, next_path_attr)
                    )
                except RateLimitedError as e:
                    rate_limited.append(stream)
                    setattr(run, f"{stream}_rate_limit_reset_at", e.state.reset_at)
                    db.commit()
                    if reassert_context:
                        reassert_context()
                    if lease_token is not None and not _lease_still_held(db, run, lease_token):
                        raise LeaseLost()
                    break

                staged = stage_events(db, run, stream, items)
                staged_counts[stream] += staged
                setattr(run, loaded_attr, getattr(run, loaded_attr) + staged)
                run.last_progress_at = datetime.now(timezone.utc)
                if not items or not next_path:
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
            rate_limited_streams=tuple(rate_limited),
        )

    if rate_limited:
        run.state = "waiting_rate_limit"
    elif run.orders_complete and run.dividends_complete:
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
#   - split/corporate-action detection and mechanical share/price adjustment
#     (plan §6). A fill whose provider `fill.type` is anything other than
#     "TRADE" (and is not already covered by an authoritative CSV export)
#     sends the run to terminal `needs_review` (plan §6.2.8): nothing is
#     imported, no completion or sync marker is set, and the user is told why.
#     This refuses both a mis-imported corporate-action-as-trade and an
#     unadjusted pre-split row. The provider does not document how a split
#     pair encodes quantity/price, so the mapper waits for real payloads;
#   - per-ticker latest-date heuristics. Only the account-wide authoritative
#     `t212_csv_covered_through` cutoff suppresses older provider events;
#   - the `/equity/history/transactions` cash-movement stream (deposits,
#     withdrawals, fees, interest) -- BrokerSyncEvent only ever stages
#     "orders"/"dividends" as of this increment (see advance_run's STREAMS).
# =============================================================================


_FINALIZE_MAPPER_VERSION = "t212_finalize_v1"


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
) -> FinalizeResult:
    """Terminal state for a run whose staged history holds corporate actions
    no mapper supports yet (plan §6.2.8). Nothing is written to the ledger, no
    completion or sync marker is set, and the run is not retried: importing
    only the ordinary trades would leave pre-action share counts unadjusted.
    `events` are the blocking events; only a bounded summary is persisted."""
    action_types = sorted({_corporate_action_type(e) for e in events} - {None})
    run.state = "needs_review"
    run.last_error = HISTORY_NEEDS_REVIEW_ERROR
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

    existing_txns = (
        db.query(Transaction)
        .filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            Transaction.ticker.isnot(None),
        )
        .all()
    )
    # Fuzzy matching is only for rows without provider event identity (legacy
    # sync and CSV). Consume each such row at most once: two identical fills
    # with distinct provider IDs are two trades, even on the same day.
    unmatched_legacy_keys: list[set[str]] = []
    existing_source_ids: set[tuple[str, str]] = set()
    for t in existing_txns:
        if t.source_event_id and t.source_event_stream:
            existing_source_ids.add((t.source_event_stream, t.source_event_id))
            continue
        keys = _dedup_keys(t.ticker, t.date, t.type, t.shares, t.price)
        if t.type == "dividend":
            keys |= _dedup_keys(t.ticker, t.date, "dividend", round(t.shares * t.price, 6))
        unmatched_legacy_keys.append(keys)

    orders_imported = orders_dup = orders_non_trade = orders_invalid = 0
    dividends_imported = dividends_dup = dividends_invalid = 0
    new_txns: list[Transaction] = []

    for event in events:
        if _is_csv_covered(event, csv_covered_through):
            if event.stream == "orders":
                orders_dup += 1
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
        else:
            outcome, txn = _finalize_dividend_event(event, run)
            if outcome == "invalid":
                dividends_invalid += 1
                continue

        source_key = (event.stream, event.provider_event_id)
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
    fx_needed = {
        (ccy, t.date) for t in new_txns
        for ccy in ((t.currency or "USD").upper(), t._native_cash_currency)
        if ccy != "CZK"
    }
    fx_map = bulk_fetch_fx(fx_needed)
    for t in new_txns:
        ccy = t._native_cash_currency
        price_ccy = (t.currency or "USD").upper()
        price_fx = 1.0 if price_ccy == "CZK" else fx_map.get((price_ccy, t.date))
        cash_fx = 1.0 if ccy == "CZK" else fx_map.get((ccy, t.date))
        if price_fx:
            t.fx_to_czk = price_fx
        if cash_fx:
            t.cash_amount = round(t._native_cash_amount * cash_fx, 2)
            t.cash_currency = "CZK"
        else:
            # The provider's paid/settled amount is still exact in its native
            # currency. Keep it usable without inventing a historical FX rate.
            t.cash_amount = t._native_cash_amount
            t.cash_currency = ccy
        db.add(t)
    if run.state != "completed":
        finalized_at = datetime.now(timezone.utc)
        run.state = "completed"
        run.completed_at = finalized_at
        run.last_error = None
        connection.last_synced_at = finalized_at
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
    )
