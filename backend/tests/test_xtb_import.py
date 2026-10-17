import io
from datetime import datetime, timezone

import pytest
from openpyxl import Workbook

from importers import registry
from importers.base import ImportFile, validate_rows
from importers.formats import xtb
from importers.instruments import DefaultInstrumentResolver

RESOLVER = DefaultInstrumentResolver(figi=None)


def _workbook(rows, currency="CZK"):
    wb = Workbook()
    ws = wb.active
    ws.title = "CASH OPERATION HISTORY"
    ws.append(["Account", "51234567"])
    ws.append(["Currency", currency])
    ws.append([])
    ws.append(["ID", "Type", "Time", "Comment", "Symbol", "Amount"])
    for row in rows:
        ws.append(row)
    wb.create_sheet("CLOSED POSITION HISTORY")
    buffer = io.BytesIO()
    wb.save(buffer)
    return ImportFile("xtb.xlsx", buffer.getvalue())


ROWS = [
    [1, "Deposit", datetime(2025, 1, 2, 9, 0), "Deposit", None, 50000],
    [2, "Stocks/ETF purchase", datetime(2025, 1, 2, 15, 31), "OPEN BUY 10 @ 190.50", "AAPL.US", -44005.5],
    [3, "DIVIDENT", datetime(2025, 5, 15, 8, 0), "AAPL.US USD 0.2500/ SHR", "AAPL.US", 57.75],
    [4, "Withholding Tax", datetime(2025, 5, 15, 8, 0), "AAPL.US USD WHT 15%", "AAPL.US", -8.66],
    [5, "Stocks/ETF sale", datetime(2025, 6, 2, 10, 0), "CLOSE BUY 4 @ 200.00", "AAPL.US", 18480.0],
    [6, "close trade", datetime(2025, 6, 3, 10, 0), "CLOSE BUY 0.1 @ 18000", "US500", 1200.0],
    [7, "Free-funds Interest", datetime(2025, 6, 30, 0, 0), "Free-funds Interest", None, 35.2],
    [8, "Free-funds Interest Tax", datetime(2025, 6, 30, 0, 0), "Free-funds Interest Tax", None, -5.28],
    [9, "CEZ.CZ purchase", datetime(2025, 7, 1, 10, 0), "OPEN BUY 5 @ 1000", "CEZ.CZ", -5000],
]


def test_detect_xlsx_only():
    assert xtb.FORMAT.detect(_workbook(ROWS))
    assert not xtb.FORMAT.detect(ImportFile("x.csv", b"a,b\n"))


def test_detect_rejects_corrupt_zip_and_other_workbooks():
    assert not xtb.FORMAT.detect(ImportFile("broken.xlsx", b"PK\x03\x04 not really a zip"))
    wb = Workbook()
    wb.active.title = "Portfolio"
    buffer = io.BytesIO()
    wb.save(buffer)
    assert not xtb.FORMAT.detect(ImportFile("other.xlsx", buffer.getvalue()))


def test_registry_picks_xtb_unambiguously():
    assert registry.detect_format(_workbook(ROWS)) is xtb.FORMAT


def test_trades_from_comment():
    result = xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    [buy] = [r for r in result.rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["price"], buy["currency"]) == ("AAPL", 10, 190.5, "USD")
    assert (buy["cash_amount"], buy["cash_currency"]) == (44005.5, "CZK")
    [sell] = [r for r in result.rows if r["type"] == "sell"]
    assert sell["shares"] == 4 and sell["price"] == 200.0


def test_server_time_is_converted_to_utc():
    [buy] = [r for r in xtb.FORMAT.parse(_workbook(ROWS[1:2]), RESOLVER).rows]
    assert buy["executed_at"] == datetime(2025, 1, 2, 14, 31, tzinfo=timezone.utc)


def test_dividend_net_in_account_currency():
    [div] = [r for r in xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER).rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(49.09) and div["cash_currency"] == "CZK"


def test_xtb_cfd_rows_skipped():
    result = xtb.FORMAT.parse(_workbook([ROWS[5]]), RESOLVER)
    assert result.skipped_reasons == {"CFD trade": 1}
    assert result.errors == []


def test_interest_tax_becomes_fee():
    rows = xtb.FORMAT.parse(_workbook(ROWS[6:8]), RESOLVER).rows
    assert sorted((r["type"], r["amount"]) for r in rows) == [("fee", 5.28), ("interest", 35.2)]


def test_unknown_type_is_error():
    result = xtb.FORMAT.parse(_workbook([ROWS[8]]), RESOLVER)
    assert any("CEZ.CZ purchase" in e for e in result.errors)


def test_unresolved_symbol_is_error_not_a_row():
    row = [10, "Stocks/ETF purchase", datetime(2025, 1, 3, 10, 0), "OPEN BUY 1 @ 10", "ABC.XX", -250]
    result = xtb.FORMAT.parse(_workbook([row]), RESOLVER)
    assert result.rows == []
    assert any("ABC.XX" in e for e in result.errors)


def test_unreadable_trade_comment_is_error():
    row = [11, "Stocks/ETF purchase", datetime(2025, 1, 3, 10, 0), "BUY something", "AAPL.US", -250]
    result = xtb.FORMAT.parse(_workbook([row]), RESOLVER)
    assert result.rows == [] and any("11" in e for e in result.errors)


def test_event_ids_are_xtb_ids():
    ids = [r["source_event_id"] for r in xtb.FORMAT.parse(_workbook(ROWS[:2]), RESOLVER).rows]
    assert ids == ["1", "2"]


def test_reimport_yields_identical_rows():
    first = xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER).rows
    second = xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER).rows
    key = lambda r: (r["source_event_stream"], r["source_event_id"])  # noqa: E731
    assert sorted(map(key, first)) == sorted(map(key, second))


def test_missing_account_currency_is_error():
    wb_file = _workbook(ROWS[:1], currency=None)
    assert xtb.FORMAT.parse(wb_file, RESOLVER).errors


def test_upload_routes_xlsx_to_xtb_preview(monkeypatch):
    from routers import portfolio as portfolio_router

    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: RESOLVER)
    upload = _workbook(ROWS[:5])
    parsed = portfolio_router._parse_import_content(upload.content, upload.filename)
    assert parsed.format_name == "XTB (xStation)"
    assert not parsed.mandatory_replace
    assert sorted(r["type"] for r in parsed.rows) == ["buy", "deposit", "dividend", "sell"]
