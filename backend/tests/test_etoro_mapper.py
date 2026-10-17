import pytest

from etoro_mapper import map_account
from importers.base import validate_rows

INSTRUMENTS = {
    1001: {"symbol": "AAPL", "exchange": "NASDAQ", "type": "Stocks", "name": "Apple"},
    1002: {"symbol": "BRK.B", "exchange": "NYSE", "type": "Stocks"},
    2002: {"symbol": "BTC", "exchange": "Digital Currency", "type": "Crypto"},
    3003: {"symbol": "SAP.DE", "exchange": "Xetra ETFs", "type": "Stocks"},
    4004: {"symbol": "EURUSD", "exchange": "FX", "type": "Currencies"},
}


def _pos(pid, iid=1001, leverage=1, is_buy=True, closed=False, units=2.0, **extra):
    item = {"positionId": pid, "instrumentId": iid, "isBuy": is_buy, "leverage": leverage,
            "units": units, "openRate": 190.0, "openTimestamp": "2025-01-02T14:30:00Z", **extra}
    if closed:
        item.update(closeRate=200.0, closeTimestamp="2025-03-03T15:00:00Z")
    return item


def _open_snapshot(pid, iid=1001, **extra):
    """Open positions use the documented schema casing and openDateTime."""
    return {"positionID": pid, "instrumentID": iid, "isBuy": True, "leverage": 1, "units": 2.0,
            "openRate": 190.0, "openDateTime": "2025-01-02T14:30:00Z", **extra}


def test_closed_position_is_buy_and_sell():
    result = map_account([_pos(1, closed=True)], [], [], INSTRUMENTS)
    assert result.errors == [] and validate_rows(result.rows) == []
    assert [(r["type"], r["source_event_id"]) for r in result.rows] == [("buy", "1:open"), ("sell", "1:close")]
    buy, sell = result.rows
    assert buy["cash_amount"] == pytest.approx(380.0) and sell["cash_amount"] == pytest.approx(400.0)


def test_open_position_is_buy_only():
    result = map_account([], [_open_snapshot(2)], [], INSTRUMENTS)
    assert validate_rows(result.rows) == []
    assert [r["type"] for r in result.rows] == ["buy"]


def test_closing_fees_become_a_fee_row():
    result = map_account([_pos(8, closed=True, fees=1.5)], [], [], INSTRUMENTS)
    assert validate_rows(result.rows) == []
    [fee] = [r for r in result.rows if r["type"] == "fee"]
    assert fee["amount"] == 1.5 and fee["source_event_id"] == "8:fees"


def test_etoro_leveraged_position_skipped():
    result = map_account([_pos(3, leverage=5, closed=True)], [_pos(4, is_buy=False)], [], INSTRUMENTS)
    assert result.rows == [] and result.skipped_reasons == {"CFD / leveraged position": 2}


def test_copy_trading_skipped():
    result = map_account([], [_open_snapshot(9, mirrorID=55)], [], INSTRUMENTS)
    assert result.rows == [] and result.skipped_reasons == {"copy trading": 1}


def test_crypto_and_class_share_tickers():
    rows = map_account([], [_pos(5, iid=2002), _pos(10, iid=1002)], [], INSTRUMENTS).rows
    assert sorted(r["ticker"] for r in rows) == ["BRK-B", "BTC-USD"]


def test_non_us_listing_fails_closed():
    result = map_account([], [_pos(11, iid=3003)], [], INSTRUMENTS)
    assert result.rows == [] and any("SAP.DE" in e for e in result.errors)


def test_currency_instrument_is_counted_as_unsupported():
    result = map_account([], [_pos(12, iid=4004)], [], INSTRUMENTS)
    assert result.rows == [] and result.errors == []
    assert result.skipped_reasons == {"unsupported asset: Currencies": 1}


def test_position_open_in_history_and_positions_is_not_duplicated():
    result = map_account([_pos(6, closed=True)], [_open_snapshot(6)], [], INSTRUMENTS)
    assert sorted(r["source_event_id"] for r in result.rows) == ["6:close", "6:open"]


def test_partially_closed_position_needs_review():
    result = map_account([_pos(13, closed=True, units=1.0)], [_open_snapshot(13)], [], INSTRUMENTS)
    assert any("partially closed" in e for e in result.errors)


def test_unknown_instrument_is_error():
    result = map_account([], [_pos(7, iid=9999)], [], INSTRUMENTS)
    assert result.errors and result.rows == []


def test_cash_input_fails_closed_until_mapped():
    result = map_account([], [], [{"id": "1"}], INSTRUMENTS)
    assert any("not mapped yet" in e for e in result.errors)
