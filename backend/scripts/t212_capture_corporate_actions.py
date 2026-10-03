"""Read-only capture of staged Trading 212 corporate-action fills.

Unblocks plan 2026-09-24 Track B: the provider docs do not specify how a
STOCK_SPLIT fill pair encodes quantity/sign/price, but the owner's own
needs_review runs already staged real examples. This tool exports them, with
identifiers replaced by stable placeholders, for a human to inspect.

Usage (from backend/, runtime DATABASE_URL, never the migration owner):
    python -m scripts.t212_capture_corporate_actions \
        --workspace <workspace uuid> --portfolio <portfolio public_id>

Output lands in tests/fixtures/t212_corporate_actions/_captured/ which is
git-ignored. Review every file before copying it into the committed fixture
directory.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from models import BrokerSyncEvent, BrokerSyncRun, Portfolio
from scripts._redact import redact_payload  # noqa: F401  (re-exported for callers/tests)

OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "t212_corporate_actions"
    / "_captured"
)


def _fill_type(event: BrokerSyncEvent) -> str:
    raw = ((event.raw_payload or {}).get("fill") or {}).get("type") or "TRADE"
    return raw.upper()


def _ticker(event: BrokerSyncEvent) -> str | None:
    return ((event.raw_payload or {}).get("order") or {}).get("ticker")


def select_capture_events(
    events: list[BrokerSyncEvent], *, window_days: int = 3
) -> list[BrokerSyncEvent]:
    orders = [event for event in events if event.stream == "orders"]
    actions = [event for event in orders if _fill_type(event) != "TRADE"]
    window = timedelta(days=window_days)
    picked: dict[str, BrokerSyncEvent] = {
        event.provider_event_id: event for event in actions
    }
    for action in actions:
        if action.provider_timestamp is None:
            continue
        for event in orders:
            if (
                _ticker(event) == _ticker(action)
                and event.provider_timestamp is not None
                and abs(event.provider_timestamp - action.provider_timestamp) <= window
            ):
                picked.setdefault(event.provider_event_id, event)
    return sorted(
        picked.values(),
        key=lambda event: (
            event.provider_timestamp.isoformat()
            if event.provider_timestamp
            else "",
            event.provider_event_id,
        ),
    )


def build_capture(
    db: Session, workspace_id: uuid.UUID, portfolio_public_id: uuid.UUID
) -> dict:
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.workspace_id == workspace_id,
            Portfolio.public_id == portfolio_public_id,
        )
        .one()
    )
    run = (
        db.query(BrokerSyncRun)
        .filter(
            BrokerSyncRun.workspace_id == workspace_id,
            BrokerSyncRun.portfolio_id == portfolio.id,
            BrokerSyncRun.state == "needs_review",
        )
        .order_by(BrokerSyncRun.created_at.desc())
        .first()
    )
    if run is None:
        raise SystemExit("No needs_review run found for this portfolio.")
    events = (
        db.query(BrokerSyncEvent)
        .filter(
            BrokerSyncEvent.workspace_id == workspace_id,
            BrokerSyncEvent.run_id == run.id,
        )
        .all()
    )
    id_map: dict[str, str] = {}
    return {
        "source": "t212 staged broker_sync_events (redacted)",
        "events": [
            {
                "stream": event.stream,
                "fill_type": _fill_type(event),
                "provider_timestamp": (
                    event.provider_timestamp.isoformat()
                    if event.provider_timestamp
                    else None
                ),
                "payload": redact_payload(event.raw_payload, id_map),
            }
            for event in select_capture_events(events)
        ],
    }


def main() -> None:
    from database import SessionLocal
    from jobs import _set_job_workspace_context

    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=uuid.UUID)
    parser.add_argument("--portfolio", required=True, type=uuid.UUID)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        _set_job_workspace_context(db, args.workspace)
        capture = build_capture(db, args.workspace, args.portfolio)
    finally:
        db.close()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    first = next(
        (event for event in capture["events"] if event["fill_type"] != "TRADE"),
        None,
    )
    stem = "capture"
    if first:
        ticker = (first["payload"].get("order") or {}).get("ticker", "unknown")
        stem = f"{ticker}_{(first['provider_timestamp'] or 'nodate')[:10]}"
    path = OUTPUT_DIR / f"{stem}.json"
    path.write_text(json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(capture['events'])} events to {path}. Review before committing.")


if __name__ == "__main__":
    main()
