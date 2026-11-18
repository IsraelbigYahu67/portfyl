"""The account-deleted notice: after an immediate deletion and after the legacy purge."""

from __future__ import annotations

import json
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
)
from app_settings import set_workspace_setting
from emails.catalog import EmailKind
from firebase_identity import VerifiedIdentity
from models import AuditLog, Membership, User, Workspace
from tenancy import RequestContextError
from routers.account import DeletionRequestPayload, delete_workspace

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


def _verifier(context, admin=None):
    identity = _identity(context)
    admin = admin or Admin()

    class Verifier:
        def verify_id_token(self, token):
            return identity

        def delete_user(self, uid):
            admin.delete_user(uid)

    return Verifier()


def _request(db, context, mailer, lang="en", admin=None):
    from fastapi import Response

    db.commit()
    return delete_workspace(
        DeletionRequestPayload(
            reauth_id_token="token",
            confirmation=context.workspace.name,
            lang=lang,
        ),
        Response(),
        db,
        context,
        _verifier(context, admin),
        mailer,
    )


def _schedule(db, context, *, lang="en"):
    """A request left over from the old 30-day rule; nothing creates these now."""
    state = {
        "version": 1,
        "requested_at": NOW.isoformat(),
        "execute_after": (NOW + timedelta(days=30)).isoformat(),
        "requested_by_user_id": str(context.user.id),
        "lang": lang,
    }
    set_workspace_setting(db, context.workspace.id, DELETION_SETTING_KEY, json.dumps(state))
    db.commit()
    return get_workspace_deletion(db, context.workspace.id)


# --- account_deleted after an immediate deletion ---------------------------


def test_immediate_deletion_sends_account_deleted_in_the_app_language(db_session, request_context):
    mailer = FakeMailer()

    body = _request(db_session, request_context, mailer, lang="cs")

    assert body == {"deleted": True, "account_deleted": True}
    (to, email, tag), = mailer.transport.sent
    assert to == ADDRESS and tag == EmailKind.ACCOUNT_DELETED.value
    assert email.subject == "Váš účet Portfyl byl smazán"
    assert ADDRESS in email.text


@pytest.mark.parametrize("lang", [None, "xx", 42, "x" * 5000])
def test_immediate_deletion_defaults_to_english_for_missing_or_garbage_lang(
    db_session, request_context, lang,
):
    mailer = FakeMailer()

    _request(db_session, request_context, mailer, lang=lang)

    (_, email, _), = mailer.transport.sent
    assert email.subject == "Your Portfyl account has been deleted"


@pytest.mark.parametrize("mailer", [
    None,
    FakeMailer(FakeTransport(available=False)),
    FakeMailer(FakeTransport(error=RuntimeError("brevo down"))),
])
def test_mailer_missing_down_or_failing_never_fails_the_deletion(db_session, request_context, mailer):
    user_id = request_context.user.id

    body = _request(db_session, request_context, mailer)

    assert body["deleted"] is True
    assert db_session.get(User, user_id) is None
    if mailer is not None:
        assert mailer.transport.sent == []


def test_notice_is_sent_only_after_the_deletion_is_committed(db_session, request_context, monkeypatch):
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


def test_no_notice_when_the_user_keeps_another_workspace(db_session, request_context):
    other = Workspace(id=uuid4(), name="Kept workspace")
    db_session.add(other)
    db_session.flush()
    db_session.add(Membership(
        user_id=request_context.user.id, workspace_id=other.id, role="owner", status="active",
    ))
    mailer = FakeMailer()

    body = _request(db_session, request_context, mailer)

    assert body == {"deleted": True, "account_deleted": False}
    assert mailer.transport.sent == []


def test_no_notice_when_the_identity_provider_fails(db_session, request_context):
    mailer = FakeMailer()

    with pytest.raises(RequestContextError):
        _request(db_session, request_context, mailer, admin=Admin(error=RuntimeError("down")))

    assert mailer.transport.sent == []
    assert db_session.get(User, request_context.user.id) is not None


def test_no_address_in_logs_or_audit_metadata(db_session, request_context, caplog):
    caplog.set_level(logging.DEBUG)
    _request(
        db_session, request_context,
        FakeMailer(FakeTransport(error=RuntimeError(f"cannot reach {ADDRESS}"))),
    )

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
