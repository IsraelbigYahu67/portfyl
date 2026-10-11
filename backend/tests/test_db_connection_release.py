"""Market-data endpoints must not hold a pooled DB connection during network I/O.

Every request's Session keeps its pooled connection from the first query
until the transaction ends (the RLS context is transaction-local, see
database.set_rls_context). Endpoints that then wait on slow Yahoo Finance
calls pinned all of the small pool (5 + 2) under a handful of concurrent
dashboard requests, so even /api/auth/me timed out with "QueuePool limit of
size 5 overflow 2 reached". These tests run each endpoint against a real
QueuePool and record how many connections are checked out whenever
yfinance is called: the answer must always be zero.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import database
import market_data
from database import Base
from models import Portfolio, Workspace
from tests.helpers import TEST_WORKSPACE_ID, make_txn


@pytest.fixture
def pooled(tmp_path):
    """A file-backed SQLite engine with a real QueuePool, like production."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.db'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=2,
    )
    # SQLite stand-in for PostgreSQL's set_config so the auth dependency can
    # run here; real RLS behaviour is covered by tests/postgres.
    event.listen(engine, "connect", lambda conn, _rec: conn.create_function("set_config", 3, lambda key, value, local: value))
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    session.add(Workspace(id=TEST_WORKSPACE_ID, name="Pool test"))
    portfolio = Portfolio(workspace_id=TEST_WORKSPACE_ID, name="Default", is_default=True)
    session.add(portfolio)
    session.flush()
    for txn in [
        make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 1, 15), portfolio_id=portfolio.id),
        make_txn("MSFT", "buy", 5, 350.0, date=date(2024, 2, 1), portfolio_id=portfolio.id),
        make_txn("AAPL", "dividend", 10, 0.5, date=date(2024, 7, 1), portfolio_id=portfolio.id),
    ]:
        session.add(txn)
    session.commit()
    portfolio_id = portfolio.id
    session.close()

    # From here on the session behaves like one handed out by get_db, and the
    # portfolio is loaded the way require_portfolio leaves it: inside an
    # open transaction that already holds a pooled connection.
    session.info[database._REQUEST_SCOPED_KEY] = True
    token = database._request_sessions.set(())
    portfolio = session.get(Portfolio, portfolio_id)
    try:
        yield engine, session, portfolio
    finally:
        database._request_sessions.reset(token)
        session.close()
        engine.dispose()


@pytest.fixture
def network_probe(mock_yfinance, monkeypatch):
    """Wrap the mocked yfinance entry points to record pool usage per call."""
    import yfinance as yf

    seen: list[int] = []
    state = {"engine": None}
    base_ticker = yf.Ticker

    def record():
        seen.append(state["engine"].pool.checkedout())

    class ProbeTicker(base_ticker):
        def __init__(self, symbol):
            record()
            super().__init__(symbol)

    def probe_download(*args, **kwargs):
        record()
        return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", ProbeTicker)
    monkeypatch.setattr(yf, "download", probe_download)
    # Start from cold caches so each endpoint really reaches yfinance.
    monkeypatch.setattr(market_data, "_cache", {})
    return seen, state


def _portfolio_router():
    from routers import portfolio as r
    return r


def _analytics_router():
    from routers import analytics as r
    return r


def _targets_router():
    from routers import allocation_targets as r
    return r


ENDPOINTS = {
    "holdings": lambda db, p: _portfolio_router().get_holdings(include_closed=False, currency="USD", db=db, portfolio=p),
    "summary": lambda db, p: _portfolio_router().get_summary(currency="USD", db=db, portfolio=p),
    "dividends": lambda db, p: _portfolio_router().get_dividends(db=db, portfolio=p),
    "dividends_forecast": lambda db, p: _portfolio_router().get_dividend_forecast(db=db, portfolio=p),
    "performance": lambda db, p: _portfolio_router().get_performance(currency="USD", period="1y", db=db, portfolio=p),
    "earnings": lambda db, p: _portfolio_router().get_earnings(db=db, portfolio=p),
    "movers": lambda db, p: _portfolio_router().get_movers(period="1d", db=db, portfolio=p),
    "heatmap": lambda db, p: _portfolio_router().get_heatmap(period="1d", db=db, portfolio=p),
    "benchmarks": lambda db, p: _portfolio_router().get_benchmarks(benchmarks="sp500", period="1y", db=db, portfolio=p),
    "insider_buys": lambda db, p: _portfolio_router().get_insider_buys(db=db, portfolio=p),
    "risk_metrics": lambda db, p: _analytics_router().risk_metrics(period="1y", benchmark_id=None, db=db, portfolio=p),
    "sector_breakdown": lambda db, p: _analytics_router().sector_breakdown(currency="USD", db=db, portfolio=p),
    "target_drift": lambda db, p: _targets_router().target_drift(currency="USD", db=db, portfolio=p),
}


@pytest.mark.parametrize("name", sorted(ENDPOINTS))
def test_endpoint_releases_its_connection_before_market_data_calls(name, pooled, network_probe):
    engine, session, portfolio = pooled
    seen, state = network_probe
    state["engine"] = engine

    try:
        ENDPOINTS[name](session, portfolio)
    except Exception:
        # Canned market data may make an endpoint bail out late; what matters
        # here is the pool state at each network call made before that.
        pass

    assert seen, f"{name} never reached yfinance, so the probe proved nothing"
    assert max(seen) == 0, f"{name} held {max(seen)} pooled connection(s) during a market-data call"


def test_release_keeps_loaded_objects_readable_without_a_new_connection(pooled):
    engine, session, portfolio = pooled
    database.release_request_connections()

    assert engine.pool.checkedout() == 0
    assert portfolio.name == "Default"
    assert engine.pool.checkedout() == 0, "reading a loaded attribute must not reopen a transaction"
    assert session.info[database._REQUEST_SCOPED_KEY] is True


def test_release_never_commits_a_pending_or_flushed_write(pooled):
    engine, session, portfolio = pooled

    portfolio.name = "Renamed"  # dirty, not flushed
    database.release_request_connections()
    assert engine.pool.checkedout() == 1

    session.flush()  # flushed but not committed
    database.release_request_connections()
    assert engine.pool.checkedout() == 1

    session.rollback()
    assert session.get(Portfolio, portfolio.id).name == "Default"


def test_sessions_outside_a_request_are_left_alone(pooled):
    engine, session, portfolio = pooled
    database.release_request_connections()
    job_session = sessionmaker(bind=engine)()  # e.g. a background job
    try:
        job_session.get(Portfolio, portfolio.id)
        assert engine.pool.checkedout() == 1

        database.release_request_connections()

        assert engine.pool.checkedout() == 1
    finally:
        job_session.close()


def _authenticated_request(engine, session):
    """Seed a user + membership in the pooled DB and return a cookie request."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from starlette.requests import Request

    from auth import SESSION_COOKIE_NAME, create_session
    from models import AuthSession, Membership, User

    user = User(id=uuid4(), firebase_uid=f"pool-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.add(Membership(user_id=user.id, workspace_id=TEST_WORKSPACE_ID, role="owner", status="active"))
    token = create_session(session, user.id).raw_token
    row = session.scalars(__import__("sqlalchemy").select(AuthSession).where(AuthSession.user_id == user.id)).one()
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(hours=1)  # stale: this request will touch it
    session.commit()
    request = Request({"type": "http", "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={token}".encode())]})
    return request, row.id


def test_auth_dependency_commits_its_touch_and_leaves_no_connection_held(pooled):
    from models import AuthSession
    from tenancy import get_request_context

    engine, session, portfolio = pooled
    request, auth_row_id = _authenticated_request(engine, session)

    context = get_request_context(request, db=session, x_workspace_id=None)

    assert engine.pool.checkedout() == 0, "the route must start without a held connection"
    assert context.workspace.id == TEST_WORKSPACE_ID
    with sessionmaker(bind=engine)() as other:
        assert other.get(AuthSession, auth_row_id).last_seen_at is not None


def test_last_seen_moves_at_most_every_few_minutes(db_session, test_user):
    from datetime import timedelta

    from auth import LAST_SEEN_RESOLUTION, create_session, resolve_session

    token = create_session(db_session, test_user.id).raw_token
    db_session.commit()

    row = resolve_session(db_session, token)
    assert row.last_seen_at is not None  # first sighting is recorded
    db_session.commit()

    resolve_session(db_session, token)
    assert not db_session.dirty, "a fresh last-seen must not turn a read into a write"

    row.last_seen_at = row.last_seen_at - LAST_SEEN_RESOLUTION - timedelta(seconds=1)
    db_session.commit()
    resolve_session(db_session, token)
    assert row in db_session.dirty
