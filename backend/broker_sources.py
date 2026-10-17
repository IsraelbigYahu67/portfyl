"""Which broker a portfolio's data comes from.

The frontend keeps each broker in its own portfolio: when the selected
portfolio already holds data from another source, a new import or broker
connection goes into a new portfolio instead. These helpers name that
source from `Transaction.source` and `BrokerConnection.broker`.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BrokerConnection, Transaction

_SOURCE_BROKER = {
    "t212_api": "trading212",
    "t212_csv": "trading212",
    "ibkr": "ibkr",
    "etoro": "etoro",
    "degiro": "degiro",
    "xtb": "xtb",
    "schwab": "schwab",
    "fidelity": "fidelity",
    "demo": "demo",
}
# Native Portfyl CSV, manual entries and anything unknown: the user's own data.
OWN = "own"


def broker_of_source(source: str | None) -> str:
    return _SOURCE_BROKER.get(source or "", OWN)


def rows_broker(rows: Iterable[dict]) -> str | None:
    """The single broker an import's rows come from; None for own or mixed rows."""
    brokers = {broker_of_source(row.get("source")) for row in rows}
    if len(brokers) != 1:
        return None
    [broker] = brokers
    return None if broker == OWN else broker


def portfolio_brokers(db: Session, workspace_id: UUID) -> dict[int, list[str]]:
    """portfolio id -> sorted brokers its transactions and connections come from."""
    found: dict[int, set[str]] = defaultdict(set)
    for portfolio_id, source in db.execute(
        select(Transaction.portfolio_id, Transaction.source)
        .where(Transaction.workspace_id == workspace_id)
        .distinct()
    ).all():
        found[portfolio_id].add(broker_of_source(source))
    for portfolio_id, broker in db.execute(
        select(BrokerConnection.portfolio_id, BrokerConnection.broker)
        .where(BrokerConnection.workspace_id == workspace_id)
    ).all():
        found[portfolio_id].add(broker)
    return {portfolio_id: sorted(brokers) for portfolio_id, brokers in found.items()}
