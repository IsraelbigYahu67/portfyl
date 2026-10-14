"""Every state-changing /api route must be CSRF-protected.

Protection is the router-level tenancy.csrf_guard added in main.py (plus the
per-route require_csrf that predates it). The auth router is excluded because
it performs its own checks and /auth/session must work without a token.
Routes are inspected in a subprocess per edition, since main.py reads
PORTFYL_EDITION once at import time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Settings the cloud edition insists on at import time (edge_trust, rate_limit).
_CLOUD_IMPORT_ENV = {
    "PORTFYL_EDGE_TOKEN": "csrf-coverage-test-token",
    "RATE_LIMIT_KEY_SECRET": "csrf-coverage-test-secret",
    **{
        f"RATE_LIMIT_{name}_{suffix}": "100" if suffix == "LIMIT" else "60"
        for name in ("GLOBAL", "AUTH_SESSION", "BROKER_SYNC", "ASSISTANT_CHAT")
        for suffix in ("LIMIT", "WINDOW_SECONDS")
    },
}

_INSPECT = r"""
import json
import main
from fastapi.routing import APIRoute
from tenancy import csrf_guard, require_csrf

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTORS = {csrf_guard, require_csrf}


def calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from calls(dep)


def api_routes(routes):
    # Newer FastAPI keeps included routers lazy (_IncludedRouter); each yields
    # per-route contexts that carry the effective path, methods and dependant
    # (router-level dependencies merged in). Older FastAPI flattens to APIRoute.
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "effective_route_contexts"):
            for context in route.effective_route_contexts():
                if getattr(context, "dependant", None) is not None:
                    yield context


checked, unprotected = 0, []
for route in api_routes(main.app.routes):
    methods = route.methods & MUTATING
    if not methods or not route.path.startswith("/api"):
        continue
    if route.path.startswith("/api/auth/"):
        continue
    checked += 1
    if not PROTECTORS.intersection(calls(route.dependant)):
        unprotected.append(f"{sorted(methods)} {route.path}")
print(json.dumps({"checked": checked, "unprotected": unprotected}))
"""


@pytest.mark.parametrize("edition", ["local", "cloud"])
def test_every_mutating_api_route_is_csrf_protected(edition: str):
    env = {**os.environ, "PORTFYL_EDITION": edition, **_CLOUD_IMPORT_ENV}
    result = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(BACKEND_DIR)!r})\n{_INSPECT}"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])

    assert report["checked"] > 20, "route discovery found suspiciously few routes"
    assert report["unprotected"] == []
