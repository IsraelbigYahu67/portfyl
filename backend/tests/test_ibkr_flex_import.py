from datetime import datetime, timezone
from pathlib import Path

import pytest

from importers.base import ImportFile, validate_rows
from importers.formats import ibkr_flex
from importers.instruments import DefaultInstrumentResolver
from routers import portfolio as portfolio_router

FIXTURE = Path(__file__).parent / "fixtures" / "brokers" / "ibkr" / "flex_2025_sample.xml"


def _parse(xml):
    return ibkr_flex.parse_flex_statement(xml, DefaultInstrumentResolver(figi=None))


@pytest.fixture
def parsed():
    return _parse(FIXTURE.read_text())


def _by(rows, **match):
    return [r for r in rows if all(r.get(k) == v for k, v in match.items())]


def _with_section(section_xml):
    return FIXTURE.read_text().replace("</FlexStatement>", f"{section_xml}</FlexStatement>")


def test_detects_flex_xml_only():
    assert ibkr_flex.FORMAT.detect(ImportFile("x.xml", FIXTURE.read_bytes()))
    assert not ibkr_flex.FORMAT.detect(ImportFile("x.csv", b"date,ticker\n"))


def test_rows_pass_shared_validation(parsed):
    assert parsed.errors == []
    assert validate_rows(parsed.rows) == []


def test_stock_buy_execution_only(parsed):
    [buy] = _by(parsed.rows, type="buy", ticker="AAPL")
    assert buy["shares"] == 10 and buy["price"] == 190.5
    assert buy["cash_amount"] == 1906 and buy["cash_currency"] == "USD"
    assert buy["fx_to_czk"] == 23.10
    assert buy["source"] == "ibkr" and buy["source_event_stream"] == "trades"
    assert buy["source_event_id"] == "9001"
    assert buy["source_instrument_id"] == "US0378331005"
    assert buy["executed_at"] == datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)


def test_xetra_sell_maps_to_de_ticker(parsed):
    [sell] = _by(parsed.rows, type="sell")
    assert sell["ticker"] == "VWCE.DE" and sell["shares"] == 2
    assert sell["cash_amount"] == 238.75


def test_ibkr_forex_trade_becomes_fx_legs(parsed):
    [fx_in] = _by(parsed.rows, type="fx_in")
    [fx_out] = _by(parsed.rows, type="fx_out")
    assert (fx_in["currency"], fx_in["amount"]) == ("EUR", 1000)
    assert (fx_out["currency"], fx_out["amount"]) == ("USD", pytest.approx(1080))
    assert _by(parsed.rows, type="fee", source_event_id="9003:commission")
    assert fx_in["fx_to_czk"] is None and fx_out["fx_to_czk"] is None


def test_ibkr_unsupported_asset_counted(parsed):
    assert parsed.skipped_reasons["options (synced to Options)"] == 1
    assert parsed.skipped_reasons["unsupported asset: BOND"] == 1


def test_ibkr_dividend_with_withholding(parsed):
    [div] = _by(parsed.rows, type="dividend")
    assert div["cash_amount"] == pytest.approx(2.125)
    assert div["shares"] == pytest.approx(10.0)  # 2.5 gross / 0.25 per share
    assert div["source_event_id"] == "div:A1"
    assert div["fx_to_czk"] == 23.20


def test_cash_rows(parsed):
    [deposit] = _by(parsed.rows, type="deposit")
    assert deposit["amount"] == 50000 and deposit["fx_to_czk"] == 1.0
    assert _by(parsed.rows, type="interest")[0]["amount"] == 1.2
    assert _by(parsed.rows, type="fee", source_event_id="8005")[0]["amount"] == 10


def test_forward_split(parsed):
    [split] = _by(parsed.rows, type="split_open")
    assert split["ticker"] == "NVDA" and split["shares"] == 90


def test_reverse_split_rows():
    xml = FIXTURE.read_text().replace(
        '<CorporateAction type="FS" assetCategory="STK" symbol="NVDA" conid="4815747" isin="US67066G1040" '
        'listingExchange="NASDAQ" currency="USD" dateTime="20250610;202500" quantity="90"',
        '<CorporateAction type="RS" assetCategory="STK" symbol="NVDA" conid="4815747" isin="US67066G1040" '
        'listingExchange="NASDAQ" currency="USD" dateTime="20250610;202500" quantity="-100"',
    ).replace(
        "</CorporateActions>",
        '<CorporateAction type="RS" assetCategory="STK" symbol="NVDA" conid="4815747" isin="US67066G1040" '
        'listingExchange="NASDAQ" currency="USD" dateTime="20250610;202500" quantity="10" '
        'transactionID="7002" levelOfDetail="DETAIL"/></CorporateActions>',
    )
    result = _parse(xml)
    assert result.errors == []
    assert [r["shares"] for r in _by(result.rows, type="split_close")] == [100]
    assert [r["shares"] for r in _by(result.rows, type="split_open")] == [10]


def test_option_corporate_action_is_counted_not_an_error():
    xml = FIXTURE.read_text().replace('type="FS" assetCategory="STK"', 'type="SO" assetCategory="OPT"')
    result = _parse(xml)
    assert result.errors == []
    assert result.skipped_reasons["options (synced to Options)"] == 2


def test_ibkr_overlapping_statements_are_idempotent(parsed):
    again = _parse(FIXTURE.read_text())
    key = lambda r: (r["source_event_stream"], r["source_event_id"])  # noqa: E731
    assert sorted(map(key, parsed.rows)) == sorted(map(key, again.rows))
    assert len(set(map(key, parsed.rows))) == len(parsed.rows)


def test_unknown_cash_type_is_error():
    result = _parse(FIXTURE.read_text().replace('type="Other Fees"', 'type="Mystery"'))
    assert any("Mystery" in e for e in result.errors)


def test_positive_fee_is_error():
    result = _parse(FIXTURE.read_text().replace('amount="-10" description="MARKET DATA"',
                                                'amount="10" description="MARKET DATA"'))
    assert any("Other Fees" in e for e in result.errors)


def test_withholding_tax_on_interest_is_a_fee():
    result = _parse(_with_section(
        '<CashTransactions><CashTransaction type="Withholding Tax" currency="USD" dateTime="20250605" '
        'amount="-0.18" description="WITHHOLDING @ 15% ON CREDIT INT" transactionID="8100" '
        'levelOfDetail="DETAIL"/></CashTransactions>'
    ))
    assert result.errors == []
    [fee] = _by(result.rows, source_event_id="8100")
    assert fee["type"] == "fee" and fee["amount"] == pytest.approx(0.18)


def test_unsupported_corporate_action_is_error():
    result = _parse(FIXTURE.read_text().replace('type="FS"', 'type="SO"'))
    assert any("SO" in e for e in result.errors)


def test_unresolved_venue_is_error_not_isin_ticker():
    result = _parse(FIXTURE.read_text().replace('listingExchange="IBIS2"', 'listingExchange="MOON"'))
    assert any("IE00BK5BQT80" in e for e in result.errors)
    assert not any(r.get("ticker") in ("IE00BK5BQT80", "VWCE") for r in result.rows)


def test_stock_transfer_in_books_cost_basis():
    result = _parse(_with_section(
        '<Transfers><Transfer type="ACATS" direction="IN" assetCategory="STK" symbol="MSFT" '
        'description="MICROSOFT CORP" isin="US5949181045" listingExchange="NASDAQ" currency="USD" '
        'dateTime="20250201" quantity="5" transferPrice="400" transactionID="6001"/></Transfers>'
    ))
    assert result.errors == []
    [deposit] = _by(result.rows, source_event_id="6001:cash")
    [buy] = _by(result.rows, source_event_id="6001:position")
    assert deposit["type"] == "deposit" and deposit["amount"] == 2000
    assert buy["type"] == "buy" and buy["ticker"] == "MSFT" and buy["price"] == 400


def test_transfer_without_cost_basis_is_error():
    result = _parse(_with_section(
        '<Transfers><Transfer type="ACATS" direction="IN" assetCategory="STK" symbol="MSFT" '
        'listingExchange="NASDAQ" currency="USD" dateTime="20250201" quantity="5" transferPrice="0" '
        'transactionID="6001"/></Transfers>'
    ))
    assert any("cost basis" in e for e in result.errors)


def test_doctype_is_rejected():
    xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><FlexQueryResponse/>'
    result = _parse(xml)
    assert result.errors and result.rows == []


def test_non_czk_base_leaves_fx_empty():
    result = _parse(FIXTURE.read_text().replace('currency="CZK"/>', 'currency="EUR"/>', 1))
    assert all(r.get("fx_to_czk") is None for r in result.rows)


@pytest.mark.parametrize("raw, expected", [
    ("20250102;093015", datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)),
    ("2025-01-02;09:30:15", datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)),
    ("2025-01-02, 09:30:15", datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)),
    ("20250102 093015", datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)),
    ("20250702;093015", datetime(2025, 7, 2, 13, 30, 15, tzinfo=timezone.utc)),
    ("20250102", None),
])
def test_flex_timestamps_are_new_york_time(raw, expected):
    day, executed_at = ibkr_flex._when(raw)
    assert day.isoformat()[:4] == "2025"
    assert executed_at == expected


def test_has_ledger_sections():
    assert ibkr_flex.has_ledger_sections(FIXTURE.read_text())
    assert not ibkr_flex.has_ledger_sections("<FlexQueryResponse><FlexStatements/></FlexQueryResponse>")


def test_flex_xml_routes_through_import_preview(monkeypatch):
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver",
                        lambda: DefaultInstrumentResolver(figi=None))
    parsed = portfolio_router._parse_import_content(FIXTURE.read_bytes(), "statement.xml")
    assert parsed.format_name == "Interactive Brokers (Flex XML)"
    assert parsed.mandatory_replace is False
    assert parsed.skipped_reasons == {"options (synced to Options)": 1, "unsupported asset: BOND": 1}
