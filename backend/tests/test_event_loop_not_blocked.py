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

import ast
import importlib
import inspect
import pkgutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
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


# ---------------------------------------------------------------------------
# Endpoints. An ``async def`` endpoint runs on the event loop, so every
# synchronous query it makes freezes the instance exactly like the plan check
# did. Endpoints that touch the database are plain ``def``; async helpers they
# share with the job passes run via private_loop.run_on_private_loop.
# ---------------------------------------------------------------------------

BACKEND = Path(__file__).resolve().parents[1]

# The only async endpoints, each proven not to touch the database: none of
# them is handed a session or a value loaded through one (checked below), and
# none opens a session itself. A new async endpoint has to be added here.
ASYNC_ENDPOINTS_WITHOUT_DB = {
    # Alpha Vantage REST call only; its route-level plan check is a sync
    # dependency that runs in the threadpool.
    "routers.market.get_politician_trades",
}

# Async helpers that receive a Session. Each interleaves database work with
# awaited network calls and must only ever run on a worker thread's private
# loop (run_on_private_loop, or a job pass driven by one), never directly
# from an async endpoint.
ASYNC_HELPERS_RUN_OFF_LOOP = {
    "jobs._advance_until_blocked",
    "jobs.account_deletion_cleanup_pass",
    "jobs.alert_check_all_workspaces",
    "jobs.autosync_all_workspaces",
    "jobs.autosync_tick",
    "jobs.broker_autosync_pass",
    "jobs.broker_backfill_all_workspaces",
    "jobs.broker_backfill_pass",
    "jobs.dividend_exdate_pass",
    "jobs.dividend_notify_all_workspaces",
    "jobs.rate_limit_cleanup_pass",
    "main._dividend_pass",  # a local poller pass, driven by main._run_periodic_pass
    # Startup hook: its one schema-head query finishes before the server
    # accepts its first request, so nothing can be waiting behind it.
    "main._start_background_pollers",
    "routers.alerts.run_check",
    "routers.discord.send_discord_notification",
    "routers.ibkr._run_ibkr_sync",
}


def _router_modules():
    import routers

    for info in pkgutil.iter_modules(routers.__path__):
        yield importlib.import_module(f"routers.{info.name}")


def _all_api_routes():
    """Every route of the app plus every router module, so routers mounted in
    only one edition (internal_jobs in cloud, local_features in local) are
    covered whichever edition this test process imported main.py under."""
    import main

    seen = set()
    sources = [main.app.routes]
    sources += [module.router.routes for module in _router_modules() if hasattr(module, "router")]
    for routes in sources:
        for route in _api_routes(routes):
            if id(route) not in seen:
                seen.add(id(route))
                yield route


def _endpoint_name(endpoint) -> str:
    return f"{endpoint.__module__}.{endpoint.__qualname__}"


def _db_backed_parameters(route) -> list[str]:
    """Endpoint parameters filled from the session or from something loaded
    through it (a Portfolio, a RequestContext...). Route-level
    ``dependencies=[...]`` have no name and hand the endpoint nothing."""
    return [
        sub.name
        for sub in route.dependant.dependencies
        if sub.name is not None and (sub.call is get_db or _uses_db(sub))
    ]


def test_endpoints_that_take_a_session_are_sync():
    offenders = sorted(
        _endpoint_name(route.endpoint)
        for route in _all_api_routes()
        if inspect.iscoroutinefunction(route.endpoint) and _db_backed_parameters(route)
    )
    assert not offenders, offenders


def test_every_async_endpoint_is_proven_database_free():
    routes = list(_all_api_routes())
    assert any(route.path.endswith("/alerts/check") for route in routes)
    assert any(route.path.endswith("/jobs/autosync") for route in routes)

    async_endpoints = {
        _endpoint_name(route.endpoint): route
        for route in routes
        if inspect.iscoroutinefunction(route.endpoint)
    }
    assert set(async_endpoints) <= ASYNC_ENDPOINTS_WITHOUT_DB, (
        "async endpoints not proven database-free (make them plain def): "
        f"{sorted(set(async_endpoints) - ASYNC_ENDPOINTS_WITHOUT_DB)}"
    )
    for name, route in async_endpoints.items():
        assert not _db_backed_parameters(route), name
        source = inspect.getsource(inspect.unwrap(route.endpoint))
        for marker in ("SessionLocal", "get_db", "Session", "run_on_private_loop"):
            assert marker not in source, f"{name} references {marker}"


def _async_functions_touching_a_session():
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND)
        if relative.parts[0] in {"tests", "alembic", ".venv", "venv"}:
            continue
        module = ".".join(relative.with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            takes_session = any(
                arg.arg == "db"
                or (arg.annotation is not None and "Session" in ast.unparse(arg.annotation))
                for arg in args
            )
            if takes_session or "SessionLocal" in ast.unparse(node):
                yield f"{module}.{node.name}"


def test_async_helpers_that_touch_the_database_are_known_off_loop():
    found = set(_async_functions_touching_a_session())
    assert "routers.alerts.run_check" in found, "the scan is broken"
    unexpected = found - ASYNC_HELPERS_RUN_OFF_LOOP
    assert not unexpected, (
        "new async function receives a Session; make it sync, or make sure it "
        f"only runs via private_loop.run_on_private_loop and list it here: {sorted(unexpected)}"
    )
    assert not ASYNC_HELPERS_RUN_OFF_LOOP - found, "stale allowlist entries"


def test_slow_database_work_in_an_endpoint_does_not_freeze_other_requests(monkeypatch):
    """POST /alerts/check used to be ``async def`` and ran the alert queries
    on the event loop. Now its database work runs on a worker thread."""
    import routers.alerts as alerts_router
    from routers.portfolios import require_portfolio

    started = threading.Event()

    async def slow_run_check(*_args, **_kwargs):
        started.set()
        time.sleep(SLOW_DB_SECONDS)  # a blocking query / pool checkout
        return []

    monkeypatch.setattr(alerts_router, "run_check", slow_run_check)
    monkeypatch.setattr(entitlements, "get_workspace_setting", lambda *_: PlanTier.PRO.value)

    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.include_router(alerts_router.router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(in_transaction=lambda: False)
    app.dependency_overrides[get_request_context] = lambda: SimpleNamespace(
        workspace=SimpleNamespace(id="workspace")
    )
    app.dependency_overrides[require_portfolio] = lambda: SimpleNamespace(
        id=1, workspace_id="workspace"
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with TestClient(app) as client:
        check_result = {}
        worker = threading.Thread(
            target=lambda: check_result.setdefault("response", client.post("/alerts/check"))
        )
        worker.start()
        assert started.wait(5)

        t0 = time.monotonic()
        assert client.get("/ping").status_code == 200
        ping_seconds = time.monotonic() - t0

        worker.join(10)

    response = check_result["response"]
    assert response.status_code == 200, response.text
    assert response.json() == {"checked": True, "fired": []}
    assert ping_seconds < SLOW_DB_SECONDS / 3, (
        f"/ping waited {ping_seconds:.2f}s behind a slow alert check: "
        "an endpoint is blocking the event loop"
    )


def test_private_loop_refuses_to_run_on_an_event_loop():
    import asyncio

    from private_loop import run_on_private_loop

    created = []

    async def noop():
        return None

    def make():
        created.append(noop())
        return created[-1]

    async def caller():
        run_on_private_loop(make)

    try:
        with pytest.raises(RuntimeError):
            asyncio.run(caller())
    finally:
        for coro in created:
            coro.close()


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
