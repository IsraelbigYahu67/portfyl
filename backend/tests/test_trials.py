"""The 10-day Pro trial: grant rules, abuse guards and expiry (backend/trials.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import entitlements as entitlements_module
import trials
from edition import Edition
from entitlements import (
    EntitlementDenied,
    ensure_count_limit,
    ensure_final_count_limit,
    require_writable_resource,
    resolve_entitlements,
)
from models import (
    AuditLog,
    BrokerConnection,
    Portfolio,
    TrialBrokerMark,
    TrialGrant,
    TrialIdentity,
    TrialIpMark,
    Workspace,
)
from plans import PlanTier

T = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ENV = {"PORTFYL_TRIAL_FINGERPRINT_KEY": "test-only-trial-fingerprint-key-0000000001"}


def _workspace(db) -> Workspace:
    workspace = Workspace(id=uuid4(), name="W")
    db.add(workspace)
    db.flush()
    return workspace


def _resolve(db, workspace_id, now):
    return resolve_entitlements(
        db, edition=Edition.CLOUD, workspace_id=workspace_id, now=now, env=ENV
    )


def _grant(db, workspace, email="alice@example.com", now=T, **kwargs):
    return trials.grant_trial(
        db, workspace_id=workspace.id, email=email, now=now, env=ENV, **kwargs
    )


def test_new_workspace_gets_ten_day_pro_trial(db_session, test_workspace):
    grant = _grant(db_session, test_workspace)
    assert grant is not None
    result = _resolve(db_session, test_workspace.id, T)
    assert result.plan is PlanTier.PRO
    assert result.source == "trial"
    assert result.effective_until == T + timedelta(days=10)
    assert result.payload()["trial_ended_reason"] is None


def test_trial_expires_to_free(db_session, test_workspace):
    _grant(db_session, test_workspace)
    result = _resolve(db_session, test_workspace.id, T + timedelta(days=10, seconds=1))
    assert result.plan is PlanTier.FREE
    assert result.source == "free"
    assert result.payload()["trial_ended_reason"] == "expired"


def test_workspace_without_trial_has_no_ended_reason(db_session, test_workspace):
    result = _resolve(db_session, test_workspace.id, T)
    assert result.payload()["trial_ended_reason"] is None


def test_second_grant_for_same_email_returns_none(db_session, test_workspace):
    assert _grant(db_session, test_workspace, "alice@example.com") is not None
    other = _workspace(db_session)
    assert _grant(db_session, other, " Alice@Example.com ") is None
    assert db_session.scalar(select(func.count()).select_from(TrialGrant)) == 1


def test_canonical_email():
    assert trials.canonical_email("Jan.Novak+1@GoogleMail.com") == "jannovak@gmail.com"
    assert trials.canonical_email("jan+x@seznam.cz") == "jan@seznam.cz"
    assert trials.canonical_email("jan.novak@outlook.com") == "jan.novak@outlook.com"
    assert trials.canonical_email("  JAN@Example.COM ") == "jan@example.com"


def test_alias_gets_no_second_trial(db_session, test_workspace, test_user):
    assert _grant(db_session, test_workspace, "jan@gmail.com") is not None
    other = _workspace(db_session)
    assert _grant(db_session, other, "j.a.n+2@gmail.com", actor_user_id=test_user.id) is None
    # The account itself still exists and is on Free.
    assert db_session.get(Workspace, other.id) is not None
    assert _resolve(db_session, other.id, T).plan is PlanTier.FREE
    event = db_session.scalar(select(AuditLog).where(AuditLog.action == "trial.withheld"))
    assert event is not None
    assert event.event_metadata == {"reason": "email_reused"}
    assert event.workspace_id == other.id


def test_disposable_domain_gets_no_trial(db_session, test_workspace, test_user):
    assert _grant(db_session, test_workspace, "x@mailinator.com", actor_user_id=test_user.id) is None
    assert db_session.scalar(select(func.count()).select_from(TrialGrant)) == 0
    # No identity was burnt either: the same mailbox is not "used up".
    assert db_session.scalar(select(func.count()).select_from(TrialIdentity)) == 0
    event = db_session.scalar(select(AuditLog).where(AuditLog.action == "trial.withheld"))
    assert event.event_metadata == {"reason": "disposable_domain"}


def test_disposable_match_is_exact_domain_not_substring_or_subdomain():
    assert trials.is_disposable_domain("a@MAILINATOR.com")
    assert not trials.is_disposable_domain("a@mailinator.org.example")
    assert not trials.is_disposable_domain("a@sub.mailinator.com.example.org")
    assert not trials.is_disposable_domain("no-at-sign")


def test_fourth_trial_from_same_ip_in_30_days_is_withheld(db_session, test_user):
    ip = "203.0.113.7"
    for i in range(3):
        grant = _grant(db_session, _workspace(db_session), f"user{i}@example.com", client_ip=ip)
        assert grant is not None
    fourth = _workspace(db_session)
    assert _grant(db_session, fourth, "user3@example.com", client_ip=ip,
                  actor_user_id=test_user.id) is None
    event = db_session.scalar(select(AuditLog).where(AuditLog.action == "trial.withheld"))
    assert event.event_metadata == {"reason": "ip_limit"}
    # A different address is unaffected.
    assert _grant(db_session, _workspace(db_session), "user4@example.com",
                  client_ip="203.0.113.8") is not None


def test_ip_limit_window_is_30_days(db_session):
    ip = "203.0.113.7"
    for i in range(3):
        _grant(db_session, _workspace(db_session), f"user{i}@example.com", client_ip=ip)
    later = T + timedelta(days=31)
    assert _grant(db_session, _workspace(db_session), "late@example.com",
                  client_ip=ip, now=later) is not None


def test_ipv6_addresses_in_one_64_share_a_counter(db_session):
    for i in range(3):
        assert _grant(db_session, _workspace(db_session), f"v{i}@example.com",
                      client_ip=f"2001:db8:1:2::{i + 1}") is not None
    assert _grant(db_session, _workspace(db_session), "v9@example.com",
                  client_ip="2001:db8:1:2:ffff::1") is None


def test_fingerprints_never_hold_raw_values(db_session, test_workspace):
    _grant(db_session, test_workspace, "alice@example.com", client_ip="203.0.113.7")
    identity = db_session.scalar(select(TrialIdentity))
    mark = db_session.scalar(select(TrialIpMark))
    assert len(identity.fingerprint) == 64 and "alice" not in identity.fingerprint
    assert len(mark.ip_fingerprint) == 64 and "203" not in mark.ip_fingerprint
    assert identity.fingerprint != mark.ip_fingerprint


def test_trial_days_zero_grants_nothing(db_session, test_workspace):
    env = {**ENV, "PORTFYL_TRIAL_DAYS": "0"}
    assert trials.grant_trial(
        db_session, workspace_id=test_workspace.id, email="a@example.com", now=T, env=env
    ) is None
    assert db_session.scalar(select(func.count()).select_from(TrialGrant)) == 0
    assert db_session.scalar(select(func.count()).select_from(TrialIdentity)) == 0


def test_withheld_trial_marks_workspace_not_eligible(db_session, test_workspace):
    from app_settings import get_workspace_setting

    assert _grant(db_session, test_workspace, "jan@gmail.com") is not None
    other = _workspace(db_session)
    assert _grant(db_session, other, "j.a.n+2@gmail.com") is None
    assert trials.trial_state(db_session, other.id, T) == (None, "not_eligible")
    assert get_workspace_setting(db_session, other.id, "trial_withheld") == "1"
    # The workspace that got the trial is not marked.
    assert get_workspace_setting(db_session, test_workspace.id, "trial_withheld") is None


def test_withheld_marker_written_even_without_actor(db_session, test_workspace):
    from app_settings import get_workspace_setting

    _grant(db_session, test_workspace, "jan@gmail.com")
    other = _workspace(db_session)
    assert _grant(db_session, other, "j.a.n+2@gmail.com", actor_user_id=None) is None
    assert get_workspace_setting(db_session, other.id, "trial_withheld") == "1"
    assert db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "trial.withheld")
    ) == 0


def test_trial_days_zero_keeps_running_trials_and_marks_nothing(db_session, test_workspace):
    from app_settings import get_workspace_setting

    assert _grant(db_session, test_workspace) is not None
    off = {**ENV, "PORTFYL_TRIAL_DAYS": "0"}
    other = _workspace(db_session)
    assert trials.grant_trial(
        db_session, workspace_id=other.id, email="b@example.com", now=T, env=off
    ) is None
    assert trials.trial_state(db_session, other.id, T) == (None, None)
    assert get_workspace_setting(db_session, other.id, "trial_withheld") is None
    # The earlier grant keeps running to its ends_at.
    grant, reason = trials.trial_state(db_session, test_workspace.id, T + timedelta(days=5))
    assert grant is not None and reason is None


def test_expired_reason_wins_over_marker(db_session, test_workspace):
    from app_settings import set_workspace_setting

    _grant(db_session, test_workspace)
    set_workspace_setting(db_session, test_workspace.id, "trial_withheld", "1")
    grant, reason = trials.trial_state(db_session, test_workspace.id, T + timedelta(days=11))
    assert grant is None and reason == "expired"


def test_trial_days_setting():
    assert trials.trial_days({}) == 10
    assert trials.trial_days({"PORTFYL_TRIAL_DAYS": ""}) == 10
    assert trials.trial_days({"PORTFYL_TRIAL_DAYS": "14"}) == 14
    assert trials.trial_days({"PORTFYL_TRIAL_DAYS": "0"}) == 0
    for bad in ("-1", "ten", "1.5"):
        with pytest.raises(RuntimeError):
            trials.trial_days({"PORTFYL_TRIAL_DAYS": bad})


def test_custom_length(db_session, test_workspace):
    env = {**ENV, "PORTFYL_TRIAL_DAYS": "3"}
    grant = trials.grant_trial(
        db_session, workspace_id=test_workspace.id, email="a@example.com", now=T, env=env
    )
    assert grant.ends_at == T + timedelta(days=3)


@pytest.mark.parametrize("key", [None, "", "short"])
def test_missing_fingerprint_key_fails_closed(db_session, test_workspace, key):
    env = {} if key is None else {"PORTFYL_TRIAL_FINGERPRINT_KEY": key}
    with pytest.raises(RuntimeError):
        trials.grant_trial(
            db_session, workspace_id=test_workspace.id, email="a@example.com", now=T, env=env
        )
    with pytest.raises(RuntimeError):
        trials.identity_fingerprint("a@example.com", env)


def test_missing_key_is_fine_when_trials_are_off(db_session, test_workspace):
    assert trials.grant_trial(
        db_session, workspace_id=test_workspace.id, email="a@example.com", now=T,
        env={"PORTFYL_TRIAL_DAYS": "0"},
    ) is None


def test_active_trial_lookup(db_session, test_workspace):
    assert trials.active_trial(db_session, test_workspace.id, T) is None
    grant = _grant(db_session, test_workspace)
    assert trials.active_trial(db_session, test_workspace.id, T).id == grant.id
    assert trials.active_trial(db_session, test_workspace.id, grant.ends_at) is None


def test_expired_trial_keeps_overflow_rows_read_only(
    db_session, test_workspace, default_portfolio, monkeypatch
):
    _grant(db_session, test_workspace)
    # During the trial (Pro: 15 portfolios, 5 connections) the workspace builds
    # more than Free (1 portfolio, 0 connections) allows.
    extra = [Portfolio(workspace_id=test_workspace.id, name=f"P{i}") for i in range(4)]
    db_session.add_all(extra)
    db_session.flush()
    for i, portfolio in enumerate([default_portfolio, *extra[:2]]):
        db_session.add(BrokerConnection(
            workspace_id=test_workspace.id, portfolio_id=portfolio.id,
            broker="trading212", api_key="k" * 20, api_secret="s",
        ))
    db_session.commit()
    portfolios = db_session.scalar(select(func.count()).select_from(Portfolio))
    connections = db_session.scalar(select(func.count()).select_from(BrokerConnection))
    assert (portfolios, connections) == (5, 3)

    after = _resolve(db_session, test_workspace.id, T + timedelta(days=11))
    assert after.plan is PlanTier.FREE
    with pytest.raises(EntitlementDenied) as exc:
        ensure_count_limit(after, "portfolios", used=portfolios)
    assert exc.value.code == "quota_exceeded"
    with pytest.raises(EntitlementDenied):
        ensure_final_count_limit(after, "portfolios", current=portfolios, final=portfolios + 1)
    ensure_final_count_limit(after, "portfolios", current=portfolios, final=portfolios - 1)

    # The deterministic overflow rule: the oldest `limit` rows stay writable,
    # later ones are read-only. Nothing was deleted.
    rows = db_session.scalars(
        select(Portfolio).where(Portfolio.workspace_id == test_workspace.id)
        .order_by(Portfolio.created_at, Portfolio.id)
    ).all()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(portfyl_edition=Edition.CLOUD)),
        path_params={"portfolio_id": str(rows[-1].public_id)},
    )
    monkeypatch.setattr(entitlements_module, "utcnow", lambda: T + timedelta(days=11))
    with pytest.raises(EntitlementDenied) as read_only:
        require_writable_resource("portfolios", Portfolio, "portfolio_id")(
            request, SimpleNamespace(workspace=test_workspace), db_session
        )
    assert read_only.value.code == "resource_read_only"
    assert db_session.scalar(select(func.count()).select_from(Portfolio)) == 5
    assert db_session.scalar(select(func.count()).select_from(BrokerConnection)) == 3


def test_purge_removes_only_identities_older_than_365_days(db_session):
    db_session.add_all([
        TrialIdentity(fingerprint="a" * 64, granted_at=T - timedelta(days=366)),
        TrialIdentity(fingerprint="b" * 64, granted_at=T - timedelta(days=364)),
    ])
    db_session.commit()
    assert trials.purge_old_identities(db_session, T) == 1
    assert [row.fingerprint for row in db_session.scalars(select(TrialIdentity))] == ["b" * 64]


def test_purge_trial_records_covers_ip_marks_and_broker_marks(db_session):
    db_session.add_all([
        TrialIpMark(ip_fingerprint="i" * 64, granted_at=T - timedelta(days=31)),
        TrialIpMark(ip_fingerprint="j" * 64, granted_at=T - timedelta(days=29)),
        TrialBrokerMark(fingerprint="x" * 64, kind="account", first_seen_at=T - timedelta(days=400)),
        TrialBrokerMark(fingerprint="y" * 64, kind="account", first_seen_at=T - timedelta(days=100)),
        TrialIdentity(fingerprint="z" * 64, granted_at=T - timedelta(days=400)),
    ])
    db_session.commit()
    summary = trials.purge_trial_records(db_session, T)
    assert summary == {"identities": 1, "ip_marks": 1, "broker_marks": 1}
    assert [m.ip_fingerprint for m in db_session.scalars(select(TrialIpMark))] == ["j" * 64]
    assert [m.fingerprint for m in db_session.scalars(select(TrialBrokerMark))] == ["y" * 64]
