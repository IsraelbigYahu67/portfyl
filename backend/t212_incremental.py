"""Incremental T212 history stop rule (parent plan §7, plan 2026-09-24 C2).

Stopping early is an optimization, never the integrity mechanism: any
ordering doubt keeps walking, and the 30-day audit (C3) re-reads everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

OVERLAP_PAGES = 2
OVERLAP_DAYS = 7


@dataclass(frozen=True)
class PageVerdict:
    stop: bool
    known_streak: int
    ordering_violation: bool


def evaluate_page(*, page_events: list[tuple[str, datetime | None]], known_ids: set[str],
                  frontier_at: datetime | None, prior_streak: int,
                  previous_page_oldest: datetime | None) -> PageVerdict:
    times = [t for _, t in page_events if t is not None]
    violation = any(later > earlier for earlier, later in zip(times, times[1:]))
    if previous_page_oldest is not None and any(t > previous_page_oldest for t in times):
        violation = True
    fully_known = bool(page_events) and all(event_id in known_ids for event_id, _ in page_events)
    oldest = min(times) if times else None
    past_overlap = (
        frontier_at is not None and oldest is not None
        and oldest <= frontier_at - timedelta(days=OVERLAP_DAYS)
    )
    streak = prior_streak + 1 if (fully_known and past_overlap) else 0
    stop = frontier_at is not None and streak >= OVERLAP_PAGES and not violation
    return PageVerdict(stop=stop, known_streak=streak, ordering_violation=violation)
