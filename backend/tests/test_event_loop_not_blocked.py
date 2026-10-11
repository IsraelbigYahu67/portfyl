"""A dependency that waits on the database must never block the event loop.

In production a dashboard burst exhausted the 5 + 2 connection pool. The
plan check (`entitlements.require_capability`) was an ``async def`` that ran
a synchronous query, so its wait for a free pooled connection (up to the 30s
pool timeout) ran on the event loop itself. The whole Cloud Run instance
froze: even /api/auth/me and /api/portfolios took 40-90s, and request
teardowns that would have returned connections to the pool could not run
until the wait timed out, so several requests failed with "QueuePool limit
of size 5 overflow 2 reached". Sync dependencies run in the threadpool, where
a slow database wait only delays the request that made it.
"""

from __future__ import annotations

import inspect
import threading
import time
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import entitlements
from app_settings import set_workspace_setting
from database import get_db
from edition import Edition
from entitlements import PRIVATE_TEST_PLAN_SETTING_KEY, require_capability
from plans import PlanTier
from tenancy import get_request_context

SLOW_DB_SECONDS = 1.5


def test_slow_plan_check_does_not_freeze_other_requests(monkeypatch):
    started = threading.Event()

    def slow_setting(_db, _workspace_id, _key):
        started.set()
        time.sleep(SLOW_DB_SECONDS)  # stands in for a blocked pool checkout
        return PlanTier.PRO.value

    monkeypatch.setattr(entitlements, "get_workspace_setting", slow_setting)

    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(in_transaction=lambda: False)
    app.dependency_overrides[get_request_context] = lambda: SimpleNamespace(
        workspace=SimpleNamespace(id="workspace")
    )

    @app.get("/gated", dependencies=[Depends(require_capability("portfolio_analytics"))])
    def gated():
        return {"ok": True}

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with TestClient(app) as client:
        gated_result = {}
        worker = threading.Thread(
            target=lambda: gated_result.setdefault("status", client.get("/gated").status_code)
        )
        worker.start()
        assert started.wait(5)

        t0 = time.monotonic()
        assert client.get("/ping").status_code == 200
        ping_seconds = time.monotonic() - t0

        worker.join(10)

    assert gated_result["status"] == 200
    assert ping_seconds < SLOW_DB_SECONDS / 3, (
        f"/ping waited {ping_seconds:.2f}s behind a slow plan check: "
        "a dependency is blocking the event loop"
    )


def test_database_dependencies_are_not_coroutines():
    for factory, args in [
        (entitlements.require_capability, ("portfolio_analytics",)),
        (entitlements.require_capacity, ("portfolios", object())),
        (entitlements.require_writable_resource, ("portfolios", object(), "id")),
        (entitlements.require_broker_capacity, ("trading212",)),
        (entitlements.require_writable_broker, ("trading212",)),
    ]:
        dependency = factory(*args)
        assert not inspect.iscoroutinefunction(dependency), factory.__name__


def _uses_db(dependant) -> bool:
    return any(sub.call is get_db or _uses_db(sub) for sub in dependant.dependencies)


def _api_routes(routes):
    from fastapi.routing import APIRoute

    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        included = getattr(route, "original_router", None)  # an include_router()
        if included is not None:
            yield from _api_routes(included.routes)


def test_no_async_dependency_in_the_app_touches_the_database():
    import main

    routes = list(_api_routes(main.app.routes))
    assert any(route.path.endswith("/risk-metrics") for route in routes)

    offenders = set()

    def walk(dependant, path):
        for sub in dependant.dependencies:
            if inspect.iscoroutinefunction(sub.call) and _uses_db(sub):
                offenders.add(f"{path}: {sub.call.__qualname__}")
            walk(sub, path)

    for route in routes:
        walk(route.dependant, route.path)

    assert not offenders, sorted(offenders)


def test_plan_check_hands_its_connection_back(db_session, test_workspace):
    """The endpoint may wait on Yahoo next; the plan check's read must not pin
    a pooled connection meanwhile (see database.release_connection)."""
    set_workspace_setting(
        db_session, test_workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, PlanTier.PRO.value
    )
    db_session.commit()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(portfyl_edition=Edition.CLOUD)))
    context = SimpleNamespace(workspace=test_workspace)

    result = require_capability("portfolio_analytics")(request, context, db_session)

    assert result.plan is PlanTier.PRO
    assert not db_session.in_transaction()
