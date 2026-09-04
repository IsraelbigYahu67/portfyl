from __future__ import annotations

from datetime import datetime, timezone

from billing_config import BillingConfig
from models import AuditLog, NotificationOutbox, TrialGrant
from trials import activate_trial, identity_fingerprint


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def _config():
    return BillingConfig(
        enabled=True,
        secret_key="sk_test",
        webhook_secret="whsec_test",
        trial_identity_key="trial-key",
        app_url="https://portfyl.test",
        current_price_version="v1",
        stripe_prices={},
    )


def test_identity_fingerprint_is_normalized_and_hides_email():
    first = identity_fingerprint(" Alice@Example.com ", "secret")
    assert first == identity_fingerprint("alice@example.com", "secret")
    assert "alice" not in first and len(first) == 64


def test_trial_requires_verified_email(db_session, test_user, test_workspace):
    test_user.email_verified_at = None
    assert activate_trial(db_session, user=test_user, workspace=test_workspace, activation_kind="csv_import", config=_config(), now=NOW) is None
    assert db_session.query(TrialGrant).count() == 0


def test_trial_activates_once_and_enqueues_notification(db_session, test_user, test_workspace):
    test_user.email_verified_at = NOW
    first = activate_trial(db_session, user=test_user, workspace=test_workspace, activation_kind="csv_import", config=_config(), now=NOW)
    second = activate_trial(db_session, user=test_user, workspace=test_workspace, activation_kind="broker_connection", config=_config(), now=NOW)
    assert first is second
    duration = first.ends_at.replace(tzinfo=timezone.utc) - first.started_at.replace(tzinfo=timezone.utc)
    assert duration.days == 7
    assert db_session.query(TrialGrant).count() == 1
    assert db_session.query(NotificationOutbox).count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.action == "billing.trial.activated").count() == 1
