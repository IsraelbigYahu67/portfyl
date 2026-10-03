"""Cash model v2: T212 full-history import, settlement-aware signed_cash,
and accrual start after the last real interest row.

The fixture rows are verbatim lines from a real Trading 212 export
(portfoliodata.csv) — one of each action type the importer must handle.
"""

from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from cash_ledger import (
    CASH_TYPES,
    EXTERNAL_FLOW_TYPES,
    accrued_interest,
    cash_balance_by_currency,
    has_external_cashflows,
    signed_cash,
)
from models import Portfolio, Transaction
from import_workflow import deduplicate_rows
from routers.portfolio import (
    _is_t212,
    _normalize_t212,
    _normalize_t212_detailed,
    import_csv,
)
from tests.helpers import T212_COVERAGE_FIELDS, make_t212_connection_with_coverage, make_txn

_T212_HEADER = (
    "Action,Time,ISIN,Ticker,Name,Notes,ID,No. of shares,Price / share,"
    "Currency (Price / share),Exchange rate,Result,Currency (Result),Total,"
    "Currency (Total),Withholding tax,Currency (Withholding tax),"
    "Currency conversion from amount,Currency (Currency conversion from amount),"
    "Currency conversion to amount,Currency (Currency conversion to amount),"
    "Currency conversion fee,Currency (Currency conversion fee),Merchant name,Merchant category"
)

_T212_ROWS = [
    'Deposit,2026-01-19 19:21:23,,,,"Bank Transfer",019bd7b4-6854-737b-b684-d370d418a7b7,,,,,,,68050.00,"CZK",,,,,,,,,,',
    'Interest on cash,2026-01-20 02:11:32,,,,"Interest on cash",019bd92b-eb5b-7235-ae55-af03f2fb1e55,,,,,,,6.76,"CZK",,,,,,,,,,',
    'Market buy,2026-01-20 10:28:43,US90353T1007,UBER,"Uber Technologies",,EOF45353502272,0.6700000000,83.5000000000,USD,0.04818109,,,1162.88,"CZK",,,,,,,1.74,"CZK",,',
    'Market sell,2026-01-22 18:02:39,US0919471013,BTGO,"BitGo",,EOF45459915169,1.0000000000,22.4200000000,USD,0.04843064,-11.03,"CZK",462.24,"CZK",,,,,,,0.69,"CZK",,',
    'Limit sell,2026-07-07 14:52:38,US3032501047,FICO,"Fair Isaac",,EOF53809672546,0.0300000000,1318.6800000000,USD,0.04718896,165.27,"CZK",837.08,"CZK",,,,,,,1.26,"CZK",,',
    'Dividend (Dividend),2026-03-11 15:20:28,US78409V1044,SPGI,"S&P Global",,,0.3500000000,0.824500,USD,20.96750000,,,6.05,"CZK",0.05,USD,,,,,,,,',
    'Card debit,2026-01-24 20:14:30,,,,,019bf4ab-4efa-7340-8baa-5995cbf7a857,,,,,,,-388.00,"CZK",,,,,,,,,"Allegro","MISCELLANEOUS"',
    'Spending cashback,2026-01-26 02:19:33,,,,,019bf819-6ae9-7dd7-a3d7-e117a9b1a764,,,,,,,5.82,"CZK",,,,,,,,,,',
    'Withdrawal,2026-03-09 17:48:08,,,,,019cd3b6-a49f-7866-9cce-5e5335c2f5d5,,,,,,,-500.00,"CZK",,,,,,,,,,',
    'Currency conversion,2026-06-03 11:13:59,,,,"5.00 USD -> 104.08 CZK",TZZIPQ4HBW4VFBP5,,,,,,,-0.16,"CZK",,,5.00,"USD",104.08,"CZK",-0.16,"CZK",,',
    'Lending interest,2026-03-20 05:07:50,,,,"Share lending interest",019d09a4-84d1-7b82-af12-79fcb320cd22,,,,,,,0.06,"CZK",,,,,,,,,,',
    'ADR Fee,2026-08-25 13:28:09,US83013J1051,SKHY,"Sky Harbour Group",,,0.40000000,-0.02000000,USD,,,,0.00,,,,,,,,,,,',
    'Stock split open,2026-07-16 07:32:21,US46116X1019,GNPX,"Genprex",,,0.6818181800,45.7893334600,USD,0.04818109,,,646.40,CZK,,,,,,,,,,',
    'Stock split close,2026-07-16 07:32:21,US46116X1019,GNPX,"Genprex",,,15.0000000000,2.0813333300,USD,0.04818109,,,646.40,CZK,,,,,,,,,,',
]

# Hand-computed CZK cash impact of the fixture (Total column, signed by type):
# +68050 +6.76 -1162.88 +462.24 +837.08 +6.05 -388 +5.82 -500
# +104.08 -0.16 +0.06. ADR fee is 0.008 USD; split rows have no cash impact.
_EXPECTED_CZK = 67421.05
_EXPECTED_USD = -5.00  # the fx_out leg of the currency conversion
_EXPECTED_USD_WITH_ADR_FEE = -5.008


def _normalized_rows():
    df = pd.read_csv(io.StringIO(_T212_HEADER + "\n" + "\n".join(_T212_ROWS)))
    df.columns = df.columns.str.lower().str.strip()
    assert _is_t212(set(df.columns))
    return _normalize_t212(df)


def _by_type(rows):
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["type"], []).append(r)
    return out


class TestNormalizeT212:
    def test_time_utc_header_is_accepted(self):
        csv_text = (_T212_HEADER.replace("Time", "Time (UTC)") + "\n" + _T212_ROWS[0])
        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = df.columns.str.lower().str.strip()

        assert _is_t212(set(df.columns))
        rows, skipped = _normalize_t212(df)
        assert skipped == 0
        assert rows[0]["date"] == date(2026, 1, 19)
        assert rows[0]["executed_at"] == datetime(
            2026, 1, 19, 19, 21, 23, tzinfo=timezone.utc,
        )
        assert rows[0]["source_event_id"] == "019bd7b4-6854-737b-b684-d370d418a7b7"
        assert rows[0]["source_event_stream"] == "csv_export"

    def test_all_recognized_events_are_normalized(self):
        rows, skipped = _normalized_rows()
        types = _by_type(rows)
        assert skipped == 0
        assert len(rows) == 16
        assert len(types["buy"]) == 1
        assert len(types["sell"]) == 2  # Market sell + Limit sell
        assert len(types["dividend"]) == 1
        assert len(types["interest"]) == 2  # cash interest + share-lending income
        assert len(types["fee"]) == 2       # FX conversion fee + ADR fee
        assert len(types["split_open"]) == 1
        assert len(types["split_close"]) == 1
        for t in ("deposit", "withdrawal", "card_debit", "cashback", "fx_in", "fx_out"):
            assert len(types[t]) == 1, t

    def test_lending_income_and_adr_fee_are_internal_cash_events(self):
        rows, _ = _normalized_rows()
        types = _by_type(rows)
        lending = [r for r in types["interest"] if "lending" in r["notes"].lower()][0]
        adr = [r for r in types["fee"] if "adr" in r["notes"].lower()][0]

        assert lending["amount"] == pytest.approx(0.06)
        assert lending["currency"] == "CZK"
        assert adr["amount"] == pytest.approx(0.008)
        assert adr["currency"] == "USD"

    def test_buy_settlement_and_exact_fx(self):
        rows, _ = _normalized_rows()
        buy = _by_type(rows)["buy"][0]
        assert buy["ticker"] == "UBER"
        assert buy["shares"] == pytest.approx(0.67)
        assert buy["price"] == pytest.approx(83.50)
        assert buy["currency"] == "USD"
        # Total (CZK, FX fee included) is the exact cash the buy consumed.
        assert buy["cash_amount"] == pytest.approx(1162.88)
        assert buy["cash_currency"] == "CZK"
        # Trades quote Exchange rate as USD per 1 CZK.
        assert buy["fx_to_czk"] == pytest.approx(1 / 0.04818109)

    def test_dividend_settlement_and_inverted_fx(self):
        rows, _ = _normalized_rows()
        div = _by_type(rows)["dividend"][0]
        assert div["ticker"] == "SPGI"
        assert div["cash_amount"] == pytest.approx(6.05)
        assert div["cash_currency"] == "CZK"
        # Dividends derive fx from Total/(shares*price) ~= the export's 20.9675.
        assert div["fx_to_czk"] == pytest.approx(20.9675, rel=1e-3)

    def test_cash_rows(self):
        rows, _ = _normalized_rows()
        types = _by_type(rows)
        assert types["deposit"][0]["amount"] == pytest.approx(68050.00)
        assert types["deposit"][0]["currency"] == "CZK"
        # Negative Totals (withdrawal/card debit) are stored as positive
        # magnitudes; direction lives in the type.
        assert types["withdrawal"][0]["amount"] == pytest.approx(500.00)
        assert types["card_debit"][0]["amount"] == pytest.approx(388.00)
        assert "Allegro" in types["card_debit"][0]["notes"]
        assert types["cashback"][0]["amount"] == pytest.approx(5.82)
        assert types["interest"][0]["amount"] == pytest.approx(6.76)

    def test_currency_conversion_becomes_three_legs(self):
        rows, _ = _normalized_rows()
        types = _by_type(rows)
        assert types["fx_out"][0]["amount"] == pytest.approx(5.00)
        assert types["fx_out"][0]["currency"] == "USD"
        assert types["fx_in"][0]["amount"] == pytest.approx(104.08)
        assert types["fx_in"][0]["currency"] == "CZK"
        assert types["fee"][0]["amount"] == pytest.approx(0.16)
        assert types["fee"][0]["currency"] == "CZK"
        assert {
            types["fx_out"][0]["source_event_id"],
            types["fx_in"][0]["source_event_id"],
            types["fee"][0]["source_event_id"],
        } == {
            "TZZIPQ4HBW4VFBP5:fx_out",
            "TZZIPQ4HBW4VFBP5:fx_in",
            "TZZIPQ4HBW4VFBP5:fee",
        }

    def test_distinct_export_ids_preserve_identical_same_second_fills(self):
        row = {
            "Action": "Market buy",
            "Time (UTC)": "2026-01-20 10:28:43",
            "Ticker": "AAPL",
            "No. of shares": 1,
            "Price / share": 100,
            "Currency (Price / share)": "USD",
            "Total": 2100,
            "Currency (Total)": "CZK",
        }
        df = pd.DataFrame([{**row, "ID": "fill-1"}, {**row, "ID": "fill-2"}])
        df.columns = df.columns.str.lower().str.strip()

        rows, skipped, errors = _normalize_t212_detailed(df)
        unique, repeated = deduplicate_rows(rows)

        assert skipped == 0
        assert errors == []
        assert repeated == 0
        assert [item["source_event_id"] for item in unique] == ["fill-1", "fill-2"]


@pytest.mark.parametrize(
    "bad_row",
    [
        {
            "Action": "Mystery action",
            "Time (UTC)": "2026-01-20 10:28:43",
            "Ticker": "AAPL",
            "No. of shares": 1,
            "Price / share": 100,
            "Total": 2100,
            "Currency (Total)": "CZK",
        },
        {
            "Action": "Market buy",
            "Time (UTC)": "2026-01-20 10:28:43",
            "Ticker": "",
            "No. of shares": 1,
            "Price / share": 100,
            "Total": 2100,
            "Currency (Total)": "CZK",
        },
        {
            "Action": "Cash in",
            "Time (UTC)": "2026-01-20 10:28:43",
            "Ticker": "",
            "No. of shares": "",
            "Price / share": "",
            "Total": 100,
            "Currency (Total)": "CZK",
        },
        {
            "Action": "Stock split open",
            "Time (UTC)": "2026-01-20 10:28:43",
            "Ticker": "SPLT",
            "No. of shares": 5,
            "Price / share": 200,
            "Total": 1000,
            "Currency (Total)": "USD",
        },
    ],
)
def test_failed_t212_normalization_cannot_replace_existing_rows(db_session, default_portfolio, bad_row):
    pid = default_portfolio.id
    old = make_txn("MSFT", "buy", 2, 300, source="t212_api", portfolio_id=pid)
    db_session.add(old)
    db_session.commit()

    payload = pd.DataFrame([bad_row]).to_csv(index=False).encode()
    upload = UploadFile(filename="bad-t212.csv", file=io.BytesIO(payload))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(import_csv(file=upload, replace=True, db=db_session,
                               portfolio=default_portfolio))

    assert exc_info.value.status_code == 400
    assert "Row 2" in str(exc_info.value.detail)
    remaining = db_session.query(Transaction).filter(Transaction.portfolio_id == pid).all()
    assert len(remaining) == 1
    assert remaining[0].ticker == "MSFT"
    assert remaining[0].source == "t212_api"


def test_t212_accepts_same_day_trade_and_split_when_timestamp_can_be_persisted():
    df = pd.DataFrame([
        {
            "Action": "Stock split close",
            "Time (UTC)": "2026-01-20 08:00:00",
            "Ticker": "SPLT",
            "No. of shares": 10,
            "Price / share": 100,
            "Total": 1000,
            "Currency (Total)": "USD",
        },
        {
            "Action": "Stock split open",
            "Time (UTC)": "2026-01-20 08:00:00",
            "Ticker": "SPLT",
            "No. of shares": 5,
            "Price / share": 200,
            "Total": 1000,
            "Currency (Total)": "USD",
        },
        {
            "Action": "Market buy",
            "Time (UTC)": "2026-01-20 12:00:00",
            "Ticker": "SPLT",
            "No. of shares": 1,
            "Price / share": 205,
            "Currency (Price / share)": "USD",
            "Total": 4200,
            "Currency (Total)": "CZK",
        },
    ])
    df.columns = df.columns.str.lower().str.strip()

    rows, _, errors = _normalize_t212_detailed(df)

    assert errors == []
    assert all(item["executed_at"] is not None for item in rows)


def test_valid_t212_replace_is_atomic_and_marks_csv_source(db_session, default_portfolio):
    pid = default_portfolio.id
    db_session.add(make_txn("MSFT", "buy", 2, 300, source="t212_api", portfolio_id=pid))
    db_session.commit()

    payload = pd.DataFrame([{
        "Action": "Deposit",
        "Time (UTC)": "2026-01-19 19:21:23",
        "Ticker": "",
        "No. of shares": "",
        "Price / share": "",
        "ID": "deposit-1",
        "Total": 68050,
        "Currency (Total)": "CZK",
    }]).to_csv(index=False).encode()
    upload = UploadFile(filename="full-t212.csv", file=io.BytesIO(payload))

    result = asyncio.run(import_csv(file=upload, replace=False, db=db_session,
                                    portfolio=default_portfolio))

    assert result["replaced"] is True
    assert result["events"] == 1
    assert result["processed_events"] == 1
    rows = db_session.query(Transaction).filter(Transaction.portfolio_id == pid).all()
    assert len(rows) == 1
    assert rows[0].type == "deposit"
    assert rows[0].source == "t212_csv"
    assert rows[0].source_event_id == "deposit-1"
    assert rows[0].source_event_stream == "csv_export"
    assert rows[0].executed_at == datetime(2026, 1, 19, 19, 21, 23)
    portfolio = db_session.query(Portfolio).filter(Portfolio.id == pid).one()
    assert portfolio.t212_csv_covered_through.isoformat() == "2026-01-19T19:21:23"


class TestSettlementSignedCash:
    def _txns(self):
        rows, _ = _normalized_rows()
        return [Transaction(**r, portfolio_id=1) for r in rows]

    def test_balance_reconciles_with_broker_totals(self):
        balances = cash_balance_by_currency(self._txns())
        assert balances["CZK"] == pytest.approx(_EXPECTED_CZK, abs=0.01)
        assert balances["USD"] == pytest.approx(_EXPECTED_USD_WITH_ADR_FEE, abs=0.001)

    def test_buy_pulls_settlement_currency(self):
        buy = make_txn(type="buy", shares=0.67, price=83.50, currency="USD",
                       cash_amount=1162.88, cash_currency="CZK")
        assert signed_cash(buy) == ("CZK", pytest.approx(-1162.88))

    def test_sell_and_dividend_push_settlement_currency(self):
        sell = make_txn(type="sell", shares=1.0, price=22.42, currency="USD",
                        cash_amount=462.24, cash_currency="CZK")
        div = make_txn(type="dividend", shares=0.35, price=0.8245, currency="USD",
                       cash_amount=6.05, cash_currency="CZK")
        assert signed_cash(sell) == ("CZK", pytest.approx(462.24))
        assert signed_cash(div) == ("CZK", pytest.approx(6.05))

    def test_legacy_trade_without_settlement_falls_back_to_native(self):
        buy = make_txn(type="buy", shares=10, price=150.0, currency="USD")
        assert signed_cash(buy) == ("USD", pytest.approx(-1500.0))

    def test_new_types_membership_and_direction(self):
        assert {"card_debit", "cashback", "fx_in", "fx_out"} <= CASH_TYPES
        assert EXTERNAL_FLOW_TYPES == {"deposit", "withdrawal", "card_debit", "cashback"}
        card = make_txn(ticker=None, type="card_debit", shares=0.0, price=0.0,
                        amount=388.0, currency="CZK")
        back = make_txn(ticker=None, type="cashback", shares=0.0, price=0.0,
                        amount=5.82, currency="CZK")
        assert signed_cash(card) == ("CZK", pytest.approx(-388.0))
        assert signed_cash(back) == ("CZK", pytest.approx(5.82))
        assert has_external_cashflows([card])
        assert has_external_cashflows([back])
        fxo = make_txn(ticker=None, type="fx_out", shares=0.0, price=0.0,
                       amount=5.0, currency="USD")
        assert signed_cash(fxo) == ("USD", pytest.approx(-5.0))
        assert not has_external_cashflows([fxo])


class TestDisplayCurrencyConversion:
    """USD display used to sum native amounts with fx=1.0 (CZK cash counted as
    USD). Now every value converts native -> CZK (snapshot) -> display (live)."""

    def _patch_live_fx(self, monkeypatch):
        import routers.portfolio as rp
        monkeypatch.setattr(
            rp, "_live_fx_to_czk",
            lambda ccy, cache: {"CZK": 1.0, "USD": 20.0}[(ccy or "USD").upper()],
        )

    def test_usd_display_converts_czk_cost(self, monkeypatch):
        self._patch_live_fx(monkeypatch)
        from routers.portfolio import _build_holdings
        buy = make_txn(ticker="CEZ", type="buy", shares=10, price=100.0,
                       currency="CZK", fx_to_czk=1.0)
        usd = _build_holdings([buy], display_ccy="USD")
        czk = _build_holdings([buy], display_ccy="CZK")
        assert usd["CEZ"]["cost"] == pytest.approx(1000.0 / 20.0)
        assert czk["CEZ"]["cost"] == pytest.approx(1000.0)

    def test_usd_display_uses_historical_snapshot_for_usd_trades(self, monkeypatch):
        self._patch_live_fx(monkeypatch)
        from routers.portfolio import _build_holdings
        # Bought when USDCZK was 25; live rate is 20 -> the USD-display cost
        # reflects the FX move (25/20), it is no longer just shares*price.
        buy = make_txn(ticker="AAPL", type="buy", shares=1, price=100.0,
                       currency="USD", fx_to_czk=25.0)
        usd = _build_holdings([buy], display_ccy="USD")
        assert usd["AAPL"]["cost"] == pytest.approx(100.0 * 25.0 / 20.0)

    def test_default_stays_native_for_shares_only_callers(self):
        from routers.portfolio import _build_holdings
        buy = make_txn(ticker="AAPL", type="buy", shares=1, price=100.0,
                       currency="USD", fx_to_czk=25.0)
        native = _build_holdings([buy])
        assert native["AAPL"]["cost"] == pytest.approx(100.0)

    def test_cash_amount_to_display_really_converts(self, monkeypatch):
        import fx as fxmod
        monkeypatch.setattr(
            fxmod, "fetch_fx_to_czk",
            lambda ccy, d=None: {"CZK": 1.0, "USD": 20.0}[(ccy or "USD").upper()],
        )
        from fx import cash_amount_to_display
        # CZK cash viewed in USD must divide by the rate (old code returned it raw).
        assert cash_amount_to_display(60000.0, "CZK", "USD") == pytest.approx(3000.0)
        assert cash_amount_to_display(100.0, "USD", "CZK") == pytest.approx(2000.0)
        assert cash_amount_to_display(42.0, "CZK", "CZK") == pytest.approx(42.0)


class TestAccrualStartsAfterLastInterestRow:
    def test_accrual_skips_period_covered_by_imported_interest(self):
        deposit = make_txn(ticker=None, type="deposit", shares=0.0, price=0.0,
                           amount=10000.0, currency="CZK", date=date(2026, 1, 1))
        interest = make_txn(ticker=None, type="interest", shares=0.0, price=0.0,
                            amount=1.0, currency="CZK", date=date(2026, 1, 6))
        rates = {"CZK": {"annual_rate": 0.0365, "enabled": True, "start_date": None}}
        out = accrued_interest([deposit, interest], rates, as_of=date(2026, 1, 16))
        # Real interest covers through Jan 6 -> accrue Jan 7..Jan 16 = 9 day-gaps
        # on a 10001 balance: 10001 * 0.0365 * 9 / 365 = 9.00.
        assert out["CZK"] == pytest.approx(10001 * 0.0365 * 9 / 365, abs=0.01)

    def test_explicit_start_date_later_than_interest_wins(self):
        deposit = make_txn(ticker=None, type="deposit", shares=0.0, price=0.0,
                           amount=10000.0, currency="CZK", date=date(2026, 1, 1))
        interest = make_txn(ticker=None, type="interest", shares=0.0, price=0.0,
                            amount=1.0, currency="CZK", date=date(2026, 1, 6))
        rates = {"CZK": {"annual_rate": 0.0365, "enabled": True,
                         "start_date": date(2026, 1, 11)}}
        out = accrued_interest([deposit, interest], rates, as_of=date(2026, 1, 16))
        assert out["CZK"] == pytest.approx(10001 * 0.0365 * 5 / 365, abs=0.01)

    def test_no_interest_rows_behaves_as_before(self):
        deposit = make_txn(ticker=None, type="deposit", shares=0.0, price=0.0,
                           amount=10000.0, currency="CZK", date=date(2026, 1, 1))
        rates = {"CZK": {"annual_rate": 0.0365, "enabled": True, "start_date": None}}
        out = accrued_interest([deposit], rates, as_of=date(2026, 1, 11))
        assert out["CZK"] == pytest.approx(10000 * 0.0365 * 10 / 365, abs=0.01)


def test_t212_full_export_replace_clears_history_coverage(db_session, default_portfolio):
    pid = default_portfolio.id
    db_session.add(make_txn("MSFT", "buy", 2, 300, source="t212_api", portfolio_id=pid))
    connection = make_t212_connection_with_coverage(db_session, default_portfolio)
    payload = pd.DataFrame([{
        "Action": "Deposit",
        "Time (UTC)": "2026-01-19 19:21:23",
        "Ticker": "",
        "No. of shares": "",
        "Price / share": "",
        "ID": "deposit-1",
        "Total": 68050,
        "Currency (Total)": "CZK",
    }]).to_csv(index=False).encode()
    upload = UploadFile(filename="full-t212.csv", file=io.BytesIO(payload))

    result = asyncio.run(import_csv(file=upload, replace=False, db=db_session,
                                    portfolio=default_portfolio))

    assert result["replaced"] is True
    db_session.refresh(connection)
    assert [getattr(connection, field) for field in T212_COVERAGE_FIELDS] == [None] * len(T212_COVERAGE_FIELDS)
