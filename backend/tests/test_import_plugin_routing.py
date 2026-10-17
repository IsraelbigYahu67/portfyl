from datetime import date

import pytest
from fastapi import HTTPException

import importers.registry as registry
from importers.base import ImportFile, ImportFormat, ParseResult, validate_rows
from importers.openfigi import OpenFigiUnavailable
from routers import portfolio as portfolio_router


def _row(**overrides):
    row = {
        "date": date(2025, 1, 2), "type": "buy", "ticker": "AAPL", "name": "Apple",
        "shares": 1.0, "price": 190.0, "currency": "USD", "source": "testbroker",
        "source_event_stream": "trades", "source_event_id": "T1",
    }
    row.update(overrides)
    return row


def test_validate_rows_accepts_a_clean_row():
    assert validate_rows([_row()]) == []


def test_validate_rows_rejects_unknown_keys_and_types():
    errors = validate_rows([_row(foo=1), _row(type="bonus")])
    assert any("foo" in e for e in errors)
    assert any("bonus" in e for e in errors)


def test_validate_rows_requires_event_identity():
    assert validate_rows([_row(source_event_id=None)])


def test_validate_rows_cash_row_needs_positive_amount():
    cash = _row(type="deposit", ticker=None, shares=0.0, price=0.0, amount=0.0)
    assert validate_rows([cash])


def test_registry_discovers_no_duplicate_keys():
    keys = [fmt.key for fmt in registry.FORMATS]
    assert len(keys) == len(set(keys))


def test_ambiguous_detection_raises(monkeypatch):
    fmt = ImportFormat("a", "A", lambda f: True, lambda f, r: None)
    other = ImportFormat("b", "B", lambda f: True, lambda f, r: None)
    monkeypatch.setattr(registry, "FORMATS", (fmt, other))
    with pytest.raises(registry.AmbiguousFormat):
        registry.detect_format(ImportFile("x.csv", b"x"))


def test_broken_detector_does_not_block_other_formats(monkeypatch):
    def boom(_file):
        raise RuntimeError("detector bug")
    broken = ImportFormat("broken", "Broken", boom, lambda f, r: None)
    good = ImportFormat("good", "Good", lambda f: True, lambda f, r: None)
    monkeypatch.setattr(registry, "FORMATS", (broken, good))
    assert registry.detect_format(ImportFile("x.csv", b"x")) is good


def test_plugin_branch_runs_before_native(monkeypatch):
    fmt = ImportFormat(
        "testbroker", "Test Broker",
        lambda f: f.filename.endswith(".test"),
        lambda f, r: ParseResult("Test Broker", [_row()], source_events=3,
                                 skipped_reasons={"options": 2}, errors=[]),
    )
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    parsed = portfolio_router._parse_import_content(b"anything", "export.test")
    assert parsed.format_name == "Test Broker"
    assert parsed.mandatory_replace is False
    assert parsed.skipped == 2 and parsed.skipped_reasons == {"options": 2}
    assert parsed.rows[0]["source"] == "testbroker"


def test_plugin_errors_become_400(monkeypatch):
    fmt = ImportFormat(
        "testbroker", "Test Broker", lambda f: True,
        lambda f, r: ParseResult("Test Broker", [], 1, {}, ["Row 2: boom"]),
    )
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    with pytest.raises(HTTPException) as exc:
        portfolio_router._parse_import_content(b"x", "x.csv")
    assert exc.value.status_code == 400
    assert exc.value.detail["errors"] == ["Row 2: boom"]


def test_plugin_with_no_rows_is_400(monkeypatch):
    fmt = ImportFormat(
        "testbroker", "Test Broker", lambda f: True,
        lambda f, r: ParseResult("Test Broker", [], 1, {"options": 1}, []),
    )
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    with pytest.raises(HTTPException) as exc:
        portfolio_router._parse_import_content(b"x", "x.csv")
    assert exc.value.status_code == 400


def test_ambiguous_upload_is_400(monkeypatch):
    fmt = ImportFormat("a", "A", lambda f: True, lambda f, r: None)
    other = ImportFormat("b", "B", lambda f: True, lambda f, r: None)
    monkeypatch.setattr(registry, "FORMATS", (fmt, other))
    with pytest.raises(HTTPException) as exc:
        portfolio_router._parse_import_content(b"x", "x.csv")
    assert exc.value.status_code == 400


def test_openfigi_outage_becomes_503(monkeypatch):
    def parse(_file, _resolver):
        raise OpenFigiUnavailable("Instrument lookup is rate-limited; try the import again in a minute")
    fmt = ImportFormat("testbroker", "Test Broker", lambda f: True, parse)
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    with pytest.raises(HTTPException) as exc:
        portfolio_router._parse_import_content(b"x", "x.csv")
    assert exc.value.status_code == 503
    assert "rate-limited" in exc.value.detail


def test_native_csv_still_parses_without_plugins(monkeypatch):
    monkeypatch.setattr(registry, "FORMATS", ())
    content = b"date,ticker,type,shares,price\n2025-01-02,AAPL,buy,1,190\n"
    parsed = portfolio_router._parse_import_content(content, "native.csv")
    assert parsed.format_name == "Native"
    assert parsed.skipped_reasons == {}
