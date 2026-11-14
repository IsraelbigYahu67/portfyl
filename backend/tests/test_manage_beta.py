"""Operator CLI for private-beta invitations: expiry handling on (re-)invite."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import manage_beta
from models import BetaInvite


@pytest.fixture
def cli(db_session, monkeypatch):
    """Point the CLI's SessionLocal at the in-memory test session."""

    @contextmanager
    def _session():
        yield db_session

    monkeypatch.setattr(manage_beta, "SessionLocal", _session)
    return manage_beta


def _row(db_session, email: str) -> BetaInvite:
    return db_session.scalar(select(BetaInvite).where(BetaInvite.email == email))


def test_invite_without_expiry_leaves_expires_at_empty(cli, db_session):
    cli.invite("new@example.com", None)

    row = _row(db_session, "new@example.com")
    assert row.status == "invited"
    assert row.expires_at is None


def test_invite_with_days_sets_expiry(cli, db_session):
    cli.invite("new@example.com", 30)

    row = _row(db_session, "new@example.com")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert expires > datetime.now(timezone.utc) + timedelta(days=29)


def test_reinvite_expired_invite_without_expiry_clears_expiry(cli, db_session):
    cli.invite("tester@example.com", 30)
    row = _row(db_session, "tester@example.com")
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    cli.invite("tester@example.com", None)

    row = _row(db_session, "tester@example.com")
    assert row.status == "invited"
    assert row.expires_at is None


def test_reinvite_accepted_tester_stays_accepted(cli, db_session):
    accepted_at = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.add(
        BetaInvite(email="tester@example.com", status="accepted", accepted_at=accepted_at)
    )
    db_session.commit()

    cli.invite("tester@example.com", None)

    row = _row(db_session, "tester@example.com")
    assert row.status == "accepted"
    assert row.accepted_at is not None


def test_reinvite_clears_revocation(cli, db_session):
    db_session.add(
        BetaInvite(
            email="tester@example.com",
            status="revoked",
            revoked_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    cli.invite("tester@example.com", None)

    row = _row(db_session, "tester@example.com")
    assert row.status == "invited"
    assert row.revoked_at is None
    assert row.expires_at is None


def test_cli_rejects_no_expiry_with_expires_days(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["manage_beta.py", "invite", "a@example.com", "--no-expiry", "--expires-days", "5"],
    )
    with pytest.raises(SystemExit):
        manage_beta.main()


def test_cli_no_expiry_flag_passes_none(monkeypatch):
    calls = []
    monkeypatch.setattr(manage_beta, "invite", lambda email, days: calls.append((email, days)))
    monkeypatch.setattr(
        "sys.argv", ["manage_beta.py", "invite", "A@Example.com", "--no-expiry"]
    )

    manage_beta.main()

    assert calls == [("a@example.com", None)]
