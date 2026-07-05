import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from routers.portfolio import _build_holdings
from tests.helpers import make_txn


def test_cash_rows_do_not_affect_holdings():
    trades = [make_txn(type="buy", shares=10, price=100, currency="USD")]
    cash = [make_txn(ticker=None, type="deposit", shares=None, price=None,
                     currency="USD", amount=5000, date=date(2024, 1, 1))]
    only_trades = _build_holdings(trades)
    with_cash = _build_holdings(trades + cash)
    assert with_cash.keys() == only_trades.keys()
    assert with_cash == only_trades


def test_cash_rows_do_not_leak_into_closed_holdings():
    """include_closed=True is the path get_holdings actually uses. Without the
    TRADE_TYPES guard, a cash `deposit` (ticker=None) creates a stray None key
    in the holdings dict, which then flows into price/FX lookups downstream."""
    trades = [make_txn(type="buy", shares=10, price=100, currency="USD")]
    cash = [
        make_txn(ticker=None, type="deposit", shares=None, price=None,
                 currency="USD", amount=5000, date=date(2024, 1, 1)),
        make_txn(ticker=None, type="withdrawal", shares=None, price=None,
                 currency="USD", amount=200, date=date(2024, 1, 2)),
        make_txn(ticker=None, type="interest", shares=None, price=None,
                 currency="USD", amount=12, date=date(2024, 1, 3)),
        make_txn(ticker=None, type="fee", shares=None, price=None,
                 currency="USD", amount=5, date=date(2024, 1, 4)),
    ]
    only_trades = _build_holdings(trades, include_closed=True)
    with_cash = _build_holdings(trades + cash, include_closed=True)
    assert None not in with_cash
    assert with_cash.keys() == only_trades.keys()
    assert with_cash == only_trades
