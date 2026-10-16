"""Write the Flex Web Service statement's stock/cash events into the ledger.

Idempotent by (source, stream, event id): the partial unique index from
migration 0016 backs the in-Python filter. Shares the parser with the Flex
XML upload, so a user can upload older yearly statements and keep the daily
sync running without duplicates.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from cash_ledger import TRADE_TYPES
from database import release_request_connections
from importers.base import validate_rows
from importers.formats.ibkr_flex import SOURCE, has_ledger_sections, parse_flex_statement
from importers.instruments import InstrumentResolver
from ledger_mutation import acquire_workspace_ledger_lock
from models import Portfolio, Transaction

MAX_SYNC_ERRORS = 20


def _result(status: str, *, imported: int = 0, already_present: int = 0,
            errors: list[str] | None = None) -> dict:
    return {"status": status, "imported": imported, "already_present": already_present,
            "errors": errors or []}


def _key(row) -> tuple:
    if isinstance(row, dict):
        return row["source"], row["source_event_stream"], row["source_event_id"]
    return row.source, row.source_event_stream, row.source_event_id


def apply_flex_ledger(db: Session, portfolio: Portfolio, xml_text: str, *,
                      resolver: InstrumentResolver) -> dict:
    """Add the statement's not-yet-imported stock/ETF/cash rows to `portfolio`.

    Returns {status: "imported" | "sections_missing" | "needs_review",
    imported, already_present, errors}. Never commits: the caller owns the
    transaction. Holds the workspace ledger lock from the duplicate check
    until that commit.
    """
    # Imported lazily: routers.portfolio pulls in the whole market-data chain.
    from routers.portfolio import _check_import_capacity, _prepare_import_transactions

    if not has_ledger_sections(xml_text):
        return _result("sections_missing")

    # Instrument and FX lookups are network calls and depend on nothing in
    # the ledger: do them before taking a pooled connection and the lock.
    release_request_connections()
    parsed = parse_flex_statement(xml_text, resolver)
    errors = [*parsed.errors, *validate_rows(parsed.rows)]
    if errors:
        return _result("needs_review", errors=errors[:MAX_SYNC_ERRORS])
    if not parsed.rows:
        return _result("imported")
    prepared = _prepare_import_transactions(parsed.rows, portfolio)

    acquire_workspace_ledger_lock(db, portfolio.workspace_id)
    existing = db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).all()
    incoming_tickers = {row.ticker for row in prepared if row.type in TRADE_TYPES}
    foreign = sorted({
        row.ticker for row in existing
        if row.type in TRADE_TYPES and row.source != SOURCE and row.ticker in incoming_tickers
    })
    if foreign:
        return _result("needs_review", errors=[
            "Portfolio already contains trades from another source for "
            f"{', '.join(foreign)}. Use a dedicated portfolio for IBKR or delete them first; "
            "options keep syncing meanwhile."
        ])

    known = {_key(row) for row in existing if row.source == SOURCE and row.source_event_id}
    new_rows = [row for row in prepared if _key(row) not in known]
    if new_rows:
        _check_import_capacity(db, portfolio, new_rows, replace=False)
        db.add_all(new_rows)
        db.flush()
    return _result("imported", imported=len(new_rows), already_present=len(prepared) - len(new_rows))
