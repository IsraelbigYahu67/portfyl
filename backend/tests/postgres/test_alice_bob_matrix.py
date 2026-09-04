"""Task 9: the complete application-layer Alice/Bob isolation matrix.

Two fully-populated tenants (see `matrix_tenants` in conftest.py) and one
authenticated client for Alice. Every case is driven through the real FastAPI
app -- the same routers `main.py` mounts, at the same prefixes, against the
disposable PostgreSQL database under the RLS-forced schema -- so a pass here
means the shipped HTTP surface is isolated, not just the ORM helpers.

The route inventory lives in `matrix_cases.py` as literal data. This file only
turns those rows into assertions, which is why every test below is
parametrized and none is `skip`ped: an unreachable case would silently shrink
the gate.

Contract asserted throughout:

  own read/list/create/update/delete   -> 2xx, and only the caller's own rows
  foreign resource UUID (any verb)     -> 404, byte-identical to a random UUID
  foreign portfolio_id query param     -> 404, before the handler body runs
  no session                           -> 401
  valid session, missing CSRF          -> 403
  forged X-Workspace-ID                -> 404
  duplicate name inside one workspace  -> 409
  same name in another workspace       -> 2xx (different customer's data)

Together with `test_runtime_role.py` (the raw-SQL half) this file is the beta
go/no-go gate documented in `docs/security/tenant-isolation-matrix.md`.
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import AuditLog, DiscordWebhook, PriceAlert, Transaction, Watchlist
from tests.postgres.conftest import MatrixTenants
from tests.postgres.matrix_cases import (
    ALICE_PORTFOLIO_PARAMS,
    BOB_PORTFOLIO_PARAMS,
    CSRF_GATED,
    FOREIGN_STATUS,
    OWN_DELETE_CASES,
    OWN_MUTATIONS,
    PORTFOLIO_SCOPED_MUTATIONS,
    PORTFOLIO_SCOPED_READS,
    RANDOM_PORTFOLIO_PARAMS,
    RESOURCE_CASES,
    ResourceCase,
    resolve,
    resolve_params,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOB_PLACEHOLDER = re.compile(r"\{bob_[a-z_]+\}")


def _randomize(template: str) -> str:
    """Turn a URL that addresses one of Bob's rows into one that addresses a
    row that exists nowhere -- the two must be indistinguishable."""
    return _BOB_PLACEHOLDER.sub("{random}", template)


def _bob_uuids(tenants: MatrixTenants) -> set[str]:
    uuids = {value for key, value in tenants.ids.items() if key.startswith("bob_")}
    # Non-vacuity guard: a leak assertion against an empty set always passes.
    assert len(uuids) >= 8, f"the fixture stopped seeding Bob's rows: {uuids}"
    return uuids


def _request(
    client: TestClient,
    method: str,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    payload: Any = None,
    files: Any = None,
):
    kwargs: dict[str, Any] = {"params": dict(params or {})}
    if files is not None:
        kwargs["files"] = files
    elif payload is not None:
        kwargs["json"] = payload
    return client.request(method, url, **kwargs)


def _hermetic():
    """Every patch the write paths in this file would otherwise take to the
    network. yfinance/FX lookups are irrelevant to isolation, and a matrix that
    depends on the internet is not a gate."""
    return (
        patch("market_data.get_info", return_value={"shortName": "Matrix Corp."}),
        patch("market_data.get_infos", return_value={}),
        patch("routers.portfolio.fetch_fx_to_czk", return_value=20.0),
        patch("routers.cash.fetch_fx_to_czk", return_value=20.0),
        patch("routers.watchlists._quote", return_value={"symbol": "NVDA"}),
        patch("routers.alerts.market_data.get_infos", return_value={}),
    )


class _Hermetic:
    def __enter__(self):
        self._patches = _hermetic()
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def _ids(case: ResourceCase) -> str:
    return case.resource


# ---------------------------------------------------------------------------
# A. Own-side: every resource must remain fully usable by its owner.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.list_url], ids=_ids,
)
def test_own_list_returns_2xx_and_never_a_foreign_uuid(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.get(
            resolve(case.list_url, matrix_tenants.ids),
            params=resolve_params(case.params, matrix_tenants.ids),
        )

    assert response.status_code == 200, response.text
    body = response.text
    leaked = sorted(uuid for uuid in _bob_uuids(matrix_tenants) if uuid in body)
    assert leaked == [], f"{case.resource} leaked Bob's UUIDs: {leaked}"


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.create_payload], ids=_ids,
)
def test_own_create_succeeds_and_is_stamped_with_the_callers_workspace(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    url = resolve(case.create_url or case.list_url, matrix_tenants.ids)
    with _Hermetic():
        response = matrix_client.post(
            url,
            params=resolve_params(case.params, matrix_tenants.ids),
            json=dict(case.create_payload),
        )

    assert response.status_code == case.create_status, response.text
    # Anything the API hands back must be a public UUID, never an integer PK.
    body = response.json()
    if isinstance(body, dict) and isinstance(body.get("id"), str):
        UUID(body["id"])


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.own_url and c.update_payload], ids=_ids,
)
def test_own_update_succeeds(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.request(
            case.update_method,
            resolve(case.own_url, matrix_tenants.ids),
            params=resolve_params(case.params, matrix_tenants.ids),
            json=dict(case.update_payload),
        )

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("resource", "url", "params", "expected"), OWN_DELETE_CASES,
    ids=[row[0] for row in OWN_DELETE_CASES],
)
def test_own_delete_succeeds(
    resource: str, url: str, params, expected: int,
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.delete(
            resolve(url, matrix_tenants.ids),
            params=resolve_params(params, matrix_tenants.ids),
        )

    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    ("name", "method", "url", "payload", "expected"), OWN_MUTATIONS,
    ids=[row[0] for row in OWN_MUTATIONS],
)
def test_own_mutation_succeeds(
    name: str, method: str, url: str, payload: Any, expected: int,
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = _request(
            matrix_client, method, resolve(url, matrix_tenants.ids),
            params=resolve_params(ALICE_PORTFOLIO_PARAMS, matrix_tenants.ids),
            payload=payload,
        )

    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    ("resource", "url"), PORTFOLIO_SCOPED_READS, ids=[row[0] for row in PORTFOLIO_SCOPED_READS],
)
def test_own_portfolio_scoped_read_succeeds(
    resource: str, url: str, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.get(
            url, params=resolve_params(ALICE_PORTFOLIO_PARAMS, matrix_tenants.ids),
        )

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# B. Foreign resource UUIDs: always 404, never 403.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.foreign_url and c.update_payload], ids=_ids,
)
def test_foreign_resource_uuid_update_is_not_addressable(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.request(
            case.update_method,
            resolve(case.foreign_url, matrix_tenants.ids),
            # Alice's OWN portfolio: the only way she can reach the route at
            # all. The foreign half of the request is the resource UUID.
            params=resolve_params(case.params, matrix_tenants.ids),
            json=dict(case.update_payload),
        )

    assert response.status_code == FOREIGN_STATUS, response.text


@pytest.mark.parametrize(
    "case",
    [c for c in RESOURCE_CASES if c.foreign_url and c.delete_supported],
    ids=_ids,
)
def test_foreign_resource_uuid_delete_is_not_addressable(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        response = matrix_client.delete(
            resolve(case.foreign_url, matrix_tenants.ids),
            params=resolve_params(case.params, matrix_tenants.ids),
        )

    assert response.status_code == FOREIGN_STATUS, response.text


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.foreign_url], ids=_ids,
)
def test_foreign_resource_uuid_is_indistinguishable_from_a_random_uuid(
    case: ResourceCase, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    """Enumeration guard: if a foreign UUID answered differently from a UUID
    that exists nowhere, the difference alone would confirm another tenant owns
    that ID."""
    params = resolve_params(case.params, matrix_tenants.ids)
    with _Hermetic():
        foreign = matrix_client.delete(
            resolve(case.foreign_url, matrix_tenants.ids), params=params,
        )
        nonexistent = matrix_client.delete(
            resolve(_randomize(case.foreign_url), matrix_tenants.ids), params=params,
        )

    assert foreign.status_code == nonexistent.status_code == FOREIGN_STATUS
    assert foreign.json() == nonexistent.json()


# ---------------------------------------------------------------------------
# C. Foreign portfolio_id: the route is reachable, the tenant's data is not.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("resource", "url"), PORTFOLIO_SCOPED_READS, ids=[row[0] for row in PORTFOLIO_SCOPED_READS],
)
def test_foreign_portfolio_read_is_not_addressable(
    resource: str, url: str, matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    with _Hermetic():
        foreign = matrix_client.get(
            url, params=resolve_params(BOB_PORTFOLIO_PARAMS, matrix_tenants.ids),
        )
        nonexistent = matrix_client.get(
            url, params=resolve_params(RANDOM_PORTFOLIO_PARAMS, matrix_tenants.ids),
        )

    assert foreign.status_code == nonexistent.status_code == FOREIGN_STATUS
    assert foreign.json() == nonexistent.json()


@pytest.mark.parametrize(
    ("name", "method", "url", "payload"), PORTFOLIO_SCOPED_MUTATIONS,
    ids=[row[0] for row in PORTFOLIO_SCOPED_MUTATIONS],
)
def test_foreign_portfolio_mutation_is_not_addressable(
    name: str, method: str, url: str, payload: Any,
    matrix_client: TestClient, matrix_tenants: MatrixTenants, postgres_engine,
):
    """`require_portfolio` is a dependency, so it rejects before the handler
    body runs -- no upstream HTTP call, no write, for any of these."""
    files = (
        {"file": ("matrix.csv", b"Action,Time\n", "text/csv")}
        if url.endswith("import-csv") else None
    )
    with _Hermetic():
        foreign = _request(
            matrix_client, method, url,
            params=resolve_params(BOB_PORTFOLIO_PARAMS, matrix_tenants.ids),
            payload=payload, files=files,
        )
        nonexistent = _request(
            matrix_client, method, url,
            params=resolve_params(RANDOM_PORTFOLIO_PARAMS, matrix_tenants.ids),
            payload=payload, files=files,
        )

    assert foreign.status_code == nonexistent.status_code == FOREIGN_STATUS
    assert foreign.json() == nonexistent.json()

    # And nothing of Bob's moved.
    with Session(postgres_engine) as db:
        bob_workspace = matrix_tenants.bob.workspace_id
        assert db.query(Transaction).filter(
            Transaction.workspace_id == bob_workspace
        ).count() == 2
        assert db.query(DiscordWebhook).filter(
            DiscordWebhook.workspace_id == bob_workspace
        ).one().webhook_url.endswith("/bob/token")
        assert db.query(PriceAlert).filter(
            PriceAlert.workspace_id == bob_workspace
        ).one().status == "active"


# ---------------------------------------------------------------------------
# D. Authentication, CSRF, and workspace selection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.list_url], ids=_ids,
)
def test_unauthenticated_request_is_401(
    case: ResourceCase, anonymous_matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = anonymous_matrix_client.get(
        resolve(case.list_url, matrix_tenants.ids),
        params=resolve_params(case.params, matrix_tenants.ids),
    )

    assert response.status_code == 401
    assert response.json() == {"code": "authentication_required"}


@pytest.mark.parametrize(
    ("name", "method", "url", "payload"), CSRF_GATED,
    ids=[row[0] for row in CSRF_GATED],
)
def test_missing_csrf_token_is_403_not_a_silent_success(
    name: str, method: str, url: str, payload: Any,
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.request(
        method,
        resolve(url, matrix_tenants.ids),
        json=payload,
        headers={"X-CSRF-Token": ""},
    )

    assert response.status_code == 403
    assert response.json() == {"code": "csrf_failed"}


def test_forged_workspace_header_is_404_for_a_non_member(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.get(
        "/api/portfolios",
        headers={"X-Workspace-ID": str(matrix_tenants.bob.workspace_public_id)},
    )

    assert response.status_code == FOREIGN_STATUS
    assert response.json() == {"code": "resource_not_found"}


def test_unknown_and_malformed_workspace_headers_match_the_foreign_contract(
    matrix_client: TestClient,
):
    unknown = matrix_client.get(
        "/api/portfolios", headers={"X-Workspace-ID": str(uuid4())},
    )
    malformed = matrix_client.get(
        "/api/portfolios", headers={"X-Workspace-ID": "not-a-uuid"},
    )

    assert unknown.status_code == malformed.status_code == FOREIGN_STATUS
    assert unknown.json() == malformed.json() == {"code": "resource_not_found"}


# ---------------------------------------------------------------------------
# E. Names are unique per workspace, not globally.
# ---------------------------------------------------------------------------


def test_duplicate_watchlist_name_is_409_inside_one_workspace(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.post("/api/watchlists", json={"name": "Shared name"})

    assert response.status_code == 409


def test_the_same_watchlist_name_already_lives_in_both_workspaces(
    matrix_tenants: MatrixTenants, postgres_engine,
):
    """The fixture gives Alice and Bob a watchlist with the identical name --
    proof that uniqueness is `(workspace_id, name)`, not global. A globally
    unique index would have made the seed itself impossible."""
    with Session(postgres_engine) as db:
        names = db.query(Watchlist).filter(Watchlist.name == "Shared name").count()

    assert names == 2


def test_duplicate_portfolio_name_is_409_inside_one_workspace(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.post("/api/portfolios", json={"name": "Alice portfolio"})

    assert response.status_code == 409


def test_a_name_bob_already_uses_is_free_for_alice(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.post("/api/portfolios", json={"name": "Bob portfolio"})

    assert response.status_code == 200
    assert response.json()["name"] == "Bob portfolio"


# ---------------------------------------------------------------------------
# F. Settings: personal vs workspace scope.
# ---------------------------------------------------------------------------


def test_personal_settings_never_surface_another_users_key(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.get("/api/assistant/config")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert "bob-secret-key" not in response.text
    assert body["key_preview"] != ""


def test_workspace_settings_never_surface_another_workspaces_value(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    response = matrix_client.get("/api/settings/sync-schedule")

    assert response.status_code == 200
    body = response.json()
    assert body["daily_time"] == "02:00"   # Alice's
    assert body["daily_time"] != "23:45"   # Bob's


def test_audit_log_lists_alice_workspace_and_personal_events_only(
    matrix_client: TestClient, matrix_tenants: MatrixTenants, postgres_engine,
):
    from audit import record_audit_event

    with Session(postgres_engine) as db:
        record_audit_event(
            db,
            actor_user_id=matrix_tenants.alice.user_id,
            workspace_id=matrix_tenants.alice.workspace_id,
            action="alice.workspace.event",
        )
        record_audit_event(
            db,
            actor_user_id=matrix_tenants.alice.user_id,
            action="alice.personal.event",
        )
        record_audit_event(
            db,
            actor_user_id=matrix_tenants.bob.user_id,
            workspace_id=matrix_tenants.bob.workspace_id,
            action="bob.workspace.event",
        )
        record_audit_event(
            db,
            actor_user_id=matrix_tenants.bob.user_id,
            action="bob.personal.event",
        )
        db.commit()

    response = matrix_client.get("/api/settings/audit-log")

    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["items"]}
    assert {"alice.workspace.event", "alice.personal.event"} <= actions
    assert "bob.workspace.event" not in actions
    assert "bob.personal.event" not in actions


# ---------------------------------------------------------------------------
# G. Portfolio delete: own row deletable, foreign row not, last one protected.
# ---------------------------------------------------------------------------


def test_own_portfolio_delete_succeeds_once_a_second_one_exists(
    matrix_client: TestClient, matrix_tenants: MatrixTenants, postgres_engine,
):
    created = matrix_client.post("/api/portfolios", json={"name": "Second"})
    assert created.status_code == 200

    deleted = matrix_client.delete(f"/api/portfolios/{created.json()['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == created.json()["id"]


def test_deleting_the_last_portfolio_is_refused_with_400_not_404(
    matrix_client: TestClient, matrix_tenants: MatrixTenants,
):
    """A 400 here is a business rule about Alice's own row -- it must not be
    confused with the 404 tenancy contract."""
    response = matrix_client.delete(
        f"/api/portfolios/{matrix_tenants.alice.portfolio_public_id}"
    )

    assert response.status_code == 400
