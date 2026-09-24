"""Serialization helpers for transaction-ledger mutations.

PostgreSQL callers lock the owning workspace row before reading ledger state
that they will subsequently mutate.  One shared lock target serializes CSV
commit/undo, manual CRUD, clear-all, and broker finalization without relying on
process-local mutexes (Cloud Run may have multiple instances).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import Workspace


BROKER_MANAGED_SOURCES = frozenset({"t212_api", "t212_csv"})


def acquire_workspace_ledger_lock(db: Session, workspace_id) -> None:
    """Hold the workspace row lock until the caller commits or rolls back."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.query(Workspace.id).filter(
        Workspace.id == workspace_id,
    ).with_for_update().one()


def is_broker_managed(transaction) -> bool:
    return transaction.source in BROKER_MANAGED_SOURCES
