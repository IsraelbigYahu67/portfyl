from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from sqlalchemy import select
from sqlalchemy.orm import Session

from entitlements import EntitlementDenied, reserve_usage
from models import UsageCounter, UsageReservation


PERIOD_START = datetime(2026, 10, 1, tzinfo=timezone.utc)
PERIOD_END = PERIOD_START + timedelta(days=31)


def _concurrent_reserve(postgres_engine, workspace_id, barrier, key):
    with Session(postgres_engine) as db:
        barrier.wait()
        try:
            reservation = reserve_usage(
                db,
                workspace_id=workspace_id,
                metric="concurrency_test",
                idempotency_key=key,
                limit=1,
                period_start=PERIOD_START,
                period_end=PERIOD_END,
            )
            db.commit()
            return ("ok", str(reservation.public_id))
        except EntitlementDenied:
            db.rollback()
            return ("quota", None)


def test_concurrent_final_allowance_cannot_exceed_limit(postgres_engine, matrix_tenants):
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda key: _concurrent_reserve(
                postgres_engine, matrix_tenants.alice.workspace_id, barrier, key
            ),
            ("request-a", "request-b"),
        ))
    assert sorted(status for status, _ in results) == ["ok", "quota"]
    with Session(postgres_engine) as db:
        counter = db.scalar(select(UsageCounter).where(
            UsageCounter.workspace_id == matrix_tenants.alice.workspace_id,
            UsageCounter.metric == "concurrency_test",
            UsageCounter.period_start == PERIOD_START,
        ))
        assert counter.used == 1


def test_concurrent_idempotent_retry_is_charged_once(postgres_engine, matrix_tenants):
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _index: _concurrent_reserve(
                postgres_engine,
                matrix_tenants.alice.workspace_id,
                barrier,
                "same-request",
            ),
            range(2),
        ))
    assert [status for status, _ in results] == ["ok", "ok"]
    assert results[0][1] == results[1][1]
    with Session(postgres_engine) as db:
        assert db.scalar(select(UsageCounter.used).where(
            UsageCounter.workspace_id == matrix_tenants.alice.workspace_id,
            UsageCounter.metric == "concurrency_test",
            UsageCounter.period_start == PERIOD_START,
        )) == 1
        assert len(db.scalars(select(UsageReservation).where(
            UsageReservation.workspace_id == matrix_tenants.alice.workspace_id,
            UsageReservation.metric == "concurrency_test",
            UsageReservation.idempotency_key == "same-request",
        )).all()) == 1
