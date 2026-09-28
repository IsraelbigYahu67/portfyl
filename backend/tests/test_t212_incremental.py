from datetime import datetime, timedelta, timezone

from t212_incremental import OVERLAP_DAYS, OVERLAP_PAGES, evaluate_page


F = datetime(2024, 6, 1, tzinfo=timezone.utc)


def d(days):
    return F - timedelta(days=days)


def test_unknown_event_resets_streak():
    verdict = evaluate_page(
        page_events=[("x", d(10)), ("y", d(11))],
        known_ids={"y"},
        frontier_at=F,
        prior_streak=1,
        previous_page_oldest=d(9),
    )
    assert (
        verdict.stop,
        verdict.known_streak,
        verdict.ordering_violation,
    ) == (False, 0, False)


def test_known_page_inside_overlap_window_does_not_count():
    verdict = evaluate_page(
        page_events=[("a", d(1)), ("b", d(2))],
        known_ids={"a", "b"},
        frontier_at=F,
        prior_streak=0,
        previous_page_oldest=None,
    )
    assert verdict.known_streak == 0 and verdict.stop is False


def test_stops_after_overlap_pages_past_frontier():
    verdict = evaluate_page(
        page_events=[
            ("a", d(OVERLAP_DAYS + 1)),
            ("b", d(OVERLAP_DAYS + 2)),
        ],
        known_ids={"a", "b"},
        frontier_at=F,
        prior_streak=OVERLAP_PAGES - 1,
        previous_page_oldest=d(OVERLAP_DAYS),
    )
    assert verdict.stop is True


def test_ordering_violation_within_page_never_stops():
    verdict = evaluate_page(
        page_events=[("a", d(OVERLAP_DAYS + 1)), ("b", d(1))],
        known_ids={"a", "b"},
        frontier_at=F,
        prior_streak=OVERLAP_PAGES,
        previous_page_oldest=d(OVERLAP_DAYS),
    )
    assert verdict.stop is False and verdict.ordering_violation is True


def test_ordering_violation_across_pages_never_stops():
    verdict = evaluate_page(
        page_events=[("a", d(5))],
        known_ids={"a"},
        frontier_at=F,
        prior_streak=OVERLAP_PAGES,
        previous_page_oldest=d(20),
    )
    assert verdict.stop is False and verdict.ordering_violation is True


def test_no_frontier_never_stops():
    verdict = evaluate_page(
        page_events=[("a", d(100))],
        known_ids={"a"},
        frontier_at=None,
        prior_streak=99,
        previous_page_oldest=None,
    )
    assert verdict.stop is False


def test_old_unknown_event_for_unseen_ticker_is_not_skipped():
    verdict = evaluate_page(
        page_events=[("known", d(30)), ("unseen", d(400))],
        known_ids={"known"},
        frontier_at=F,
        prior_streak=OVERLAP_PAGES,
        previous_page_oldest=d(29),
    )
    assert verdict.stop is False and verdict.known_streak == 0
