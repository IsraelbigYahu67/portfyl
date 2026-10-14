"""The value/cashflow series must be bit-for-bit what the quadratic version gave.

`_reference_build_value_cashflow_series` is the implementation as it stood
before the cash ledger became a running balance (it rescanned every earlier
transaction on every trading day). It is kept verbatim as the oracle: random
ledgers go through both and V and C must be *identical*, not approximately
equal -- the new code adds the same floats in the same order.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from cash_ledger import (
    EXTERNAL_FLOW_TYPES,
    POSITION_TYPES,
    cash_balance_by_currency,
    has_external_cashflows,
    signed_cash,
)
from routers.analytics import (
    _build_value_cashflow_series,
    _fx_to_usd_series,
    _load_close_panel,
    _price_to_usd,
    _ticker_currencies,
    _usd_series_to_display,
)
from ticker_map import yf_symbol
from tests.helpers import make_txn
from transaction_ordering import chronological_key


def _reference_build_value_cashflow_series(
    transactions: list,
    start_date: date,
    display_currency: str = "USD",
):
    """Pre-optimisation implementation, copied unchanged."""
    transactions = sorted(transactions, key=chronological_key)
    held_tickers = sorted({t.ticker for t in transactions if t.type in POSITION_TYPES and t.ticker})
    if not held_tickers:
        return None, None, None

    yf_to_orig: dict[str, str] = {}
    for t in held_tickers:
        yf_to_orig.setdefault(yf_symbol(t), t)
    yf_tickers = list(yf_to_orig.keys())

    closes = _load_close_panel(yf_tickers, start_date)
    if closes.empty:
        return None, None, None
    closes = closes.rename(columns=yf_to_orig)

    ticker_ccy = _ticker_currencies(held_tickers)
    fx_series = _fx_to_usd_series(set(ticker_ccy.values()), start_date, closes.index)

    txns_by_date: dict[date, list] = defaultdict(list)
    for t in transactions:
        txns_by_date[t.date].append(t)

    first_trading_day = closes.index[0].date()
    holdings: dict[str, float] = {}
    for d_key in [d for d in list(txns_by_date.keys()) if d < first_trading_day]:
        for txn in txns_by_date.pop(d_key):
            if txn.type == "buy":
                holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
            elif txn.type == "sell":
                prev = holdings.get(txn.ticker, 0)
                holdings[txn.ticker] = max(0.0, prev - min(txn.shares, prev))
            elif txn.type == "split_close":
                holdings[txn.ticker] = max(0.0, holdings.get(txn.ticker, 0) - txn.shares)
            elif txn.type == "split_open":
                holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares

    if has_external_cashflows(transactions):
        cash_ccys = {signed_cash(t)[0] for t in transactions}
        extra_ccys = cash_ccys - set(fx_series.keys()) - {"USD"}
        cash_fx_series = _fx_to_usd_series(extra_ccys, start_date, closes.index) if extra_ccys else {}
        combined_fx = {**fx_series, **cash_fx_series}

        pre_window_cash = [t for t in transactions if t.date < first_trading_day]
        cash_txns_to_date: list = list(pre_window_cash)

        values: list[float] = []
        cashflows: list[float] = []
        for date_idx in closes.index:
            curr_date = date_idx.date()
            cf_today = 0.0
            for d_key in [d for d in list(txns_by_date.keys()) if d <= curr_date]:
                for txn in txns_by_date.pop(d_key):
                    if txn.type == "buy":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
                    elif txn.type == "sell":
                        prev = holdings.get(txn.ticker, 0)
                        sold = min(txn.shares, prev)
                        holdings[txn.ticker] = max(0.0, prev - sold)
                    elif txn.type == "split_close":
                        holdings[txn.ticker] = max(
                            0.0, holdings.get(txn.ticker, 0) - txn.shares
                        )
                    elif txn.type == "split_open":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares

                    if txn.type in EXTERNAL_FLOW_TYPES:
                        amt_usd = _price_to_usd(txn.amount, (txn.currency or "USD").upper(), combined_fx, date_idx)
                        if pd.notna(amt_usd):
                            cf_today += amt_usd if txn.type in ("deposit", "cashback") else -amt_usd
                    cash_txns_to_date.append(txn)

            v = 0.0
            for tk, sh in holdings.items():
                if sh <= 0 or tk not in closes.columns:
                    continue
                try:
                    p = float(closes.loc[date_idx, tk])
                except Exception:
                    continue
                p_usd = _price_to_usd(p, ticker_ccy.get(tk, "USD"), fx_series, date_idx)
                if pd.notna(p_usd):
                    v += sh * p_usd

            balances = cash_balance_by_currency(cash_txns_to_date)
            for ccy, bal in balances.items():
                bal_usd = _price_to_usd(bal, ccy, combined_fx, date_idx)
                if pd.notna(bal_usd):
                    v += bal_usd

            values.append(v)
            cashflows.append(cf_today)

        V = pd.Series(values, index=closes.index)
        C = pd.Series(cashflows, index=closes.index)
        V, C = _usd_series_to_display(V, C, start_date, display_currency)
        return V, C, closes.index
    else:
        values: list[float] = []
        cashflows: list[float] = []
        for date_idx in closes.index:
            curr_date = date_idx.date()
            cf_today = 0.0
            for d_key in [d for d in list(txns_by_date.keys()) if d <= curr_date]:
                for txn in txns_by_date.pop(d_key):
                    ccy = ticker_ccy.get(txn.ticker, "USD")
                    if txn.type == "buy":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
                        px_usd = _price_to_usd(txn.price, ccy, fx_series, date_idx)
                        if pd.notna(px_usd):
                            cf_today += txn.shares * px_usd
                    elif txn.type == "sell":
                        prev = holdings.get(txn.ticker, 0)
                        sold = min(txn.shares, prev)
                        holdings[txn.ticker] = max(0.0, prev - sold)
                        px_usd = _price_to_usd(txn.price, ccy, fx_series, date_idx)
                        if pd.notna(px_usd):
                            cf_today -= sold * px_usd

            v = 0.0
            for tk, sh in holdings.items():
                if sh <= 0 or tk not in closes.columns:
                    continue
                try:
                    p = float(closes.loc[date_idx, tk])
                except Exception:
                    continue
                p_usd = _price_to_usd(p, ticker_ccy.get(tk, "USD"), fx_series, date_idx)
                if pd.notna(p_usd):
                    v += sh * p_usd

            values.append(v)
            cashflows.append(cf_today)

        V = pd.Series(values, index=closes.index)
        C = pd.Series(cashflows, index=closes.index)
        V, C = _usd_series_to_display(V, C, start_date, display_currency)
        return V, C, closes.index


# ---------------------------------------------------------------------------
# Synthetic market and ledger generator
# ---------------------------------------------------------------------------

LISTING_CCY = {"AAA": "USD", "BBB": "EUR", "CCC": "GBp", "DDD": "CZK"}
# SEK has no FX history on purpose: its cash must be skipped, not zeroed.
CASH_CCYS = ["USD", "EUR", "CZK", "GBP", "SEK"]
FX_TO_USD = {"EUR": 1.08, "GBP": 1.27, "CZK": 0.043}


class _FakeMarket:
    """Deterministic stand-in for Yahoo: closes, split column and FX history."""

    def __init__(self, rng: random.Random, first_day: date, n_days: int):
        self.index = pd.bdate_range(first_day, periods=n_days)
        self.closes = pd.DataFrame(
            {
                tk: [rng.uniform(5, 400) for _ in range(n_days)]
                for tk in LISTING_CCY
            },
            index=self.index,
        )
        self.fx: dict[str, pd.Series] = {}
        for ccy, base in FX_TO_USD.items():
            series = pd.Series(
                [base * rng.uniform(0.9, 1.1) for _ in range(n_days)], index=self.index
            )
            # Holes force the forward-fill path.
            self.fx[ccy] = series.drop(series.index[[i for i in range(n_days) if rng.random() < 0.05]])

    def download(self, tickers, start=None, **_kwargs):
        if isinstance(tickers, str):
            ccy = tickers[:3]
            if ccy not in self.fx:
                return pd.DataFrame()
            fx = self.fx[ccy]
            return pd.DataFrame({"Close": fx[fx.index >= pd.Timestamp(start)]})
        closes = self.closes[self.closes.index >= pd.Timestamp(start)][list(tickers)]
        return pd.concat(
            {"Close": closes, "Stock Splits": closes * 0.0},
            axis=1,
        )

    def infos(self, tickers):
        return {tk: {"currency": LISTING_CCY.get(tk, "USD")} for tk in tickers}


def _cash_row(rng: random.Random, type_: str, day: date):
    return make_txn(
        ticker=None, type=type_, shares=0.0, price=0.0,
        amount=rng.uniform(1, 9000), currency=rng.choice(CASH_CCYS), date=day,
    )


def make_ledger(
    rng: random.Random,
    n_txns: int,
    first_day: date,
    last_day: date,
    *,
    external: bool = True,
) -> list:
    """A messy ledger: weekends, several rows per day, rows before the first
    trading day, rows after the last, splits, and `executed_at` timestamps whose
    UTC date differs from `date` (so chronological order != date-key order)."""
    span = (last_day - first_day).days
    txns: list = []
    cash_types = ["fee", "interest", "fx_in", "fx_out"]
    if external:
        cash_types += ["deposit", "deposit", "withdrawal", "card_debit", "cashback"]
        txns.append(_cash_row(rng, "deposit", first_day - timedelta(days=20)))

    for _ in range(n_txns):
        day = first_day + timedelta(days=rng.randint(-40, span + 8))
        roll = rng.random()
        if roll < 0.30:
            txn = _cash_row(rng, rng.choice(cash_types), day)
        elif roll < 0.42:
            tk = rng.choice(list(LISTING_CCY))
            txn = make_txn(
                tk, "dividend", rng.uniform(1, 50), rng.uniform(0.1, 3),
                currency=LISTING_CCY[tk].upper(), date=day,
                cash_amount=rng.uniform(1, 300), cash_currency=rng.choice(CASH_CCYS),
            )
        elif roll < 0.46:
            tk = rng.choice(list(LISTING_CCY))
            shares = rng.uniform(1, 40)
            txns.append(make_txn(tk, "split_close", shares, 0.0, date=day))
            txn = make_txn(tk, "split_open", shares * 2, 0.0, date=day)
        else:
            tk = rng.choice(list(LISTING_CCY))
            kind = "buy" if roll < 0.74 else "sell"
            shares = rng.uniform(0.5, 30)
            price = rng.uniform(5, 400)
            with_settlement = rng.random() < 0.6
            txn = make_txn(
                tk, kind, shares, price, currency=LISTING_CCY[tk].upper(), date=day,
                cash_amount=shares * price * rng.uniform(0.95, 1.05) if with_settlement else None,
                cash_currency=rng.choice(CASH_CCYS) if with_settlement else None,
            )
        if rng.random() < 0.25 and txn.date:
            # Evening trade: UTC date is the next calendar day.
            txn.executed_at = datetime.combine(
                txn.date + timedelta(days=rng.choice([-1, 1])), datetime.min.time(),
                tzinfo=timezone.utc,
            ) + timedelta(hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        txns.append(txn)

    rng.shuffle(txns)
    return txns


def _run(build, market, txns, start, display="USD"):
    with patch("routers.analytics.market_data.download", side_effect=market.download), \
         patch("routers.analytics.market_data.get_infos", side_effect=market.infos):
        return build(txns, start, display)


def _assert_identical(got, expected):
    V, C, idx = got
    ref_V, ref_C, ref_idx = expected
    assert V is not None
    assert idx.equals(ref_idx)
    pd.testing.assert_series_equal(V, ref_V, check_exact=True)
    pd.testing.assert_series_equal(C, ref_C, check_exact=True)


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("external", [True, False], ids=["cash-aware", "trades-only"])
def test_series_matches_reference_on_random_ledgers(seed, external):
    rng = random.Random(seed)
    first_day, last_day = date(2022, 3, 1), date(2023, 6, 30)
    market = _FakeMarket(rng, first_day, n_days=330)
    txns = make_ledger(rng, 260, first_day, last_day, external=external)
    start = first_day - timedelta(days=5)

    got = _run(_build_value_cashflow_series, market, txns, start)
    expected = _run(_reference_build_value_cashflow_series, market, txns, start)

    _assert_identical(got, expected)
    assert (got[0] != 0).any()
    if external:
        assert (got[1] != 0).any()


def test_series_matches_reference_in_czk_display_currency():
    rng = random.Random(99)
    first_day, last_day = date(2022, 3, 1), date(2023, 3, 31)
    market = _FakeMarket(rng, first_day, n_days=260)
    txns = make_ledger(rng, 150, first_day, last_day)
    start = first_day - timedelta(days=5)

    got = _run(_build_value_cashflow_series, market, txns, start, "CZK")
    expected = _run(_reference_build_value_cashflow_series, market, txns, start, "CZK")

    _assert_identical(got, expected)


def test_series_matches_reference_for_several_rows_on_one_day():
    rng = random.Random(7)
    first_day = date(2023, 1, 2)
    market = _FakeMarket(rng, first_day, n_days=20)
    day = date(2023, 1, 5)
    txns = [
        make_txn(None, "deposit", 0, 0, amount=1000.1, currency="EUR", date=first_day),
        make_txn("AAA", "buy", 3, 100.1, date=day, cash_amount=300.3, cash_currency="CZK"),
        make_txn(None, "deposit", 0, 0, amount=0.7, currency="EUR", date=day),
        make_txn("AAA", "sell", 1, 120.2, date=day, cash_amount=120.2, cash_currency="CZK"),
        make_txn(None, "fee", 0, 0, amount=0.3, currency="EUR", date=day),
        make_txn("BBB", "buy", 2, 50.5, currency="EUR", date=day),
    ]
    start = first_day - timedelta(days=5)

    got = _run(_build_value_cashflow_series, market, txns, start)
    expected = _run(_reference_build_value_cashflow_series, market, txns, start)

    _assert_identical(got, expected)
