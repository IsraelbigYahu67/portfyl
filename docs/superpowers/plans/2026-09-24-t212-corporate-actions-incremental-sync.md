# T212 Corporate Actions, Review Loop, and Incremental Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four items left open after commit `6ff6c15`: get real
split payloads, stop the `needs_review` re-download loop now, build the
`STOCK_SPLIT` mapper and corporate-action records once real payloads exist, and
deliver the parent plan's Task 5 (incremental sync and 30-day audits).

**Architecture:** The work runs in three tracks with one hard gate.
Track A needs no provider knowledge. It captures the split payloads already
staged in `broker_sync_events`, records why each run needed review, and stops
syncs from re-staging the full history into the same dead end. Track B (the
split mapper plus the `BrokerCorporateAction`/application tables) is gated on
**G1**, a written, human-approved encoding record built from those captured
payloads. Track C (per-stream coverage checkpoints, incremental stop rule,
audit runs) depends only on Track A and can proceed in parallel with Track B.
Portfolios with splits get incremental sync once Track B lands.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL forced RLS,
`httpx`, pytest (fast SQLite suite + `tests/postgres/`), React 18,
TanStack Query, Vitest.

**Spec:** `docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md`
(§4.4, §4.6, §5.5, §6, §7, §10 Tasks 4–5, §11). Read §6 and §7 in full before
Track B or Track C.

## Global Constraints

- Never guess provider encoding for financial data. No code may change share
  counts or prices from a `STOCK_SPLIT` fill until gate **G1** is signed off.
- Only same-instrument `STOCK_SPLIT` gets a mechanical transform (parent §6.2.8).
  `STOCK_DISTRIBUTION`, `SPIN_OFF`, `STOCK_ACQUISITION`, `FOP`,
  `FOP_CORRECTION` and every unknown `fill.type` stay `needs_review`.
- Yfinance evidence may only confirm plausibility. It never creates, applies,
  or deletes anything (parent §6.2.9).
- One provider action has exactly one quantity-changing representation. That
  is either CSV `split_open`/`split_close` rows or normalized API trades plus
  application records, never both (parent §4.6, §6.2.7).
- No adjustment transactions to force ledger and snapshot to agree (parent §3).
- Every change under `backend/alembic/versions/` updates
  `backend/database.py`'s `EXPECTED_ALEMBIC_HEAD` in the same commit. Alembic
  must have exactly one head. The current head is `0018_t212_account_binding`.
- Every new tenant table gets composite workspace FKs, forced RLS with
  `<table>_tenant_policy`, explicit `portfyl_runtime` table + sequence grants,
  cascade on portfolio delete, and workspace-export/account-deletion coverage.
  Copy the loop at the end of `0015_broker_sync_runs.py` exactly.
- Raw staged payloads are never logged, never exported in workspace export,
  and never returned by an API. Review details carry only fill type, ticker,
  and date.
- Captured fixtures are the user's real account data. They are written
  locally and **not committed** until the user reviews them (Task A1).
- Before starting any task, run `git status` and check for concurrent Codex
  edits (the user runs Claude Code and Codex in parallel on this repo). Do
  not commit files you did not write.

## File Structure

| File | Responsibility | Track |
|---|---|---|
| `backend/scripts/__init__.py` (new, empty) | package marker | A |
| `backend/scripts/t212_capture_corporate_actions.py` (new) | read-only, redacting export of staged non-TRADE fills + same-instrument neighbours to a local fixture | A |
| `backend/tests/test_t212_capture.py` (new) | redaction + selection tests | A |
| `docs/research/t212-corporate-action-encoding.md` (new) | G1 decision record: observed encoding, answered questions, sign-off | A→B gate |
| `backend/alembic/versions/0019_sync_run_review_details.py` (new) | `broker_sync_runs.review_details` JSON | A |
| `backend/t212_sync.py` | review details, `SUPPORTED_CORPORATE_ACTION_TYPES`, `history_run_decision()` | A, B, C |
| `backend/routers/broker.py` | sync uses the decision; `POST /trading212/history/retry`; `review` block on history-status | A |
| `frontend/src/api.js`, `frontend/src/hooks/useT212Sync.js`, `frontend/src/pages/Settings.jsx` | review panel, retry, CSV guidance | A |
| `backend/alembic/versions/0020_broker_corporate_actions.py` (new) | two tenant tables | B |
| `backend/t212_corporate_actions.py` (new) | pair collapse, ratio, application (pure functions + DB apply) | B |
| `backend/tests/fixtures/t212_corporate_actions/*.json` (new, from A1 after review) | real split payload fixtures | B |
| `backend/import_undo.py`, `backend/workspace_export.py` | capture/restore actions + applications (undo schema v3) | B |
| `backend/alembic/versions/0021_t212_history_coverage.py` (new) | per-stream frontier + audit timestamps on `broker_connections`; run stop-rule state | C |
| `backend/t212_incremental.py` (new) | stop-rule evaluation, monotonic check (pure) | C |
| `backend/jobs.py` | autosync audit creation passes through `history_run_decision` | C |
| `backend/data_retention.py` | staged-event retention that never deletes an uncaptured `needs_review` run's events | C |

---

# Track A — No provider knowledge required

### Task A1: Capture staged corporate-action payloads

The user's own `needs_review` runs already hold the unknown split payloads.
Staging retention is not implemented yet (see `backend/data_retention.py`,
which does not touch `broker_sync_events`). This tool extracts them safely.

**Files:**
- Create: `backend/scripts/__init__.py` (empty)
- Create: `backend/scripts/t212_capture_corporate_actions.py`
- Modify: `.gitignore`
- Test: `backend/tests/test_t212_capture.py`

**Interfaces:**
- Produces: `redact_payload(payload: dict, id_map: dict[str, str]) -> dict`,
  `select_capture_events(events: list[BrokerSyncEvent], *, window_days: int = 3) -> list[BrokerSyncEvent]`,
  `build_capture(db, workspace_id: uuid.UUID, portfolio_public_id: uuid.UUID) -> dict`.
  The CLI writes `backend/tests/fixtures/t212_corporate_actions/_captured/<ticker>_<date>.json`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_t212_capture.py
from datetime import datetime

from models import BrokerSyncEvent
from scripts.t212_capture_corporate_actions import redact_payload, select_capture_events


def _ev(event_id, ticker, filled_at, fill_type="TRADE", stream="orders"):
    return BrokerSyncEvent(
        stream=stream,
        provider_event_id=event_id,
        provider_timestamp=datetime.fromisoformat(filled_at.replace("Z", "+00:00")),
        raw_payload={
            "order": {"id": 123456789, "ticker": ticker, "side": "BUY",
                      "instrument": {"currency": "USD", "isin": "US67066G1040"}},
            "fill": {"id": 987654321, "type": fill_type, "quantity": 9.0,
                     "price": 120.5, "filledAt": filled_at,
                     "walletImpact": {"netValue": -1084.5, "currency": "USD"}},
        },
    )


def test_redaction_replaces_identifiers_but_keeps_economics():
    id_map: dict[str, str] = {}
    out = redact_payload(_ev("fill:1", "NVDA_US_EQ", "2024-06-10T10:00:00Z").raw_payload, id_map)
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
    out = redact_payload({"accountId": 42, "reference": "abc", "fill": {"id": 1}}, {})
    assert "accountId" not in out
    assert out["reference"].startswith("id-")


def test_selection_keeps_actions_and_same_ticker_neighbours_only():
    events = [
        _ev("fill:s1", "NVDA_US_EQ", "2024-06-10T04:00:00Z", "STOCK_SPLIT"),
        _ev("fill:s2", "NVDA_US_EQ", "2024-06-10T04:00:00Z", "STOCK_SPLIT"),
        _ev("fill:t1", "NVDA_US_EQ", "2024-06-08T15:00:00Z"),  # within window
        _ev("fill:t2", "NVDA_US_EQ", "2024-05-01T15:00:00Z"),  # outside window
        _ev("fill:t3", "AAPL_US_EQ", "2024-06-10T15:00:00Z"),  # other ticker
    ]
    picked = {e.provider_event_id for e in select_capture_events(events, window_days=3)}
    assert picked == {"fill:s1", "fill:s2", "fill:t1"}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_t212_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.t212_capture_corporate_actions'`

- [ ] **Step 3: Implement**

```python
# backend/scripts/t212_capture_corporate_actions.py
"""Read-only capture of staged Trading 212 corporate-action fills.

Unblocks plan 2026-09-24 Track B: the provider docs do not specify how a
STOCK_SPLIT fill pair encodes quantity/sign/price, but the owner's own
needs_review runs already staged real examples. This tool exports them, with
identifiers replaced by stable placeholders, for a human to inspect.

Usage (from backend/, runtime DATABASE_URL, never the migration owner):
    python -m scripts.t212_capture_corporate_actions \
        --workspace <workspace uuid> --portfolio <portfolio public_id>

Output lands in tests/fixtures/t212_corporate_actions/_captured/ which is
git-ignored. Review every file before copying it into the committed
fixture directory.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from models import BrokerSyncEvent, BrokerSyncRun, Portfolio

_ID_KEYS = {"id", "reference", "parentOrder", "orderId", "fillId"}
_DROP_KEYS = {"accountId", "accountNumber", "clientId"}
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "t212_corporate_actions" / "_captured"
)


def redact_payload(payload, id_map: dict[str, str]):
    if isinstance(payload, list):
        return [redact_payload(item, id_map) for item in payload]
    if not isinstance(payload, dict):
        return payload
    out = {}
    for key, value in payload.items():
        if key in _DROP_KEYS:
            continue
        if key in _ID_KEYS and value is not None and not isinstance(value, (dict, list)):
            raw = str(value)
            if raw not in id_map:
                id_map[raw] = f"id-{len(id_map) + 1:04d}"
            out[key] = id_map[raw]
        else:
            out[key] = redact_payload(value, id_map)
    return out


def _fill_type(event: BrokerSyncEvent) -> str:
    raw = ((event.raw_payload or {}).get("fill") or {}).get("type") or "TRADE"
    return raw.upper()


def _ticker(event: BrokerSyncEvent) -> str | None:
    return ((event.raw_payload or {}).get("order") or {}).get("ticker")


def select_capture_events(events: list[BrokerSyncEvent], *, window_days: int = 3) -> list[BrokerSyncEvent]:
    orders = [e for e in events if e.stream == "orders"]
    actions = [e for e in orders if _fill_type(e) != "TRADE"]
    window = timedelta(days=window_days)
    picked: dict[str, BrokerSyncEvent] = {e.provider_event_id: e for e in actions}
    for action in actions:
        if action.provider_timestamp is None:
            continue
        for e in orders:
            if (
                _ticker(e) == _ticker(action)
                and e.provider_timestamp is not None
                and abs(e.provider_timestamp - action.provider_timestamp) <= window
            ):
                picked.setdefault(e.provider_event_id, e)
    return sorted(picked.values(), key=lambda e: (e.provider_timestamp.isoformat()
                                                  if e.provider_timestamp else "", e.provider_event_id))


def build_capture(db: Session, workspace_id: uuid.UUID, portfolio_public_id: uuid.UUID) -> dict:
    portfolio = db.query(Portfolio).filter(
        Portfolio.workspace_id == workspace_id, Portfolio.public_id == portfolio_public_id,
    ).one()
    run = (
        db.query(BrokerSyncRun)
        .filter(BrokerSyncRun.workspace_id == workspace_id,
                BrokerSyncRun.portfolio_id == portfolio.id,
                BrokerSyncRun.state == "needs_review")
        .order_by(BrokerSyncRun.created_at.desc())
        .first()
    )
    if run is None:
        raise SystemExit("No needs_review run found for this portfolio.")
    events = db.query(BrokerSyncEvent).filter(
        BrokerSyncEvent.workspace_id == workspace_id, BrokerSyncEvent.run_id == run.id,
    ).all()
    id_map: dict[str, str] = {}
    return {
        "source": "t212 staged broker_sync_events (redacted)",
        "events": [
            {"stream": e.stream, "fill_type": _fill_type(e),
             "provider_timestamp": e.provider_timestamp.isoformat() if e.provider_timestamp else None,
             "payload": redact_payload(e.raw_payload, id_map)}
            for e in select_capture_events(events)
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
    first = next((e for e in capture["events"] if e["fill_type"] != "TRADE"), None)
    stem = "capture"
    if first:
        ticker = (first["payload"].get("order") or {}).get("ticker", "unknown")
        stem = f"{ticker}_{(first['provider_timestamp'] or 'nodate')[:10]}"
    path = OUTPUT_DIR / f"{stem}.json"
    path.write_text(json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(capture['events'])} events to {path}. Review before committing.")


if __name__ == "__main__":
    main()
```

Before relying on `_set_job_workspace_context(db, workspace_id)` and
`database.SessionLocal`, confirm both signatures in `backend/jobs.py` and
`backend/database.py`. If a name differs, use the real one. Do not write a
new RLS helper.

Append to `.gitignore`:

```
backend/tests/fixtures/t212_corporate_actions/_captured/
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_t212_capture.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/t212_capture_corporate_actions.py backend/tests/test_t212_capture.py .gitignore
git commit -m "feat(t212): read-only redacting capture of staged corporate-action fills"
```

- [ ] **Step 6 (user-run, not agent): capture**

The user runs the CLI against their own database (local, or Neon with the
runtime credential) for every portfolio whose history-status shows
`needs_review`. If no portfolio has one, use the fallback: a T212 **demo**
account with an instrument that split, connected in a disposable local
portfolio. The user also exports the T212 CSV covering the same split dates,
which is needed for question 10 in A2.

---

### Task A2: Gate G1 — encoding decision record

This task is a document plus a human sign-off. No code. **Track B may not start
until the "Sign-off" line is filled in.**

**Files:**
- Create: `docs/research/t212-corporate-action-encoding.md`
- Create (copied after approval): `backend/tests/fixtures/t212_corporate_actions/stock_split_<forward|reverse>_<num>-<den>.json`

- [ ] **Step 1: Write the record from the captured files**

Answer each question with a quoted excerpt from a captured fixture:

```markdown
# Trading 212 corporate-action fill encoding (observed)

Sources: <list of _captured/*.json files, ticker, date, known split ratio from
the issuer's announcement>

## STOCK_SPLIT
1. How many fills per split event? (one net delta / close+open pair / other)
2. Do both legs share `order.id`? `filledAt`? `order.ticker`?
3. Leg direction: `order.side` values, and sign of `fill.quantity` per leg.
4. Quantity meaning: old total / new total / delta?
5. `fill.price` per leg: pre-split price, post-split price, 0, or absent?
6. `fill.walletImpact`: present? netValue non-zero? (must be 0 for a pure split)
7. Fractional remainder / cash-in-lieu: where does it appear?
8. Does the ratio derived from (1)–(5) equal the issuer's announced ratio?
9. Reverse split example available? Same encoding?
10. Matching T212 CSV rows for the same event ("Stock split open/close"):
    shares and price per leg, and the `ID` column value vs API `fill.id`.

## Other non-TRADE types seen
<type, count, one redacted example each; these remain needs_review>

## Decision
Chosen pair-collapse rule: <exact rule>
Ratio formula: <exact formula>
Differences from hypothesis H1 (plan Track B header): <none / list>

Sign-off: <name, date>. Mapper may be implemented against this record.
```

- [ ] **Step 2: Copy approved fixtures**

After the user approves, copy the reviewed files from `_captured/` to
`backend/tests/fixtures/t212_corporate_actions/`. Name them
`stock_split_<forward|reverse>_<num>-<den>.json` so B2's parametrized test can
read the issuer ratio from the file name.

- [ ] **Step 3: Commit**

```bash
git add docs/research/t212-corporate-action-encoding.md backend/tests/fixtures/t212_corporate_actions/*.json
git commit -m "docs(t212): record observed STOCK_SPLIT fill encoding (gate G1)"
```

---

### Task A3: Persist why a run needed review

**Files:**
- Create: `backend/alembic/versions/0019_sync_run_review_details.py`
- Modify: `backend/models.py` (`BrokerSyncRun`, after `last_error`)
- Modify: `backend/database.py:56` (`EXPECTED_ALEMBIC_HEAD`)
- Modify: `backend/t212_sync.py:743-769` (`_send_run_to_needs_review`) and its call site `:1011-1018`
- Test: `backend/tests/test_t212_finalize.py`

**Interfaces:**
- Produces: `BrokerSyncRun.review_details: list[dict] | None`, where each item is
  `{"fill_type": str, "ticker": str | None, "date": "YYYY-MM-DD" | None}`,
  deduplicated, sorted by date, and capped at `REVIEW_DETAILS_LIMIT = 50`.
  Also `t212_sync.SUPPORTED_CORPORATE_ACTION_TYPES: frozenset[str] = frozenset()`.

- [ ] **Step 1: Write the failing test**

Add it to the class in `test_t212_finalize.py` that holds
`test_corporate_action_fill_sends_run_to_needs_review_without_ledger_writes`:

```python
    def test_needs_review_records_bounded_review_details(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:a",
                     ticker="NVDA_US_EQ", day="2024-06-10", fill_type="STOCK_SPLIT")
        _order_event(db_session, completed_run, event_id="fill:b",
                     ticker="GE_US_EQ", day="2024-04-02", fill_type="SPIN_OFF")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(completed_run)
        assert completed_run.review_details == [
            {"fill_type": "SPIN_OFF", "ticker": "GE", "date": "2024-04-02"},
            {"fill_type": "STOCK_SPLIT", "ticker": "NVDA", "date": "2024-06-10"},
        ]
        assert all(set(d) == {"fill_type", "ticker", "date"} for d in completed_run.review_details)
```

The expected tickers assume `t212_sync._normalize_t212_ticker("NVDA_US_EQ") == "NVDA"`.
Check with one REPL call. If it differs, assert the function's real output.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_t212_finalize.py -k review_details -v`
Expected: FAIL (`review_details` attribute/column missing)

- [ ] **Step 3: Implement**

Model (`backend/models.py`, inside `BrokerSyncRun`, after `last_error`):

```python
    # Bounded, payload-free summary of why a run ended in needs_review
    # (fill type, normalized ticker, date). Never the raw provider payload.
    review_details = Column(JSON, nullable=True)
```

Migration:

```python
"""Record why a T212 history run needed review.

Revision ID: 0019_sync_run_review_details
Revises: 0018_t212_account_binding
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_sync_run_review_details"
down_revision: Union[str, Sequence[str], None] = "0018_t212_account_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broker_sync_runs", sa.Column("review_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_sync_runs", "review_details")
```

`backend/database.py`: `EXPECTED_ALEMBIC_HEAD = "0019_sync_run_review_details"`.

`backend/t212_sync.py`, next to `TERMINAL_RUN_STATES`:

```python
REVIEW_DETAILS_LIMIT = 50
# fill.type values finalize_run can transform. Empty until gate G1 (plan
# 2026-09-24 Task A2) is signed off and Task B3 lands.
SUPPORTED_CORPORATE_ACTION_TYPES: frozenset[str] = frozenset()


def _review_details(events: list[BrokerSyncEvent]) -> list[dict]:
    seen: set[tuple] = set()
    details: list[dict] = []
    for event in events:
        order = (event.raw_payload or {}).get("order") or {}
        raw_ticker = (order.get("ticker") or "").strip()
        when = _staged_event_time(event)
        item = {
            "fill_type": _corporate_action_type(event),
            "ticker": _normalize_t212_ticker(raw_ticker) if raw_ticker else None,
            "date": when.date().isoformat() if when else None,
        }
        key = (item["fill_type"], item["ticker"], item["date"])
        if key not in seen:
            seen.add(key)
            details.append(item)
    details.sort(key=lambda d: (d["date"] or "", d["fill_type"] or "", d["ticker"] or ""))
    return details[:REVIEW_DETAILS_LIMIT]
```

Change the signature to `_send_run_to_needs_review(db, run, events: list[BrokerSyncEvent])`.
Inside it, compute
`action_types = sorted({_corporate_action_type(e) for e in events} - {None})`,
set `run.review_details = _review_details(events)`, and keep the rest.
In `finalize_run`, replace the `unsupported` set comprehension with:

```python
        unsupported_events = [
            event for event in events
            if (action := _corporate_action_type(event)) is not None
            and action not in SUPPORTED_CORPORATE_ACTION_TYPES
            and not _is_csv_covered(event, csv_covered_through)
        ]
        if unsupported_events:
            return _send_run_to_needs_review(db, run, unsupported_events)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_t212_finalize.py tests/test_broker_backfill.py -v`
Expected: all pass (existing `unsupported_action_types` assertions unchanged)

- [ ] **Step 5: Verify migration head**

Run: `cd backend && alembic heads`
Expected: `0019_sync_run_review_details (head)`. If PostgreSQL is available,
also run `alembic upgrade head` with the migration-owner credential.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0019_sync_run_review_details.py backend/models.py backend/database.py backend/t212_sync.py backend/tests/test_t212_finalize.py
git commit -m "feat(t212): record payload-free review details on needs_review runs"
```

---

### Task A4: Break the needs_review re-download loop

Today every manual sync and every autosync (`broker_autosync_pass` calls
`sync_transactions`, `backend/jobs.py:264-304`) calls `claim_or_create_run`.
Each new run re-stages the full history and ends in `needs_review` again.
After this task, the snapshot still refreshes, but no new history run is
created while the blocking reason is unchanged.

**Files:**
- Modify: `backend/t212_sync.py` (new `HistoryDecision`, `review_resolution`, `history_run_decision` after `claim_or_create_run`)
- Modify: `backend/routers/broker.py:581-660` (`sync_transactions`), `:280-345` (history-status), new retry route
- Test: `backend/tests/test_t212_sync_runs.py`, `backend/tests/test_broker.py`, `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `BrokerSyncRun.review_details`, `SUPPORTED_CORPORATE_ACTION_TYPES` (A3).
- Produces:
  - `t212_sync.HistoryDecision(action: str, run: BrokerSyncRun | None, mode: str = "incremental")`,
    where `action` ∈ `{"reuse", "create", "blocked"}` (`mode` is used by C1/C3).
  - `t212_sync.history_run_decision(db, connection, portfolio, *, force: bool = False) -> HistoryDecision`.
  - `t212_sync.review_resolution(run, connection, portfolio) -> dict`, which returns
    `{"csv_covers_all": bool, "csv_needed_through": "YYYY-MM-DD" | None, "mapper_supports_all": bool}`.
  - `POST /api/broker/trading212/history/retry`, returning `{"run_id", "status", "complete": False, "blocked": False}`.
  - `sync_transactions`' `history` block gains `"blocked": bool`.
  - history-status `run` gains
    `"review": {"items": [...], "csv_covers_all", "csv_needed_through", "mapper_supports_all"} | None`.

Decision rule. Only the **latest** run for the connection matters:

| latest run | condition | action |
|---|---|---|
| non-terminal | — | `reuse` |
| `needs_review` | `force=True` | `create` |
| `needs_review` | review items non-empty and every type ∈ `SUPPORTED_CORPORATE_ACTION_TYPES` | `create` |
| `needs_review` | CSV coverage (max of portfolio/connection `t212_csv_covered_through`) ≥ start of the day after the latest review date (UTC) | `create` |
| `needs_review` | otherwise, including legacy runs with `review_details IS NULL` | `blocked` |
| none / other terminal | — | `create` |

- [ ] **Step 1: Write failing unit tests** (`backend/tests/test_t212_sync_runs.py`; reuse the file's connection/portfolio fixtures and adapt fixture names to what it defines)

```python
from datetime import datetime, timezone

import t212_sync
from models import BrokerSyncRun

SPLIT = [{"fill_type": "STOCK_SPLIT", "ticker": "NVDA", "date": "2024-06-10"}]


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


def test_blocked_when_needs_review_is_unresolved(db_session, default_portfolio, connection):
    run = _review_run(db_session, connection, default_portfolio, SPLIT)
    decision = t212_sync.history_run_decision(db_session, connection, default_portfolio)
    assert decision.action == "blocked"
    assert decision.run.id == run.id


def test_force_creates_a_new_run(db_session, default_portfolio, connection):
    _review_run(db_session, connection, default_portfolio, SPLIT)
    decision = t212_sync.history_run_decision(db_session, connection, default_portfolio, force=True)
    assert decision.action == "create"


def test_csv_coverage_past_last_action_unblocks(db_session, default_portfolio, connection):
    _review_run(db_session, connection, default_portfolio, SPLIT)
    connection.t212_csv_covered_through = datetime(2024, 6, 11, tzinfo=timezone.utc)
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).action == "create"


def test_csv_coverage_inside_action_day_stays_blocked(db_session, default_portfolio, connection):
    _review_run(db_session, connection, default_portfolio, SPLIT)
    connection.t212_csv_covered_through = datetime(2024, 6, 10, 12, tzinfo=timezone.utc)
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).action == "blocked"


def test_newly_supported_type_unblocks(db_session, default_portfolio, connection, monkeypatch):
    _review_run(db_session, connection, default_portfolio, SPLIT)
    monkeypatch.setattr(t212_sync, "SUPPORTED_CORPORATE_ACTION_TYPES", frozenset({"STOCK_SPLIT"}))
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).action == "create"


def test_legacy_needs_review_without_details_is_blocked(db_session, default_portfolio, connection):
    _review_run(db_session, connection, default_portfolio, None)
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).action == "blocked"


def test_failed_latest_run_creates(db_session, default_portfolio, connection):
    run = _review_run(db_session, connection, default_portfolio, SPLIT)
    run.state = "failed"
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).action == "create"
```

- [ ] **Step 2: Write failing route/job tests**

In `backend/tests/test_broker.py`, next to
`test_needs_review_run_is_not_reported_as_retrying`, add these two tests.
Patch `t212_sync.fetch_snapshot` the same way that file's existing
`sync_transactions` tests do, and build the needs_review run with the
`_review_run` shape above:

```python
    def test_sync_refreshes_snapshot_but_creates_no_run_when_blocked(self, db_session, default_portfolio, connection):
        # arrange: needs_review run with SPLIT details; fetch_snapshot patched to succeed
        result = sync_transactions(db=db_session, portfolio=default_portfolio, _context=None)
        assert result["snapshot"]["status"] == "ready"
        assert result["history"]["status"] == "needs_review"
        assert result["history"]["blocked"] is True
        assert db_session.query(BrokerSyncRun).count() == 1

    def test_retry_route_creates_new_run(self, db_session, default_portfolio, connection):
        # arrange: needs_review run with SPLIT details
        result = retry_history(db=db_session, portfolio=default_portfolio, _context=None)
        assert result["status"] == "pending"
        assert result["blocked"] is False
        assert db_session.query(BrokerSyncRun).count() == 2
```

In `backend/tests/test_jobs.py`, add a test asserting that
`broker_autosync_pass` over an `auto_sync=True` connection whose latest run is
an unresolved `needs_review` leaves `BrokerSyncRun` count unchanged. Copy the
setup of that file's existing autosync test.

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_t212_sync_runs.py tests/test_broker.py tests/test_jobs.py -k "blocked or force or csv_coverage or supported or retry or legacy_needs_review or failed_latest" -v`
Expected: FAIL with `AttributeError: module 't212_sync' has no attribute 'history_run_decision'`

- [ ] **Step 4: Implement in `backend/t212_sync.py`** (after `claim_or_create_run`)

```python
@dataclass(frozen=True)
class HistoryDecision:
    action: str  # "reuse" | "create" | "blocked"
    run: BrokerSyncRun | None
    mode: str = "incremental"


def _latest_run(db: Session, connection: BrokerConnection) -> BrokerSyncRun | None:
    return (
        db.query(BrokerSyncRun)
        .filter(BrokerSyncRun.workspace_id == connection.workspace_id,
                BrokerSyncRun.connection_id == connection.id)
        .order_by(BrokerSyncRun.created_at.desc(), BrokerSyncRun.id.desc())
        .first()
    )


def review_resolution(run: BrokerSyncRun, connection: BrokerConnection, portfolio: Portfolio) -> dict:
    details = run.review_details or []
    dates = [d["date"] for d in details if d.get("date")]
    needed = max(dates) if dates else None
    coverage = _latest_csv_coverage(portfolio.t212_csv_covered_through,
                                    connection.t212_csv_covered_through)
    # _is_csv_covered compares exact event timestamps, so coverage must pass
    # the end of the action's calendar day to guarantee every leg is covered.
    csv_covers_all = bool(
        needed and coverage is not None
        and coverage >= datetime.fromisoformat(needed).replace(tzinfo=timezone.utc) + timedelta(days=1)
    )
    types = {d.get("fill_type") for d in details}
    mapper_supports_all = bool(details) and types <= SUPPORTED_CORPORATE_ACTION_TYPES
    return {"csv_covers_all": csv_covers_all, "csv_needed_through": needed,
            "mapper_supports_all": mapper_supports_all}


def history_run_decision(
    db: Session, connection: BrokerConnection, portfolio: Portfolio, *, force: bool = False,
) -> HistoryDecision:
    latest = _latest_run(db, connection)
    if latest is not None and latest.state not in TERMINAL_RUN_STATES:
        return HistoryDecision("reuse", latest, latest.mode)
    if latest is not None and latest.state == "needs_review" and not force:
        res = review_resolution(latest, connection, portfolio)
        if not (res["csv_covers_all"] or res["mapper_supports_all"]):
            return HistoryDecision("blocked", latest, latest.mode)
    return HistoryDecision("create", None)
```

- [ ] **Step 5: Wire routes in `backend/routers/broker.py`**

In `sync_transactions`, replace
`history_run = t212_sync.claim_or_create_run(db, conn, portfolio)`:

```python
    decision = t212_sync.history_run_decision(db, conn, portfolio)
    if decision.action == "blocked":
        history_run, blocked = decision.run, True
    else:
        history_run, blocked = t212_sync.claim_or_create_run(db, conn, portfolio), False
```

and add `"blocked": blocked,` to the returned `history` dict.

Directly below `sync_transactions`, add the retry route. Copy the
`@router.post("/trading212/sync", ...)` decorator's `dependencies=[...]` list
verbatim onto it:

```python
@router.post("/trading212/history/retry")
def retry_history(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="Trading 212 is not connected")
    decision = t212_sync.history_run_decision(db, conn, portfolio, force=True)
    run = decision.run if decision.action == "reuse" else t212_sync.claim_or_create_run(db, conn, portfolio)
    db.commit()
    return {"run_id": str(run.public_id), "status": run.state, "complete": False, "blocked": False}
```

In history-status's returned `run` dict, add:

```python
            "review": (
                {"items": run.review_details or [],
                 **t212_sync.review_resolution(run, conn, portfolio)}
                if run.state == "needs_review" else None
            ),
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && python -m pytest tests/test_t212_sync_runs.py tests/test_broker.py tests/test_jobs.py tests/test_broker_backfill.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/t212_sync.py backend/routers/broker.py backend/tests/test_t212_sync_runs.py backend/tests/test_broker.py backend/tests/test_jobs.py
git commit -m "fix(t212): stop re-staging full history into an unchanged needs_review"
```

---

### Task A5: Review panel, CSV guidance, and retry in Settings

**Files:**
- Modify: `frontend/src/api.js:303` (add `retryT212History`)
- Modify: `frontend/src/hooks/useT212Sync.js` (add `retryHistory`, `retryPending`)
- Modify: `frontend/src/pages/Settings.jsx:35-70` (`HistoryBackfillStatus`) and its call site `:199`
- Test: `frontend/src/hooks/useT212Sync.test.jsx`; `frontend/src/pages/Settings.test.jsx` (create if absent, following `src/pages/Overview.test.jsx` patterns)

**Interfaces:**
- Consumes: history-status `run.review` and `POST /broker/trading212/history/retry` (A4).
- Produces: `retryT212History(): Promise<{run_id, status, complete, blocked}>`;
  the hook returns `retryHistory: () => void` and `retryPending: boolean`;
  `HistoryBackfillStatus` is exported with props `{ run, onRetry, retryPending }`.

- [ ] **Step 1: Failing tests**

```jsx
// useT212Sync.test.jsx — mock ../api the way the file's existing tests do
it("retryHistory posts retry and refetches history status", async () => {
  api.retryT212History.mockResolvedValue({ run_id: "r2", status: "pending", complete: false, blocked: false });
  const { result } = renderHook(() => useT212Sync({ portfolioId: "p1" }), { wrapper });
  await waitFor(() => expect(api.fetchT212HistoryStatus).toHaveBeenCalled());
  const before = api.fetchT212HistoryStatus.mock.calls.length;
  await act(async () => { result.current.retryHistory(); });
  expect(api.retryT212History).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(api.fetchT212HistoryStatus.mock.calls.length).toBeGreaterThan(before));
});
```

```jsx
// Settings.test.jsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HistoryBackfillStatus } from "./Settings";

it("lists review items, the CSV date needed, and a retry button", () => {
  render(
    <MemoryRouter>
      <HistoryBackfillStatus
        run={{
          state: "needs_review", last_error: "Trading 212 history contains corporate actions",
          review: { items: [{ fill_type: "STOCK_SPLIT", ticker: "NVDA", date: "2024-06-10" }],
                    csv_needed_through: "2024-06-10", csv_covers_all: false, mapper_supports_all: false },
        }}
        onRetry={() => {}}
        retryPending={false}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText(/Stock split · NVDA · 2024-06-10/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Trading 212 CSV export/i })).toHaveAttribute("href", "/import");
  expect(screen.getByRole("button", { name: /Retry history import/i })).toBeEnabled();
});
```

If `Settings.jsx` imports modules that need providers (auth, query client)
at module level, wrap the render in the providers `Overview.test.jsx` uses.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hooks/useT212Sync.test.jsx src/pages/Settings.test.jsx`
Expected: FAIL (`retryT212History` is not a function / `HistoryBackfillStatus` not exported)

- [ ] **Step 3: Implement**

`api.js`, after `fetchT212HistoryStatus`:

```js
export const retryT212History = () => api.post("/broker/trading212/history/retry").then((r) => r.data);
```

`useT212Sync.js`: add `retryT212History` to the `../api` import, then add
this next to `syncMutation`, using the history query's real `queryKey`
from the same file:

```js
  const retryMutation = useMutation({
    mutationFn: retryT212History,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: historyQueryKey }),
  });
```

Return `retryHistory: retryMutation.mutate` and `retryPending: retryMutation.isPending`.

`Settings.jsx`: export `HistoryBackfillStatus`, accept `onRetry` and
`retryPending`, and render this block when
`run.state === "needs_review" && run.review`:

```jsx
const FILL_TYPE_LABEL = {
  STOCK_SPLIT: "Stock split",
  STOCK_DISTRIBUTION: "Stock distribution",
  SPIN_OFF: "Spin-off",
  STOCK_ACQUISITION: "Acquisition",
  FOP: "Free-of-payment transfer",
  FOP_CORRECTION: "Transfer correction",
};

{run.state === "needs_review" && run.review && (
  <div className="mt-2 space-y-2 text-xs">
    <ul className="space-y-0.5">
      {run.review.items.map((i) => (
        <li key={`${i.fill_type}-${i.ticker}-${i.date}`}>
          {FILL_TYPE_LABEL[i.fill_type] ?? i.fill_type} · {i.ticker ?? "unknown"} · {i.date ?? "unknown date"}
        </li>
      ))}
    </ul>
    {run.review.csv_needed_through && (
      <p>
        To import this history now, <Link to="/import">import a Trading 212 CSV export</Link> that
        covers at least through {run.review.csv_needed_through}, then retry.
      </p>
    )}
    <button type="button" onClick={onRetry} disabled={retryPending}>
      Retry history import
    </button>
  </div>
)}
```

Give the button the classes of the neighbouring secondary Settings buttons.
Add no new colours; use tokens from `index.css`. At `Settings.jsx:199`, pass
`onRetry={t212.retryHistory} retryPending={t212.retryPending}`.

- [ ] **Step 4: Run the gates**

Run: `cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/hooks/useT212Sync.js frontend/src/hooks/useT212Sync.test.jsx frontend/src/pages/Settings.jsx frontend/src/pages/Settings.test.jsx
git commit -m "feat(settings): explain T212 needs_review items with CSV guidance and retry"
```

---

# Track B — Split mapper (GATED on G1)

> **Do not start Track B until `docs/research/t212-corporate-action-encoding.md`
> has a filled "Sign-off" line.** The code below is written against
> **hypothesis H1**, which mirrors the T212 CSV representation Portfyl
> already imports (`backend/routers/portfolio.py:176-209`, and the tests in
> `backend/tests/test_cash_api.py:814-850`): a split is two same-instrument
> fills at the same `filledAt`. The *close* leg carries the old share count
> at the old price, and the *open* leg carries the new share count at the new
> price. `order.side` identifies the leg: `SELL` = close, `BUY` = open. If G1
> records a different leg encoding, change **only** `_leg_of()` and
> `collapse_split_pairs()` in B2 to match it, and update B2/B3's hand-built
> H1 test legs accordingly. If G1 shows a single net-delta fill, or
> non-zero `walletImpact`, stop and revise this track with the user.

### Task B1: Corporate-action and application tables

This task is encoding-agnostic. It may start once G1 is signed off, before B2.

**Files:**
- Create: `backend/alembic/versions/0020_broker_corporate_actions.py`
- Modify: `backend/models.py` (two classes after `BrokerSyncEvent`)
- Modify: `backend/database.py` (`EXPECTED_ALEMBIC_HEAD = "0020_broker_corporate_actions"`) — 0020 revises 0021, see Step 4
- Modify: `backend/workspace_export.py` (export both tables; bump export schema 3 → 4)
- Test: `backend/tests/test_account_export.py`, `backend/tests/postgres/test_integration_tenancy.py`

**Interfaces:**
- Produces:
  - `BrokerCorporateAction`. Columns: `id, public_id, workspace_id, portfolio_id, broker,
    account_fingerprint, provider_instrument_id, ticker, action_type, effective_at,
    provider_event_key, ratio_numerator, ratio_denominator, representation, run_id, created_at`.
    Unique on `(workspace_id, portfolio_id, account_fingerprint, provider_instrument_id,
    action_type, effective_at, provider_event_key)`.
    `representation` ∈ `{"api_normalized", "csv_rows"}`. `run_id` is an audit
    integer only, with no FK, because runs are purgeable operational data.
  - `BrokerCorporateActionApplication`. Columns: `id, workspace_id, action_id,
    transaction_id, shares_before, price_before, shares_after, price_after,
    applied_by_run_id, applied_at`. Unique on
    `(workspace_id, action_id, transaction_id)`. It uses the integer
    `transaction_id`, because CSV/legacy rows have no provider event id.

- [ ] **Step 1: Failing export test** (`test_account_export.py`)

```python
from datetime import datetime, timezone

from models import BrokerCorporateAction, BrokerCorporateActionApplication


def test_export_includes_corporate_actions_and_applications(db_session, default_portfolio):
    txn = make_txn("NVDA", "buy", 90, 120, portfolio_id=default_portfolio.id, source="t212_api")
    db_session.add(txn)
    db_session.flush()
    action = BrokerCorporateAction(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", account_fingerprint="f" * 64, provider_instrument_id="NVDA_US_EQ",
        ticker="NVDA", action_type="STOCK_SPLIT",
        effective_at=datetime(2024, 6, 10, tzinfo=timezone.utc), provider_event_key="fill:a|fill:b",
        ratio_numerator=10, ratio_denominator=1, representation="api_normalized",
    )
    db_session.add(action)
    db_session.flush()
    db_session.add(BrokerCorporateActionApplication(
        workspace_id=default_portfolio.workspace_id, action_id=action.id, transaction_id=txn.id,
        shares_before=9, price_before=1200, shares_after=90, price_after=120,
    ))
    db_session.commit()

    exported = _export(db_session, default_portfolio)  # the helper/entry point this file already uses

    assert exported["schema_version"] == 4
    [a] = exported["broker_corporate_actions"]
    assert a["action_type"] == "STOCK_SPLIT"
    assert float(a["ratio_numerator"]) == 10.0
    [ap] = exported["broker_corporate_action_applications"]
    assert ap["shares_after"] == 90
```

Export the account fingerprint exactly the way `workspace_export.py` treats
`transactions.source_account_fingerprint` today.

- [ ] **Step 2: Run → FAIL** (`ImportError: cannot import name 'BrokerCorporateAction'`)

Run: `cd backend && python -m pytest tests/test_account_export.py -k corporate -v`

- [ ] **Step 3: Implement models**

```python
class BrokerCorporateAction(Base):
    __tablename__ = "broker_corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "portfolio_id", "account_fingerprint", "provider_instrument_id",
            "action_type", "effective_at", "provider_event_key",
            name="uq_broker_corporate_action_identity",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_broker_corporate_action_workspace_id"),
        CheckConstraint("representation IN ('api_normalized', 'csv_rows')",
                        name="ck_broker_corporate_action_representation"),
        CheckConstraint("ratio_numerator > 0 AND ratio_denominator > 0",
                        name="ck_broker_corporate_action_ratio_positive"),
    )
    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True, nullable=False)
    workspace_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    portfolio_id = Column(Integer, nullable=False, index=True)
    broker = Column(String, nullable=False)
    account_fingerprint = Column(String(64), nullable=False)
    provider_instrument_id = Column(String, nullable=False)
    ticker = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    provider_event_key = Column(String, nullable=False)
    ratio_numerator = Column(Numeric(20, 10), nullable=False)
    ratio_denominator = Column(Numeric(20, 10), nullable=False)
    representation = Column(String, nullable=False)
    run_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BrokerCorporateActionApplication(Base):
    __tablename__ = "broker_corporate_action_applications"
    __table_args__ = (
        UniqueConstraint("workspace_id", "action_id", "transaction_id",
                         name="uq_broker_corporate_action_application"),
    )
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    action_id = Column(Integer, nullable=False, index=True)
    transaction_id = Column(Integer, nullable=False, index=True)
    shares_before = Column(Float, nullable=False)
    price_before = Column(Float, nullable=False)
    shares_after = Column(Float, nullable=False)
    price_after = Column(Float, nullable=False)
    applied_by_run_id = Column(Integer, nullable=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
```

Match the exact `public_id` declaration and imports `BrokerSyncRun` uses in
`models.py`. Add `Numeric`/`CheckConstraint` to the imports if missing.

- [ ] **Step 4: Migration** `0020_broker_corporate_actions.py` (`down_revision = "0021_t212_history_coverage"`;
  Track C shipped first and left the number 0020 free, so 0020 revises 0021 and
  `EXPECTED_ALEMBIC_HEAD` becomes `"0020_broker_corporate_actions"`)

Create both tables with columns matching the models and these composite FKs:
- actions: `["workspace_id", "portfolio_id"] → ["portfolios.workspace_id", "portfolios.id"]`, `ondelete="CASCADE"`;
- applications: `["workspace_id", "action_id"] → ["broker_corporate_actions.workspace_id", "broker_corporate_actions.id"]`, `ondelete="CASCADE"`,
  and `["workspace_id", "transaction_id"] → ["transactions.workspace_id", "transactions.id"]`, `ondelete="CASCADE"`.
  Check `transactions` for a `(workspace_id, id)` unique constraint first. If
  it has none, create one before the table, as 0015 did for `broker_connections`.

Indexes: `public_id` (unique), `workspace_id`, `portfolio_id` on actions;
`workspace_id`, `action_id`, `transaction_id` on applications. Then the RLS/grant loop:

```python
    for table in ("broker_corporate_actions", "broker_corporate_action_applications"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO portfyl_runtime")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO portfyl_runtime")
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (workspace_id = {_WORKSPACE_SETTING})
            WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
        """)
```

`_WORKSPACE_SETTING` is copied from 0015. `downgrade()` mirrors 0015's
downgrade: drop policy, no force, disable, revoke, drop indexes, drop tables
(applications first).

- [ ] **Step 5: Export + PostgreSQL tenancy test**

Add both tables to `workspace_export.py` and bump its schema version to 4.
In `tests/postgres/test_integration_tenancy.py`, extend the Alice/Bob matrix
the same way it covers `broker_sync_runs`: Bob can neither select nor insert
into either table under Alice's workspace, and deleting Alice's portfolio
cascades both.

- [ ] **Step 6: Run**

Run: `cd backend && python -m pytest tests/test_account_export.py -v && alembic heads`
If Docker is available: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait` then `python -m pytest tests/postgres/ -v`
Expected: pass; single head `0020_broker_corporate_actions`.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0020_broker_corporate_actions.py backend/models.py backend/database.py backend/workspace_export.py backend/tests/test_account_export.py backend/tests/postgres/test_integration_tenancy.py
git commit -m "feat(t212): durable corporate-action and application records (RLS)"
```

---

### Task B2: Pure split-pair collapse and ratio

**Files:**
- Create: `backend/t212_corporate_actions.py`
- Create: `backend/tests/test_t212_corporate_actions.py`
- Uses: `backend/tests/fixtures/t212_corporate_actions/stock_split_*.json` (A2)

**Interfaces:**
- Produces:
  - `SplitEvidence(provider_instrument_id: str, effective_at: datetime, provider_event_key: str, old_shares: Decimal, new_shares: Decimal, event_ids: tuple[str, ...])`,
    with property `ratio -> Fraction` (`new/old`, `limit_denominator(1000)`).
  - `class UnpairedSplitLeg(Exception)`.
  - `collapse_split_pairs(events: list[BrokerSyncEvent]) -> list[SplitEvidence]`, sorted by `(instrument, effective_at)`.

- [ ] **Step 1: Failing tests**

```python
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from models import BrokerSyncEvent
from t212_corporate_actions import UnpairedSplitLeg, collapse_split_pairs

FIXTURES = Path(__file__).parent / "fixtures" / "t212_corporate_actions"


def _events_from_fixture(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [
        BrokerSyncEvent(stream="orders", provider_event_id=f"fill:{i}", raw_payload=e["payload"])
        for i, e in enumerate(data["events"]) if e["fill_type"] == "STOCK_SPLIT"
    ]


def _h1_leg(event_id, side, qty, price, at="2024-06-10T04:00:00Z", ticker="NVDA_US_EQ"):
    return BrokerSyncEvent(stream="orders", provider_event_id=event_id, raw_payload={
        "order": {"ticker": ticker, "side": side},
        "fill": {"type": "STOCK_SPLIT", "quantity": qty, "price": price, "filledAt": at},
    })


def test_forward_split_pair_collapses_to_one_evidence():
    [ev] = collapse_split_pairs([_h1_leg("fill:a", "SELL", 9, 1200), _h1_leg("fill:b", "BUY", 90, 120)])
    assert ev.ratio == Fraction(10, 1)
    assert ev.provider_event_key == "fill:a|fill:b"
    assert (ev.old_shares, ev.new_shares) == (Decimal("9"), Decimal("90"))


def test_reverse_split_ratio_is_fractional():
    [ev] = collapse_split_pairs([_h1_leg("fill:a", "SELL", 10, 2), _h1_leg("fill:b", "BUY", 1, 20)])
    assert ev.ratio == Fraction(1, 10)


def test_unpaired_leg_raises():
    with pytest.raises(UnpairedSplitLeg):
        collapse_split_pairs([_h1_leg("fill:a", "SELL", 9, 1200)])


def test_non_split_events_are_ignored():
    trade = BrokerSyncEvent(stream="orders", provider_event_id="fill:t", raw_payload={
        "order": {"ticker": "NVDA_US_EQ", "side": "BUY"},
        "fill": {"type": "TRADE", "quantity": 1, "price": 1, "filledAt": "2024-06-10T04:00:00Z"},
    })
    assert collapse_split_pairs([trade]) == []


def test_order_of_events_does_not_matter():
    a, b = _h1_leg("fill:a", "SELL", 9, 1200), _h1_leg("fill:b", "BUY", 90, 120)
    assert collapse_split_pairs([b, a]) == collapse_split_pairs([a, b])


def test_two_instruments_same_time_are_separate():
    evs = collapse_split_pairs([
        _h1_leg("fill:a", "SELL", 9, 1200), _h1_leg("fill:b", "BUY", 90, 120),
        _h1_leg("fill:c", "SELL", 4, 400, ticker="AVGO_US_EQ"),
        _h1_leg("fill:d", "BUY", 40, 40, ticker="AVGO_US_EQ"),
    ])
    assert [e.provider_instrument_id for e in evs] == ["AVGO_US_EQ", "NVDA_US_EQ"]


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("stock_split_*.json")))
def test_real_fixture_ratio_matches_issuer(fixture):
    num, den = fixture.removesuffix(".json").rsplit("_", 1)[1].split("-")
    [ev] = collapse_split_pairs(_events_from_fixture(fixture))
    assert ev.ratio == Fraction(int(num), int(den))
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: No module named 't212_corporate_actions'`)

Run: `cd backend && python -m pytest tests/test_t212_corporate_actions.py -v`

- [ ] **Step 3: Implement** (`backend/t212_corporate_actions.py`)

```python
"""Trading 212 corporate-action normalization (plan 2026-09-24 Track B).

The leg encoding is defined by docs/research/t212-corporate-action-encoding.md
(gate G1). Only _leg_of and collapse_split_pairs know that encoding.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from models import BrokerSyncEvent
from t212_sync import _parse_t212_datetime


class UnpairedSplitLeg(Exception):
    """A STOCK_SPLIT leg without exactly one counterpart in the staged set."""


@dataclass(frozen=True)
class SplitEvidence:
    provider_instrument_id: str
    effective_at: datetime
    provider_event_key: str
    old_shares: Decimal
    new_shares: Decimal
    event_ids: tuple[str, ...]

    @property
    def ratio(self) -> Fraction:
        return Fraction(self.new_shares / self.old_shares).limit_denominator(1000)


def _leg_of(event: BrokerSyncEvent) -> str:
    # G1 / H1: SELL = close (old shares), BUY = open (new shares).
    side = (((event.raw_payload or {}).get("order") or {}).get("side") or "").upper()
    if side == "SELL":
        return "close"
    if side == "BUY":
        return "open"
    raise UnpairedSplitLeg(f"split leg {event.provider_event_id} has unknown side {side!r}")


def collapse_split_pairs(events: list[BrokerSyncEvent]) -> list[SplitEvidence]:
    groups: dict[tuple[str, datetime], dict[str, list[BrokerSyncEvent]]] = defaultdict(
        lambda: {"open": [], "close": []}
    )
    for event in events:
        payload = event.raw_payload or {}
        fill = payload.get("fill") or {}
        if (fill.get("type") or "").upper() != "STOCK_SPLIT":
            continue
        instrument = ((payload.get("order") or {}).get("ticker") or "").strip()
        at = _parse_t212_datetime(fill.get("filledAt"))
        if not instrument or at is None:
            raise UnpairedSplitLeg(f"split leg {event.provider_event_id} lacks instrument or time")
        groups[(instrument, at)][_leg_of(event)].append(event)

    out: list[SplitEvidence] = []
    for (instrument, at), legs in sorted(groups.items()):
        if len(legs["open"]) != 1 or len(legs["close"]) != 1:
            raise UnpairedSplitLeg(
                f"{instrument} at {at.isoformat()}: "
                f"{len(legs['close'])} close / {len(legs['open'])} open legs"
            )
        close, open_ = legs["close"][0], legs["open"][0]
        old = abs(Decimal(str(close.raw_payload["fill"]["quantity"])))
        new = abs(Decimal(str(open_.raw_payload["fill"]["quantity"])))
        if old <= 0 or new <= 0:
            raise UnpairedSplitLeg(f"{instrument} at {at.isoformat()}: non-positive leg quantity")
        ids = tuple(sorted((close.provider_event_id, open_.provider_event_id)))
        out.append(SplitEvidence(instrument, at, "|".join(ids), old, new, ids))
    return out
```

- [ ] **Step 4: Run → PASS**

Run: `cd backend && python -m pytest tests/test_t212_corporate_actions.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/t212_corporate_actions.py backend/tests/test_t212_corporate_actions.py
git commit -m "feat(t212): collapse STOCK_SPLIT fill pairs into split evidence (per G1)"
```

---

### Task B3: Apply splits in finalization

**Files:**
- Modify: `backend/t212_corporate_actions.py` (add `ApplySummary`, `apply_splits`)
- Modify: `backend/t212_sync.py` (`SUPPORTED_CORPORATE_ACTION_TYPES`, `_FINALIZE_MAPPER_VERSION = "t212_finalize_v2"`, `finalize_run`)
- Test: `backend/tests/test_t212_finalize.py`

**Interfaces:**
- Consumes: `collapse_split_pairs`, `SplitEvidence`, `UnpairedSplitLeg` (B2); models (B1); `_review_details` (A3).
- Produces: `ApplySummary(actions_created: int, applications_created: int, csv_represented: int)`;
  `apply_splits(db, *, run, portfolio, evidence: list[SplitEvidence], pending: list[Transaction]) -> ApplySummary`.

These rules run in order, inside the ledger lock `finalize_run` already holds:
1. Upsert one `BrokerCorporateAction` per evidence item by its unique identity.
2. **CSV already represents it:** when the portfolio has both a `split_open`
   and a `split_close` row for the same normalized ticker on
   `effective_at.date()`, a new action gets `representation="csv_rows"` and
   nothing is applied.
3. Otherwise `representation="api_normalized"`. Eligible rows are
   `buy`/`sell` rows for that ticker whose time
   (`executed_at`, else end of `date` in UTC) is before `effective_at`, and
   that are T212-origin: `source in {"t212_api", "t212_csv"}`, or `source`
   empty with `notes` starting `"T212"`. Both persisted rows and this run's
   `pending` rows are eligible. Actions are applied in `effective_at` order.
   Each eligible row without an application for this action gets
   `shares *= ratio` and `price /= ratio`, `cash_amount` untouched, plus one
   application row.
4. The application unique key is the only idempotency guard. Check it before
   mutating.
5. Manual rows (`source="manual"` or any other non-T212 source) are never touched.

- [ ] **Step 1: Failing tests** (`test_t212_finalize.py`)

First extend the `_order_event` helper with `side="BUY"`, if it doesn't
already take one, so split legs can be built. Then add:

```python
from models import BrokerCorporateAction, BrokerCorporateActionApplication


def _stage_split(db, run, ticker="NVDA_US_EQ", day="2024-06-10", old=9, new=90, old_px=1200, new_px=120):
    _order_event(db, run, event_id=f"fill:sc-{day}", ticker=ticker, side="SELL",
                 qty=old, price=old_px, day=day, fill_type="STOCK_SPLIT")
    _order_event(db, run, event_id=f"fill:so-{day}", ticker=ticker, side="BUY",
                 qty=new, price=new_px, day=day, fill_type="STOCK_SPLIT")


class TestSplitFinalization:
    @pytest.fixture(autouse=True)
    def _supported(self, monkeypatch):
        monkeypatch.setattr(t212_sync, "SUPPORTED_CORPORATE_ACTION_TYPES", frozenset({"STOCK_SPLIT"}))

    def test_split_adjusts_prior_api_trade_once(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=9, price=1200, day="2024-05-01")
        _stage_split(db_session, completed_run)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (90, 120)
        assert db_session.query(BrokerCorporateAction).one().representation == "api_normalized"
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)  # retry of completed run
        db_session.refresh(buy)
        assert (buy.shares, buy.price) == (90, 120)
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_trade_after_split_is_not_adjusted(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:t2", ticker="NVDA_US_EQ",
                     qty=5, price=125, day="2024-06-11")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (5, 125)
        assert db_session.query(BrokerCorporateActionApplication).count() == 0

    def test_split_adjusts_existing_t212_csv_trade(self, db_session, default_portfolio, completed_run):
        db_session.add(make_txn("NVDA", "buy", 9, 1200, date=date(2024, 5, 1),
                                portfolio_id=default_portfolio.id, source="t212_csv"))
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (90, 120)

    def test_csv_split_rows_represent_action_and_nothing_is_adjusted(
        self, db_session, default_portfolio, completed_run
    ):
        for t in (
            make_txn("NVDA", "buy", 9, 1200, date=date(2024, 5, 1), portfolio_id=default_portfolio.id, source="t212_csv"),
            make_txn("NVDA", "split_close", 9, 1200, date=date(2024, 6, 10), portfolio_id=default_portfolio.id, source="t212_csv"),
            make_txn("NVDA", "split_open", 90, 120, date=date(2024, 6, 10), portfolio_id=default_portfolio.id, source="t212_csv"),
        ):
            db_session.add(t)
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (9, 1200)
        assert db_session.query(BrokerCorporateAction).one().representation == "csv_rows"
        assert db_session.query(BrokerCorporateActionApplication).count() == 0

    def test_manual_trade_is_never_adjusted(self, db_session, default_portfolio, completed_run):
        db_session.add(make_txn("NVDA", "buy", 9, 1200, date=date(2024, 5, 1),
                                portfolio_id=default_portfolio.id, source="manual"))
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (9, 1200)

    def test_unpaired_split_leg_goes_to_needs_review(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:sc", ticker="NVDA_US_EQ", side="SELL",
                     qty=9, price=1200, day="2024-06-10", fill_type="STOCK_SPLIT")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.needs_review is True
        assert db_session.query(Transaction).count() == 0
        assert completed_run.review_details[0]["fill_type"] == "STOCK_SPLIT"

    def test_spin_off_still_needs_review_with_split_supported(self, db_session, default_portfolio, completed_run):
        _stage_split(db_session, completed_run)
        _order_event(db_session, completed_run, event_id="fill:so1", ticker="GE_US_EQ",
                     day="2024-04-02", fill_type="SPIN_OFF")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.needs_review is True
        assert [d["fill_type"] for d in completed_run.review_details] == ["SPIN_OFF"]
        assert db_session.query(BrokerCorporateAction).count() == 0
```

Late pre-split fill in a later run: add
`test_late_pre_split_fill_in_later_run_gets_adjusted`. Finalize run 1 (a split
plus one prior buy). Create a second `BrokerSyncRun` in state `finalizing` for
the same connection. Stage in it the same split pair plus an older fill
`fill:t0` of 3 @ 1100 on 2024-04-01, and finalize. Assert that `fill:t0` is
stored as 30 @ 110, that the run-1 buy is still 90 @ 120 (not 900 @ 12), and
that there are exactly 2 applications and 1 action.

- [ ] **Step 2: Run → FAIL**

Run: `cd backend && python -m pytest tests/test_t212_finalize.py -k "Split or split" -v`

- [ ] **Step 3: Implement `apply_splits`** (append to `t212_corporate_actions.py`)

```python
from datetime import time, timezone

from sqlalchemy.orm import Session

from models import (BrokerCorporateAction, BrokerCorporateActionApplication,
                    BrokerSyncRun, Portfolio, Transaction)


@dataclass(frozen=True)
class ApplySummary:
    actions_created: int
    applications_created: int
    csv_represented: int


def _is_t212_origin(t: Transaction) -> bool:
    if t.source in {"t212_api", "t212_csv"}:
        return True
    return not t.source and (t.notes or "").startswith("T212")


def _row_time(t: Transaction) -> datetime:
    if t.executed_at is not None:
        return t.executed_at if t.executed_at.tzinfo else t.executed_at.replace(tzinfo=timezone.utc)
    return datetime.combine(t.date, time.max, tzinfo=timezone.utc)


def apply_splits(db: Session, *, run: BrokerSyncRun, portfolio: Portfolio,
                 evidence: list[SplitEvidence], pending: list[Transaction]) -> ApplySummary:
    from t212_sync import _normalize_t212_ticker

    created = applied = csv_rep = 0
    for ev in sorted(evidence, key=lambda e: e.effective_at):
        ticker = _normalize_t212_ticker(ev.provider_instrument_id)
        rows = db.query(Transaction).filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            Transaction.ticker == ticker,
        ).all()
        action = db.query(BrokerCorporateAction).filter_by(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
            account_fingerprint=run.account_fingerprint,
            provider_instrument_id=ev.provider_instrument_id, action_type="STOCK_SPLIT",
            effective_at=ev.effective_at, provider_event_key=ev.provider_event_key,
        ).first()
        if action is None:
            csv_legs = {t.type for t in rows
                        if t.type in {"split_open", "split_close"} and t.date == ev.effective_at.date()}
            action = BrokerCorporateAction(
                workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
                broker="trading212", account_fingerprint=run.account_fingerprint,
                provider_instrument_id=ev.provider_instrument_id, ticker=ticker,
                action_type="STOCK_SPLIT", effective_at=ev.effective_at,
                provider_event_key=ev.provider_event_key,
                ratio_numerator=ev.ratio.numerator, ratio_denominator=ev.ratio.denominator,
                representation="csv_rows" if csv_legs == {"split_open", "split_close"} else "api_normalized",
                run_id=run.id,
            )
            db.add(action)
            db.flush()
            created += 1
        if action.representation == "csv_rows":
            csv_rep += 1
            continue
        already = {
            a.transaction_id for a in db.query(BrokerCorporateActionApplication).filter_by(
                workspace_id=portfolio.workspace_id, action_id=action.id,
            )
        }
        candidates = rows + [p for p in pending if p.ticker == ticker and p not in rows]
        for t in candidates:
            if t.type not in {"buy", "sell"} or not _is_t212_origin(t):
                continue
            if _row_time(t) >= ev.effective_at:
                continue
            if t.id is None:
                db.add(t)
                db.flush()
            if t.id in already:
                continue
            before_shares, before_price = t.shares, t.price
            t.shares = float(Fraction(str(t.shares)) * ev.ratio)
            t.price = float(Fraction(str(t.price)) / ev.ratio)
            db.add(BrokerCorporateActionApplication(
                workspace_id=portfolio.workspace_id, action_id=action.id, transaction_id=t.id,
                shares_before=before_shares, price_before=before_price,
                shares_after=t.shares, price_after=t.price, applied_by_run_id=run.id,
            ))
            already.add(t.id)
            applied += 1
    return ApplySummary(created, applied, csv_rep)
```

- [ ] **Step 4: Wire into `finalize_run`** (`backend/t212_sync.py`)

- Set `SUPPORTED_CORPORATE_ACTION_TYPES = frozenset({"STOCK_SPLIT"})` and
  `_FINALIZE_MAPPER_VERSION = "t212_finalize_v2"`.
- After the unsupported check (A3), also for a retried `completed` run:

```python
    from t212_corporate_actions import UnpairedSplitLeg, apply_splits, collapse_split_pairs

    split_events = [
        e for e in events
        if _corporate_action_type(e) == "STOCK_SPLIT" and not _is_csv_covered(e, csv_covered_through)
    ]
    try:
        split_evidence = collapse_split_pairs(split_events)
    except UnpairedSplitLeg:
        if run.state == "finalizing":
            return _send_run_to_needs_review(db, run, split_events)
        raise
```

- Split legs keep returning `"non_trade"` from `_finalize_order_event`, so they
  never become transactions (parent §4.6: no API `split_open`/`split_close` rows).
- Call `apply_splits(db, run=run, portfolio=portfolio, evidence=split_evidence, pending=new_txns)`
  after FX resolution and **before** the final insert/commit, so it shares the
  commit that marks the run `completed`. Keep the rest of the insert path
  unchanged. `apply_splits` may already have flushed some pending rows, and
  `db.add` on an already-added object is a no-op.
- Import inside the function to avoid a circular import, because
  `t212_corporate_actions` imports from `t212_sync`.

- [ ] **Step 5: Update the legacy tests**

`test_corporate_action_fill_sends_run_to_needs_review_without_ledger_writes`
and the parametrized `test_every_non_trade_fill_type_needs_review` stage a
single `STOCK_SPLIT` leg. That still yields `needs_review` (unpaired), so
keep them, but change the parametrized case's assertion for `STOCK_SPLIT`
only if its `unsupported_action_types` now differs. Change test data, not
intent.

- [ ] **Step 6: Run the full fast suite**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/t212_corporate_actions.py backend/t212_sync.py backend/tests/test_t212_finalize.py
git commit -m "feat(t212): apply provider-labelled stock splits once via durable applications"
```

---

### Task B4: Import undo keeps actions and applications consistent

**Files:**
- Modify: `backend/import_undo.py` (`UNDO_SCHEMA_VERSION = 3`, `_SUPPORTED_UNDO_SCHEMA_VERSIONS = {1, 2, 3}`)
- Test: `backend/tests/test_import_workflow.py`

**Interfaces:**
- Consumes: B1 models.
- Produces: the undo payload gains `"corporate_actions": [...]` (all action
  columns except `id`) and `"corporate_action_applications": [...]`. Each
  application stores `transaction_index`, its position in the payload's
  captured transaction list, instead of `transaction_id`, because ids change
  on restore. It also stores the action's identity tuple instead of
  `action_id`.

- [ ] **Step 1: Failing test**

Build it on the replace/undo helpers the test around
`original.source_fill_type = "TRADE"` (`test_import_workflow.py:494`) uses:

```python
def test_undo_restores_adjusted_rows_with_their_application_markers(db_session, default_portfolio):
    # arrange: t212_api buy "fill:t1" stored as 90 @ 120, an api_normalized STOCK_SPLIT
    #          action (10/1, effective 2024-06-10) and one application 9@1200 -> 90@120
    # act: preview + commit a T212 CSV replace import (creates the undo point), then undo it
    # assert: exactly one buy with source_event_id "fill:t1" at 90 @ 120
    # assert: exactly one action and one application; application.transaction_id == restored buy id
    # assert: finalize_run on a new finalizing run staging the same split pair creates 0 new applications
```

Write each comment line as real code. The values are exact.

- [ ] **Step 2: Run → FAIL**

Run: `cd backend && python -m pytest tests/test_import_workflow.py -k application_markers -v`

- [ ] **Step 3: Implement.** Capture the portfolio's actions, and the applications
  whose transaction is in the captured set. On restore, inside the
  already-held workspace ledger lock: delete current actions for the portfolio
  (applications cascade), re-insert actions, then transactions (existing
  code), then applications mapped through `transaction_index` and the action
  identity. A v1/v2 payload restores with no action data, which is correct
  because those points predate any action.

- [ ] **Step 4: Run** `cd backend && python -m pytest tests/test_import_workflow.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add backend/import_undo.py backend/tests/test_import_workflow.py
git commit -m "feat(import): undo schema v3 preserves corporate-action applications"
```

---

# Track C — Incremental sync and audits (parent Task 5)

Track C depends on A3/A4 only. A connection's history counts as complete once
its latest `initial` run is `completed`. Portfolios still blocked in
`needs_review` never reach that state, so they stay on full runs until Track B
unblocks them. This is intended.

### Task C1: Per-stream coverage checkpoints and run mode

**Files:**
- Create: `backend/alembic/versions/0021_t212_history_coverage.py`. Its
  `down_revision` is the head at the time of writing: `0020_broker_corporate_actions`
  if B1 is merged, otherwise `0019_sync_run_review_details`. If B1 lands
  later, it re-points its own `down_revision` so there is exactly one head.
- Modify: `backend/models.py` (`BrokerConnection`, `BrokerSyncRun`), `backend/database.py`
- Modify: `backend/t212_sync.py` (`finalize_run` success path, `history_run_decision` create branch)
- Modify: `backend/routers/broker.py` (`sync_transactions`, `retry_history` pass `mode`)
- Modify: every place that invalidates T212 coverage today. Find them with
  `grep -rn "t212_csv_covered_through =" backend/routers backend/*.py`
  (clear-all, CSV replace).
- Test: `backend/tests/test_t212_finalize.py`, `backend/tests/test_t212_sync_runs.py`, `backend/tests/test_portfolio.py`

**Interfaces:**
- Produces on `BrokerConnection` (all nullable): `history_complete_at` (aware dt),
  `orders_frontier_at` (aware dt), `orders_frontier_event_id` (str),
  `dividends_frontier_at`, `dividends_frontier_event_id`, `last_full_audit_at`.
- Produces on `BrokerSyncRun`: `orders_known_streak`, `dividends_known_streak`
  (`INTEGER NOT NULL DEFAULT 0`), `orders_last_page_oldest_at`,
  `dividends_last_page_oldest_at` (nullable aware dt). These are used by C2.
- Rules:
  - A `completed` run in mode `initial` or `audit` sets `history_complete_at = now()`
    and sets each stream's frontier to its newest staged event (max
    `provider_timestamp`, tie-break max `provider_event_id`). `audit` also sets
    `last_full_audit_at = now()`. `incremental` only advances a frontier when
    the newest staged event is newer. All of this happens in the run's
    completion commit.
  - `needs_review`/`failed`/`cancelled` runs never touch these fields.
  - Clear-all and CSV replace set all six connection fields to `None`.
  - `history_run_decision`'s `create` branch returns
    `mode="initial"` when `connection.history_complete_at is None`, else `"incremental"`.
    C3 adds `audit`. `sync_transactions`/`retry_history` pass `mode=decision.mode`
    to `claim_or_create_run`.

- [ ] **Step 1: Failing tests**

```python
    def test_completed_initial_run_sets_frontiers(self, db_session, default_portfolio, connection, completed_run):
        completed_run.mode = "initial"
        _order_event(db_session, completed_run, event_id="fill:old", day="2024-01-01")
        _order_event(db_session, completed_run, event_id="fill:new", day="2024-06-01")
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        db_session.refresh(connection)
        assert connection.orders_frontier_event_id == "fill:new"
        assert connection.orders_frontier_at.date() == date(2024, 6, 1)
        assert connection.history_complete_at is not None
        assert connection.last_full_audit_at is None

    def test_needs_review_run_sets_no_frontier(self, db_session, default_portfolio, connection, completed_run):
        completed_run.mode = "initial"
        _order_event(db_session, completed_run, event_id="fill:x", fill_type="SPIN_OFF")
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        db_session.refresh(connection)
        assert connection.history_complete_at is None
        assert connection.orders_frontier_event_id is None
```

In `test_t212_sync_runs.py`:

```python
def test_create_mode_is_initial_without_coverage(db_session, default_portfolio, connection):
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).mode == "initial"


def test_create_mode_is_incremental_with_coverage(db_session, default_portfolio, connection):
    connection.history_complete_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    connection.last_full_audit_at = datetime.now(timezone.utc)
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).mode == "incremental"
```

In `test_portfolio.py`, add a clear-all test: set all six fields, call the
clear-all route function the way that file's existing clear-all test does,
and assert all six are `None`.

- [ ] **Step 2: Run → FAIL**

Run: `cd backend && python -m pytest tests/test_t212_finalize.py tests/test_t212_sync_runs.py tests/test_portfolio.py -k "frontier or create_mode or clear" -v`

- [ ] **Step 3: Implement.** Add the model columns and the migration (plain
  `op.add_column`/`op.drop_column`), and bump `EXPECTED_ALEMBIC_HEAD` to
  `"0021_t212_history_coverage"`. In `finalize_run`, just before the success
  commit, add:

```python
    def _newest(stream: str) -> BrokerSyncEvent | None:
        staged = [e for e in events if e.stream == stream and e.provider_timestamp is not None]
        return max(staged, key=lambda e: (e.provider_timestamp, e.provider_event_id), default=None)

    now = datetime.now(timezone.utc)
    for stream in STREAMS:
        newest = _newest(stream)
        if newest is None:
            continue
        current = getattr(connection, f"{stream}_frontier_at")
        if run.mode in {"initial", "audit"} or current is None or newest.provider_timestamp > current:
            setattr(connection, f"{stream}_frontier_at", newest.provider_timestamp)
            setattr(connection, f"{stream}_frontier_event_id", newest.provider_event_id)
    if run.mode in {"initial", "audit"}:
        connection.history_complete_at = now
    if run.mode == "audit":
        connection.last_full_audit_at = now
```

Update `history_run_decision`'s final line to
`return HistoryDecision("create", None, "initial" if connection.history_complete_at is None else "incremental")`,
and pass `mode=decision.mode` at both `claim_or_create_run` call sites.

- [ ] **Step 4: Run → PASS**, then `cd backend && alembic heads` shows one head.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0021_t212_history_coverage.py backend/models.py backend/database.py backend/t212_sync.py backend/routers/broker.py backend/routers/portfolio.py backend/tests/test_t212_finalize.py backend/tests/test_t212_sync_runs.py backend/tests/test_portfolio.py
git commit -m "feat(t212): persist per-stream history coverage frontiers and run mode"
```

(Also add any other coverage-invalidation file the grep found.)

---

### Task C2: Incremental stop rule

**Files:**
- Create: `backend/t212_incremental.py`
- Create: `backend/tests/test_t212_incremental.py`
- Modify: `backend/t212_sync.py` (`advance_run` per-page loop)
- Test: `backend/tests/test_t212_sync_runs.py`

**Interfaces:**
- Consumes: C1 run/connection columns.
- Produces:

```python
OVERLAP_PAGES = 2   # consecutive fully-known pages past the frontier before stopping
OVERLAP_DAYS = 7    # a counted page's oldest event must be this far behind the frontier

@dataclass(frozen=True)
class PageVerdict:
    stop: bool
    known_streak: int
    ordering_violation: bool

def evaluate_page(*, page_events: list[tuple[str, datetime | None]], known_ids: set[str],
                  frontier_at: datetime | None, prior_streak: int,
                  previous_page_oldest: datetime | None) -> PageVerdict
```

Rules (parent §7):
- Pages arrive newest-first. `ordering_violation` is true if the page's
  timestamps are not non-increasing, or if any event is newer than
  `previous_page_oldest`. Events with `None` timestamps are ignored for
  ordering.
- A page is fully known when every id is in `known_ids`.
- `known_streak = prior_streak + 1` if the page is fully known and its oldest
  timestamp is `<= frontier_at - OVERLAP_DAYS`. Otherwise it resets to `0`.
- `stop = frontier_at is not None and known_streak >= OVERLAP_PAGES and not ordering_violation`.
- Nothing compares against `max(Transaction.date)`.

- [ ] **Step 1: Failing pure tests**

```python
from datetime import datetime, timedelta, timezone

from t212_incremental import OVERLAP_DAYS, OVERLAP_PAGES, evaluate_page

F = datetime(2024, 6, 1, tzinfo=timezone.utc)


def d(days):
    return F - timedelta(days=days)


def test_unknown_event_resets_streak():
    v = evaluate_page(page_events=[("x", d(10)), ("y", d(11))], known_ids={"y"},
                      frontier_at=F, prior_streak=1, previous_page_oldest=d(9))
    assert (v.stop, v.known_streak, v.ordering_violation) == (False, 0, False)


def test_known_page_inside_overlap_window_does_not_count():
    v = evaluate_page(page_events=[("a", d(1)), ("b", d(2))], known_ids={"a", "b"},
                      frontier_at=F, prior_streak=0, previous_page_oldest=None)
    assert v.known_streak == 0 and v.stop is False


def test_stops_after_overlap_pages_past_frontier():
    v = evaluate_page(page_events=[("a", d(OVERLAP_DAYS + 1)), ("b", d(OVERLAP_DAYS + 2))],
                      known_ids={"a", "b"}, frontier_at=F,
                      prior_streak=OVERLAP_PAGES - 1, previous_page_oldest=d(OVERLAP_DAYS))
    assert v.stop is True


def test_ordering_violation_within_page_never_stops():
    v = evaluate_page(page_events=[("a", d(OVERLAP_DAYS + 1)), ("b", d(1))],
                      known_ids={"a", "b"}, frontier_at=F,
                      prior_streak=OVERLAP_PAGES, previous_page_oldest=d(OVERLAP_DAYS))
    assert v.stop is False and v.ordering_violation is True


def test_ordering_violation_across_pages_never_stops():
    v = evaluate_page(page_events=[("a", d(5))], known_ids={"a"}, frontier_at=F,
                      prior_streak=OVERLAP_PAGES, previous_page_oldest=d(20))
    assert v.stop is False and v.ordering_violation is True


def test_no_frontier_never_stops():
    v = evaluate_page(page_events=[("a", d(100))], known_ids={"a"}, frontier_at=None,
                      prior_streak=99, previous_page_oldest=None)
    assert v.stop is False


def test_old_unknown_event_for_unseen_ticker_is_not_skipped():
    v = evaluate_page(page_events=[("known", d(30)), ("unseen", d(400))],
                      known_ids={"known"}, frontier_at=F, prior_streak=OVERLAP_PAGES,
                      previous_page_oldest=d(29))
    assert v.stop is False and v.known_streak == 0
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: No module named 't212_incremental'`)

Run: `cd backend && python -m pytest tests/test_t212_incremental.py -v`

- [ ] **Step 3: Implement** (`backend/t212_incremental.py`)

```python
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
```

- [ ] **Step 4: Wire into `advance_run`** (only when `run.mode == "incremental"`)

Once per stream per `advance_run` call, load
`known_ids = {row[0] for row in db.query(Transaction.source_event_id).filter(workspace, portfolio, Transaction.source == "t212_api", Transaction.source_event_stream == stream)}`.
After staging each page, build `page_events = [(_event_id(stream, i), _extract_provider_timestamp(stream, i)) for i in items]`
and call `evaluate_page` with `frontier_at=getattr(connection, f"{stream}_frontier_at")`,
`prior_streak=getattr(run, f"{stream}_known_streak")`, and
`previous_page_oldest=getattr(run, f"{stream}_last_page_oldest_at")`. Then,
in the same commit as the page:
- persist `known_streak` and the page's oldest timestamp on the run;
- if `verdict.ordering_violation`: set `run.mode = "audit"` so the walk
  continues to the end and C1 records a full audit (the parent §7 deeper
  fallback);
- elif `verdict.stop`: set `<stream>_complete = True` and `<stream>_next_page_path = None`.

`advance_run` needs the connection. Pass it as a new keyword argument
`connection: BrokerConnection | None = None`, and supply it from
`broker_backfill_pass` (`backend/jobs.py`, which already loads `connection`).
With `connection=None` the stop rule is skipped.

- [ ] **Step 5: Integration tests** (`test_t212_sync_runs.py`)

Patch `t212_sync._fetch_stream_page` to return scripted
`(items, next_path)` pages. Four tests:
(a) an incremental run with 1 new page and then known pages past the frontier
stops after `1 + OVERLAP_PAGES` pages, and the stream is marked complete;
(b) an unknown old event on page 5 keeps walking and page 6 is fetched;
(c) a page newer than the previous page flips `run.mode` to `"audit"` and the
walk runs until `next_path` is `None`;
(d) a run in `mode="initial"` never stops early.

- [ ] **Step 6: Run**

Run: `cd backend && python -m pytest tests/test_t212_incremental.py tests/test_t212_sync_runs.py tests/test_broker_backfill.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/t212_incremental.py backend/tests/test_t212_incremental.py backend/t212_sync.py backend/jobs.py backend/tests/test_t212_sync_runs.py
git commit -m "feat(t212): incremental history stop rule with overlap and deeper fallback"
```

---

### Task C3: 30-day audits and payload revisions

**Files:**
- Modify: `backend/t212_sync.py` (`history_run_decision`, `finalize_run`, `FinalizeResult`)
- Modify: `backend/routers/broker.py` (`sync_transactions` passes the reconciliation mismatch)
- Test: `backend/tests/test_t212_sync_runs.py`, `backend/tests/test_t212_finalize.py`, `backend/tests/test_broker_backfill.py`

**Interfaces:**
- Consumes: C1 fields; `_reconcile_history(db, portfolio, conn, run)` in `routers/broker.py`.
- Produces: `AUDIT_INTERVAL = timedelta(days=30)`;
  `history_run_decision(..., reconciliation_mismatch: bool = False)`;
  `FinalizeResult.revised: int = 0`.

Rules (parent §7):
- In the create branch, mode is `initial` if `history_complete_at is None`.
  It is `audit` if `last_full_audit_at is None`, or older than
  `AUDIT_INTERVAL`, or if `reconciliation_mismatch`. Otherwise it is
  `incremental`.
- The decision runs only from `sync_transactions` (manual, or autosync for
  `auto_sync=True` connections) and `retry_history`. `broker_backfill` never
  creates runs, so disabled auto-sync means no unrequested broker access.
- `sync_transactions` computes `reconciliation_mismatch` from
  `_reconcile_history` for the latest `completed` run. It is `True` if any item
  status is `"different"`.
- Audit finalization: when a staged event's `(stream, provider_event_id)`
  already exists as a `t212_api` transaction, compare that row's
  `source_payload_hash` with `_stable_fingerprint(payload)`. If they differ,
  re-map the event with the existing mapper and update the row's
  `shares, price, date, executed_at, cash_amount, cash_currency,
  source_payload_hash, source_mapper_version` under the ledger lock. If the row
  has corporate-action applications, apply the recorded ratios in action order
  to the re-mapped values and update each application's `*_before`/`*_after`.
  Increment `revised`. Unknown IDs are imported as usual, which covers
  late-inserted old dividends.

- [ ] **Step 1: Failing tests**

```python
def test_mode_is_audit_after_30_days(db_session, default_portfolio, connection):
    connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    connection.last_full_audit_at = datetime.now(timezone.utc) - timedelta(days=31)
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).mode == "audit"


def test_mode_is_incremental_within_30_days(db_session, default_portfolio, connection):
    connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    connection.last_full_audit_at = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.commit()
    assert t212_sync.history_run_decision(db_session, connection, default_portfolio).mode == "incremental"


def test_reconciliation_mismatch_forces_audit(db_session, default_portfolio, connection):
    connection.history_complete_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    connection.last_full_audit_at = datetime.now(timezone.utc)
    db_session.commit()
    decision = t212_sync.history_run_decision(
        db_session, connection, default_portfolio, reconciliation_mismatch=True,
    )
    assert decision.mode == "audit"
```

In `test_broker_backfill.py`: `test_backfill_never_creates_runs`. With a
connected portfolio and no runs, `broker_backfill_pass` returns `[]` and
`BrokerSyncRun` count stays 0.

In `test_t212_finalize.py`:

```python
    def test_audit_updates_row_whose_payload_changed(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:f1", qty=10, price=150.0)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [row] = db_session.query(Transaction).all()
        old_hash = row.source_payload_hash

        audit = BrokerSyncRun(
            workspace_id=completed_run.workspace_id, portfolio_id=completed_run.portfolio_id,
            connection_id=completed_run.connection_id, broker="trading212",
            account_fingerprint=completed_run.account_fingerprint,
            credential_generation=completed_run.credential_generation,
            mode="audit", state="finalizing", orders_complete=True, dividends_complete=True,
        )
        db_session.add(audit)
        db_session.commit()
        _order_event(db_session, audit, event_id="fill:f1", qty=10, price=151.0)

        result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(row)
        assert result.revised == 1
        assert row.price == 151.0
        assert row.source_payload_hash != old_hash
        assert db_session.query(Transaction).count() == 1

    def test_audit_imports_late_inserted_old_dividend(self, db_session, default_portfolio, completed_run):
        # completed_run.mode = "audit"; stage a 2023-02-01 dividend with reference "div-old"
        # unknown to the ledger -> result.dividends_imported == 1
```

Write the second body in full with the file's existing dividend-staging
helper. Values are as commented.

- [ ] **Step 2: Run → FAIL**

Run: `cd backend && python -m pytest tests/test_t212_sync_runs.py tests/test_t212_finalize.py tests/test_broker_backfill.py -k "audit or revised or never_creates or mismatch" -v`

- [ ] **Step 3: Implement** the rules above. Add `revised: int = 0` as the
  last `FinalizeResult` field so existing constructors keep working.

- [ ] **Step 4: Run the fast suite**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/t212_sync.py backend/routers/broker.py backend/tests/test_t212_sync_runs.py backend/tests/test_t212_finalize.py backend/tests/test_broker_backfill.py
git commit -m "feat(t212): 30-day and mismatch-triggered audit runs with payload revisions"
```

---

### Task C4: Staging retention that keeps review evidence

**Files:**
- Modify: `backend/data_retention.py` (`cleanup_retained_operational_data`)
- Modify: `backend/jobs.py:1029-1033` (log line)
- Modify: the data-processing inventory under `docs/compliance/`
  (`grep -rn "broker_sync_events\|staged" docs/compliance`; add a row if absent)
- Test: the existing retention test module (`grep -rln cleanup_retained_operational_data backend/tests`)

**Interfaces:**
- Produces: `STAGING_RETENTION = timedelta(days=14)`,
  `STAGING_REVIEW_RETENTION = timedelta(days=90)`, and the summary key `"broker_sync_events"`.

Rules:
- Delete events of runs in `completed`/`failed`/`cancelled` whose
  `completed_at` (falling back to `updated_at`) is older than 14 days.
- Delete events of `needs_review` runs older than 90 days, **except** the
  latest run of each connection when that run is `needs_review`. Its events
  are the A1 capture source.
- Never touch events of non-terminal runs.
- Use bounded batches, processed per workspace context the same way the
  existing categories are.

- [ ] **Step 1: Failing tests** (one per rule)

```python
def test_old_completed_run_events_are_purged(db_session, ...):      # 15-day-old completed run -> 0 events left
def test_recent_completed_run_events_are_kept(db_session, ...):     # 3-day-old completed run -> events kept
def test_latest_needs_review_run_events_are_never_purged(db_session, ...):  # 200-day-old, latest -> kept
def test_superseded_old_needs_review_events_are_purged(db_session, ...):    # 100-day-old, newer run exists -> purged
def test_active_run_events_are_never_purged(db_session, ...):       # fetching run 30 days old -> kept
```

Write each in full using the run/event construction from
`test_broker_backfill.py`'s `_run_row` and `BrokerSyncEvent(...)` examples.
Call `cleanup_retained_operational_data(db_session, now=<fixed>)` and assert
the event counts and `summary["broker_sync_events"]`.

- [ ] **Step 2: FAIL → Step 3: implement → Step 4: PASS**

Run: `cd backend && python -m pytest <retention test file> -v`

- [ ] **Step 5: Commit**

```bash
git add backend/data_retention.py backend/jobs.py docs/compliance backend/tests/<retention test file>
git commit -m "feat(retention): bounded cleanup of staged T212 events, keeping review evidence"
```

---

# Final verification

### Task V1: Gates and real-environment checks

- [ ] `cd backend && python -m pytest tests/ --ignore=tests/postgres -q`: all pass
- [ ] `cd backend && alembic heads`: exactly one head, equal to `EXPECTED_ALEMBIC_HEAD`
- [ ] PostgreSQL/RLS suite, which also covers the still-unverified `0017`/`0018`
  and new `0019`–`0021`: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`,
  then `cd backend && python -m pytest tests/postgres/ -v`. If Docker is still
  unavailable, report **not verified**. Do not claim done.
- [ ] `cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud`
- [ ] Real browser (Playwright MCP, http://localhost:5173, Firebase test login):
  the needs_review panel lists items with the CSV link, and retry creates a
  run. Check a completed run too, at mobile and desktop widths.
- [ ] T212 demo account: the initial run crosses a rate-limit reset and, after
  Track B, contains a split. The second sync is incremental (new page +
  overlap). Set `last_full_audit_at` 31 days back and check the next manual
  sync creates an `audit` run.
- [ ] Update docs in the same change: the parent plan's status header and §10
  checkboxes (Tasks 4–5), the `t212_sync.py` Task 3/Task 4 section
  docstrings' "deliberately excludes" lists, and `deploy/cloudrun.md` if
  retention changes a scheduled job.

## Out of scope (still tracked by the parent plan)

- `/equity/history/transactions` cash-movement stream and `TRANSFER` handling (parent §5.5 items 7–8).
- Mappers for `STOCK_DISTRIBUTION`, `SPIN_OFF`, `STOCK_ACQUISITION`, `FOP*`.
  Each needs its own captured payloads and a gate like G1.
- §2.3 stable holdings/summary envelope.
- Yfinance ratio/date plausibility cross-check (parent §6.2 items 2–3, 9). It
  is optional because provider-labelled splits are authoritative. If it is
  added later, it may only flag a mismatch into `needs_review`, never apply
  anything.

## Sequencing

```
A1 ─► (user captures) ─► A2 / G1 sign-off ─► B1 ─► B2 ─► B3 ─► B4
A3 ─► A4 ─► A5
A3 + A4 ─► C1 ─► C2 ─► C3
A3 ─► C4
all ─► V1
```

A1 comes first because the user's capture is the long pole. A3–A5 and C1–C4
proceed while G1 waits.
