from __future__ import annotations

from datetime import date
import asyncio
import io

from fastapi import HTTPException, UploadFile
from unittest.mock import patch
import pytest

from import_workflow import (
    build_preview,
    canonical_transaction,
    deduplicate_rows,
)
from models import Transaction
from routers.portfolio import preview_import_csv
from tests.helpers import make_txn


def row(**overrides):
    values = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "type": "buy",
        "shares": 2.0,
        "price": 150.0,
        "amount": None,
        "currency": "USD",
        "cash_amount": 6900.0,
        "cash_currency": "CZK",
        "date": date(2026, 1, 2),
        "notes": None,
        "source": "csv",
        "fx_to_czk": 23.0,
    }
    values.update(overrides)
    return values


def test_canonical_identity_ignores_display_name_fx_and_generated_ids():
    first = row(name="Apple Inc.", fx_to_czk=23.0, public_id="generated-one")
    second = row(name="APPLE", fx_to_czk=24.5, id=99)

    assert canonical_transaction(first) == canonical_transaction(second)


def test_canonical_identity_normalizes_case_dates_nulls_and_numeric_values():
    first = row(
        ticker=" aapl ",
        type=" BUY ",
        shares=2,
        price=150,
        currency=" usd ",
        cash_currency=" czk ",
        date="2026-01-02",
        notes="",
    )
    second = row(notes=None)

    assert canonical_transaction(first) == canonical_transaction(second)


def test_business_field_change_is_not_a_duplicate():
    baseline = canonical_transaction(row())

    assert canonical_transaction(row(price=151.0)) != baseline
    assert canonical_transaction(row(cash_amount=6800.0)) != baseline
    assert canonical_transaction(row(notes="corrected")) != baseline


def test_origin_metadata_does_not_turn_the_same_business_event_into_a_new_row():
    assert canonical_transaction(row(source="manual")) == canonical_transaction(
        row(source="t212_csv")
    )


def test_deduplicate_rows_keeps_first_occurrence_and_reports_repeat_count():
    unique, repeated = deduplicate_rows([
        row(name="first"),
        row(name="same identity, different display name"),
        row(ticker="MSFT", name="Microsoft"),
    ])

    assert repeated == 1
    assert [item["name"] for item in unique] == ["first", "Microsoft"]


def test_append_preview_skips_existing_exact_duplicates():
    current = [row(name="persisted")]
    incoming = [
        row(name="uploaded"),
        row(ticker="MSFT", name="Microsoft", cash_amount=7000.0),
    ]

    preview = build_preview(
        current_rows=current,
        incoming_rows=incoming,
        requested_replace=False,
        mandatory_replace=False,
        portfolio_public_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        source_events=2,
        skipped=0,
        format_name="Native",
    )

    assert preview["mode"] == "append"
    assert preview["counts"] == {
        "source_events": 2,
        "recognized_rows": 2,
        "unique_rows": 2,
        "duplicates_in_file": 0,
        "duplicates_existing": 1,
        "current": 1,
        "added": 1,
        "removed": 0,
        "unchanged": 1,
        "projected": 2,
        "skipped": 0,
    }
    assert [item["ticker"] for item in preview["rows_to_insert"]] == ["MSFT"]
    assert preview["preview_id"]


def test_replace_preview_reconciles_removed_and_unchanged_rows():
    current = [row(), row(ticker="OLD", name="Old", cash_amount=100.0)]
    incoming = [
        row(name="same business row"),
        row(ticker="NEW", name="New", cash_amount=200.0),
        row(ticker="NEW", name="duplicate", cash_amount=200.0),
    ]

    preview = build_preview(
        current_rows=current,
        incoming_rows=incoming,
        requested_replace=False,
        mandatory_replace=True,
        portfolio_public_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        source_events=3,
        skipped=4,
        format_name="Trading 212",
    )

    assert preview["mode"] == "replace"
    assert preview["mandatory_replace"] is True
    assert preview["counts"] == {
        "source_events": 3,
        "recognized_rows": 3,
        "unique_rows": 2,
        "duplicates_in_file": 1,
        "duplicates_existing": 1,
        "current": 2,
        "added": 1,
        "removed": 1,
        "unchanged": 1,
        "projected": 2,
        "skipped": 4,
    }
    assert len(preview["rows_to_insert"]) == 2


def test_preview_id_changes_with_mode_portfolio_content_or_current_state():
    kwargs = {
        "current_rows": [row()],
        "incoming_rows": [row(ticker="MSFT")],
        "requested_replace": False,
        "mandatory_replace": False,
        "portfolio_public_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "source_events": 1,
        "skipped": 0,
        "format_name": "Native",
    }
    baseline = build_preview(**kwargs)["preview_id"]

    assert build_preview(**{**kwargs, "requested_replace": True})["preview_id"] != baseline
    assert build_preview(**{**kwargs, "portfolio_public_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"})["preview_id"] != baseline
    assert build_preview(**{**kwargs, "incoming_rows": [row(ticker="NVDA")]})["preview_id"] != baseline
    assert build_preview(**{**kwargs, "current_rows": [row(price=151)]})["preview_id"] != baseline


def _upload(text: str, filename: str = "portfolio.csv") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(text.encode("utf-8")))


def test_preview_endpoint_is_read_only_and_returns_bounded_reconciliation(
    db_session,
    default_portfolio,
    request_context,
):
    db_session.add(make_txn(
        "AAPL",
        "buy",
        2,
        150,
        date=date(2026, 1, 2),
        portfolio_id=default_portfolio.id,
        source="manual",
    ))
    db_session.commit()
    csv = """date,ticker,type,shares,price,currency
2026-01-02,AAPL,buy,2,150,USD
2026-01-03,MSFT,buy,1,400,USD
2026-01-03,MSFT,buy,1,400,USD
"""

    with patch("routers.portfolio.bulk_fetch_fx", return_value={
        ("USD", date(2026, 1, 2)): 23.0,
        ("USD", date(2026, 1, 3)): 23.0,
    }):
        result = asyncio.run(preview_import_csv(
            file=_upload(csv),
            replace=False,
            db=db_session,
            portfolio=default_portfolio,
            _context=request_context,
        ))

    assert result["format"] == "Native"
    assert result["mode"] == "append"
    assert result["counts"]["duplicates_in_file"] == 1
    assert result["counts"]["duplicates_existing"] == 1
    assert result["counts"]["added"] == 1
    assert result["counts"]["projected"] == 2
    assert result["sample"] == [
        {
            "date": "2026-01-03",
            "ticker": "MSFT",
            "type": "buy",
            "shares": 1.0,
            "price": 400.0,
            "amount": None,
            "currency": "USD",
            "cash_amount": None,
            "cash_currency": None,
            "notes": None,
        }
    ]
    assert "rows_to_insert" not in result
    stored = db_session.query(Transaction).filter(
        Transaction.portfolio_id == default_portfolio.id
    ).all()
    assert [(item.ticker, item.source) for item in stored] == [("AAPL", "manual")]


def test_preview_rejects_upload_larger_than_five_mib(
    db_session,
    default_portfolio,
    request_context,
):
    upload = UploadFile(
        filename="too-large.csv",
        file=io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(preview_import_csv(
            file=upload,
            replace=False,
            db=db_session,
            portfolio=default_portfolio,
            _context=request_context,
        ))

    assert exc_info.value.status_code == 413
    assert "5 MiB" in str(exc_info.value.detail)
