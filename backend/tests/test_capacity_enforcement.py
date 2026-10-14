"""Lock-free capacity dependencies, locked authoritative checks, id-bypass fixes (B1)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import entitlements as entitlements_module
from app_settings import set_workspace_setting
from edition import Edition
from entitlements import (
    PRIVATE_TEST_PLAN_SETTING_KEY,
    EntitlementDenied,
    enforce_broker_capacity_locked,
    enforce_capacity_locked,
    require_broker_capacity,
    require_capacity,
    require_writable_broker,
    require_writable_resource,
)
from models import BrokerConnection, Portfolio, Watchlist
from plans import PlanTier
from tenancy import RequestContextError


def _request(path_params: dict | None = None):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(portfyl_edition=Edition.CLOUD)),
        path_params=path_params or {},
        query_params={},
    )


def _plan(db, workspace, tier: PlanTier) -> None:
    set_workspace_setting(db, workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, tier.value)
    db.commit()


def _watchlists(db, workspace, count: int) -> list[Watchlist]:
    rows = [Watchlist(workspace_id=workspace.id, name=f"List {i}") for i in range(count)]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def lock_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        entitlements_module,
        "acquire_workspace_ledger_lock",
        lambda db, workspace_id: calls.append(workspace_id),
    )
    return calls


@pytest.fixture
def cloud_env(monkeypatch):
    monkeypatch.setenv("PORTFYL_EDITION", "cloud")


# --- require_capacity: early check, no lock ----------------------------------

def test_require_capacity_takes_no_lock_and_hands_the_connection_back(
    db_session, test_workspace, lock_calls
):
    db_session.commit()  # the fixture's workspace is only flushed
    context = SimpleNamespace(workspace=test_workspace)

    result = require_capacity("watchlists", Watchlist)(_request(), context, db_session)

    assert result.plan is PlanTier.FREE
    assert lock_calls == []
    assert not db_session.in_transaction()


def test_require_capacity_still_rejects_at_the_limit(db_session, test_workspace, lock_calls):
    _watchlists(db_session, test_workspace, 1)  # Free: one watchlist
    context = SimpleNamespace(workspace=test_workspace)

    with pytest.raises(EntitlementDenied) as exc:
        require_capacity("watchlists", Watchlist)(_request(), context, db_session)

    assert exc.value.code == "quota_exceeded"
    assert lock_calls == []


# --- enforce_capacity_locked: authoritative, takes the lock ------------------

def test_enforce_capacity_locked_takes_the_lock_then_counts(
    db_session, test_workspace, lock_calls, cloud_env
):
    _watchlists(db_session, test_workspace, 1)

    with pytest.raises(EntitlementDenied) as exc:
        enforce_capacity_locked(db_session, test_workspace.id, None, "watchlists", Watchlist)

    assert exc.value.code == "quota_exceeded"
    assert lock_calls == [test_workspace.id]


def test_enforce_capacity_locked_allows_below_the_limit(
    db_session, test_workspace, lock_calls, cloud_env
):
    enforce_capacity_locked(db_session, test_workspace.id, None, "watchlists", Watchlist)

    assert lock_calls == [test_workspace.id]


def test_enforce_capacity_locked_resolves_the_plan_under_the_lock(
    db_session, test_workspace, lock_calls, cloud_env
):
    """A plan changed while the handler waited on the network is honoured."""
    _watchlists(db_session, test_workspace, 1)
    _plan(db_session, test_workspace, PlanTier.INVESTOR)  # 5 watchlists

    enforce_capacity_locked(db_session, test_workspace.id, None, "watchlists", Watchlist)


def test_enforce_capacity_locked_uses_given_entitlements(
    db_session, test_workspace, lock_calls
):
    free = entitlements_module.resolve_entitlements(
        db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id
    )
    _watchlists(db_session, test_workspace, 1)

    with pytest.raises(EntitlementDenied):
        enforce_capacity_locked(db_session, test_workspace.id, free, "watchlists", Watchlist)


# --- require_writable_resource: parsed UUIDs, not strings --------------------

@pytest.mark.parametrize(
    "spelling",
    [str, lambda u: str(u).upper(), lambda u: u.hex, lambda u: u.hex.upper()],
    ids=["canonical", "upper-case", "no-dashes", "upper-case-no-dashes"],
)
def test_overflow_resource_is_read_only_in_every_uuid_spelling(
    db_session, test_workspace, spelling
):
    rows = _watchlists(db_session, test_workspace, 2)  # Free: only the first is writable
    context = SimpleNamespace(workspace=test_workspace)
    dependency = require_writable_resource("watchlists", Watchlist, "watchlist_id")

    dependency(_request({"watchlist_id": spelling(rows[0].public_id)}), context, db_session)
    with pytest.raises(EntitlementDenied) as exc:
        dependency(_request({"watchlist_id": spelling(rows[1].public_id)}), context, db_session)

    assert exc.value.code == "resource_read_only"


def test_writable_resource_rejects_a_malformed_id_as_not_found(db_session, test_workspace):
    _watchlists(db_session, test_workspace, 2)
    context = SimpleNamespace(workspace=test_workspace)

    with pytest.raises(RequestContextError) as exc:
        require_writable_resource("watchlists", Watchlist, "watchlist_id")(
            _request({"watchlist_id": "not-a-uuid"}), context, db_session
        )

    assert exc.value.status_code == 404


# --- broker capacity: the route's own portfolio ------------------------------

def _portfolio(db, workspace, name, *, default=False) -> Portfolio:
    portfolio = Portfolio(workspace_id=workspace.id, name=name, is_default=default)
    db.add(portfolio)
    db.commit()
    return portfolio


def _connection(db, workspace, portfolio, broker) -> BrokerConnection:
    connection = BrokerConnection(
        workspace_id=workspace.id, portfolio_id=portfolio.id, broker=broker,
        api_key="k" * 20, api_secret="s",
    )
    db.add(connection)
    db.commit()
    return connection


def test_writable_broker_checks_the_portfolio_it_is_given(db_session, test_workspace):
    """No `portfolio_id` query is needed: the route's portfolio is passed in."""
    _plan(db_session, test_workspace, PlanTier.INVESTOR)  # two broker connections
    first = _portfolio(db_session, test_workspace, "First", default=True)
    second = _portfolio(db_session, test_workspace, "Second")
    _connection(db_session, test_workspace, first, "trading212")
    _connection(db_session, test_workspace, first, "ibkr")
    _connection(db_session, test_workspace, second, "ibkr")  # third: over the limit
    context = SimpleNamespace(workspace=test_workspace)
    dependency = require_writable_broker("ibkr")

    dependency(_request(), context, first, db_session)
    with pytest.raises(EntitlementDenied) as exc:
        dependency(_request(), context, second, db_session)

    assert exc.value.code == "resource_read_only"


def test_broker_capacity_allows_rotation_but_rejects_a_new_connection_at_the_limit(
    db_session, test_workspace, lock_calls
):
    _plan(db_session, test_workspace, PlanTier.INVESTOR)
    first = _portfolio(db_session, test_workspace, "First", default=True)
    second = _portfolio(db_session, test_workspace, "Second")
    _connection(db_session, test_workspace, first, "trading212")
    _connection(db_session, test_workspace, first, "ibkr")
    context = SimpleNamespace(workspace=test_workspace)
    dependency = require_broker_capacity("ibkr")

    with pytest.raises(EntitlementDenied) as exc:
        dependency(_request(), context, second, db_session)  # a third connection
    dependency(_request(), context, first, db_session)  # rotating its own key

    assert exc.value.code == "quota_exceeded"
    assert lock_calls == []
    assert not db_session.in_transaction()


def test_enforce_broker_capacity_locked_takes_the_lock(
    db_session, test_workspace, lock_calls, cloud_env
):
    _plan(db_session, test_workspace, PlanTier.INVESTOR)
    first = _portfolio(db_session, test_workspace, "First", default=True)
    second = _portfolio(db_session, test_workspace, "Second")
    _connection(db_session, test_workspace, first, "trading212")
    _connection(db_session, test_workspace, first, "ibkr")

    enforce_broker_capacity_locked(db_session, test_workspace.id, None, "ibkr", first)
    with pytest.raises(EntitlementDenied):
        enforce_broker_capacity_locked(db_session, test_workspace.id, None, "ibkr", second)

    assert lock_calls == [test_workspace.id, test_workspace.id]
