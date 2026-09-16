"""Workspace-scoped pending portfolio activation state for onboarding imports."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Portfolio, Transaction, WorkspaceSetting


PENDING_PORTFOLIO_SETTING_KEY = "onboarding_pending_portfolio"
PENDING_PORTFOLIO_SCHEMA_VERSION = 1
PENDING_PORTFOLIO_KIND = "csv_import"


def _setting(db: Session, workspace_id: UUID) -> WorkspaceSetting | None:
    return db.scalar(select(WorkspaceSetting).where(
        WorkspaceSetting.workspace_id == workspace_id,
        WorkspaceSetting.key == PENDING_PORTFOLIO_SETTING_KEY,
    ))


def _decode(value: str | None) -> UUID | None:
    try:
        payload = json.loads(value or "")
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != PENDING_PORTFOLIO_SCHEMA_VERSION
            or payload.get("kind") != PENDING_PORTFOLIO_KIND
        ):
            return None
        return UUID(str(payload["portfolio_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def pending_portfolio(
    db: Session,
    workspace_id: UUID,
    *,
    clean_stale: bool = False,
    require_empty: bool = True,
) -> Portfolio | None:
    """Return only a valid, empty pending portfolio in the same workspace."""
    row = _setting(db, workspace_id)
    if row is None:
        return None
    public_id = _decode(row.value)
    portfolio = None
    if public_id is not None:
        portfolio = db.scalar(select(Portfolio).where(
            Portfolio.workspace_id == workspace_id,
            Portfolio.public_id == public_id,
        ))
        if portfolio is not None and require_empty:
            transaction_count = db.scalar(select(func.count()).select_from(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.portfolio_id == portfolio.id,
            )) or 0
            if transaction_count:
                portfolio = None
    if portfolio is None and clean_stale:
        db.delete(row)
        db.flush()
    return portfolio


def set_pending_portfolio(db: Session, portfolio: Portfolio) -> None:
    payload = json.dumps({
        "schema_version": PENDING_PORTFOLIO_SCHEMA_VERSION,
        "portfolio_id": str(portfolio.public_id),
        "kind": PENDING_PORTFOLIO_KIND,
    }, sort_keys=True, separators=(",", ":"))
    row = _setting(db, portfolio.workspace_id)
    if row is None:
        db.add(WorkspaceSetting(
            workspace_id=portfolio.workspace_id,
            key=PENDING_PORTFOLIO_SETTING_KEY,
            value=payload,
        ))
    else:
        row.value = payload
    db.flush()


def clear_pending_portfolio(db: Session, portfolio: Portfolio) -> bool:
    """Clear the marker only when it identifies this exact tenant portfolio."""
    row = _setting(db, portfolio.workspace_id)
    if row is None or _decode(row.value) != portfolio.public_id:
        return False
    db.delete(row)
    db.flush()
    return True
