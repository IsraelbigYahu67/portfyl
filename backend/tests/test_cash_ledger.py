import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from cash_ledger import signed_cash, cash_balance_by_currency
from tests.helpers import make_txn


def _cash(type, amount, currency="USD", d=date(2024, 1, 1)):
    return make_txn(ticker=None, type=type, shares=None, price=None,
                    currency=currency, date=d, amount=amount)


def test_signed_cash_directions():
    assert signed_cash(_cash("deposit", 1000)) == ("USD", 1000.0)
    assert signed_cash(_cash("withdrawal", 300)) == ("USD", -300.0)
    assert signed_cash(_cash("fee", 5)) == ("USD", -5.0)
    assert signed_cash(_cash("interest", 12)) == ("USD", 12.0)


def test_signed_cash_trades_use_shares_price():
    assert signed_cash(make_txn(type="buy", shares=10, price=100, currency="USD")) == ("USD", -1000.0)
    assert signed_cash(make_txn(type="sell", shares=4, price=150, currency="USD")) == ("USD", 600.0)
    assert signed_cash(make_txn(type="dividend", shares=10, price=2, currency="USD")) == ("USD", 20.0)


def test_cash_balance_by_currency_mixes_flows_and_trades_per_currency():
    txns = [
        _cash("deposit", 5000, "USD"),
        make_txn(type="buy", shares=10, price=100, currency="USD"),   # -1000
        make_txn(type="sell", shares=2, price=150, currency="USD"),   # +300
        _cash("fee", 20, "USD"),                                      # -20
        _cash("deposit", 1000, "GBP"),
        _cash("withdrawal", 250, "GBP"),
    ]
    bal = cash_balance_by_currency(txns)
    assert round(bal["USD"], 2) == 4280.0   # 5000 -1000 +300 -20
    assert round(bal["GBP"], 2) == 750.0


def test_cash_balance_allows_negative():
    txns = [make_txn(type="buy", shares=1, price=100, currency="USD")]
    assert round(cash_balance_by_currency(txns)["USD"], 2) == -100.0


from cash_ledger import accrued_interest


def test_accrued_interest_straight_line_on_positive_balance():
    # 10,000 USD deposited 2024-01-01, 5% APY, as_of exactly one year later.
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": None}}
    acc = accrued_interest(txns, rates, as_of=date(2025, 1, 1))
    # 366 days in 2024 (leap): 10000 * 0.05 * 366/365 ≈ 501.37
    assert 500.0 <= acc["USD"] <= 503.0


def test_accrued_interest_disabled_currency_is_zero():
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": False, "start_date": None}}
    assert accrued_interest(txns, rates, as_of=date(2025, 1, 1)) == {}


def test_accrued_interest_only_positive_balances():
    txns = [make_txn(type="buy", shares=1, price=100, currency="USD", date=date(2024, 1, 1))]  # -100
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": None}}
    assert accrued_interest(txns, rates, as_of=date(2025, 1, 1)).get("USD", 0.0) == 0.0


def test_accrued_interest_respects_start_date():
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": date(2024, 7, 1)}}
    acc = accrued_interest(txns, rates, as_of=date(2025, 1, 1))
    # only ~184 days accrue: 10000 * 0.05 * 184/365 ≈ 252
    assert 240.0 <= acc["USD"] <= 260.0
