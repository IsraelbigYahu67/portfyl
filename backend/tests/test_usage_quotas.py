from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from entitlements import EntitlementDenied, finalize_usage, release_usage, reserve_usage
from models import UsageCounter


START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _reserve(db, workspace_id, key, limit=2):
    return reserve_usage(
        db,
        workspace_id=workspace_id,
        metric="hosted_ai_monthly",
        idempotency_key=key,
        limit=limit,
        period_start=START,
        period_end=START + timedelta(days=30),
    )


def test_usage_reservation_is_idempotent(db_session, test_workspace):
    first = _reserve(db_session, test_workspace.id, "request-1")
    second = _reserve(db_session, test_workspace.id, "request-1")
    assert first is second
    assert second._portfyl_reused is True
    assert db_session.query(UsageCounter).one().used == 1


def test_usage_limit_and_release(db_session, test_workspace):
    first = _reserve(db_session, test_workspace.id, "request-1", limit=1)
    with pytest.raises(EntitlementDenied):
        _reserve(db_session, test_workspace.id, "request-2", limit=1)
    release_usage(db_session, first)
    assert _reserve(db_session, test_workspace.id, "request-2", limit=1).status == "reserved"


def test_finalized_usage_cannot_be_released(db_session, test_workspace):
    reservation = _reserve(db_session, test_workspace.id, "request-1")
    finalize_usage(db_session, reservation)
    release_usage(db_session, reservation)
    assert db_session.query(UsageCounter).one().used == 1
