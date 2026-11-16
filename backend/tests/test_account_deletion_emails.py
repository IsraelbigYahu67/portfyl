"""Wave 2: the two account-deletion notices (scheduled, deleted)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from account_deletion import (
    WorkspaceDeletion,
    DELETION_SETTING_KEY,
    get_workspace_deletion,
    purge_due_workspace_deletions,
    schedule_workspace_deletion,
)
from app_settings import set_workspace_setting
from emails.catalog import EmailKind
from firebase_identity import VerifiedIdentity
from models import AuditLog, Membership, User, Workspace
from routers.account import DeletionRequestPayload, schedule_deletion

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
APP_URL = "https://app.portfyl.com"
ADDRESS = "unit-tests@example.com"


class FakeTransport:
    def __init__(self, *, available=True, error=None):
        self._available, self._error = available, error
        self.sent = []

    def available(self):
        return self._available

    def send(self, *, to, email, tag):
        if self._error is not None:
            raise self._error
        self.sent.append((to, email, tag))
        return "msg-1"


class FakeMailer:
    def __init__(self, transport=None):
        self.transport = transport or FakeTransport()
        self.links = SimpleNamespace(_app_url=APP_URL)


class Admin:
    def __init__(self, error=None):
        self.deleted, self.error = [], error

    def delete_user(self, uid):
        if self.error:
            raise self.error
        self.deleted.append(uid)


def _identity(context, authenticated_at=None):
    return VerifiedIdentity(
        uid=context.user.firebase_uid,
        email=context.user.email,
        email_verified=True,
        display_name=None,
        authenticated_at=authenticated_at or datetime.now(timezone.utc),
    )


def _verifier(context):
    identity = _identity(context)

    class Verifier:
        def verify_id_token(self, token):
            return identity

    return Verifier()


def _request(db, context, mailer, lang="en"):
    return schedule_deletion(
        DeletionRequestPayload(
            reauth_id_token="token",
            confirmation=context.workspace.name,
            lang=lang,
        ),
        db,
        context,
        _verifier(context),
        mailer,
    )


def _schedule(db, context, *, lang="en"):
    state = schedule_workspace_deletion(
        db,
        context,
        identity=_identity(context, NOW - timedelta(minutes=1)),
        confirmation=context.workspace.name,
        now=NOW,
        lang=lang,
    )
    db.commit()
    return state


# --- account_deletion_scheduled -------------------------------------------


def test_schedule_request_sends_one_notice_with_date_and_settings_button(db_session, request_context):
    mailer = FakeMailer()

    status = _request(db_session, request_context, mailer, lang="cs")

    (to, email, tag), = mailer.transport.sent
    assert to == ADDRESS and tag == EmailKind.ACCOUNT_DELETION_SCHEDULED.value
    assert email.subject.startswith("Váš účet Portfyl bude smazán")
    execute_after = datetime.fromisoformat(status["execute_after"])
    assert f"{execute_after.day}." in email.subject
    assert f"{APP_URL}/settings" in email.text
    assert ADDRESS in email.text


def test_schedule_request_defaults_to_english_for_missing_or_garbage_lang(db_session, request_context):
    for lang in (None, "xx", 42, "x" * 5000):
        mailer = FakeMailer()
        # a fresh workspace state each time
        from account_deletion import cancel_workspace_deletion
        cancel_workspace_deletion(db_session, request_context)
        db_session.commit()
        _request(db_session, request_context, mailer, lang=lang)
        (_, email, _), = mailer.transport.sent
        assert email.subject.startswith("Your Portfyl account will be deleted on")


def test_repeat_request_returns_existing_state_and_sends_nothing_more(db_session, request_context):
    mailer = FakeMailer()
    first = _request(db_session, request_context, mailer)
    second = _request(db_session, request_context, mailer)

    assert second == first
    assert len(mailer.transport.sent) == 1


@pytest.mark.parametrize("mailer", [
    None,
    FakeMailer(FakeTransport(available=False)),
    FakeMailer(FakeTransport(error=RuntimeError("brevo down"))),
])
def test_mailer_missing_down_or_failing_never_fails_the_request(db_session, request_context, mailer):
    status = _request(db_session, request_context, mailer)

    assert status["scheduled"] is True
    assert get_workspace_deletion(db_session, request_context.workspace.id) is not None
    if mailer is not None:
        assert mailer.transport.sent == []


def test_notice_is_attempted_after_the_state_is_committed(db_session, request_context, monkeypatch):
    events = []
    original_commit = db_session.commit

    def commit():
        events.append("commit")
        original_commit()

    monkeypatch.setattr(db_session, "commit", commit)

    class Transport(FakeTransport):
        def send(self, *, to, email, tag):
            events.append("send")
            return super().send(to=to, email=email, tag=tag)

    _request(db_session, request_context, FakeMailer(Transport()))

    assert events.count("send") == 1
    assert "commit" in events[: events.index("send")]


def test_no_address_in_logs_or_audit_metadata(db_session, request_context, caplog):
    caplog.set_level(logging.DEBUG)
    for mailer in (
        FakeMailer(),
        FakeMailer(FakeTransport(error=RuntimeError(f"cannot reach {ADDRESS}"))),
    ):
        from account_deletion import cancel_workspace_deletion
        cancel_workspace_deletion(db_session, request_context)
        db_session.commit()
        _request(db_session, request_context, mailer)

    assert ADDRESS not in caplog.text
    assert APP_URL not in caplog.text
    for row in db_session.scalars(select(AuditLog)).all():
        assert ADDRESS not in str(row.event_metadata)


# --- lang inside the stored state ------------------------------------------


def test_lang_is_stored_in_the_state_and_survives_a_reload(db_session, request_context):
    state = _schedule(db_session, request_context, lang="CS-cz")

    assert state.lang == "cs"
    assert get_workspace_deletion(db_session, request_context.workspace.id).lang == "cs"


def test_old_state_without_lang_parses_as_english(db_session, request_context):
    set_workspace_setting(
        db_session,
        request_context.workspace.id,
        DELETION_SETTING_KEY,
        '{"version":1,"requested_at":"2026-09-07T12:00:00+00:00",'
        '"execute_after":"2026-10-07T12:00:00+00:00",'
        f'"requested_by_user_id":"{request_context.user.id}"}}',
    )
    db_session.commit()

    state = get_workspace_deletion(db_session, request_context.workspace.id)

    assert isinstance(state, WorkspaceDeletion)
    assert state.lang == "en"


# --- account_deleted -------------------------------------------------------


def test_purge_sends_account_deleted_to_the_stored_address_and_language(db_session, request_context):
    user_id = request_context.user.id
    _schedule(db_session, request_context, lang="cs")
    mailer = FakeMailer()

    summary = purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=30), mailer=mailer
    )

    assert summary["purged"] == 1 and summary["errors"] == 0
    assert db_session.get(User, user_id) is None
    (to, email, tag), = mailer.transport.sent
    assert to == ADDRESS and tag == EmailKind.ACCOUNT_DELETED.value
    assert email.subject == "Váš účet Portfyl byl smazán"
    assert ADDRESS in email.text


def test_purge_sends_in_english_for_an_old_state_without_lang(db_session, request_context):
    set_workspace_setting(
        db_session,
        request_context.workspace.id,
        DELETION_SETTING_KEY,
        '{"version":1,"requested_at":"2026-09-07T12:00:00+00:00",'
        '"execute_after":"2026-10-07T12:00:00+00:00",'
        f'"requested_by_user_id":"{request_context.user.id}"}}',
    )
    db_session.commit()
    mailer = FakeMailer()

    purge_due_workspace_deletions(db_session, Admin(), now=NOW + timedelta(days=31), mailer=mailer)

    (_, email, _), = mailer.transport.sent
    assert email.subject == "Your Portfyl account has been deleted"


def test_purge_send_failure_does_not_block_or_count_as_error(db_session, request_context):
    user_id = request_context.user.id
    _schedule(db_session, request_context)
    mailer = FakeMailer(FakeTransport(error=RuntimeError("brevo down")))

    summary = purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=30), mailer=mailer
    )

    assert summary["purged"] == 1 and summary["errors"] == 0
    assert db_session.get(User, user_id) is None


def test_purge_with_the_mailer_unavailable_still_purges(db_session, request_context):
    _schedule(db_session, request_context)
    mailer = FakeMailer(FakeTransport(available=False))

    summary = purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=30), mailer=mailer
    )

    assert summary["purged"] == 1
    assert mailer.transport.sent == []


def test_retried_purge_does_not_send_twice(db_session, request_context):
    _schedule(db_session, request_context)
    mailer = FakeMailer()

    for days in (30, 31, 32):
        purge_due_workspace_deletions(
            db_session, Admin(), now=NOW + timedelta(days=days), mailer=mailer
        )

    assert len(mailer.transport.sent) == 1


def test_failed_identity_deletion_sends_nothing_and_a_retry_sends_once(db_session, request_context):
    _schedule(db_session, request_context)
    mailer = FakeMailer()

    failed = purge_due_workspace_deletions(
        db_session, Admin(error=RuntimeError("firebase unavailable")),
        now=NOW + timedelta(days=30), mailer=mailer,
    )
    assert failed["errors"] == 1 and mailer.transport.sent == []

    retried = purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=31), mailer=mailer
    )
    assert retried["purged"] == 1
    assert len(mailer.transport.sent) == 1


def test_no_account_deleted_notice_while_the_user_keeps_another_workspace(db_session, request_context):
    other = Workspace(id=uuid4(), name="Kept workspace")
    db_session.add(other)
    db_session.flush()
    db_session.add(Membership(
        user_id=request_context.user.id, workspace_id=other.id, role="owner", status="active",
    ))
    _schedule(db_session, request_context)
    mailer = FakeMailer()

    summary = purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=31), mailer=mailer
    )

    assert summary["purged"] == 1
    assert mailer.transport.sent == []


def test_no_notice_before_the_deadline(db_session, request_context):
    _schedule(db_session, request_context)
    mailer = FakeMailer()

    purge_due_workspace_deletions(db_session, Admin(), now=NOW + timedelta(days=29), mailer=mailer)

    assert mailer.transport.sent == []


def test_purge_logs_carry_no_address(db_session, request_context, caplog):
    caplog.set_level(logging.DEBUG)
    _schedule(db_session, request_context)
    mailer = FakeMailer(FakeTransport(error=RuntimeError(f"cannot reach {ADDRESS}")))

    purge_due_workspace_deletions(
        db_session, Admin(), now=NOW + timedelta(days=30), mailer=mailer
    )

    assert ADDRESS not in caplog.text
