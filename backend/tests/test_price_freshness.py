"""Quote freshness: when a price was set, how delayed it is, and whether it
can still be trusted (market_data.price_freshness)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import market_data

NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


def _info(minutes_ago: float, state: str = "REGULAR", delay: int = 15,
          source: str = "Delayed Quote") -> dict:
    return {
        "regularMarketTime": int((NOW - timedelta(minutes=minutes_ago)).timestamp()),
        "marketState": state,
        "exchangeDataDelayedBy": delay,
        "quoteSourceName": source,
    }


def test_missing_price_is_missing_whatever_the_info_says():
    f = market_data.price_freshness(_info(1), price=0.0, now=NOW)
    assert f["price_status"] == "missing"


def test_open_market_with_exchange_delay_is_delayed():
    f = market_data.price_freshness(_info(16), price=100.0, now=NOW)
    assert f["price_status"] == "delayed"
    assert f["price_delay_minutes"] == 15
    assert f["price_as_of"] == "2026-10-09T17:44:00Z"
    assert f["price_source"] == "Yahoo Finance"


def test_real_time_source_overrides_the_reported_exchange_delay():
    # Yahoo reports exchangeDataDelayedBy=15 for Nasdaq even when the quote
    # source is "Nasdaq Real Time Price".
    f = market_data.price_freshness(
        _info(1, source="Nasdaq Real Time Price"), price=100.0, now=NOW)
    assert f["price_status"] == "live"
    assert f["price_delay_minutes"] == 0


def test_closed_market_keeps_its_last_close_time():
    f = market_data.price_freshness(_info(60 * 20, state="POSTPOST"), price=100.0, now=NOW)
    assert f["price_status"] == "closed"
    assert f["price_as_of"] == "2026-10-08T22:00:00Z"


def test_a_weekend_old_close_is_not_stale():
    f = market_data.price_freshness(_info(60 * 24 * 4, state="CLOSED"), price=100.0, now=NOW)
    assert f["price_status"] == "closed"


def test_a_price_older_than_five_days_is_stale():
    f = market_data.price_freshness(_info(60 * 24 * 6, state="CLOSED"), price=100.0, now=NOW)
    assert f["price_status"] == "stale"


def test_no_quote_time_is_unknown_not_fresh():
    f = market_data.price_freshness({}, price=100.0, now=NOW)
    assert f["price_status"] == "unknown"
    assert f["price_as_of"] is None
    assert f["price_delay_minutes"] is None


def test_garbage_quote_time_is_treated_as_unknown():
    f = market_data.price_freshness(
        {"regularMarketTime": "not-a-time", "marketState": "REGULAR"}, price=100.0, now=NOW)
    assert f["price_status"] == "unknown"
    assert f["price_as_of"] is None
