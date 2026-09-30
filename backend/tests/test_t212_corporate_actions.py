import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from models import BrokerSyncEvent
from t212_corporate_actions import InvalidSplitPair, UnpairedSplitLeg, collapse_split_pairs

FIXTURES = Path(__file__).parent / "fixtures" / "t212_corporate_actions"


def _events_from_fixture(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [
        BrokerSyncEvent(stream="orders", provider_event_id=f"fill:{i}", raw_payload=e["payload"])
        for i, e in enumerate(data["events"]) if e["fill_type"] == "STOCK_SPLIT"
    ]


def _leg(event_id, side, qty, price, at="2024-06-10T04:00:00Z", ticker="NVDA_US_EQ", net_value=None):
    """A STOCK_SPLIT leg as observed in gate G1: the close leg (SELL) carries a
    negative quantity, the open leg (BUY) a positive one."""
    fill = {"type": "STOCK_SPLIT", "quantity": -abs(qty) if side == "SELL" else abs(qty),
            "price": price, "filledAt": at}
    if net_value is not None:
        fill["walletImpact"] = {"currency": "CZK", "netValue": net_value, "taxes": []}
    return BrokerSyncEvent(stream="orders", provider_event_id=event_id, raw_payload={
        "order": {"ticker": ticker, "side": side}, "fill": fill,
    })


def test_forward_split_pair_collapses_to_one_evidence():
    [ev] = collapse_split_pairs([_leg("fill:a", "SELL", 9, 1200), _leg("fill:b", "BUY", 90, 120)])
    assert ev.ratio == Fraction(10, 1)
    assert ev.provider_event_key == "fill:a|fill:b"
    assert (ev.old_shares, ev.new_shares) == (Decimal("9"), Decimal("90"))


def test_reverse_split_ratio_is_fractional():
    [ev] = collapse_split_pairs([_leg("fill:a", "SELL", 10, 2), _leg("fill:b", "BUY", 1, 20)])
    assert ev.ratio == Fraction(1, 10)


def test_unpaired_leg_raises():
    with pytest.raises(UnpairedSplitLeg):
        collapse_split_pairs([_leg("fill:a", "SELL", 9, 1200)])


def test_two_legs_on_the_same_side_raise():
    with pytest.raises(UnpairedSplitLeg):
        collapse_split_pairs([_leg("fill:a", "SELL", 9, 1200), _leg("fill:b", "SELL", 9, 1200)])


def test_non_split_events_are_ignored():
    trade = BrokerSyncEvent(stream="orders", provider_event_id="fill:t", raw_payload={
        "order": {"ticker": "NVDA_US_EQ", "side": "BUY"},
        "fill": {"type": "TRADE", "quantity": 1, "price": 1, "filledAt": "2024-06-10T04:00:00Z"},
    })
    assert collapse_split_pairs([trade]) == []


def test_order_of_events_does_not_matter():
    a, b = _leg("fill:a", "SELL", 9, 1200), _leg("fill:b", "BUY", 90, 120)
    assert collapse_split_pairs([b, a]) == collapse_split_pairs([a, b])


def test_two_instruments_same_time_are_separate():
    evs = collapse_split_pairs([
        _leg("fill:a", "SELL", 9, 1200), _leg("fill:b", "BUY", 90, 120),
        _leg("fill:c", "SELL", 4, 400, ticker="AVGO_US_EQ"),
        _leg("fill:d", "BUY", 40, 40, ticker="AVGO_US_EQ"),
    ])
    assert [e.provider_instrument_id for e in evs] == ["AVGO_US_EQ", "NVDA_US_EQ"]


def test_equal_wallet_impact_on_both_legs_is_ignored_and_accepted():
    # G1 decision 1: walletImpact is informational for split legs.
    [ev] = collapse_split_pairs([
        _leg("fill:a", "SELL", 9, 1200, net_value=646.4), _leg("fill:b", "BUY", 90, 120, net_value=646.4),
    ])
    assert ev.ratio == Fraction(10, 1)


def test_unequal_wallet_impact_is_not_a_pure_split():
    with pytest.raises(InvalidSplitPair):
        collapse_split_pairs([
            _leg("fill:a", "SELL", 9, 1200, net_value=646.4), _leg("fill:b", "BUY", 90, 120, net_value=500.0),
        ])


def test_wallet_impact_on_only_one_leg_is_not_a_pure_split():
    with pytest.raises(InvalidSplitPair):
        collapse_split_pairs([
            _leg("fill:a", "SELL", 9, 1200, net_value=646.4), _leg("fill:b", "BUY", 90, 120),
        ])


def test_price_ratio_that_disagrees_with_share_ratio_is_rejected():
    # 9 -> 90 shares says 10:1, but 1200 -> 200 says 6:1: value is not conserved.
    with pytest.raises(InvalidSplitPair):
        collapse_split_pairs([_leg("fill:a", "SELL", 9, 1200), _leg("fill:b", "BUY", 90, 200)])


def test_missing_price_is_rejected_because_the_ratio_cannot_be_checked():
    with pytest.raises(InvalidSplitPair):
        collapse_split_pairs([_leg("fill:a", "SELL", 9, None), _leg("fill:b", "BUY", 90, 120)])


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("stock_split_*.json")))
def test_real_fixture_ratio_matches_issuer(fixture):
    num, den = fixture.removesuffix(".json").rsplit("_", 1)[1].split("-")
    [ev] = collapse_split_pairs(_events_from_fixture(fixture))
    assert ev.ratio == Fraction(int(num), int(den))
