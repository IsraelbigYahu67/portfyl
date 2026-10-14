"""Workspace lock scope and entitlement bypasses (review findings N8, N10; decision R3).

The workspace row lock (the one `acquire_workspace_ledger_lock` takes) must be
held only around the writing transaction, never across a Yahoo / Trading 212 /
KMS call. Limits are still enforced authoritatively under that lock, so two
concurrent creates at limit-1 let exactly one through.

Handlers that wait on the network here wait on a `Barrier` inside the mocked
call: the test only passes if both requests get there together, i.e. neither
holds the lock (or the other would never arrive and the barrier would break).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import main
import market_data
from app_settings import set_workspace_setting
from edition import Edition
from entitlements import (
    PRIVATE_TEST_PLAN_SETTING_KEY,
    EntitlementDenied,
    entitlement_denied_handler,
)
from models import (
    BrokerConnection,
    CashInterestRate,
    Portfolio,
    PriceAlert,
    Transaction,
    Watchlist,
    WatchlistItem,
)

JSON = {"content-type": "application/json"}
BARRIER_TIMEOUT = 20


# --- fixtures and helpers ----------------------------------------------------

@pytest.fixture
def cloud(matrix_client, matrix_tenants, postgres_engine, monkeypatch):
    """Alice's client against the cloud edition, on the Free plan."""
    monkeypatch.setenv("PORTFYL_EDITION", "cloud")
    app = matrix_client.app
    app.state.portfyl_edition = Edition.CLOUD
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.add_exception_handler(
        RequestValidationError, main.request_validation_error_handler
    )
    app.middleware_stack = None  # rebuild so the handlers above are seen
    return SimpleNamespace(
        client=matrix_client,
        tenants=matrix_tenants,
        engine=postgres_engine,
        workspace_id=matrix_tenants.alice.workspace_id,
        portfolio_id=matrix_tenants.alice.portfolio_id,
        portfolio_public_id=matrix_tenants.alice.portfolio_public_id,
        ids=matrix_tenants.ids,
    )


def set_plan(cloud, tier: str) -> None:
    with Session(cloud.engine) as db:
        set_workspace_setting(db, cloud.workspace_id, PRIVATE_TEST_PLAN_SETTING_KEY, tier)
        db.commit()


def workspace_lock_free(engine, workspace_id) -> bool:
    """Can another connection lock the workspace row right now?"""
    with engine.connect() as connection:
        try:
            connection.execute(
                text("SELECT id FROM workspaces WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": workspace_id},
            )
            return True
        except DBAPIError:
            return False
        finally:
            connection.rollback()


def idle_in_transaction(engine) -> int:
    with engine.connect() as connection:
        return connection.scalar(text(
            "SELECT count(*) FROM pg_stat_activity"
            " WHERE datname = current_database()"
            " AND state LIKE 'idle in transaction%'"
            " AND pid <> pg_backend_pid()"
        ))


class Probe:
    """Records whether the workspace lock and a pooled connection were held."""

    def __init__(self, cloud):
        self.cloud = cloud
        self.samples: list[tuple[bool, int]] = []

    def __call__(self) -> None:
        self.samples.append((
            workspace_lock_free(self.cloud.engine, self.cloud.workspace_id),
            idle_in_transaction(self.cloud.engine),
        ))

    def assert_clean(self, *, at_least: int = 1) -> None:
        assert len(self.samples) >= at_least, self.samples
        assert all(free for free, _ in self.samples), "workspace row was locked"
        assert all(idle == 0 for _, idle in self.samples), "a connection was held open"


def count(engine, model, workspace_id) -> int:
    with Session(engine) as db:
        return db.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
        )


def fill_transactions(cloud, total: int) -> None:
    """Top Alice's workspace up to `total` ledger rows."""
    missing = total - count(cloud.engine, Transaction, cloud.workspace_id)
    with Session(cloud.engine) as db:
        db.add_all(
            Transaction(
                workspace_id=cloud.workspace_id, portfolio_id=cloud.portfolio_id,
                ticker=None, name=None, type="deposit", shares=0.0, price=0.0,
                amount=1.0, currency="USD", date=date(2024, 2, 1), source="manual",
            )
            for _ in range(missing)
        )
        db.commit()


def run_pair(first, second):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(first), pool.submit(second)]
        return [future.result() for future in futures]


TRANSACTION = {
    "ticker": "AAPL", "type": "buy", "shares": 1, "price": 10.0,
    "currency": "USD", "date": "2026-01-02",
}


def patch_transaction_network(monkeypatch, hook):
    def get_info(ticker, *args, **kwargs):
        hook()
        return {"shortName": "Apple"}

    monkeypatch.setattr(market_data, "get_info", get_info)
    monkeypatch.setattr("routers.portfolio.fetch_fx_to_czk", lambda currency, when: 23.0)


# --- the lock is not held across network calls (N8) ---------------------------

def test_create_transaction_holds_no_lock_while_fetching_market_data(cloud, monkeypatch):
    probe = Probe(cloud)
    patch_transaction_network(monkeypatch, probe)

    response = cloud.client.post("/api/portfolio/transactions", json=TRANSACTION)

    assert response.status_code == 200, response.text
    probe.assert_clean()


def test_add_watchlist_item_holds_no_lock_while_fetching_the_quote(cloud, monkeypatch):
    probe = Probe(cloud)

    def quote(symbol):
        probe()
        return {"symbol": symbol}

    monkeypatch.setattr("routers.watchlists._quote", quote)

    response = cloud.client.post(
        f"/api/watchlists/{cloud.ids['alice_watchlist']}/items", json={"ticker": "ko"}
    )

    assert response.status_code == 200, response.text
    probe.assert_clean()


def test_trading212_connect_holds_no_lock_during_network_calls(cloud, monkeypatch):
    set_plan(cloud, "investor")
    probe = Probe(cloud)

    def get(*args, **kwargs):
        probe()
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def summary(*args, **kwargs):
        probe()
        return {"id": "acct-1"}

    monkeypatch.setattr("routers.broker.httpx.get", get)
    monkeypatch.setattr("routers.broker._fetch_account_summary", summary)
    monkeypatch.setattr(
        "routers.broker._summary_account_fingerprint",
        lambda *args, **kwargs: "alice-account-fingerprint",
    )

    response = cloud.client.post(
        "/api/broker/trading212/connect",
        json={"api_key": "new-key-1234567890", "api_secret": "secret"},
    )

    assert response.status_code == 200, response.text
    probe.assert_clean(at_least=2)


def test_trading212_connect_rechecks_the_account_binding_under_the_lock(cloud, monkeypatch):
    """The portfolio is bound to another account while Trading 212 is being
    called: the fingerprint binding under the lock must see it."""
    set_plan(cloud, "investor")

    def summary(*args, **kwargs):
        with Session(cloud.engine) as db:
            db.execute(
                text("UPDATE portfolios SET t212_account_fingerprint = 'other' WHERE id = :id"),
                {"id": cloud.portfolio_id},
            )
            db.commit()
        return {"id": "acct-1"}

    monkeypatch.setattr(
        "routers.broker.httpx.get",
        lambda *a, **k: SimpleNamespace(status_code=200, raise_for_status=lambda: None),
    )
    monkeypatch.setattr("routers.broker._fetch_account_summary", summary)
    monkeypatch.setattr(
        "routers.broker._summary_account_fingerprint",
        lambda *args, **kwargs: "alice-account-fingerprint",
    )

    response = cloud.client.post(
        "/api/broker/trading212/connect",
        json={"api_key": "new-key-1234567890", "api_secret": "secret"},
    )

    assert response.status_code == 409, response.text


def test_ibkr_connect_holds_no_lock_during_the_flex_call(cloud, monkeypatch):
    set_plan(cloud, "investor")
    probe = Probe(cloud)
    monkeypatch.setattr("routers.ibkr.run_on_private_loop", lambda *a, **k: probe())

    response = cloud.client.post(
        "/api/broker/ibkr/connect", json={"flex_token": "token", "query_id": "query"}
    )

    assert response.status_code == 200, response.text
    probe.assert_clean()


def test_polymarket_connect_holds_no_lock_during_the_data_api_call(cloud, monkeypatch):
    set_plan(cloud, "pro")
    probe = Probe(cloud)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *args, **kwargs):
            probe()
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr("routers.polymarket.httpx.Client", FakeClient)

    response = cloud.client.post(
        "/api/broker/polymarket/connect", json={"address": "0x" + "a" * 40}
    )

    assert response.status_code == 200, response.text
    probe.assert_clean()


# --- two concurrent creates at limit-1: exactly one passes --------------------

def test_concurrent_transactions_at_limit_minus_one_admit_exactly_one(cloud, monkeypatch):
    fill_transactions(cloud, 249)  # Free: 250
    barrier = Barrier(2, timeout=BARRIER_TIMEOUT)
    patch_transaction_network(monkeypatch, barrier.wait)

    responses = run_pair(
        lambda: cloud.client.post("/api/portfolio/transactions", json=TRANSACTION),
        lambda: cloud.client.post("/api/portfolio/transactions", json=TRANSACTION),
    )

    assert sorted(r.status_code for r in responses) == [200, 403], [r.text for r in responses]
    denied = next(r for r in responses if r.status_code == 403)
    assert denied.json()["code"] == "quota_exceeded"
    assert denied.json()["resource"] == "transactions"
    assert count(cloud.engine, Transaction, cloud.workspace_id) == 250


def test_concurrent_watchlist_items_at_limit_minus_one_admit_exactly_one(cloud, monkeypatch):
    with Session(cloud.engine) as db:  # Free: 15 symbols, 1 already there
        watchlist = db.scalar(select(Watchlist).where(Watchlist.workspace_id == cloud.workspace_id))
        db.add_all(
            WatchlistItem(workspace_id=cloud.workspace_id, watchlist_id=watchlist.id, ticker=f"T{i}")
            for i in range(13)
        )
        db.commit()
    barrier = Barrier(2, timeout=BARRIER_TIMEOUT)

    def quote(symbol):
        barrier.wait()
        return {"symbol": symbol}

    monkeypatch.setattr("routers.watchlists._quote", quote)
    url = f"/api/watchlists/{cloud.ids['alice_watchlist']}/items"

    responses = run_pair(
        lambda: cloud.client.post(url, json={"ticker": "KO"}),
        lambda: cloud.client.post(url, json={"ticker": "PEP"}),
    )

    assert sorted(r.status_code for r in responses) == [200, 403], [r.text for r in responses]
    assert count(cloud.engine, WatchlistItem, cloud.workspace_id) == 15


def test_concurrent_alerts_at_limit_minus_one_admit_exactly_one(cloud, monkeypatch):
    import routers.alerts as alerts_router

    with Session(cloud.engine) as db:  # Free: 3 alerts, 1 already there
        db.add(PriceAlert(
            workspace_id=cloud.workspace_id, portfolio_id=cloud.portfolio_id,
            ticker="MSFT", direction="above", target_price=500.0,
            enabled=True, status="active",
        ))
        db.commit()
    barrier = Barrier(2, timeout=BARRIER_TIMEOUT)
    real = alerts_router.enforce_capacity_locked

    def gated(*args, **kwargs):
        barrier.wait()  # both passed the lock-free check; now race for the lock
        return real(*args, **kwargs)

    monkeypatch.setattr(alerts_router, "enforce_capacity_locked", gated)
    body = {"ticker": "NVDA", "direction": "above", "target_price": 900.0}

    responses = run_pair(
        lambda: cloud.client.post("/api/alerts", json=body),
        lambda: cloud.client.post("/api/alerts", json=body),
    )

    assert sorted(r.status_code for r in responses) == [200, 403], [r.text for r in responses]
    assert count(cloud.engine, PriceAlert, cloud.workspace_id) == 3


def test_concurrent_broker_connects_at_limit_minus_one_admit_exactly_one(cloud, monkeypatch):
    set_plan(cloud, "investor")  # two broker connections
    with Session(cloud.engine) as db:
        db.query(BrokerConnection).filter(
            BrokerConnection.workspace_id == cloud.workspace_id,
            BrokerConnection.broker.in_(["ibkr", "polymarket"]),
        ).delete(synchronize_session=False)
        second = Portfolio(workspace_id=cloud.workspace_id, name="Second", is_default=False)
        db.add(second)
        db.commit()
        second_public_id = second.public_id
    barrier = Barrier(2, timeout=BARRIER_TIMEOUT)
    monkeypatch.setattr("routers.ibkr.run_on_private_loop", lambda *a, **k: barrier.wait())
    body = {"flex_token": "token", "query_id": "query"}

    responses = run_pair(
        lambda: cloud.client.post(
            f"/api/broker/ibkr/connect?portfolio_id={cloud.portfolio_public_id}", json=body
        ),
        lambda: cloud.client.post(
            f"/api/broker/ibkr/connect?portfolio_id={second_public_id}", json=body
        ),
    )

    assert sorted(r.status_code for r in responses) == [200, 403], [r.text for r in responses]
    assert count(cloud.engine, BrokerConnection, cloud.workspace_id) == 2


# --- bypasses (N10) -----------------------------------------------------------

def add_overflow_watchlist(cloud) -> str:
    with Session(cloud.engine) as db:
        extra = Watchlist(
            workspace_id=cloud.workspace_id, name="Overflow",
            created_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.add(extra)
        db.commit()
        return str(extra.public_id)


def uuid_spellings(value: str) -> list[str]:
    return [value, value.upper(), value.replace("-", ""), value.replace("-", "").upper()]


def test_overflow_watchlist_stays_read_only_in_every_uuid_spelling(cloud):
    overflow = add_overflow_watchlist(cloud)  # Free: one writable watchlist

    for spelling in uuid_spellings(overflow):
        patched = cloud.client.patch(f"/api/watchlists/{spelling}", json={"name": "hacked"})
        added = cloud.client.post(f"/api/watchlists/{spelling}/items", json={"ticker": "KO"})
        assert patched.status_code == 403, spelling
        assert patched.json()["code"] == "resource_read_only", spelling
        assert added.status_code == 403, spelling
        assert added.json()["code"] == "resource_read_only", spelling

    with Session(cloud.engine) as db:
        assert db.scalar(select(Watchlist.name).where(Watchlist.public_id == overflow)) == "Overflow"
    writable = cloud.client.patch(
        f"/api/watchlists/{cloud.ids['alice_watchlist'].upper()}", json={"name": "Renamed"}
    )
    assert writable.status_code == 200, writable.text


def test_malformed_resource_id_is_not_found(cloud):
    add_overflow_watchlist(cloud)

    response = cloud.client.patch("/api/watchlists/not-a-uuid", json={"name": "x"})

    assert response.status_code == 404


def test_broker_sync_without_portfolio_id_checks_the_default_portfolio(cloud):
    set_plan(cloud, "investor")  # two broker connections; Alice already has three
    with Session(cloud.engine) as db:
        db.execute(
            text("UPDATE portfolios SET is_default = false WHERE id = :id"),
            {"id": cloud.portfolio_id},
        )
        db.commit()
        newest = Portfolio(workspace_id=cloud.workspace_id, name="Newest", is_default=True)
        db.add(newest)
        db.commit()
        db.add(BrokerConnection(
            workspace_id=cloud.workspace_id, portfolio_id=newest.id, broker="ibkr",
            api_key="token", api_secret="query",
            created_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
        db.commit()

    response = cloud.client.post("/api/broker/ibkr/sync")  # no portfolio_id

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "resource_read_only"


def test_cash_entries_count_against_the_transaction_limit(cloud, monkeypatch):
    monkeypatch.setattr("routers.cash.fetch_fx_to_czk", lambda currency, when: 23.0)
    fill_transactions(cloud, 249)  # Free: 250
    body = {"type": "deposit", "amount": 10, "currency": "USD", "date": "2026-01-02"}

    last_allowed = cloud.client.post("/api/cash", json=body)
    over_limit = cloud.client.post("/api/cash", json=body)

    assert last_allowed.status_code == 200, last_allowed.text
    assert over_limit.status_code == 403, over_limit.text
    assert over_limit.json()["code"] == "quota_exceeded"
    assert over_limit.json()["resource"] == "transactions"
    assert count(cloud.engine, Transaction, cloud.workspace_id) == 250


# --- non-finite numbers (R3) ---------------------------------------------------

def test_non_finite_json_literals_are_422_and_nothing_is_saved(cloud, monkeypatch):
    monkeypatch.setattr("routers.cash.fetch_fx_to_czk", lambda currency, when: 23.0)
    before = {
        model: count(cloud.engine, model, cloud.workspace_id)
        for model in (Transaction, PriceAlert, CashInterestRate)
    }
    cash = '{"type": "deposit", "amount": Infinity, "currency": "USD", "date": "2026-01-02"}'
    rates = '{"rates": [{"currency": "USD", "annual_rate": Infinity, "enabled": true}]}'
    alert = '{"ticker": "AAPL", "direction": "above", "target_price": NaN}'
    transaction = (
        '{"ticker": "AAPL", "type": "buy", "shares": NaN, "price": 10,'
        ' "currency": "USD", "date": "2026-01-02"}'
    )

    responses = [
        cloud.client.post("/api/cash", content=cash, headers=JSON),
        cloud.client.put("/api/cash/interest-rates", content=rates, headers=JSON),
        cloud.client.post("/api/alerts", content=alert, headers=JSON),
        cloud.client.post("/api/portfolio/transactions", content=transaction, headers=JSON),
    ]

    assert [r.status_code for r in responses] == [422, 422, 422, 422]
    after = {
        model: count(cloud.engine, model, cloud.workspace_id)
        for model in (Transaction, PriceAlert, CashInterestRate)
    }
    assert after == before
    with Session(cloud.engine) as db:
        assert db.scalar(select(CashInterestRate.annual_rate).where(
            CashInterestRate.workspace_id == cloud.workspace_id,
            CashInterestRate.currency == "USD",
        )) == 0.01
