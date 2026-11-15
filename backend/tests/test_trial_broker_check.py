"""The free-trial broker check: a repeat trial ends when its broker account or
its imported history is already known (backend/trials.py::record_broker_marks
and the import / sync call sites)."""
from __future__ import annotations

import io
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select

import trials
from account_identity import account_fingerprint
from edition import Edition
from entitlements import resolve_entitlements
from importers.formats.ibkr_flex import flex_account_ids
from importers.instruments import DefaultInstrumentResolver
from models import (
    AuditLog,
    BrokerConnection,
    Membership,
    Portfolio,
    TrialBrokerMark,
    TrialGrant,
    User,
    Workspace,
)
from plans import PlanTier
from private_loop import run_on_private_loop
from routers import etoro as etoro_router
from routers import ibkr as ibkr_router
from routers import portfolio as portfolio_router
from routers.broker import connect
from routers.portfolio import commit_import_csv, preview_import_csv

T = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ENV = {"PORTFYL_TRIAL_FINGERPRINT_KEY": "test-only-trial-fingerprint-key-0000000001"}
FIXTURES = Path(__file__).parent / "fixtures" / "brokers"
FLEX_XML = (FIXTURES / "ibkr" / "flex_2025_sample.xml").read_text()
SAMPLE_CSV = (Path(__file__).resolve().parents[2] / "sample_portfolio.csv").read_text()
RESOLVER = DefaultInstrumentResolver(figi=None)

_T212_HEADER = (
    "Action,Time,ISIN,Ticker,Name,Notes,ID,No. of shares,Price / share,"
    "Currency (Price / share),Exchange rate,Result,Currency (Result),Total,"
    "Currency (Total),Withholding tax,Currency (Withholding tax),"
    "Currency conversion from amount,Currency (Currency conversion from amount),"
    "Currency conversion to amount,Currency (Currency conversion to amount),"
    "Currency conversion fee,Currency (Currency conversion fee),Merchant name,Merchant category"
)


def _t212_csv(prefix: str = "a") -> str:
    """Six cash rows with ids; the same `prefix` means the same export."""
    rows = [
        f'Deposit,2026-01-{10 + n} 19:21:23,,,,"Bank Transfer",{prefix}-id-{n},,,,,,,{1000 + n}.00,"CZK",,,,,,,,,,'
        for n in range(6)
    ]
    return _T212_HEADER + "\n" + "\n".join(rows) + "\n"


# --- helpers -----------------------------------------------------------------


def _workspace_with_trial(db, *, name="Other", now=T, trial=True):
    workspace = Workspace(id=uuid4(), name=name)
    user = User(id=uuid4(), firebase_uid=f"uid-{uuid4()}", email=f"{uuid4()}@example.com")
    db.add_all([workspace, user])
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="owner", status="active"))
    portfolio = Portfolio(workspace_id=workspace.id, name="P", is_default=True)
    db.add(portfolio)
    db.flush()
    if trial:
        trials.grant_trial(
            db, workspace_id=workspace.id, email=f"{uuid4()}@example.com", now=now, env=ENV
        )
    db.commit()
    return SimpleNamespace(workspace=workspace, user=user, portfolio=portfolio,
                           context=SimpleNamespace(user=user))


@pytest.fixture
def alice(db_session, test_user, test_workspace, test_membership, default_portfolio):
    trials.grant_trial(db_session, workspace_id=test_workspace.id,
                       email="alice@example.com", now=T, env=ENV)
    db_session.commit()
    return SimpleNamespace(workspace=test_workspace, user=test_user, portfolio=default_portfolio,
                           context=SimpleNamespace(user=test_user))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("routers.portfolio.bulk_fetch_fx", lambda keys: {})
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: RESOLVER)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    # check_broker stamps `now`; keep it inside the 10-day trial of the fixtures.
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return T + timedelta(hours=1) if tz else (T + timedelta(hours=1)).replace(tzinfo=None)

    monkeypatch.setattr(trials, "datetime", _Clock)


def _grant(db, workspace_id):
    return db.scalar(select(TrialGrant).where(TrialGrant.workspace_id == workspace_id))


def _import(db, tenant, text, filename="export.csv"):
    def upload():
        return UploadFile(filename=filename, file=io.BytesIO(text.encode("utf-8")))

    preview = preview_import_csv(file=upload(), replace=False, db=db,
                                 portfolio=tenant.portfolio, _context=tenant.context)
    return commit_import_csv(file=upload(), preview_id=preview["preview_id"], replace=False,
                             db=db, portfolio=tenant.portfolio, context=tenant.context)


def _keys(n=5, prefix="a"):
    return [("t212_csv", "csv_export", f"{prefix}-id-{i}") for i in range(n)]


def _marks(db):
    return db.scalars(select(TrialBrokerMark)).all()


def _fp(value="U1111111", broker="ibkr", environment="live"):
    return account_fingerprint(broker=broker, environment=environment, provider_account_id=value)


def _record(db, tenant, **kwargs):
    return trials.record_broker_marks(
        db, workspace_id=tenant.workspace.id, now=T + timedelta(hours=1), env=ENV,
        **{"account_fingerprints": [], "oldest_event_keys": [], **kwargs},
    )


# --- record_broker_marks -----------------------------------------------------


def test_workspace_without_active_trial_records_nothing(db_session):
    free = _workspace_with_trial(db_session, trial=False)
    assert _record(db_session, free, account_fingerprints=[_fp()], oldest_event_keys=_keys()) is None
    assert _marks(db_session) == []


def test_expired_trial_records_nothing(db_session):
    late = _workspace_with_trial(db_session, now=T - timedelta(days=30))
    assert _record(db_session, late, account_fingerprints=[_fp()]) is None
    assert _marks(db_session) == []


def test_known_account_from_another_workspace_ends_the_trial(db_session, alice):
    bob = _workspace_with_trial(db_session)
    assert _record(db_session, alice, account_fingerprints=[_fp()]) is None
    assert _record(db_session, bob, account_fingerprints=[_fp()]) == "broker_account_reused"
    db_session.commit()

    assert _grant(db_session, bob.workspace.id).ended_reason == "broker_account_reused"
    assert _grant(db_session, alice.workspace.id).ended_reason is None
    result = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=bob.workspace.id,
                                  now=T + timedelta(hours=2), env=ENV)
    assert result.plan is PlanTier.FREE
    assert result.payload()["trial_ended_reason"] == "broker_account_reused"
    result_a = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=alice.workspace.id,
                                    now=T + timedelta(hours=2), env=ENV)
    assert result_a.plan is PlanTier.PRO and result_a.source == "trial"


def test_audit_event_carries_the_reason_and_no_account_number(db_session, alice):
    bob = _workspace_with_trial(db_session)
    account = "U7654321"
    _record(db_session, alice, account_fingerprints=[_fp(account)])
    _record(db_session, bob, account_fingerprints=[_fp(account)], actor_user_id=bob.user.id)
    db_session.commit()

    [event] = db_session.scalars(select(AuditLog).where(AuditLog.action == "trial.ended_early")).all()
    assert event.workspace_id == bob.workspace.id
    assert event.actor_user_id == bob.user.id
    assert event.event_metadata == {"reason": "broker_account_reused"}
    assert account not in str(event.event_metadata) and _fp(account) not in str(event.event_metadata)


def test_background_sync_attributes_the_audit_event_to_the_owner(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _record(db_session, alice, account_fingerprints=[_fp()])
    _record(db_session, bob, account_fingerprints=[_fp()])  # no actor: a job
    db_session.commit()
    [event] = db_session.scalars(select(AuditLog).where(AuditLog.action == "trial.ended_early")).all()
    assert event.actor_user_id == bob.user.id


def test_same_workspace_reimporting_its_own_account_ends_nothing(db_session, alice):
    assert _record(db_session, alice, account_fingerprints=[_fp()], oldest_event_keys=_keys()) is None
    assert _record(db_session, alice, account_fingerprints=[_fp()], oldest_event_keys=_keys()) is None
    assert _grant(db_session, alice.workspace.id).ended_reason is None
    assert len(_marks(db_session)) == 1 + 5


def test_mark_of_a_deleted_workspace_still_ends_a_new_trial(db_session, alice):
    _record(db_session, alice, account_fingerprints=[_fp()])
    mark = _marks(db_session)[0]
    mark.workspace_id = None  # what ON DELETE SET NULL leaves behind
    db_session.commit()
    carol = _workspace_with_trial(db_session)
    assert _record(db_session, carol, account_fingerprints=[_fp()]) == "broker_account_reused"


def test_two_of_five_history_matches_end_nothing_three_do(db_session, alice):
    bob = _workspace_with_trial(db_session)
    dave = _workspace_with_trial(db_session)
    _record(db_session, alice, oldest_event_keys=_keys(5))
    two = _keys(2) + _keys(3, prefix="other")
    assert _record(db_session, bob, oldest_event_keys=two) is None
    three = _keys(3) + _keys(2, prefix="another")
    assert _record(db_session, dave, oldest_event_keys=three) == "history_reused"
    assert _grant(db_session, dave.workspace.id).ended_reason == "history_reused"
    assert _grant(db_session, bob.workspace.id).ended_reason is None


def test_account_and_history_marks_do_not_collide(db_session, alice):
    # A history fingerprint is never read as an account number or vice versa.
    bob = _workspace_with_trial(db_session)
    _record(db_session, alice, oldest_event_keys=_keys(5))
    assert _record(db_session, bob, account_fingerprints=[_marks(db_session)[0].fingerprint]) is None


def test_trial_that_starts_this_instant_can_still_end_now(db_session, test_workspace):
    trials.grant_trial(db_session, workspace_id=test_workspace.id, email="x@example.com", now=T, env=ENV)
    other = _workspace_with_trial(db_session)
    _record(db_session, other, account_fingerprints=[_fp()])
    tenant = SimpleNamespace(workspace=test_workspace)
    reason = trials.record_broker_marks(
        db_session, workspace_id=test_workspace.id, account_fingerprints=[_fp()],
        oldest_event_keys=[], now=T, env=ENV,
    )
    db_session.commit()  # the CHECK ends_at > started_at must hold
    grant = _grant(db_session, tenant.workspace.id)
    assert reason == "broker_account_reused"
    assert grant.ended_reason == "broker_account_reused"
    assert grant.ends_at.replace(tzinfo=timezone.utc) > grant.started_at.replace(tzinfo=timezone.utc)
    assert trials.active_trial(db_session, test_workspace.id, T) is None


def test_ending_later_sets_ends_at_to_now(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _record(db_session, alice, account_fingerprints=[_fp()])
    later = T + timedelta(days=2)
    trials.record_broker_marks(
        db_session, workspace_id=bob.workspace.id, account_fingerprints=[_fp()],
        oldest_event_keys=[], now=later, env=ENV,
    )
    assert _grant(db_session, bob.workspace.id).ends_at.replace(tzinfo=timezone.utc) == later


# --- check_broker (best-effort wrapper) ---------------------------------------


def test_trading212_demo_is_skipped(db_session, alice):
    bob = _workspace_with_trial(db_session)
    demo = _fp("1", "trading212", "demo")
    assert trials.check_broker(db_session, workspace_id=alice.workspace.id, broker="trading212",
                               environment="demo", account_fingerprints=[demo]) is None
    assert trials.check_broker(db_session, workspace_id=bob.workspace.id, broker="trading212",
                               environment="demo", account_fingerprints=[demo]) is None
    assert _marks(db_session) == []
    assert _grant(db_session, bob.workspace.id).ended_reason is None


def test_ibkr_paper_and_masked_account_ids_are_skipped(db_session, alice):
    bob = _workspace_with_trial(db_session)
    for tenant in (alice, bob):
        assert trials.check_broker(db_session, workspace_id=tenant.workspace.id, broker="ibkr",
                                   account_ids=["DU1234567", "U***4567", ""]) is None
    assert _marks(db_session) == []


def test_raw_account_id_is_never_stored(db_session, alice):
    trials.check_broker(db_session, workspace_id=alice.workspace.id, broker="ibkr",
                        account_ids=["U7654321"])
    [mark] = _marks(db_session)
    assert mark.fingerprint == _fp("U7654321") and mark.kind == "account"
    assert "U7654321" not in mark.fingerprint


def test_a_failing_check_never_breaks_the_caller(db_session, alice, monkeypatch, caplog):
    def boom(*_a, **_k):
        raise RuntimeError("PORTFYL_TRIAL_FINGERPRINT_KEY missing")

    monkeypatch.setattr(trials, "record_broker_marks", boom)
    with caplog.at_level(logging.WARNING):
        assert trials.check_broker(db_session, workspace_id=alice.workspace.id, broker="ibkr",
                                   account_ids=["U1"]) is None
    db_session.commit()  # the session is still usable


def test_demo_and_idless_rows_are_never_fingerprinted():
    rows = [
        {"source": "demo", "source_event_stream": "demo", "source_event_id": "d1", "date": date(2020, 1, 1)},
        {"source": "csv", "source_event_stream": None, "source_event_id": None, "date": date(2020, 1, 1)},
        {"source": "t212_csv", "source_event_stream": "csv_export", "source_event_id": "x", "date": date(2021, 1, 1)},
    ]
    assert trials.oldest_history_keys(rows) == [("t212_csv", "csv_export", "x")]


def test_oldest_keys_are_the_five_oldest_in_a_stable_order():
    rows = [
        {"source": "t212_csv", "source_event_stream": "csv_export", "source_event_id": f"id{n}",
         "date": date(2021, 1, 10 - n)}
        for n in range(8)
    ]
    keys = trials.oldest_history_keys(rows)
    assert [k[2] for k in keys] == ["id7", "id6", "id5", "id4", "id3"]
    assert trials.oldest_history_keys(list(reversed(rows))) == keys


# --- Review Focus 3: through the real import commit --------------------------


def test_ibkr_xml_in_a_second_trial_ends_it_with_broker_account_reused(db_session, alice):
    bob = _workspace_with_trial(db_session)
    first = _import(db_session, alice, FLEX_XML, "flex.xml")
    second = _import(db_session, bob, FLEX_XML, "flex.xml")

    assert first["imported"] > 0 and second["imported"] == first["imported"]  # B's import is complete
    assert _grant(db_session, bob.workspace.id).ended_reason == "broker_account_reused"
    assert _grant(db_session, alice.workspace.id).ended_reason is None
    [event] = db_session.scalars(select(AuditLog).where(AuditLog.action == "trial.ended_early")).all()
    assert "U0000000" not in str(event.event_metadata)


def test_t212_csv_in_a_second_trial_ends_it_with_history_reused(db_session, alice):
    bob = _workspace_with_trial(db_session)
    first = _import(db_session, alice, _t212_csv())
    second = _import(db_session, bob, _t212_csv())

    assert first["imported"] == second["imported"] > 0
    assert _grant(db_session, bob.workspace.id).ended_reason == "history_reused"
    assert _grant(db_session, alice.workspace.id).ended_reason is None


def test_a_different_t212_export_ends_nothing(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _import(db_session, alice, _t212_csv("a"))
    _import(db_session, bob, _t212_csv("b"))
    assert _grant(db_session, bob.workspace.id).ended_reason is None


def test_sample_csv_in_both_workspaces_ends_nothing(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _import(db_session, alice, SAMPLE_CSV, "sample_portfolio.csv")
    _import(db_session, bob, SAMPLE_CSV, "sample_portfolio.csv")
    assert _marks(db_session) == []
    assert _grant(db_session, bob.workspace.id).ended_reason is None


def test_reimporting_the_same_export_in_the_same_workspace_ends_nothing(db_session, alice):
    _import(db_session, alice, FLEX_XML, "flex.xml")
    _import(db_session, alice, FLEX_XML, "flex.xml")
    assert _grant(db_session, alice.workspace.id).ended_reason is None


def test_import_without_a_trial_records_nothing(db_session, default_portfolio, request_context):
    tenant = SimpleNamespace(portfolio=default_portfolio, context=request_context)
    _import(db_session, tenant, FLEX_XML, "flex.xml")
    assert _marks(db_session) == []


def test_flex_account_ids_helper():
    assert flex_account_ids(FLEX_XML) == ["U0000000"]
    assert flex_account_ids("<not xml") == []
    assert flex_account_ids('<!DOCTYPE x [<!ENTITY a "b">]><FlexStatement accountId="U1"/>') == []


# --- Flex API sync, eToro sync, Trading 212 connect --------------------------


def _flex_sync(db, tenant):
    with patch.object(ibkr_router, "_send_flex_request", AsyncMock(return_value="REF")), \
         patch.object(ibkr_router, "_poll_flex_statement", AsyncMock(return_value=FLEX_XML)), \
         patch("importers.instruments.DefaultInstrumentResolver.from_env", return_value=RESOLVER):
        return run_on_private_loop(ibkr_router._run_ibkr_sync, db,
                                   tenant.workspace.id, tenant.portfolio.id)


def _ibkr_connection(db, tenant):
    db.add(BrokerConnection(workspace_id=tenant.workspace.id, portfolio_id=tenant.portfolio.id,
                            broker="ibkr", api_key="token-0000000000", api_secret="123456",
                            environment="live"))
    db.commit()


def test_ibkr_flex_sync_and_xml_upload_share_the_account(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _import(db_session, alice, FLEX_XML, "flex.xml")
    _ibkr_connection(db_session, bob)
    result = _flex_sync(db_session, bob)
    assert result["ledger"]["status"] == "imported"
    assert _grant(db_session, bob.workspace.id).ended_reason == "broker_account_reused"


def test_ibkr_flex_sync_of_a_new_account_ends_nothing(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _import(db_session, alice, FLEX_XML, "flex.xml")
    _ibkr_connection(db_session, bob)
    other = FLEX_XML.replace("U0000000", "U9999999")
    with patch.object(ibkr_router, "_send_flex_request", AsyncMock(return_value="REF")), \
         patch.object(ibkr_router, "_poll_flex_statement", AsyncMock(return_value=other)), \
         patch("importers.instruments.DefaultInstrumentResolver.from_env", return_value=RESOLVER):
        run_on_private_loop(ibkr_router._run_ibkr_sync, db_session,
                            bob.workspace.id, bob.portfolio.id)
    assert _grant(db_session, bob.workspace.id).ended_reason is None


class _EtoroClient:
    history = [
        {"positionId": n, "instrumentId": 1001, "isBuy": True, "leverage": 1, "units": 2.0,
         "openRate": 190.0, "openTimestamp": f"2025-01-0{n}T14:30:00Z",
         "closeRate": 200.0, "closeTimestamp": f"2025-03-0{n}T15:00:00Z"}
        for n in range(1, 5)
    ]

    def __init__(self, *_a, **_k):
        pass

    def positions(self):
        return []

    def trade_history(self, min_date):
        return list(self.history)

    def instruments(self, ids):
        return {1001: {"symbol": "AAPL", "exchange": "NASDAQ", "type": "Stocks", "name": "Apple"}}


def _etoro_sync(db, tenant, monkeypatch):
    monkeypatch.setenv("PORTFYL_ETORO_APP_KEY", "app")
    monkeypatch.setattr(etoro_router, "EtoroClient", _EtoroClient)
    db.add(BrokerConnection(workspace_id=tenant.workspace.id, portfolio_id=tenant.portfolio.id,
                            broker="etoro", api_key="user-key-123456"))
    db.commit()
    return etoro_router.etoro_sync(db, tenant.workspace.id, tenant.portfolio.id)


def test_etoro_sync_uses_the_history_fingerprint(db_session, alice, monkeypatch):
    bob = _workspace_with_trial(db_session)
    assert _etoro_sync(db_session, alice, monkeypatch)["status"] == "imported"
    assert _etoro_sync(db_session, bob, monkeypatch)["status"] == "imported"
    assert _grant(db_session, bob.workspace.id).ended_reason == "history_reused"
    assert _grant(db_session, alice.workspace.id).ended_reason is None
    assert all(m.kind == "history" for m in _marks(db_session))


def test_etoro_repeat_sync_adds_no_marks(db_session, alice, monkeypatch):
    _etoro_sync(db_session, alice, monkeypatch)
    count = len(_marks(db_session))
    etoro_router.etoro_sync(db_session, alice.workspace.id, alice.portfolio.id)
    assert len(_marks(db_session)) == count == 5


def _t212_response(account_id):
    response = MagicMock(status_code=200)
    response.json.return_value = {"id": account_id}
    return response


def _t212_connect(db, tenant, key, environment="live", account_id=4242):
    with patch("routers.broker.httpx.get", return_value=_t212_response(account_id)):
        return connect(payload={"api_key": key, "environment": environment},
                       db=db, portfolio=tenant.portfolio, _context=tenant.context)


def test_second_workspace_with_new_t212_key_but_same_account_ends_its_trial(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _t212_connect(db_session, alice, "first-key-value-1234567890")
    _t212_connect(db_session, bob, "freshly-generated-key-1234567890")
    assert _grant(db_session, bob.workspace.id).ended_reason == "broker_account_reused"
    assert _grant(db_session, alice.workspace.id).ended_reason is None
    # the stored mark is the existing fingerprint, never the key or the id
    [mark] = _marks(db_session)
    assert mark.fingerprint == _fp(4242, "trading212", "live")


def test_t212_demo_connections_end_nothing(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _t212_connect(db_session, alice, "first-key-value-1234567890", "demo")
    _t212_connect(db_session, bob, "freshly-generated-key-1234567890", "demo")
    assert _marks(db_session) == []
    assert _grant(db_session, bob.workspace.id).ended_reason is None


def test_t212_connect_rolls_marks_back_with_the_connection(db_session, alice):
    bob = _workspace_with_trial(db_session)
    _t212_connect(db_session, alice, "first-key-value-1234567890")
    with patch("routers.broker.record_audit_event", side_effect=RuntimeError("boom")), \
            patch("routers.broker.httpx.get", return_value=_t212_response(4242)):
        with pytest.raises(RuntimeError):
            connect(payload={"api_key": "freshly-generated-key-1234567890"},
                    db=db_session, portfolio=bob.portfolio, _context=bob.context)
    db_session.rollback()
    assert _grant(db_session, bob.workspace.id).ended_reason is None
