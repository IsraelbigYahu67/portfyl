"""Write the Flex Web Service statement's stock/cash events into the ledger.

Idempotent by (source, stream, event id): the partial unique index from
migration 0016 backs the in-Python filter. Shares the parser with the Flex
XML upload, so a user can upload older yearly statements and keep the daily
sync running without duplicates.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import release_request_connections
from importers.base import validate_rows
from importers.formats.ibkr_flex import SOURCE, has_ledger_sections, parse_flex_statement
from importers.instruments import InstrumentResolver
from ledger_import import MAX_SYNC_ERRORS, insert_new_provider_rows, ledger_result
from models import Portfolio


def apply_flex_ledger(db: Session, portfolio: Portfolio, xml_text: str, *,
                      resolver: InstrumentResolver) -> dict:
    """Add the statement's not-yet-imported stock/ETF/cash rows to `portfolio`.

    Returns {status: "imported" | "sections_missing" | "needs_review",
    imported, already_present, errors}. Never commits: the caller owns the
    transaction (see ledger_import.insert_new_provider_rows).
    """
    if not has_ledger_sections(xml_text):
        return ledger_result("sections_missing")

    # Instrument lookups are network calls and depend on nothing in the
    # ledger: do them before taking a pooled connection and the lock.
    release_request_connections()
    parsed = parse_flex_statement(xml_text, resolver)
    errors = [*parsed.errors, *validate_rows(parsed.rows)]
    if errors:
        return ledger_result("needs_review", errors=errors[:MAX_SYNC_ERRORS])
    result = insert_new_provider_rows(db, portfolio, parsed.rows, source=SOURCE)
    if result["status"] == "needs_review":
        result["errors"] = [f"{result['errors'][0]} Options keep syncing meanwhile."]
    return result
