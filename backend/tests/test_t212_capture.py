from datetime import datetime

from models import BrokerSyncEvent
from scripts.t212_capture_corporate_actions import redact_payload, select_capture_events


def _ev(event_id, ticker, filled_at, fill_type="TRADE", stream="orders"):
    return BrokerSyncEvent(
        stream=stream,
        provider_event_id=event_id,
        provider_timestamp=datetime.fromisoformat(filled_at.replace("Z", "+00:00")),
        raw_payload={
            "order": {
                "id": 123456789,
                "ticker": ticker,
                "side": "BUY",
                "instrument": {"currency": "USD", "isin": "US67066G1040"},
            },
            "fill": {
                "id": 987654321,
                "type": fill_type,
                "quantity": 9.0,
                "price": 120.5,
                "filledAt": filled_at,
                "walletImpact": {"netValue": -1084.5, "currency": "USD"},
            },
        },
    )


def test_redaction_replaces_identifiers_but_keeps_economics():
    id_map: dict[str, str] = {}
    out = redact_payload(
        _ev("fill:1", "NVDA_US_EQ", "2024-06-10T10:00:00Z").raw_payload,
        id_map,
    )
    assert out["order"]["id"] == "id-0001"
    assert out["fill"]["id"] == "id-0002"
    assert out["fill"]["quantity"] == 9.0
    assert out["fill"]["price"] == 120.5
    assert out["fill"]["walletImpact"]["netValue"] == -1084.5
    assert out["order"]["ticker"] == "NVDA_US_EQ"
    assert out["order"]["instrument"]["isin"] == "US67066G1040"


def test_redaction_is_stable_across_payloads():
    id_map: dict[str, str] = {}
    a = redact_payload({"order": {"id": 5}, "fill": {"id": 6}}, id_map)
    b = redact_payload({"order": {"id": 5}, "fill": {"id": 7}}, id_map)
    assert a["order"]["id"] == b["order"]["id"] == "id-0001"
    assert b["fill"]["id"] == "id-0003"


def test_redaction_drops_account_level_keys():
    out = redact_payload(
        {"accountId": 42, "reference": "abc", "fill": {"id": 1}},
        {},
    )
    assert "accountId" not in out
    assert out["reference"].startswith("id-")


def test_selection_keeps_actions_and_same_ticker_neighbours_only():
    events = [
        _ev("fill:s1", "NVDA_US_EQ", "2024-06-10T04:00:00Z", "STOCK_SPLIT"),
        _ev("fill:s2", "NVDA_US_EQ", "2024-06-10T04:00:00Z", "STOCK_SPLIT"),
        _ev("fill:t1", "NVDA_US_EQ", "2024-06-08T15:00:00Z"),
        _ev("fill:t2", "NVDA_US_EQ", "2024-05-01T15:00:00Z"),
        _ev("fill:t3", "AAPL_US_EQ", "2024-06-10T15:00:00Z"),
    ]
    picked = {
        event.provider_event_id
        for event in select_capture_events(events, window_days=3)
    }
    assert picked == {"fill:s1", "fill:s2", "fill:t1"}
