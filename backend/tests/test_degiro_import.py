from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import importers.registry as registry
from importers.base import ImportFile, validate_rows
from importers.formats import degiro_account, degiro_transactions
from importers.formats._degiro_common import classify_description

FIX = Path(__file__).parent / "fixtures" / "brokers" / "degiro"


class FakeResolver:
    def __init__(self, mapping):
        self.mapping = mapping

    def resolve_many(self, refs):
        return {ref: self.mapping[ref.isin] for ref in refs if ref.isin in self.mapping}


RESOLVER = FakeResolver({"US0378331005": "AAPL", "IE00BK5BQT80": "VWCE.DE"})


def _file(name):
    return ImportFile(name, (FIX / name).read_bytes())


def _text_file(text):
    return ImportFile("a.csv", text.encode())


def test_detection_is_exclusive():
    assert degiro_transactions.FORMAT.detect(_file("transactions_en.csv"))
    assert degiro_transactions.FORMAT.detect(_file("transactions_cz.csv"))
    assert not degiro_account.FORMAT.detect(_file("transactions_en.csv"))
    assert degiro_account.FORMAT.detect(_file("account_en.csv"))
    assert not degiro_transactions.FORMAT.detect(_file("account_en.csv"))


def test_registry_picks_exactly_one_format():
    assert registry.detect_format(_file("transactions_en.csv")) is degiro_transactions.FORMAT
    assert registry.detect_format(_file("account_en.csv")) is degiro_account.FORMAT
    native = ImportFile("n.csv", b"date,ticker,type,shares,price\n2025-01-02,AAPL,buy,1,190\n")
    assert registry.detect_format(native) is None


def test_transactions_en():
    result = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    buy, sell = result.rows
    assert (buy["type"], buy["ticker"], buy["shares"], buy["price"], buy["currency"]) == ("buy", "AAPL", 10, 190.5, "USD")
    assert (buy["cash_amount"], buy["cash_currency"]) == (1835.70, "EUR")
    assert buy["date"] == date(2025, 1, 2)
    assert buy["executed_at"] == datetime(2025, 1, 2, 14, 31, tzinfo=timezone.utc)
    assert buy["source_event_id"] == "0f1e2d3c-1111-2222-3333-444455556666:1"
    assert (sell["type"], sell["ticker"], sell["cash_amount"]) == ("sell", "VWCE.DE", 239.0)


def test_partial_fills_of_one_order_get_distinct_ids():
    text = (FIX / "transactions_en.csv").read_text()
    first_fill = text.splitlines()[1]
    result = degiro_transactions.FORMAT.parse(_text_file(text + first_fill + "\n"), RESOLVER)
    ids = [r["source_event_id"] for r in result.rows]
    assert ids.count("0f1e2d3c-1111-2222-3333-444455556666:1") == 1
    assert "0f1e2d3c-1111-2222-3333-444455556666:2" in ids


def test_older_export_without_autofx_column():
    lines = (FIX / "transactions_en.csv").read_text().splitlines()

    def drop_autofx(line):
        cells = line.split(",")
        return ",".join(cells[:14] + cells[15:])
    result = degiro_transactions.FORMAT.parse(_text_file("\n".join(map(drop_autofx, lines))), RESOLVER)
    assert result.errors == []
    assert [r["cash_amount"] for r in result.rows] == [1835.70, 239.0]


def test_degiro_czech_locale_file():
    en = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows[0]
    cz = degiro_transactions.FORMAT.parse(_file("transactions_cz.csv"), RESOLVER).rows[0]
    for key in ("shares", "price", "cash_amount", "source_event_id"):
        assert en[key] == cz[key]


def test_degiro_reimport_same_rows_no_duplicates():
    a = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows
    b = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows
    assert [r["source_event_id"] for r in a] == [r["source_event_id"] for r in b]
    assert len({r["source_event_id"] for r in a}) == len(a)


def test_degiro_unresolved_isin_blocks_preview():
    result = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), FakeResolver({}))
    assert any("US0378331005" in e for e in result.errors)
    assert all(r.get("ticker") for r in result.rows)


def test_account_statement():
    result = degiro_account.FORMAT.parse(_file("account_en.csv"), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    assert sorted(r["type"] for r in result.rows) == ["deposit", "dividend", "fee", "fx_in", "fx_out"]
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(2.12) and div["ticker"] == "AAPL"
    assert div["date"] == date(2025, 5, 14)
    assert result.skipped_reasons == {"trade settlement (imported from Transactions.csv)": 1}


def test_account_ids_are_stable_across_overlapping_exports():
    full = degiro_account.FORMAT.parse(_file("account_en.csv"), RESOLVER).rows
    lines = (FIX / "account_en.csv").read_text().splitlines()
    shorter = degiro_account.FORMAT.parse(_text_file("\n".join(lines[:2])), RESOLVER).rows
    [deposit] = shorter
    assert deposit["source_event_id"] in {r["source_event_id"] for r in full}


def test_tax_keyword_wins_over_dividend():
    assert classify_description("Dividend Tax") == "tax"
    assert classify_description("Dividendová daň") == "tax"
    assert classify_description("Dividend") == "gross"
    assert classify_description("Valuta Creditering") == "fx_in"
    assert classify_description("DEGIRO Exchange Connectivity Fee 2025") == "fee"


def test_unknown_account_description_is_error():
    text = (FIX / "account_en.csv").read_text().replace("flatex Deposit", "Something New")
    result = degiro_account.FORMAT.parse(_text_file(text), RESOLVER)
    assert any("Something New" in e for e in result.errors)


def test_unpaired_fx_is_error():
    lines = [line for line in (FIX / "account_en.csv").read_text().splitlines()
             if "Valuta Creditering" not in line]
    result = degiro_account.FORMAT.parse(_text_file("\n".join(lines)), RESOLVER)
    assert any("unpaired currency conversion" in e for e in result.errors)


def test_sign_contradiction_is_error():
    text = (FIX / "account_en.csv").read_text().replace(
        "flatex Deposit,,EUR,2000.00", "flatex Deposit,,EUR,-2000.00")
    result = degiro_account.FORMAT.parse(_text_file(text), RESOLVER)
    assert any("sign contradicts" in e for e in result.errors)


def test_dividend_tax_without_dividend_is_error():
    lines = [line for line in (FIX / "account_en.csv").read_text().splitlines()
             if ",Dividend," not in line]
    result = degiro_account.FORMAT.parse(_text_file("\n".join(lines)), RESOLVER)
    assert any("AAPL" in e for e in result.errors)
