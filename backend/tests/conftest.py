"""Shared test fixtures: in-memory SQLite DB, pre-built transactions, mock yfinance."""

from __future__ import annotations

import os
import sys

# Ensure the backend package is importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch os.rename BEFORE database.py is imported, so its startup migration becomes a no-op.
import os as _os

_original_exists = _os.path.exists
_original_rename = _os.rename


def _noop_rename(src, dst):
    pass


_os.rename = _noop_rename

from datetime import date, timedelta
from typing import Callable
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from models import Transaction, Portfolio, Benchmark, BenchmarkComponent

# Restore os.rename after database module is loaded so nothing else is affected.
_os.rename = _original_rename


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_session() -> Session:
    """In-memory SQLite session, fresh per test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def default_portfolio(db_session: Session) -> Portfolio:
    """Create and return a default portfolio."""
    p = Portfolio(name="Default", is_default=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def pid(default_portfolio) -> int:
    """Convenience: just the portfolio id."""
    return default_portfolio.id


# ---------------------------------------------------------------------------
# Transaction builders
# ---------------------------------------------------------------------------


def make_txn(
    ticker: str = "AAPL",
    type: str = "buy",
    shares: float = 10,
    price: float = 150.0,
    currency: str = "USD",
    date: date | None = None,
    fx_to_czk: float | None = None,
    name: str | None = None,
    notes: str | None = None,
    source: str | None = "manual",
    portfolio_id: int = 1,
) -> Transaction:
    return Transaction(
        portfolio_id=portfolio_id,
        ticker=ticker.upper(),
        name=name or ticker.upper(),
        type=type,
        shares=shares,
        price=price,
        currency=currency,
        date=date or date(2024, 1, 15),
        fx_to_czk=fx_to_czk,
        notes=notes,
        source=source,
    )


@pytest.fixture
def txns_demo(db_session: Session, pid: int) -> list[Transaction]:
    """A canonical set of transactions for holdings / P&L tests."""
    txns = [
        make_txn("AAPL", "buy", 100, 150.0, date=date(2024, 1, 15), portfolio_id=pid),
        make_txn("AAPL", "buy", 50, 160.0, date=date(2024, 3, 10), portfolio_id=pid),
        make_txn("AAPL", "sell", 30, 175.0, date=date(2024, 6, 1), portfolio_id=pid),
        make_txn("AAPL", "dividend", 100, 0.50, date=date(2024, 7, 1), portfolio_id=pid),
        make_txn("MSFT", "buy", 20, 350.0, date=date(2024, 2, 1), portfolio_id=pid),
        make_txn("MSFT", "sell", 10, 400.0, date=date(2024, 5, 1), portfolio_id=pid),
    ]
    for t in txns:
        db_session.add(t)
    db_session.commit()
    for t in txns:
        db_session.refresh(t)
    return txns


# ---------------------------------------------------------------------------
# yfinance mock helpers
# ---------------------------------------------------------------------------


def mock_yf_info(info: dict | None = None) -> dict:
    """Default yfinance info dict for a stock."""
    return {
        "currentPrice": 180.0,
        "regularMarketPrice": 180.0,
        "shortName": "Apple Inc.",
        "longName": "Apple Inc.",
        "currency": "USD",
        "marketCap": 2_800_000_000_000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "quoteType": "EQUITY",
        "trailingPE": 30.0,
        "forwardPE": 28.0,
        "priceToBook": 45.0,
        "dividendYield": 0.0055,
        "beta": 1.2,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 140.0,
        "fiftyDayAverage": 175.0,
        "twoHundredDayAverage": 160.0,
        "sharesOutstanding": 15_000_000_000,
        "dividendRate": 1.0,
        **(info or {}),
    }


@pytest.fixture
def mock_yfinance(monkeypatch):
    """Monkeypatch yfinance to return canned data so tests don't hit the network."""
    import yfinance as yf

    class MockTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self._info = mock_yf_info()
            # Canned dividend history: quarterly $0.25/share, 4 payments in 2024
            import pandas as pd
            self._dividends = pd.Series(
                [0.25, 0.25, 0.25, 0.25],
                index=pd.to_datetime(["2024-02-01", "2024-05-01", "2024-08-01", "2024-11-01"]),
            )

        @property
        def info(self) -> dict:
            return self._info

        @property
        def fast_info(self):
            return type("obj", (object,), {"last_price": self._info.get("currentPrice", 180.0)})()

        @property
        def dividends(self):
            return self._dividends

        @property
        def splits(self):
            import pandas as pd
            return pd.Series(dtype=float)

        @property
        def calendar(self):
            return None

        @property
        def institutional_holders(self):
            return None

        @property
        def insider_transactions(self):
            return None

        @property
        def recommendations_summary(self):
            return None

        @property
        def earnings_estimate(self):
            return None

        @property
        def revenue_estimate(self):
            return None

        @property
        def income_stmt(self):
            return None

        @property
        def balance_sheet(self):
            return None

        @property
        def cashflow(self):
            return None

        @property
        def quarterly_income_stmt(self):
            return None

        @property
        def quarterly_balance_sheet(self):
            return None

        @property
        def quarterly_cashflow(self):
            return None

        def history(self, **kwargs):
            import pandas as pd
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", MockTicker)
    monkeypatch.setattr(yf, "download", lambda *args, **kwargs: pd.DataFrame())
    return MockTicker
