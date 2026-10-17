"""eToro connect/status/sync/auto-sync/disconnect, with the Public API faked."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from etoro_client import EtoroAuthError, EtoroRateLimited
from models import BrokerConnection, Transaction
from routers import etoro as etoro_router
from tests.helpers import make_txn

CLOSED = {"positionId": 1, "instrumentId": 1001, "isBuy": True, "leverage": 1, "units": 2.0,
          "openRate": 190.0, "openTimestamp": "2025-01-02T14:30:00Z",
          "closeRate": 200.0, "closeTimestamp": "2025-03-03T15:00:00Z"}
OPEN = {"positionID": 2, "instrumentID": 1001, "isBuy": True, "leverage": 1, "units": 1.5,
        "openRate": 210.0, "openDateTime": "2025-04-01T14:30:00Z"}
INSTRUMENTS = {1001: {"symbol": "AAPL", "exchange": "NASDAQ", "type": "Stocks", "name": "Apple"}}


class FakeClient:
    history = [CLOSED]
    open_positions = [OPEN]
    fail: Exception | None = None
    calls: list = []

    def __init__(self, app_key, user_key, **kw):
        self.app_key = app_key
        self.user_key = user_key

    def positions(self):
        FakeClient.calls.append(("positions", self.user_key))
        if self.user_key == "bad":
            raise EtoroAuthError("bad key")
        if FakeClient.fail:
            raise FakeClient.fail
        return list(FakeClient.open_positions)

    def trade_history(self, min_date):
        FakeClient.calls.append(("trade_history", min_date))
        return list(FakeClient.history)

    def cash_transactions(self, account_id):  # pragma: no cover - must not be called
        raise AssertionError("cash is not mapped yet; the sync must not fetch it")

    def instruments(self, ids):
        return {i: INSTRUMENTS[i] for i in ids if i in INSTRUMENTS}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PORTFYL_ETORO_APP_KEY", "app")
    monkeypatch.setattr(etoro_router, "EtoroClient", FakeClient)
    monkeypatch.setattr("routers.portfolio.bulk_fetch_fx", lambda keys: {})
    FakeClient.history = [CLOSED]
    FakeClient.open_positions = [OPEN]
    FakeClient.fail = None
    FakeClient.calls = []


def _connect(db, portfolio, context=None, key="user-key-123456"):
    return etoro_router.connect(etoro_router.ConnectBody(user_key=key), db=db,
                                portfolio=portfolio, _context=context)


def _conn(db, portfolio):
    return db.query(BrokerConnection).filter(BrokerConnection.portfolio_id == portfolio.id,
                                             BrokerConnection.broker == "etoro").one()


def _sync(db, portfolio):
    return etoro_router.etoro_sync(db, portfolio.workspace_id, portfolio.id)


def test_connect_requires_app_key(monkeypatch, db_session, default_portfolio):
    monkeypatch.delenv("PORTFYL_ETORO_APP_KEY")
    with pytest.raises(HTTPException) as exc:
        _connect(db_session, default_portfolio)
    assert exc.value.status_code == 503


def test_connect_rejects_bad_key(db_session, default_portfolio):
    with pytest.raises(HTTPException) as exc:
        _connect(db_session, default_portfolio, key="bad")
    assert exc.value.status_code == 400
    assert "API Key Management" in exc.value.detail
    assert db_session.query(BrokerConnection).count() == 0


def test_connect_stores_encrypted_key(db_session, default_portfolio, request_context):
    result = _connect(db_session, default_portfolio, request_context)
    conn = _conn(db_session, default_portfolio)
    assert result["connected"] is True and result["id"] == str(conn.public_id)
    assert conn.api_key == "user-key-123456"
    assert b"user-key-123456" not in conn.api_key_ciphertext


def test_reconnect_rotates_key_in_place(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    conn = _conn(db_session, default_portfolio)
    conn.needs_attention, conn.consecutive_failures = True, 3
    db_session.commit()
    _connect(db_session, default_portfolio, key="second-key-654321")
    conn = _conn(db_session, default_portfolio)
    assert conn.api_key == "second-key-654321"
    assert (conn.needs_attention, conn.consecutive_failures) == (False, 0)


def test_status_never_returns_key(db_session, default_portfolio):
    _connect(db_session, default_portfolio, key="secret-user-key")
    status = etoro_router.get_status(db=db_session, portfolio=default_portfolio)
    assert status["connected"] is True and status["configured"] is True
    assert "secret-user-key" not in str(status)


def test_status_reports_missing_configuration(monkeypatch, db_session, default_portfolio):
    monkeypatch.delenv("PORTFYL_ETORO_APP_KEY")
    status = etoro_router.get_status(db=db_session, portfolio=default_portfolio)
    assert status == {"connected": False, "configured": False,
                      "portfolio_id": str(default_portfolio.public_id)}


def test_sync_is_idempotent(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    first = _sync(db_session, default_portfolio)
    second = _sync(db_session, default_portfolio)
    assert first["status"] == "imported" and first["imported"] == 3  # buy+sell, open buy
    assert second["imported"] == 0 and second["already_present"] == 3
    rows = db_session.query(Transaction).filter(Transaction.portfolio_id == default_portfolio.id).all()
    assert sorted((r.type, r.shares) for r in rows) == [("buy", 1.5), ("buy", 2.0), ("sell", 2.0)]
    assert {r.source for r in rows} == {"etoro"}
    assert _conn(db_session, default_portfolio).last_synced_at is not None


def test_first_sync_reads_full_history_then_overlaps_30_days(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    _sync(db_session, default_portfolio)
    synced = _conn(db_session, default_portfolio).last_synced_at
    _sync(db_session, default_portfolio)
    windows = [arg for name, arg in FakeClient.calls if name == "trade_history"]
    assert windows[0] == date(2007, 1, 1)
    assert windows[1] == synced.date() - timedelta(days=30)


def test_mapping_errors_flag_connection_and_import_nothing(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    FakeClient.open_positions = [{**OPEN, "instrumentID": 9999}]
    result = _sync(db_session, default_portfolio)
    conn = _conn(db_session, default_portfolio)
    assert result["status"] == "needs_review" and result["imported"] == 0
    assert conn.needs_attention is True and "9999" in conn.last_error
    assert conn.last_synced_at is None  # the next sync re-reads the same window
    assert db_session.query(Transaction).count() == 0


def test_clean_sync_clears_review_flag(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    conn = _conn(db_session, default_portfolio)
    conn.needs_attention, conn.last_error = True, "old"
    db_session.commit()
    _sync(db_session, default_portfolio)
    assert (conn.needs_attention, conn.last_error) == (False, None)


def test_leveraged_positions_are_counted_not_imported(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    FakeClient.open_positions = [{**OPEN, "leverage": 5}]
    result = _sync(db_session, default_portfolio)
    assert result["skipped_reasons"] == {"CFD / leveraged position": 1}
    assert result["imported"] == 2


def test_manual_rows_for_same_ticker_need_review(db_session, default_portfolio):
    db_session.add(make_txn("AAPL", "buy", 1, 100, source="csv", portfolio_id=default_portfolio.id))
    db_session.commit()
    _connect(db_session, default_portfolio)
    result = _sync(db_session, default_portfolio)
    assert result["status"] == "needs_review" and "eToro" in result["errors"][0]
    assert _conn(db_session, default_portfolio).needs_attention is True


def test_auth_error_flags_connection(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    FakeClient.fail = EtoroAuthError("revoked")
    with pytest.raises(HTTPException) as exc:
        _sync(db_session, default_portfolio)
    assert exc.value.status_code == 400
    conn = _conn(db_session, default_portfolio)
    assert conn.needs_attention is True and "revoked" in conn.last_error


def test_rate_limit_is_429_with_retry_after(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    FakeClient.fail = EtoroRateLimited(42)
    with pytest.raises(HTTPException) as exc:
        _sync(db_session, default_portfolio)
    assert exc.value.status_code == 429 and exc.value.headers["Retry-After"] == "42"


def test_sync_without_connection_is_404(db_session, default_portfolio):
    with pytest.raises(HTTPException) as exc:
        _sync(db_session, default_portfolio)
    assert exc.value.status_code == 404


def test_auto_sync_toggle_and_disconnect(db_session, default_portfolio, request_context):
    _connect(db_session, default_portfolio)
    out = etoro_router.set_auto_sync(etoro_router.AutoSyncBody(enabled=True), db=db_session,
                                     portfolio=default_portfolio, _context=None)
    assert out == {"ok": True, "auto_sync": True}
    etoro_router.disconnect(db=db_session, portfolio=default_portfolio, _context=request_context)
    assert db_session.query(BrokerConnection).count() == 0
    with pytest.raises(HTTPException) as exc:
        etoro_router.disconnect(db=db_session, portfolio=default_portfolio, _context=None)
    assert exc.value.status_code == 404
