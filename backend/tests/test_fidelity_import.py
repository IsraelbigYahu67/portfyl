from pathlib import Path

import pytest

import importers.registry as registry
from importers.base import ImportFile, validate_rows
from importers.formats import fidelity
from importers.instruments import DefaultInstrumentResolver

FILE = Path(__file__).parent / "fixtures" / "brokers" / "fidelity" / "activity.csv"
RESOLVER = DefaultInstrumentResolver(figi=None)


def _parse(content=None):
    return fidelity.FORMAT.parse(ImportFile("f.csv", content or FILE.read_bytes()), RESOLVER)


def test_detect():
    assert fidelity.FORMAT.detect(ImportFile("f.csv", FILE.read_bytes()))
    assert not fidelity.FORMAT.detect(ImportFile("f.csv", b"date,ticker,type,shares,price\n"))
    assert registry.detect_format(ImportFile("f.csv", FILE.read_bytes())) is fidelity.FORMAT


def test_buy_and_dividend_net():
    result = _parse()
    assert result.errors == [] and validate_rows(result.rows) == []
    [buy] = [r for r in result.rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["cash_amount"]) == ("AAPL", 10, 1905)
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(2.12)


def test_money_market_sweep_skipped():
    result = _parse()
    assert result.skipped_reasons == {"money market sweep": 1}
    assert [r["amount"] for r in result.rows if r["type"] == "interest"] == [1.1]


def test_disclaimer_ignored():
    assert {r["type"] for r in _parse().rows} == {"buy", "dividend", "interest", "deposit"}


def test_starred_money_market_symbol_is_a_sweep():
    content = FILE.read_text().replace(",SPAXX,", ",SPAXX**,").encode()
    assert _parse(content).skipped_reasons == {"money market sweep": 1}


def test_unknown_action_is_error():
    content = FILE.read_text().replace("YOU BOUGHT", "YOU TELEPORTED").encode()
    assert any("YOU TELEPORTED" in e for e in _parse(content).errors)


def test_occurrence_ids_unique():
    ids = [(r["source_event_stream"], r["source_event_id"]) for r in _parse().rows]
    assert len(ids) == len(set(ids))
