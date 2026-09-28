"""Tests for backend/t212_sync.py Task 3: resumable history runs.

docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md, Task 3.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import t212_sync
from models import BrokerConnection, BrokerSyncEvent, BrokerSyncRun, Portfolio
from t212_incremental import OVERLAP_PAGES
from tests.helpers import make_txn


# ---------------------------------------------------------------------------
# Rate-limit header parsing
# ---------------------------------------------------------------------------


class TestParseRateLimitHeaders:
    def test_parses_remaining_and_reset(self):
        now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        state = t212_sync.parse_rate_limit_headers(
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "30"}, now=now
        )
        assert state.remaining == 0
        assert state.reset_at == now + timedelta(seconds=30)

    def test_missing_headers_are_none(self):
        state = t212_sync.parse_rate_limit_headers({})
        assert state.remaining is None
        assert state.reset_at is None

    def test_malformed_values_degrade_to_none(self):
        state = t212_sync.parse_rate_limit_headers(
            {"x-ratelimit-remaining": "not-a-number", "x-ratelimit-reset": "also-bad"}
        )
        assert state.remaining is None
        assert state.reset_at is None


# ---------------------------------------------------------------------------
# next_page_path validation (security-critical: never forward auth to an
# absolute/cross-origin/unexpected-endpoint URL)
# ---------------------------------------------------------------------------


class TestValidateNextPagePath:
    def test_valid_relative_path_with_cursor(self):
        result = t212_sync.validate_next_page_path(
            "/equity/history/orders?cursor=abc123&limit=50", "orders"
        )
        assert result == "/equity/history/orders?cursor=abc123&limit=50"

    def test_valid_relative_path_dividends(self):
        result = t212_sync.validate_next_page_path(
            "/equity/history/dividends?cursor=xyz", "dividends"
        )
        assert result == "/equity/history/dividends?cursor=xyz"

    def test_none_or_empty_rejected(self):
        assert t212_sync.validate_next_page_path(None, "orders") is None
        assert t212_sync.validate_next_page_path("", "orders") is None

    def test_absolute_url_rejected(self):
        assert t212_sync.validate_next_page_path(
            "https://evil.example.com/equity/history/orders?cursor=x", "orders"
        ) is None

    def test_protocol_relative_url_rejected(self):
        assert t212_sync.validate_next_page_path(
            "//evil.example.com/equity/history/orders?cursor=x", "orders"
        ) is None

    def test_wrong_endpoint_path_rejected(self):
        assert t212_sync.validate_next_page_path(
            "/equity/history/dividends?cursor=x", "orders"
        ) is None

    def test_fragment_rejected(self):
        assert t212_sync.validate_next_page_path(
            "/equity/history/orders?cursor=x#frag", "orders"
        ) is None

    def test_unexpected_query_key_rejected(self):
        assert t212_sync.validate_next_page_path(
            "/equity/history/orders?cursor=x&evil=1", "orders"
        ) is None

    def test_path_traversal_rejected(self):
        assert t212_sync.validate_next_page_path(
            "/equity/history/orders/../../secret?cursor=x", "orders"
        ) is None

    def test_no_query_string_is_valid(self):
        assert t212_sync.validate_next_page_path(
            "/equity/history/orders", "orders"
        ) == "/equity/history/orders"


# ---------------------------------------------------------------------------
# Single-page fetch
# ---------------------------------------------------------------------------


class TestFetchStreamPage:
    def test_first_page_uses_limit_param(self):
        response = MagicMock(status_code=200, headers={})
        response.json.return_value = {"items": [{"a": 1}], "nextPagePath": None}
        with patch("t212_sync.httpx.get", return_value=response) as get:
            items, next_path = t212_sync._fetch_stream_page(
                "https://live.trading212.com/api/v0", {"Authorization": "x"}, "orders", None
            )
        get.assert_called_once_with(
            "https://live.trading212.com/api/v0/equity/history/orders",
            headers={"Authorization": "x"}, params={"limit": 50}, timeout=15,
        )
        assert items == [{"a": 1}]
        assert next_path is None

    def test_subsequent_page_follows_full_next_path_verbatim(self):
        response = MagicMock(status_code=200, headers={})
        response.json.return_value = {"items": [], "nextPagePath": None}
        with patch("t212_sync.httpx.get", return_value=response) as get:
            t212_sync._fetch_stream_page(
                "https://live.trading212.com/api/v0", {"Authorization": "x"}, "orders",
                "/equity/history/orders?cursor=abc&limit=50",
            )
        get.assert_called_once_with(
            "https://live.trading212.com/api/v0/equity/history/orders?cursor=abc&limit=50",
            headers={"Authorization": "x"}, timeout=15,
        )

    def test_401_raises_http_exception(self):
        response = MagicMock(status_code=401, headers={})
        with patch("t212_sync.httpx.get", return_value=response):
            with pytest.raises(Exception) as exc_info:
                t212_sync._fetch_stream_page("base", {}, "orders", None)
        assert exc_info.value.status_code == 401

    def test_429_raises_rate_limited_error_with_parsed_state(self):
        response = MagicMock(
            status_code=429,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "10"},
        )
        with patch("t212_sync.httpx.get", return_value=response):
            with pytest.raises(t212_sync.RateLimitedError) as exc_info:
                t212_sync._fetch_stream_page("base", {}, "orders", None)
        assert exc_info.value.state.remaining == 0

    def test_invalid_next_page_path_in_response_is_dropped(self):
        response = MagicMock(status_code=200, headers={})
        response.json.return_value = {
            "items": [{"a": 1}],
            "nextPagePath": "https://evil.example.com/equity/history/orders?cursor=x",
        }
        with patch("t212_sync.httpx.get", return_value=response):
            items, next_path = t212_sync._fetch_stream_page("base", {}, "orders", None)
        assert next_path is None


# ---------------------------------------------------------------------------
# Provider event identity
# ---------------------------------------------------------------------------


class TestEventIdentity:
    def test_order_prefers_fill_id_over_order_id(self):
        item = {"order": {"id": "order-1"}, "fill": {"id": "fill-1"}}
        assert t212_sync._order_event_id(item) == "fill:fill-1"

    def test_order_falls_back_to_order_id(self):
        item = {"order": {"id": "order-1"}, "fill": {}}
        assert t212_sync._order_event_id(item) == "order:order-1"

    def test_order_falls_back_to_fingerprint(self):
        item = {"order": {}, "fill": {}, "extra": "data"}
        event_id = t212_sync._order_event_id(item)
        assert event_id.startswith("order-fp:")

    def test_two_fills_of_partially_filled_order_get_distinct_ids(self):
        item1 = {"order": {"id": "order-1", "status": "PARTIAL"}, "fill": {"id": "fill-1"}}
        item2 = {"order": {"id": "order-1", "status": "FILLED"}, "fill": {"id": "fill-2"}}
        assert t212_sync._order_event_id(item1) != t212_sync._order_event_id(item2)

    def test_dividend_prefers_reference(self):
        item = {"reference": "div-ref-1"}
        assert t212_sync._dividend_event_id(item) == "dividend:div-ref-1"

    def test_dividend_falls_back_to_fingerprint(self):
        item = {"ticker": "AAPL", "amount": 1.0}
        assert t212_sync._dividend_event_id(item).startswith("dividend-fp:")


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_run(db_session, default_portfolio):
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20,
    )
    db_session.add(conn)
    db_session.flush()
    run = BrokerSyncRun(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=default_portfolio.id,
        connection_id=conn.id,
        broker="trading212",
        credential_generation=conn.credential_generation,
        mode="incremental",
        state="pending",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


class TestStageEvents:
    def test_stages_new_items(self, db_session, sync_run):
        items = [
            {"order": {"id": "o1"}, "fill": {"id": "f1", "filledAt": "2026-01-01T00:00:00Z"}},
            {"order": {"id": "o2"}, "fill": {"id": "f2", "filledAt": "2026-01-02T00:00:00Z"}},
        ]
        staged = t212_sync.stage_events(db_session, sync_run, "orders", items)
        db_session.commit()
        assert staged == 2
        assert db_session.query(BrokerSyncEvent).count() == 2

    def test_restaging_same_page_is_idempotent(self, db_session, sync_run):
        items = [{"order": {"id": "o1"}, "fill": {"id": "f1"}}]
        t212_sync.stage_events(db_session, sync_run, "orders", items)
        db_session.commit()
        staged_again = t212_sync.stage_events(db_session, sync_run, "orders", items)
        db_session.commit()
        assert staged_again == 0
        assert db_session.query(BrokerSyncEvent).count() == 1

    def test_same_id_in_different_streams_is_not_deduped_across_streams(self, db_session, sync_run):
        # Extremely unlikely in practice (fingerprints differ per stream
        # shape), but the unique key includes stream, so prove it holds.
        order_item = {"order": {"id": "shared"}, "fill": {}}
        t212_sync.stage_events(db_session, sync_run, "orders", [order_item])
        db_session.commit()
        assert db_session.query(BrokerSyncEvent).filter(
            BrokerSyncEvent.stream == "orders",
        ).count() == 1

    def test_empty_items_returns_zero(self, db_session, sync_run):
        assert t212_sync.stage_events(db_session, sync_run, "orders", []) == 0

    def test_later_run_may_restage_same_provider_id(self, db_session, sync_run, default_portfolio):
        item = {"order": {"id": "o1"}, "fill": {"id": "f1"}}
        t212_sync.stage_events(db_session, sync_run, "orders", [item])
        db_session.commit()

        other_run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            connection_id=sync_run.connection_id,
            broker="trading212",
            credential_generation=sync_run.credential_generation,
            mode="audit",
            state="pending",
        )
        db_session.add(other_run)
        db_session.commit()
        db_session.refresh(other_run)

        staged = t212_sync.stage_events(db_session, other_run, "orders", [item])
        db_session.commit()
        assert staged == 1
        assert db_session.query(BrokerSyncEvent).count() == 2


# ---------------------------------------------------------------------------
# claim_or_create_run
# ---------------------------------------------------------------------------


class TestClaimOrCreateRun:
    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            broker="trading212", api_key="k" * 20,
        )
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)
        return conn

    def test_creates_a_new_run_with_copied_generation(self, db_session, default_portfolio, connection):
        connection.credential_generation = 3
        db_session.commit()

        run = t212_sync.claim_or_create_run(db_session, connection, default_portfolio)
        db_session.commit()

        assert run.workspace_id == default_portfolio.workspace_id
        assert run.connection_id == connection.id
        assert run.credential_generation == 3
        assert run.state == "pending"
        assert run.mode == "incremental"

    def test_duplicate_call_returns_the_same_active_run(self, db_session, default_portfolio, connection):
        first = t212_sync.claim_or_create_run(db_session, connection, default_portfolio)
        db_session.commit()
        second = t212_sync.claim_or_create_run(db_session, connection, default_portfolio)
        db_session.commit()

        assert first.id == second.id
        assert db_session.query(BrokerSyncRun).count() == 1

    def test_terminal_run_does_not_block_a_new_one(self, db_session, default_portfolio, connection):
        first = t212_sync.claim_or_create_run(db_session, connection, default_portfolio)
        first.state = "completed"
        db_session.commit()

        second = t212_sync.claim_or_create_run(db_session, connection, default_portfolio)
        db_session.commit()

        assert second.id != first.id
        assert db_session.query(BrokerSyncRun).count() == 2


# ---------------------------------------------------------------------------
# claim_lease
# ---------------------------------------------------------------------------


class TestClaimLease:
    def test_claims_an_unleased_run(self, db_session, sync_run):
        claimed = t212_sync.claim_lease(db_session, sync_run.id, sync_run.workspace_id)
        db_session.commit()
        assert claimed is not None
        assert claimed.lease_token is not None
        assert claimed.lease_expires_at is not None

    def test_does_not_reclaim_an_unexpired_lease(self, db_session, sync_run):
        now = datetime.now(timezone.utc)
        first = t212_sync.claim_lease(db_session, sync_run.id, sync_run.workspace_id, now=now)
        db_session.commit()
        second = t212_sync.claim_lease(
            db_session, sync_run.id, sync_run.workspace_id, now=now + timedelta(seconds=5)
        )
        db_session.commit()
        assert first is not None
        assert second is None

    def test_reclaims_after_lease_expires(self, db_session, sync_run):
        now = datetime.now(timezone.utc)
        first = t212_sync.claim_lease(
            db_session, sync_run.id, sync_run.workspace_id, now=now, lease_seconds=10
        )
        first_token = first.lease_token
        db_session.commit()
        second = t212_sync.claim_lease(
            db_session, sync_run.id, sync_run.workspace_id, now=now + timedelta(seconds=11)
        )
        db_session.commit()
        assert second is not None
        assert second.lease_token != first_token

    def test_nonexistent_run_returns_none(self, db_session, default_portfolio):
        assert t212_sync.claim_lease(db_session, 999999, default_portfolio.workspace_id) is None


# ---------------------------------------------------------------------------
# advance_run
# ---------------------------------------------------------------------------


def _page_response(items, next_page_path=None, *, headers=None):
    response = MagicMock(status_code=200, headers=headers or {})
    response.json.return_value = {"items": items, "nextPagePath": next_page_path}
    return response


class TestAdvanceRun:
    def test_completed_streams_wait_for_atomic_finalization(self, db_session, sync_run):
        order_item = {"order": {"id": "o1"}, "fill": {"id": "f1"}}
        div_item = {"reference": "d1"}
        responses = {
            "https://x/equity/history/orders": _page_response([order_item], None),
            "https://x/equity/history/dividends": _page_response([div_item], None),
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            return responses[url]

        with patch("t212_sync.httpx.get", side_effect=fake_get):
            result = t212_sync.advance_run(db_session, sync_run, "https://x", {})

        assert result.state == "finalizing"
        assert result.orders_staged == 1
        assert result.dividends_staged == 1
        assert sync_run.orders_complete is True
        assert sync_run.dividends_complete is True
        assert sync_run.completed_at is None
        assert db_session.query(BrokerSyncEvent).count() == 2

    def test_stays_fetching_when_budget_exhausted_before_completion(self, db_session, sync_run):
        # Every page returns a next_page_path, so 3 pages/stream never finishes.
        page = _page_response(
            [{"order": {"id": "o"}, "fill": {"id": "f"}}],
            "/equity/history/orders?cursor=next",
        )
        div_page = _page_response([{"reference": "d"}], "/equity/history/dividends?cursor=next")

        def fake_get(url, headers=None, params=None, timeout=None):
            return page if "orders" in url else div_page

        with patch("t212_sync.httpx.get", side_effect=fake_get):
            result = t212_sync.advance_run(
                db_session, sync_run, "https://x", {}, max_pages_per_stream=3
            )

        assert result.state == "fetching"
        assert sync_run.orders_complete is False
        assert sync_run.orders_next_page_path == "/equity/history/orders?cursor=next"

    def test_rate_limit_on_one_stream_does_not_block_the_other(self, db_session, sync_run):
        rate_limited_resp = MagicMock(
            status_code=429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "5"},
        )
        div_item = {"reference": "d1"}

        def fake_get(url, headers=None, params=None, timeout=None):
            if "orders" in url:
                return rate_limited_resp
            return _page_response([div_item], None)

        with patch("t212_sync.httpx.get", side_effect=fake_get):
            result = t212_sync.advance_run(db_session, sync_run, "https://x", {})

        assert result.state == "waiting_rate_limit"
        assert result.rate_limited_streams == ("orders",)
        assert sync_run.dividends_complete is True
        assert sync_run.orders_rate_limit_reset_at is not None

    def test_rate_limit_preserves_the_committed_next_page_checkpoint(
        self, db_session, sync_run
    ):
        checkpoint = "/equity/history/orders?cursor=resume-me&limit=50"
        sync_run.orders_next_page_path = checkpoint
        sync_run.dividends_complete = True
        db_session.commit()
        response = MagicMock(
            status_code=429,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "60"},
        )

        with patch("t212_sync.httpx.get", return_value=response):
            result = t212_sync.advance_run(db_session, sync_run, "https://x", {})

        assert result.state == "waiting_rate_limit"
        assert sync_run.orders_next_page_path == checkpoint
        assert sync_run.orders_rate_limit_reset_at is not None

    def test_empty_first_page_marks_stream_complete_immediately(self, db_session, sync_run):
        empty = _page_response([], None)
        with patch("t212_sync.httpx.get", return_value=empty):
            result = t212_sync.advance_run(db_session, sync_run, "https://x", {})
        assert result.state == "finalizing"
        assert result.orders_staged == 0

    def test_reassert_context_called_after_every_commit(self, db_session, sync_run):
        empty = _page_response([], None)
        calls = []
        with patch("t212_sync.httpx.get", return_value=empty):
            t212_sync.advance_run(
                db_session, sync_run, "https://x", {},
                reassert_context=lambda: calls.append(1),
            )
        assert len(calls) >= 2  # at least the initial "fetching" commit + final commit

    def test_lease_lost_stops_advancing_without_losing_committed_progress(self, db_session, sync_run):
        order_item = {"order": {"id": "o1"}, "fill": {"id": "f1"}}
        page1 = _page_response([order_item], "/equity/history/orders?cursor=next")
        page2 = _page_response([{"order": {"id": "o2"}, "fill": {"id": "f2"}}], None)
        call_count = {"n": 0}

        def fake_get(url, headers=None, params=None, timeout=None):
            call_count["n"] += 1
            if "dividends" in url:
                return _page_response([], None)
            return page1 if call_count["n"] == 1 else page2

        stolen_token = uuid4()

        def steal_lease_after_first_commit():
            # Simulate another worker reclaiming this run right after the
            # first page's commit.
            sync_run.lease_token = stolen_token
            db_session.commit()

        original_lease = uuid4()
        sync_run.lease_token = original_lease
        db_session.commit()

        calls = {"n": 0}

        def reassert():
            calls["n"] += 1
            # Call #1 is the initial pending->fetching commit; call #2 is the
            # commit right after the first orders page (o1) is staged. Steal
            # the lease then, so o1 survives but o2 (and dividends) never do.
            if calls["n"] == 2:
                steal_lease_after_first_commit()

        with patch("t212_sync.httpx.get", side_effect=fake_get):
            t212_sync.advance_run(
                db_session, sync_run, "https://x", {},
                lease_token=original_lease, reassert_context=reassert,
            )

        # The first order (committed before the lease was stolen) survives;
        # advancing stopped before staging the second.
        assert db_session.query(BrokerSyncEvent).filter(
            BrokerSyncEvent.stream == "orders"
        ).count() == 1


# ---------------------------------------------------------------------------
# history_run_decision (plan 2026-09-24, Task A4)
# ---------------------------------------------------------------------------

SPLIT = [{"fill_type": "STOCK_SPLIT", "ticker": "NVDA", "date": "2024-06-10"}]


@pytest.fixture
def connection(db_session, default_portfolio):
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20, account_fingerprint="f" * 64,
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


def _review_run(db, conn, portfolio, details):
    run = BrokerSyncRun(
        workspace_id=conn.workspace_id, portfolio_id=portfolio.id, connection_id=conn.id,
        broker="trading212", account_fingerprint=conn.account_fingerprint,
        credential_generation=conn.credential_generation, mode="incremental",
        state="needs_review", review_details=details,
    )
    db.add(run)
    db.commit()
    return run


class TestHistoryRunDecision:
    def test_blocked_when_needs_review_is_unresolved(self, db_session, default_portfolio, connection):
        run = _review_run(db_session, connection, default_portfolio, SPLIT)
        decision = t212_sync.history_run_decision(db_session, connection, default_portfolio)
        assert decision.action == "blocked"
        assert decision.run.id == run.id

    def test_force_creates_a_new_run(self, db_session, default_portfolio, connection):
        _review_run(db_session, connection, default_portfolio, SPLIT)
        decision = t212_sync.history_run_decision(
            db_session, connection, default_portfolio, force=True,
        )
        assert decision.action == "create"

    def test_csv_coverage_past_last_action_unblocks(self, db_session, default_portfolio, connection):
        _review_run(db_session, connection, default_portfolio, SPLIT)
        connection.t212_csv_covered_through = datetime(2024, 6, 11, tzinfo=timezone.utc)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "create"

    def test_csv_coverage_inside_action_day_stays_blocked(
        self, db_session, default_portfolio, connection
    ):
        _review_run(db_session, connection, default_portfolio, SPLIT)
        connection.t212_csv_covered_through = datetime(2024, 6, 10, 12, tzinfo=timezone.utc)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "blocked"

    def test_newly_supported_type_unblocks(
        self, db_session, default_portfolio, connection, monkeypatch
    ):
        _review_run(db_session, connection, default_portfolio, SPLIT)
        monkeypatch.setattr(
            t212_sync, "SUPPORTED_CORPORATE_ACTION_TYPES", frozenset({"STOCK_SPLIT"}),
        )
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "create"

    def test_legacy_needs_review_without_details_is_blocked(
        self, db_session, default_portfolio, connection
    ):
        _review_run(db_session, connection, default_portfolio, None)
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "blocked"

    def test_failed_latest_run_creates(self, db_session, default_portfolio, connection):
        run = _review_run(db_session, connection, default_portfolio, SPLIT)
        run.state = "failed"
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "create"

    def test_active_run_is_reused(self, db_session, default_portfolio, connection):
        run = _review_run(db_session, connection, default_portfolio, SPLIT)
        run.state = "fetching"
        db_session.commit()
        decision = t212_sync.history_run_decision(db_session, connection, default_portfolio)
        assert decision.action == "reuse"
        assert decision.run.id == run.id

    def test_only_the_latest_run_matters(self, db_session, default_portfolio, connection):
        old = _review_run(db_session, connection, default_portfolio, SPLIT)
        old.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        db_session.commit()
        newer = _review_run(db_session, connection, default_portfolio, SPLIT)
        newer.state = "completed"
        newer.created_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).action == "create"


class TestHistoryRunMode:
    """Plan 2026-09-24 Task C1: the create branch picks the run mode."""

    def test_create_mode_is_initial_without_coverage(
        self, db_session, default_portfolio, connection
    ):
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "initial"

    def test_create_mode_is_incremental_with_coverage(
        self, db_session, default_portfolio, connection
    ):
        connection.history_complete_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        connection.last_full_audit_at = datetime.now(timezone.utc)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "incremental"

    def test_forced_retry_without_coverage_is_initial(
        self, db_session, default_portfolio, connection
    ):
        _review_run(db_session, connection, default_portfolio, SPLIT)
        decision = t212_sync.history_run_decision(
            db_session, connection, default_portfolio, force=True,
        )
        assert (decision.action, decision.mode) == ("create", "initial")


# ---------------------------------------------------------------------------
# Incremental stop rule wired into advance_run (plan 2026-09-24, Task C2)
# ---------------------------------------------------------------------------

FRONTIER = datetime(2024, 6, 1, tzinfo=timezone.utc)


def _iso(days_before):
    return (FRONTIER - timedelta(days=days_before)).isoformat().replace("+00:00", "Z")


def _order_item(event_id, days_before):
    return {"order": {"id": f"o-{event_id}", "ticker": "AAPL_US_EQ"},
            "fill": {"id": event_id, "filledAt": _iso(days_before)}}


def _dividend_item(reference, days_before):
    return {"reference": reference, "ticker": "KO", "paidOn": _iso(days_before)}


def _incremental_run(db, portfolio, *, mode="incremental", frontier=FRONTIER):
    conn = BrokerConnection(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
        broker="trading212", api_key="k" * 20, account_fingerprint="f" * 64,
        history_complete_at=frontier, orders_frontier_at=frontier,
        dividends_frontier_at=frontier,
    )
    db.add(conn)
    db.flush()
    run = BrokerSyncRun(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
        connection_id=conn.id, broker="trading212", account_fingerprint="f" * 64,
        credential_generation=conn.credential_generation, mode=mode, state="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return conn, run


def _known(db, portfolio, event_ids, *, stream="orders", source="t212_api", prefix="fill"):
    for event_id in event_ids:
        txn = make_txn(
            "AAPL", "buy", 1, 100, portfolio_id=portfolio.id, source=source,
            workspace_id=portfolio.workspace_id,
        )
        txn.source_event_id = f"{prefix}:{event_id}"
        txn.source_event_stream = stream
        db.add(txn)
    db.commit()


def _scripted_fetch(pages_by_stream):
    """A stand-in for t212_sync._fetch_stream_page serving scripted pages
    (newest first) and counting the pages fetched per stream."""
    calls = {"orders": 0, "dividends": 0}

    def fake(base, headers, stream, next_path):
        index = 0 if next_path is None else int(next_path.removeprefix("page"))
        calls[stream] += 1
        pages = pages_by_stream.get(stream, [[]])
        following = f"page{index + 1}" if index + 1 < len(pages) else None
        return pages[index], following

    return fake, calls


def _advance(db, run, pages_by_stream, **kwargs):
    fake, calls = _scripted_fetch(pages_by_stream)
    with patch("t212_sync._fetch_stream_page", side_effect=fake):
        result = t212_sync.advance_run(
            db, run, "https://x", {}, max_pages_per_stream=10, **kwargs,
        )
    return result, calls


class TestIncrementalStopRule:
    def test_stops_after_overlap_pages_past_the_frontier(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5", "k6"])
        pages = {"orders": [
            [_order_item("new", -1), _order_item("k1", 0)],
            [_order_item("k2", 8), _order_item("k3", 9)],
            [_order_item("k4", 10), _order_item("k5", 11)],
            [_order_item("k6", 12)],
        ]}

        result, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 1 + OVERLAP_PAGES
        db_session.refresh(run)
        assert run.orders_complete is True
        assert run.orders_next_page_path is None
        assert run.orders_known_streak == OVERLAP_PAGES
        assert run.mode == "incremental"
        assert result.state == "finalizing"
        staged = {e.provider_event_id for e in db_session.query(BrokerSyncEvent).filter(
            BrokerSyncEvent.stream == "orders")}
        assert staged == {"fill:new", "fill:k1", "fill:k2", "fill:k3", "fill:k4", "fill:k5"}

    def test_connection_is_looked_up_when_not_passed(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5"])
        pages = {"orders": [
            [_order_item("k1", 8)], [_order_item("k2", 9)], [_order_item("k3", 10)],
            [_order_item("k4", 11)], [_order_item("k5", 12)],
        ]}

        _, calls = _advance(db_session, run, pages)

        # Pages 1 and 2 are fully known and past the overlap window: streak 2.
        assert calls["orders"] == OVERLAP_PAGES
        db_session.refresh(run)
        assert run.orders_known_streak == OVERLAP_PAGES

    def test_unknown_old_event_keeps_the_walk_going(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5"])
        pages = {"orders": [
            [_order_item("k1", 1)],
            [_order_item("k2", 8)],
            [_order_item("k3", 9), _order_item("u1", 10)],
            [_order_item("k4", 11)],
            [_order_item("u2", 12)],
            [_order_item("k5", 13)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 6
        db_session.refresh(run)
        assert run.orders_complete is True
        assert run.orders_known_streak == 1

    def test_page_newer_than_the_previous_one_falls_back_to_an_audit(
        self, db_session, default_portfolio
    ):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5", "k6"])
        pages = {"orders": [
            [_order_item("k1", 8), _order_item("k2", 9)],
            [_order_item("k3", 5)],  # newer than page 1's oldest event
            [_order_item("k4", 12)],
            [_order_item("k5", 13)],
            [_order_item("k6", 14)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 5
        db_session.refresh(run)
        assert run.mode == "audit"
        assert run.orders_complete is True

    def test_initial_run_never_stops_early(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio, mode="initial")
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5", "k6"])
        pages = {"orders": [
            [_order_item("k1", 8)], [_order_item("k2", 9)], [_order_item("k3", 10)],
            [_order_item("k4", 11)], [_order_item("k5", 12)], [_order_item("k6", 13)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 6
        db_session.refresh(run)
        assert run.mode == "initial"
        assert run.orders_known_streak == 0

    def test_incremental_run_without_a_frontier_never_stops_early(
        self, db_session, default_portfolio
    ):
        conn, run = _incremental_run(db_session, default_portfolio, frontier=None)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5"])
        pages = {"orders": [
            [_order_item("k1", 8)], [_order_item("k2", 9)], [_order_item("k3", 10)],
            [_order_item("k4", 11)], [_order_item("k5", 12)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 5

    def test_only_provider_api_rows_count_as_known(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5"], source="t212_csv")
        pages = {"orders": [
            [_order_item("k1", 8)], [_order_item("k2", 9)], [_order_item("k3", 10)],
            [_order_item("k4", 11)], [_order_item("k5", 12)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 5

    def test_csv_covered_events_count_as_known(self, db_session, default_portfolio):
        # Finalization skips everything at or before the authoritative CSV
        # cutoff, so those events never become t212_api rows. Treating them as
        # unknown would turn every incremental sync of a CSV-seeded portfolio
        # into a full walk.
        conn, run = _incremental_run(db_session, default_portfolio)
        conn.t212_csv_covered_through = FRONTIER - timedelta(days=8)
        db_session.commit()
        pages = {"orders": [
            [_order_item("c1", 8)], [_order_item("c2", 9)], [_order_item("c3", 10)],
            [_order_item("c4", 11)], [_order_item("c5", 12)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == OVERLAP_PAGES

    def test_events_after_the_csv_cutoff_are_not_known_by_time(
        self, db_session, default_portfolio
    ):
        conn, run = _incremental_run(db_session, default_portfolio)
        default_portfolio.t212_csv_covered_through = FRONTIER - timedelta(days=30)
        db_session.commit()
        pages = {"orders": [
            [_order_item("c1", 8)], [_order_item("c2", 9)], [_order_item("c3", 10)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 3

    def test_events_a_completed_run_already_finalized_count_as_known(
        self, db_session, default_portfolio
    ):
        # Legacy-duplicate, non-trade, and invalid events are decided by
        # finalization without ever becoming t212_api rows.
        conn, run = _incremental_run(db_session, default_portfolio)
        previous = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212", account_fingerprint="f" * 64,
            credential_generation=conn.credential_generation, mode="initial",
            state="completed",
        )
        db_session.add(previous)
        db_session.flush()
        for event_id in ("d1", "d2", "d3"):
            db_session.add(BrokerSyncEvent(
                workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
                run_id=previous.id, broker="trading212", account_fingerprint="f" * 64,
                stream="orders", provider_event_id=f"fill:{event_id}", raw_payload={},
            ))
        db_session.commit()
        pages = {"orders": [
            [_order_item("d1", 8)], [_order_item("d2", 9)], [_order_item("d3", 10)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == OVERLAP_PAGES

    def test_events_of_a_needs_review_run_are_not_known(self, db_session, default_portfolio):
        conn, run = _incremental_run(db_session, default_portfolio)
        blocked = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212", account_fingerprint="f" * 64,
            credential_generation=conn.credential_generation, mode="initial",
            state="needs_review",
        )
        db_session.add(blocked)
        db_session.flush()
        for event_id in ("r1", "r2", "r3"):
            db_session.add(BrokerSyncEvent(
                workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
                run_id=blocked.id, broker="trading212", account_fingerprint="f" * 64,
                stream="orders", provider_event_id=f"fill:{event_id}", raw_payload={},
            ))
        db_session.commit()
        pages = {"orders": [
            [_order_item("r1", 8)], [_order_item("r2", 9)], [_order_item("r3", 10)],
        ]}

        _, calls = _advance(db_session, run, pages, connection=conn)

        assert calls["orders"] == 3

    def test_audit_fallback_restarts_a_stream_that_already_stopped_early(
        self, db_session, default_portfolio
    ):
        conn, run = _incremental_run(db_session, default_portfolio)
        _known(db_session, default_portfolio, ["k1", "k2", "k3", "k4", "k5", "k6"])
        _known(db_session, default_portfolio, ["dk1", "dk2", "dk3", "dk4"],
               stream="dividends", prefix="dividend")
        orders = [
            [_order_item("new", -1), _order_item("k1", 0)],
            [_order_item("k2", 8), _order_item("k3", 9)],
            [_order_item("k4", 10), _order_item("k5", 11)],
            [_order_item("k6", 12)],
        ]
        dividends = [
            [_dividend_item("dk1", 8), _dividend_item("dk2", 9)],
            [_dividend_item("dk3", 5)],  # newer than the previous page: ordering doubt
            [_dividend_item("dk4", 12)],
        ]

        first, first_calls = _advance(
            db_session, run, {"orders": orders, "dividends": dividends}, connection=conn,
        )

        # Orders stopped early (3 of 4 pages), then dividends flipped the run to
        # an audit: orders must be walked again in full, or the audit stamp
        # would vouch for history that was never read.
        assert first_calls["orders"] == 3
        db_session.refresh(run)
        assert run.mode == "audit"
        assert run.orders_complete is False
        assert run.orders_next_page_path is None
        assert run.orders_known_streak == 0
        assert run.dividends_complete is True
        assert first.state == "fetching"

        second, second_calls = _advance(
            db_session, run, {"orders": orders, "dividends": dividends}, connection=conn,
        )

        assert second_calls["orders"] == 4
        assert second_calls["dividends"] == 0
        db_session.refresh(run)
        assert run.orders_complete is True
        assert second.state == "finalizing"


class TestHistoryRunAuditMode:
    """Plan 2026-09-24 Task C3: 30-day and mismatch-triggered audits."""

    def test_mode_is_audit_after_30_days(self, db_session, default_portfolio, connection):
        connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        connection.last_full_audit_at = datetime.now(timezone.utc) - timedelta(days=31)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "audit"

    def test_mode_is_incremental_within_30_days(self, db_session, default_portfolio, connection):
        connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        connection.last_full_audit_at = datetime.now(timezone.utc) - timedelta(days=5)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "incremental"

    def test_reconciliation_mismatch_forces_audit(self, db_session, default_portfolio, connection):
        connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        connection.last_full_audit_at = datetime.now(timezone.utc)
        db_session.commit()
        decision = t212_sync.history_run_decision(
            db_session, connection, default_portfolio, reconciliation_mismatch=True,
        )
        assert decision.mode == "audit"

    def test_recent_initial_run_counts_as_a_full_read(
        self, db_session, default_portfolio, connection
    ):
        # An initial run read the whole history; the next sync must not audit
        # it again just because no audit has ever been recorded.
        connection.history_complete_at = datetime.now(timezone.utc) - timedelta(days=2)
        db_session.commit()
        assert connection.last_full_audit_at is None
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "incremental"

    def test_old_initial_run_without_an_audit_becomes_an_audit(
        self, db_session, default_portfolio, connection
    ):
        connection.history_complete_at = datetime.now(timezone.utc) - timedelta(days=31)
        db_session.commit()
        assert t212_sync.history_run_decision(
            db_session, connection, default_portfolio,
        ).mode == "audit"

    def test_mismatch_before_history_completes_still_starts_an_initial_run(
        self, db_session, default_portfolio, connection
    ):
        decision = t212_sync.history_run_decision(
            db_session, connection, default_portfolio, reconciliation_mismatch=True,
        )
        assert decision.mode == "initial"
