"""Standalone due-deletion command contract."""

from __future__ import annotations

import json

import purge_account_deletions as command


class _SessionContext:
    def __init__(self):
        self.session = object()

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def test_cli_emits_machine_readable_summary_and_success_exit(monkeypatch, capsys):
    session_context = _SessionContext()
    identity_admin = object()
    summary = {
        "scanned": 2,
        "purged": 1,
        "not_due": 1,
        "shared": 0,
        "invalid": 0,
        "errors": 0,
    }
    monkeypatch.setattr(command, "SessionLocal", lambda: session_context)
    monkeypatch.setattr(command, "FirebaseIdentityVerifier", lambda: identity_admin)
    monkeypatch.setattr(
        command,
        "purge_due_workspace_deletions",
        lambda db, verifier: summary
        if (db, verifier) == (session_context.session, identity_admin)
        else None,
    )

    exit_code = command.main()

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == summary


def test_cli_returns_failure_when_any_tenant_failed(monkeypatch, capsys):
    summary = {
        "scanned": 1,
        "purged": 0,
        "not_due": 0,
        "shared": 0,
        "invalid": 0,
        "errors": 1,
    }
    monkeypatch.setattr(command, "SessionLocal", _SessionContext)
    monkeypatch.setattr(command, "FirebaseIdentityVerifier", object)
    monkeypatch.setattr(
        command,
        "purge_due_workspace_deletions",
        lambda *_args: summary,
    )

    assert command.main() == 1
    assert json.loads(capsys.readouterr().out) == summary
