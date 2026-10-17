from datetime import date
from pathlib import Path

import pytest

import importers.registry as registry
from importers.base import ImportFile, validate_rows
from importers.formats import schwab
from importers.instruments import DefaultInstrumentResolver

FILE = Path(__file__).parent / "fixtures" / "brokers" / "schwab" / "transactions.csv"
RESOLVER = DefaultInstrumentResolver(figi=None)


def _parse(content=None):
    return schwab.FORMAT.parse(ImportFile("schwab.csv", content or FILE.read_bytes()), RESOLVER)


def test_detect():
    assert schwab.FORMAT.detect(ImportFile("s.csv", FILE.read_bytes()))
    assert not schwab.FORMAT.detect(ImportFile("s.csv", b"date,ticker,type,shares,price\n"))
    assert registry.detect_format(ImportFile("s.csv", FILE.read_bytes())) is schwab.FORMAT


def test_schwab_as_of_dates_and_parentheses():
    result = _parse()
    assert result.errors == [] and validate_rows(result.rows) == []
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["date"] == date(2025, 2, 14)
    assert div["cash_amount"] == pytest.approx(2.12)


def test_trades_and_class_shares():
    rows = _parse().rows
    [buy] = [r for r in rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["price"], buy["cash_amount"]) == ("AAPL", 10, 190.5, 1905.0)
    [sell] = [r for r in rows if r["type"] == "sell"]
    assert sell["ticker"] == "BRK-B" and sell["cash_amount"] == pytest.approx(959.98)


def test_cash_rows_and_total_line_ignored():
    rows = _parse().rows
    assert {r["type"] for r in rows} == {"buy", "sell", "dividend", "interest", "deposit"}
    assert len(rows) == 5


def test_file_without_banner():
    lines = FILE.read_text().splitlines()[1:]
    assert len(_parse("\n".join(lines).encode()).rows) == 5


def test_reimport_ids_are_stable_and_unique():
    a, b = _parse().rows, _parse().rows
    assert [r["source_event_id"] for r in a] == [r["source_event_id"] for r in b]
    assert len({r["source_event_id"] for r in a}) == len(a)


def test_option_legs_are_counted_not_errors():
    content = FILE.read_text().replace(
        '"Transactions Total"',
        '"04/02/2025","Buy to Open","AAPL 06/20/2025 200.00 C","CALL APPLE","1","$3.00","$0.65","-$300.65"\n'
        '"Transactions Total"',
    ).encode()
    result = _parse(content)
    assert result.errors == []
    assert result.skipped_reasons == {"options (not imported)": 1}


def test_interest_with_negative_amount_is_error():
    content = FILE.read_text().replace('"SCHWAB1 INT","","","","$1.15"', '"SCHWAB1 INT","","","","-$1.15"')
    assert any("does not fit" in e for e in _parse(content.encode()).errors)


def test_unknown_action_is_error():
    content = FILE.read_text().replace('"Bank Interest"', '"Mystery Action"').encode()
    assert any("Mystery Action" in e for e in _parse(content).errors)
