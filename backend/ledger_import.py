"""Append a broker API's ledger rows to a portfolio, once.

Shared by the IBKR Flex sync and the eToro sync. Idempotent by (source,
stream, event id): the partial unique index from migration 0016 backs the
in-Python filter, so overlapping statements or sync windows never import a
row twice.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from cash_ledger import TRADE_TYPES
from database import release_request_connections
from ledger_mutation import acquire_workspace_ledger_lock
from models import Portfolio, Transaction

MAX_SYNC_ERRORS = 20
BROKER_LABELS = {"ibkr": "IBKR", "etoro": "eToro"}


def ledger_result(status: str, *, imported: int = 0, already_present: int = 0,
                  errors: list[str] | None = None) -> dict:
    return {"status": status, "imported": imported, "already_present": already_present,
            "errors": errors or []}


def _key(row) -> tuple:
    if isinstance(row, dict):
        return row["source"], row["source_event_stream"], row["source_event_id"]
    return row.source, row.source_event_stream, row.source_event_id


def insert_new_provider_rows(db: Session, portfolio: Portfolio, rows: list[dict], *,
                             source: str) -> dict:
    """Add the not-yet-imported `rows` (already validated) to `portfolio`.

    Returns {status: "imported" | "needs_review", imported, already_present,
    errors}. Never commits: the caller owns the transaction. Holds the
    workspace ledger lock from the duplicate check until that commit.
    """
    # Imported lazily: routers.portfolio pulls in the whole market-data chain.
    from routers.portfolio import _check_import_capacity, _prepare_import_transactions

    if not rows:
        return ledger_result("imported")
    # FX does not depend on ledger state: fetch it before taking a pooled
    # connection and the lock.
    release_request_connections()
    prepared = _prepare_import_transactions(rows, portfolio)

    acquire_workspace_ledger_lock(db, portfolio.workspace_id)
    existing = db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).all()
    incoming_tickers = {row.ticker for row in prepared if row.type in TRADE_TYPES}
    foreign = sorted({
        row.ticker for row in existing
        if row.type in TRADE_TYPES and row.source != source and row.ticker in incoming_tickers
    })
    if foreign:
        label = BROKER_LABELS.get(source, source)
        return ledger_result("needs_review", errors=[
            "Portfolio already contains trades from another source for "
            f"{', '.join(foreign)}. Use a dedicated portfolio for {label} or delete them first."
        ])

    known = {_key(row) for row in existing if row.source == source and row.source_event_id}
    new_rows = [row for row in prepared if _key(row) not in known]
    if new_rows:
        _check_import_capacity(db, portfolio, new_rows, replace=False)
        db.add_all(new_rows)
        db.flush()
    return ledger_result("imported", imported=len(new_rows),
                         already_present=len(prepared) - len(new_rows))
