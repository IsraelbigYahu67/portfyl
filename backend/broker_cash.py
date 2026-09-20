"""Current broker cash snapshots shared by dashboard and allocation views."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from fx import cash_amount_to_display
from models import BrokerBalance, Portfolio


@dataclass(frozen=True)
class BrokerCashSnapshot:
    amount: float
    native_amount: float
    currency: str
    as_of: date | None
    updated_at: datetime | None


def current_t212_cash(
    db: Session, portfolio: Portfolio, display_currency: str
) -> BrokerCashSnapshot | None:
    """Return the latest persisted T212 cash snapshot in display currency."""
    balance = (
        db.query(BrokerBalance)
        .filter(
            BrokerBalance.workspace_id == portfolio.workspace_id,
            BrokerBalance.portfolio_id == portfolio.id,
            BrokerBalance.broker == "trading212",
        )
        .first()
    )
    if balance is None:
        return None

    native_amount = float(balance.cash or 0.0)
    native_currency = (balance.base_currency or display_currency or "USD").upper()
    amount = cash_amount_to_display(
        native_amount, native_currency, display_currency.upper()
    )
    return BrokerCashSnapshot(
        amount=amount,
        native_amount=native_amount,
        currency=native_currency,
        as_of=balance.as_of,
        updated_at=balance.updated_at,
    )
