"""Remove onboarding sample data once a real broker account is connected."""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ledger_mutation import acquire_workspace_ledger_lock
from models import (
    AllocationTarget,
    Benchmark,
    BrokerConnection,
    CashInterestRate,
    DiscordWebhook,
    OptionsTrade,
    PolymarketPosition,
    Portfolio,
    PriceAlert,
    Transaction,
)


DEMO_SOURCE = "demo"
DEMO_PORTFOLIO_NAME = "Portfyl demo"
CONNECTED_PORTFOLIO_NAME = "Trading 212"

# Every portfolio FK cascades on delete, so a sample portfolio the user has
# since added any of these to is no longer a pristine demo and is kept.
_USER_DATA_MODELS = (
    BrokerConnection,
    OptionsTrade,
    PolymarketPosition,
    Benchmark,
    AllocationTarget,
    PriceAlert,
    DiscordWebhook,
    CashInterestRate,
)


def purge_demo_data(db: Session, portfolio: Portfolio) -> dict:
    """Drop sample data from the workspace that `portfolio` was just connected in.

    Only rows the onboarding demo created are touched: `source == "demo"`
    transactions in the connected portfolio, and any other portfolio that still
    holds nothing but demo transactions and no other user data (see
    `_USER_DATA_MODELS`). Real or manually entered rows are never deleted. The
    caller commits.
    """
    workspace_id = portfolio.workspace_id
    acquire_workspace_ledger_lock(db, workspace_id)

    removed_transactions = db.query(Transaction).filter(
        Transaction.workspace_id == workspace_id,
        Transaction.portfolio_id == portfolio.id,
        Transaction.source == DEMO_SOURCE,
    ).delete(synchronize_session=False)

    sample_portfolios = db.scalars(
        select(Portfolio).where(
            Portfolio.workspace_id == workspace_id,
            Portfolio.id != portfolio.id,
            Portfolio.name == DEMO_PORTFOLIO_NAME,
            *(
                ~exists().where(
                    model.workspace_id == workspace_id,
                    model.portfolio_id == Portfolio.id,
                )
                for model in _USER_DATA_MODELS
            ),
            ~exists().where(
                Transaction.workspace_id == workspace_id,
                Transaction.portfolio_id == Portfolio.id,
                Transaction.source != DEMO_SOURCE,
            ),
        )
    ).all()

    removed_portfolios = 0
    for sample in sample_portfolios:
        removed_transactions += db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            Transaction.portfolio_id == sample.id,
        ).delete(synchronize_session=False)
        if sample.is_default:
            portfolio.is_default = True
        db.delete(sample)
        removed_portfolios += 1
    db.flush()

    renamed = False
    if portfolio.name == DEMO_PORTFOLIO_NAME and (
        removed_transactions or removed_portfolios
    ):
        name_taken = db.scalar(
            select(exists().where(
                Portfolio.workspace_id == workspace_id,
                Portfolio.name == CONNECTED_PORTFOLIO_NAME,
            ))
        )
        if not name_taken:
            portfolio.name = CONNECTED_PORTFOLIO_NAME
            renamed = True

    return {
        "transactions": removed_transactions,
        "portfolios": removed_portfolios,
        "renamed": renamed,
    }
