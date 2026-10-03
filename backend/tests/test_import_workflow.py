from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from import_undo import (
    _as_v1_snapshot,
    _encode,
    capture_portfolio_state,
    save_undo_snapshot,
    snapshot_fingerprint,
    undo_status,
    undo_setting_key,
)
from decimal import Decimal
from types import SimpleNamespace

from models import (AuditLog, BrokerCorporateAction, BrokerCorporateActionApplication, TradeNote,
                    Transaction, WorkspaceSetting)
from t212_corporate_actions import SplitEvidence, apply_splits
from portfolio_activation import PENDING_PORTFOLIO_SETTING_KEY, set_pending_portfolio
from routers.portfolio import (
    commit_import_csv,
    get_import_undo_status,
    preview_import_csv,
    undo_import_csv,
)
from tests.helpers import T212_COVERAGE_FIELDS, make_t212_connection_with_coverage, make_txn


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


def test_provider_identity_precedes_matching_business_fields():
    first = row(
        source="t212_csv",
        source_event_stream="csv_export",
        source_event_id="fill-1",
        executed_at=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
    )
    second = {
        **first,
        "source_event_id": "fill-2",
    }

    assert canonical_transaction(first) != canonical_transaction(second)


def test_full_timestamp_distinguishes_rows_without_provider_identity():
    first = row(executed_at=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc))
    second = row(executed_at=datetime(2026, 1, 2, 10, 31, tzinfo=timezone.utc))

    assert canonical_transaction(first) != canonical_transaction(second)


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
    assert build_preview(**{**kwargs, "incoming_rows": [row(ticker="MSFT", name="Renamed") ]})["preview_id"] != baseline
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


def _preview(
    csv: str,
    *,
    db_session,
    default_portfolio,
    request_context,
    replace: bool = False,
):
    return asyncio.run(preview_import_csv(
        file=_upload(csv),
        replace=replace,
        db=db_session,
        portfolio=default_portfolio,
        _context=request_context,
    ))


def _commit(
    csv: str,
    preview_id: str,
    *,
    db_session,
    default_portfolio,
    request_context,
    replace: bool = False,
):
    return asyncio.run(commit_import_csv(
        file=_upload(csv),
        preview_id=preview_id,
        replace=replace,
        db=db_session,
        portfolio=default_portfolio,
        context=request_context,
    ))


def test_commit_requires_matching_preview_and_current_state(
    db_session,
    default_portfolio,
    request_context,
):
    csv = "date,ticker,type,shares,price,currency\n2026-01-03,MSFT,buy,1,400,USD\n"
    preview = _preview(
        csv,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )

    changed_csv = "date,ticker,type,shares,price,currency\n2026-01-03,NVDA,buy,1,400,USD\n"
    with pytest.raises(HTTPException) as changed_file:
        _commit(
            changed_csv,
            preview["preview_id"],
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )
    assert changed_file.value.status_code == 409
    assert "preview" in str(changed_file.value.detail).lower()

    db_session.add(make_txn("AAPL", portfolio_id=default_portfolio.id))
    db_session.commit()
    with pytest.raises(HTTPException) as changed_state:
        _commit(
            csv,
            preview["preview_id"],
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )
    assert changed_state.value.status_code == 409
    assert db_session.query(Transaction).count() == 1


def test_append_commit_skips_duplicates_and_creates_undo_point(
    db_session,
    default_portfolio,
    request_context,
):
    db_session.add(make_txn(
        "AAPL", "buy", 2, 150,
        date=date(2026, 1, 2),
        portfolio_id=default_portfolio.id,
    ))
    db_session.commit()
    csv = """date,ticker,type,shares,price,currency
2026-01-02,AAPL,buy,2,150,USD
2026-01-03,MSFT,buy,1,400,USD
2026-01-03,MSFT,buy,1,400,USD
"""
    preview = _preview(
        csv,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )

    with patch("routers.portfolio.bulk_fetch_fx", return_value={
        ("USD", date(2026, 1, 3)): 23.0,
    }):
        result = _commit(
            csv,
            preview["preview_id"],
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )

    assert result["imported"] == 1
    assert result["duplicates_skipped"] == 2
    assert result["projected"] == 2
    assert [item.ticker for item in db_session.query(Transaction).order_by(Transaction.date)] == [
        "AAPL", "MSFT",
    ]
    status = get_import_undo_status(db=db_session, portfolio=default_portfolio)
    assert status["available"] is True
    assert status["mode"] == "append"
    assert status["imported"] == 1


def test_successful_pending_import_activates_in_the_commit_transaction(
    db_session,
    default_portfolio,
    request_context,
):
    set_pending_portfolio(db_session, default_portfolio)
    db_session.commit()
    csv = "date,ticker,type,shares,price,currency\n2026-01-03,MSFT,buy,1,400,USD\n"
    preview = _preview(
        csv,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )

    with patch("routers.portfolio.bulk_fetch_fx", return_value={("USD", date(2026, 1, 3)): 23.0}):
        _commit(
            csv,
            preview["preview_id"],
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )

    assert db_session.query(WorkspaceSetting).filter_by(key=PENDING_PORTFOLIO_SETTING_KEY).first() is None
    audit = db_session.query(AuditLog).filter_by(action="onboarding.portfolio.activated").one()
    assert audit.event_metadata == {"kind": "csv_import"}


def test_failed_pending_import_keeps_activation_marker(
    db_session,
    default_portfolio,
    request_context,
):
    set_pending_portfolio(db_session, default_portfolio)
    db_session.commit()
    csv = "date,ticker,type,shares,price,currency\n2026-01-03,MSFT,buy,1,400,USD\n"

    with pytest.raises(HTTPException) as exc_info:
        _commit(
            csv,
            "stale-preview",
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )

    assert exc_info.value.status_code == 409
    assert db_session.query(WorkspaceSetting).filter_by(key=PENDING_PORTFOLIO_SETTING_KEY).one()


def test_replace_undo_restores_public_ids_and_trade_notes(
    db_session,
    default_portfolio,
    request_context,
):
    original = make_txn(
        "AAPL", "buy", 2, 150,
        date=date(2026, 1, 2),
        source="t212_api",
        portfolio_id=default_portfolio.id,
    )
    original.source_event_id = "fill-123"
    original.source_event_stream = "orders"
    original.source_account_fingerprint = "f" * 64
    original.source_credential_generation = 3
    original.source_instrument_id = "AAPL_US_EQ"
    original.source_fill_type = "TRADE"
    original.executed_at = datetime(2026, 1, 2, 14, 30, 45)
    original.source_payload_hash = "a" * 64
    original.source_mapper_version = "t212_finalize_v1"
    db_session.add(original)
    db_session.flush()
    db_session.add(TradeNote(
        workspace_id=default_portfolio.workspace_id,
        transaction_id=original.id,
        content="Keep this thesis",
        tags="quality",
        sentiment="bullish",
    ))
    db_session.commit()
    original_public_id = original.public_id
    csv = "date,ticker,type,shares,price,currency\n2026-02-01,MSFT,buy,1,400,USD\n"
    preview = _preview(
        csv,
        replace=True,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )
    with patch("routers.portfolio.bulk_fetch_fx", return_value={
        ("USD", date(2026, 2, 1)): 23.0,
    }):
        _commit(
            csv,
            preview["preview_id"],
            replace=True,
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )
    assert [item.ticker for item in db_session.query(Transaction).all()] == ["MSFT"]

    result = undo_import_csv(
        db=db_session,
        portfolio=default_portfolio,
        context=request_context,
    )

    restored = db_session.query(Transaction).one()
    note = db_session.query(TradeNote).one()
    assert result["restored"] == 1
    assert restored.ticker == "AAPL"
    assert restored.public_id == original_public_id
    assert restored.source_event_id == "fill-123"
    assert restored.source_event_stream == "orders"
    assert restored.source_account_fingerprint == "f" * 64
    assert restored.source_credential_generation == 3
    assert restored.source_instrument_id == "AAPL_US_EQ"
    assert restored.source_fill_type == "TRADE"
    assert restored.executed_at == datetime(2026, 1, 2, 14, 30, 45)
    assert restored.source_payload_hash == "a" * 64
    assert restored.source_mapper_version == "t212_finalize_v1"
    assert note.transaction_id == restored.id
    assert note.content == "Keep this thesis"
    assert get_import_undo_status(db=db_session, portfolio=default_portfolio)["available"] is False


def test_undo_refuses_to_overwrite_post_import_manual_change(
    db_session,
    default_portfolio,
    request_context,
):
    csv = "date,ticker,type,shares,price,currency\n2026-02-01,MSFT,buy,1,400,USD\n"
    preview = _preview(
        csv,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )
    with patch("routers.portfolio.bulk_fetch_fx", return_value={
        ("USD", date(2026, 2, 1)): 23.0,
    }):
        _commit(
            csv,
            preview["preview_id"],
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )
    db_session.add(make_txn("NVDA", portfolio_id=default_portfolio.id))
    db_session.commit()

    status = get_import_undo_status(db=db_session, portfolio=default_portfolio)
    assert status["available"] is False
    assert status["reason"] == "portfolio_changed"
    with pytest.raises(HTTPException) as exc_info:
        undo_import_csv(
            db=db_session,
            portfolio=default_portfolio,
            context=request_context,
        )
    assert exc_info.value.status_code == 409
    assert {item.ticker for item in db_session.query(Transaction)} == {"MSFT", "NVDA"}


def test_undo_snapshot_expires_after_twenty_four_hours(
    db_session,
    default_portfolio,
):
    state = capture_portfolio_state(db_session, default_portfolio)
    created_at = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    save_undo_snapshot(
        db_session,
        default_portfolio,
        before=state,
        after=state,
        mode="append",
        imported=1,
        format_name="Native",
        now=created_at,
    )

    assert undo_status(
        db_session,
        default_portfolio,
        now=created_at + timedelta(hours=23, minutes=59),
    )["available"] is True
    expired = undo_status(
        db_session,
        default_portfolio,
        now=created_at + timedelta(hours=24),
    )
    assert expired["available"] is False
    assert expired["reason"] == "expired"


def test_active_v1_undo_snapshot_remains_compatible(db_session, default_portfolio):
    db_session.add(make_txn("AAPL", portfolio_id=default_portfolio.id))
    db_session.commit()
    current = _as_v1_snapshot(capture_portfolio_state(db_session, default_portfolio))
    created_at = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1,
        "portfolio_id": str(default_portfolio.public_id),
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(hours=24)).isoformat(),
        "mode": "append",
        "format": "Native",
        "imported": 1,
        "before": current,
        "after_fingerprint": snapshot_fingerprint(current),
    }
    db_session.add(WorkspaceSetting(
        workspace_id=default_portfolio.workspace_id,
        key=undo_setting_key(default_portfolio),
        value=_encode(payload),
    ))
    db_session.commit()

    assert undo_status(db_session, default_portfolio)["available"] is True


def test_mutating_import_routes_use_csrf_dependency_and_legacy_route_is_absent():
    from routers.portfolio import router
    from tenancy import require_csrf

    routes = {
        (method, route.path): route
        for route in router.routes
        for method in route.methods
    }
    assert ("POST", "/portfolio/import-csv") not in routes
    for key in (
        ("POST", "/portfolio/import-csv/commit"),
        ("POST", "/portfolio/import-csv/undo"),
    ):
        calls = {dependency.call for dependency in routes[key].dependant.dependencies}
        assert require_csrf in calls


def _import_csv_via_preview(csv, *, replace, db_session, default_portfolio, request_context):
    preview = _preview(
        csv,
        replace=replace,
        db_session=db_session,
        default_portfolio=default_portfolio,
        request_context=request_context,
    )
    with patch("routers.portfolio.bulk_fetch_fx", return_value={
        ("USD", date(2026, 2, 1)): 23.0,
    }):
        return _commit(
            csv,
            preview["preview_id"],
            replace=replace,
            db_session=db_session,
            default_portfolio=default_portfolio,
            request_context=request_context,
        )


def test_replace_import_clears_t212_history_coverage(
    db_session, default_portfolio, request_context
):
    db_session.add(make_txn(
        "AAPL", "buy", 2, 150, date=date(2026, 1, 2),
        source="t212_api", portfolio_id=default_portfolio.id,
    ))
    connection = make_t212_connection_with_coverage(db_session, default_portfolio)
    csv = "date,ticker,type,shares,price,currency\n2026-02-01,MSFT,buy,1,400,USD\n"

    _import_csv_via_preview(
        csv, replace=True, db_session=db_session,
        default_portfolio=default_portfolio, request_context=request_context,
    )

    db_session.refresh(connection)
    assert [getattr(connection, field) for field in T212_COVERAGE_FIELDS] == [None] * len(T212_COVERAGE_FIELDS)


def test_append_import_keeps_t212_history_coverage(
    db_session, default_portfolio, request_context
):
    db_session.add(make_txn(
        "AAPL", "buy", 2, 150, date=date(2026, 1, 2),
        source="t212_api", portfolio_id=default_portfolio.id,
    ))
    connection = make_t212_connection_with_coverage(db_session, default_portfolio)
    csv = "date,ticker,type,shares,price,currency\n2026-02-01,MSFT,buy,1,400,USD\n"

    _import_csv_via_preview(
        csv, replace=False, db_session=db_session,
        default_portfolio=default_portfolio, request_context=request_context,
    )

    db_session.refresh(connection)
    assert all(getattr(connection, field) is not None for field in T212_COVERAGE_FIELDS)


def _seed_adjusted_split(db, portfolio):
    """One T212 API buy stored post-split (90 @ 120), the api_normalized action
    that adjusted it (10:1, 2024-06-10) and its application marker."""
    buy = make_txn("NVDA", "buy", 90, 120, date=date(2024, 5, 1), source="t212_api",
                   portfolio_id=portfolio.id)
    buy.source_event_id = "fill:t1"
    buy.source_event_stream = "orders"
    db.add(buy)
    db.flush()
    action = BrokerCorporateAction(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id, broker="trading212",
        account_fingerprint="f" * 64, provider_instrument_id="NVDA_US_EQ", ticker="NVDA",
        action_type="STOCK_SPLIT", effective_at=datetime(2024, 6, 10, 10, tzinfo=timezone.utc),
        provider_event_key="fill:a|fill:b", ratio_numerator=10, ratio_denominator=1,
        representation="api_normalized", run_id=7,
    )
    db.add(action)
    db.flush()
    db.add(BrokerCorporateActionApplication(
        workspace_id=portfolio.workspace_id, action_id=action.id, transaction_id=buy.id,
        shares_before=9, price_before=1200, shares_after=90, price_after=120, applied_by_run_id=7,
    ))
    db.commit()
    return buy


def test_undo_restores_adjusted_rows_with_their_application_markers(
    db_session,
    default_portfolio,
    request_context,
):
    _seed_adjusted_split(db_session, default_portfolio)
    csv = "date,ticker,type,shares,price,currency\n2026-02-01,MSFT,buy,1,400,USD\n"
    preview = _preview(
        csv, replace=True, db_session=db_session, default_portfolio=default_portfolio,
        request_context=request_context,
    )
    with patch("routers.portfolio.bulk_fetch_fx", return_value={("USD", date(2026, 2, 1)): 23.0}):
        _commit(
            csv, preview["preview_id"], replace=True, db_session=db_session,
            default_portfolio=default_portfolio, request_context=request_context,
        )
    assert db_session.query(Transaction).filter_by(ticker="NVDA").count() == 0

    undo_import_csv(db=db_session, portfolio=default_portfolio, context=request_context)

    [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
    assert buy.source_event_id == "fill:t1"
    assert (buy.shares, buy.price) == (90, 120)
    [action] = db_session.query(BrokerCorporateAction).all()
    assert (action.representation, float(action.ratio_numerator), float(action.ratio_denominator)) == (
        "api_normalized", 10.0, 1.0)
    assert action.run_id == 7
    [application] = db_session.query(BrokerCorporateActionApplication).all()
    assert application.transaction_id == buy.id
    assert application.action_id == action.id
    assert (application.shares_before, application.shares_after) == (9, 90)

    # The restored marker is what stops a later sync from adjusting the row again.
    evidence = SplitEvidence(
        provider_instrument_id="NVDA_US_EQ",
        effective_at=datetime(2024, 6, 10, 10, tzinfo=timezone.utc),
        provider_event_key="fill:a|fill:b", old_shares=Decimal("9"), new_shares=Decimal("90"),
        event_ids=("fill:a", "fill:b"),
    )
    run = SimpleNamespace(account_fingerprint="f" * 64, id=8)
    summary = apply_splits(db_session, run=run, portfolio=default_portfolio, evidence=[evidence], pending=[])
    assert (summary.actions_created, summary.applications_created) == (0, 0)
    db_session.refresh(buy)
    assert (buy.shares, buy.price) == (90, 120)


def test_undo_point_taken_before_corporate_actions_existed_is_still_usable(
    db_session, default_portfolio, request_context,
):
    """A live v2 undo point predates the action tables: its fingerprint has no
    action keys, so the current state must be compared without them."""
    from import_undo import _as_v2_snapshot

    _seed_adjusted_split(db_session, default_portfolio)
    current = capture_portfolio_state(db_session, default_portfolio)
    assert current["corporate_actions"] and current["corporate_action_applications"]
    projected = _as_v2_snapshot(current)
    assert "corporate_actions" not in projected and "corporate_action_applications" not in projected
    assert projected["transactions"] == current["transactions"]
