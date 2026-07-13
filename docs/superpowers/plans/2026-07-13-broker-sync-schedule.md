# Broker Auto-Sync Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed 6-hour broker auto-sync interval with a configurable schedule — daily at HH:MM (default 02:00 Europe/Prague) or every N hours — editable from the Settings page.

**Architecture:** The autosync background task becomes a 60-second heartbeat that calls a due-check against schedule settings persisted in the existing `AppSetting` key/value table. A pure `sync_due()` function decides daily-boundary/interval dueness (catch-up after downtime falls out of the boundary rule); a new `/api/settings/sync-schedule` router exposes GET/PUT; a new `SyncScheduleSettings` card on the Settings page edits it.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 (backend, Python 3.12, `zoneinfo`), pytest (direct-call tests against in-memory SQLite — no TestClient), React 18 + react-query + vitest/testing-library (frontend).

**Spec:** `docs/superpowers/specs/2026-07-13-broker-sync-schedule-design.md`

## Global Constraints

- Timezone constant: `Europe/Prague`, env override `BROKER_SYNC_TIMEZONE`. No timezone UI.
- AppSetting keys, exact strings: `broker_sync_mode`, `broker_sync_daily_time`, `broker_sync_interval_hours`, `broker_sync_last_run`.
- Defaults: mode `daily`, daily time `02:00`, interval `6` hours. Interval bounds: 1–168.
- `BROKER_AUTOSYNC_ENABLED=0` remains the kill switch; `BROKER_AUTOSYNC_INTERVAL_SECONDS` is retired.
- `/settings` endpoints are global config → must be added to `PORTFOLIO_AGNOSTIC_PREFIXES` in `frontend/src/api.js`.
- Backend tests: direct-call style with the `db_session` / `pid` fixtures from `backend/tests/conftest.py`; run from `backend/` with the repo venv: `python -m pytest tests/ -v` (pytest is installed in the venv but NOT in requirements.txt — leave it that way).
- **The repo has unrelated uncommitted changes on `main`. Every commit must `git add` only the files named in its task — never `git add -A` / `git add .`.**
- **Task 0 gate — do this before Task 1:** the pre-existing uncommitted work overlaps files this plan modifies (`backend/jobs.py`, `backend/main.py`, `backend/tests/test_jobs.py`), so a task-level `git add` of those paths would silently fold that work into a feature commit. First run `git status`; if those files are still dirty, commit the pre-existing work as its own commit (or have the user do it) so this plan starts from a clean state for the files it touches. Do not start Task 1 while they are dirty.
- All `datetime`s crossing module boundaries are timezone-aware UTC; `broker_sync_last_run` is stored as ISO-8601 with offset.

---

### Task 1: Shared AppSetting helpers (`app_settings.py`)

`_get_setting`/`_set_setting` currently live privately in `routers/assistant.py`. The scheduler and the new settings router both need them — extract to a shared module, point assistant.py at it.

**Files:**
- Create: `backend/app_settings.py`
- Modify: `backend/routers/assistant.py:26-41` (replace private helpers with imports)
- Test: `backend/tests/test_app_settings.py`

**Interfaces:**
- Consumes: `models.AppSetting` (existing).
- Produces: `get_setting(db: Session, key: str) -> str | None` and `set_setting(db: Session, key: str, value: str | None) -> None` (upsert, **does not commit** — callers own the transaction). Later tasks import these from `app_settings`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_app_settings.py`:

```python
"""Tests for the shared AppSetting key/value helpers."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_settings import get_setting, set_setting


def test_get_missing_key_returns_none(db_session):
    assert get_setting(db_session, "nope") is None


def test_set_then_get_roundtrip(db_session):
    set_setting(db_session, "k", "v1")
    db_session.commit()
    assert get_setting(db_session, "k") == "v1"


def test_set_updates_existing_row(db_session):
    set_setting(db_session, "k", "v1")
    db_session.commit()
    set_setting(db_session, "k", "v2")
    db_session.commit()
    assert get_setting(db_session, "k") == "v2"
    # still a single row, not a duplicate key
    from models import AppSetting
    assert db_session.query(AppSetting).filter(AppSetting.key == "k").count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

From `backend/` (venv active): `python -m pytest tests/test_app_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app_settings'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app_settings.py`:

```python
"""Shared helpers for the AppSetting key/value store (global app config).

Extracted from routers/assistant.py so background jobs and the settings
router can reuse them without importing a router module.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models import AppSetting


def get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def set_setting(db: Session, key: str, value: Optional[str]) -> None:
    """Upsert without committing — callers own the transaction."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
```

In `backend/routers/assistant.py`, delete the `_get_setting` and `_set_setting` function definitions (lines 30–41, under the "App-setting helpers" header) and add to the imports near the top:

```python
from app_settings import get_setting as _get_setting, set_setting as _set_setting
```

Keep `_key_preview` where it is. Keep the `# App-setting helpers` section comment only if other helpers remain under it (`_key_preview` does — keep it).

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`: `python -m pytest tests/test_app_settings.py tests/test_assistant.py -v` — if `tests/test_assistant.py` does not exist, run `python -m pytest tests/ -v` instead to prove assistant.py still imports.
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app_settings.py backend/routers/assistant.py backend/tests/test_app_settings.py
git commit -m "refactor: extract shared AppSetting get/set helpers"
```

---

### Task 2: Pure schedule functions `sync_due` / `next_sync_run` (jobs.py)

The heart of the feature: given "now", the schedule config, and the last run, decide whether a sync is due, and compute the next run instant for display. Pure functions — no DB, no clock reads.

**Files:**
- Modify: `backend/jobs.py` (add a new section after the imports/constants, before `broker_autosync_pass`)
- Test: `backend/tests/test_jobs.py` (append a new section)

**Interfaces:**
- Consumes: nothing project-specific (stdlib `datetime`, `zoneinfo`).
- Produces (later tasks call these with exactly these signatures):
  - `sync_due(now: datetime, mode: str, daily_time: str, interval_hours: int, last_run: datetime | None, tz: ZoneInfo) -> bool`
  - `next_sync_run(now: datetime, mode: str, daily_time: str, interval_hours: int, last_run: datetime | None, tz: ZoneInfo) -> datetime | None` (None = "would run immediately")
  - `now` / `last_run` are timezone-aware UTC datetimes.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_jobs.py`:

```python
# -------- sync_due / next_sync_run ------------------------------------------

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from jobs import sync_due, next_sync_run

PRAGUE = ZoneInfo("Europe/Prague")
# 2026-07-13 is CEST (UTC+2): the 02:00 local boundary is 00:00 UTC.


def test_daily_due_when_never_ran():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, None, PRAGUE) is True


def test_daily_not_due_after_todays_run():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)  # ran just after 02:00 local
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is False


def test_daily_due_once_boundary_crossed():
    # Ran yesterday; now it's 03:00 local today — today's boundary has passed.
    now = datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 12, 0, 5, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is True


def test_daily_not_due_before_todays_boundary():
    # 01:30 local on the 13th — most recent boundary is yesterday's, already ran.
    now = datetime(2026, 7, 12, 23, 30, tzinfo=timezone.utc)
    last = datetime(2026, 7, 12, 0, 10, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is False


def test_daily_catches_up_after_downtime():
    # App was down for three days: first check after boot must fire.
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 10, 0, 5, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is True


def test_daily_dst_spring_forward_fires_once():
    # 2026-03-29: Prague jumps 02:00 CET -> 03:00 CEST; 02:00 does not exist.
    # The boundary resolves to 01:00 UTC. Ran yesterday -> due; ran today -> not.
    now = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    ran_yesterday = datetime(2026, 3, 28, 1, 30, tzinfo=timezone.utc)
    ran_today = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, ran_yesterday, PRAGUE) is True
    assert sync_due(now, "daily", "02:00", 6, ran_today, PRAGUE) is False


def test_interval_due_when_never_ran():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "interval", "02:00", 6, None, PRAGUE) is True


def test_interval_due_after_elapsed():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "interval", "02:00", 6, now - timedelta(hours=7), PRAGUE) is True
    assert sync_due(now, "interval", "02:00", 6, now - timedelta(hours=5), PRAGUE) is False


def test_next_run_none_when_due_now():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert next_sync_run(now, "daily", "02:00", 6, None, PRAGUE) is None


def test_next_run_daily_is_next_boundary():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)
    nxt = next_sync_run(now, "daily", "02:00", 6, last, PRAGUE)
    assert nxt == datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc)  # 02:00 CEST tomorrow


def test_next_run_interval_is_last_plus_interval():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)
    nxt = next_sync_run(now, "interval", "02:00", 6, last, PRAGUE)
    assert nxt == last + timedelta(hours=6)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`: `python -m pytest tests/test_jobs.py -v -k "sync_due or next_run or daily or interval"`
Expected: FAIL — `ImportError: cannot import name 'sync_due' from 'jobs'`

- [ ] **Step 3: Write the implementation**

In `backend/jobs.py`, extend the stdlib import (line 24) to:

```python
from datetime import date, datetime, timedelta, timezone
```

and add after the color constants (below line 34):

```python
# -------- Sync schedule ------------------------------------------------------
# The autosync poller in main.py ticks every minute and asks sync_due() whether
# the configured schedule (Settings -> Auto-sync schedule) says it's time.
# Config lives in the AppSetting table under these keys; timestamps are aware
# UTC; "daily" boundaries are computed in SYNC's local timezone.

SYNC_MODE_KEY = "broker_sync_mode"                  # "daily" | "interval"
SYNC_DAILY_TIME_KEY = "broker_sync_daily_time"      # "HH:MM" 24h local time
SYNC_INTERVAL_HOURS_KEY = "broker_sync_interval_hours"
SYNC_LAST_RUN_KEY = "broker_sync_last_run"          # ISO-8601 UTC

DEFAULT_SYNC_MODE = "daily"
DEFAULT_SYNC_DAILY_TIME = "02:00"
DEFAULT_SYNC_INTERVAL_HOURS = 6


def _daily_boundary(local_now: datetime, daily_time: str) -> datetime:
    """Most recent occurrence of `daily_time` at or before `local_now`, as an
    aware datetime in local tz. On DST spring-forward days a nonexistent wall
    time resolves via fold=0 (shifted forward), so the boundary still exists
    exactly once per day."""
    hh, mm = (int(p) for p in daily_time.split(":"))
    boundary = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if boundary > local_now:
        boundary -= timedelta(days=1)
    return boundary


def sync_due(now: datetime, mode: str, daily_time: str, interval_hours: int,
             last_run: datetime | None, tz) -> bool:
    """Is a broker sync due? `now`/`last_run` are aware UTC datetimes.
    daily: due when the most recent daily_time boundary (in tz) hasn't been
    run yet — which is also the catch-up rule after downtime.
    interval: due when interval_hours have elapsed since last_run."""
    if last_run is None:
        return True
    if mode == "interval":
        return now - last_run >= timedelta(hours=interval_hours)
    boundary = _daily_boundary(now.astimezone(tz), daily_time)
    return last_run < boundary.astimezone(timezone.utc)


def next_sync_run(now: datetime, mode: str, daily_time: str, interval_hours: int,
                  last_run: datetime | None, tz) -> datetime | None:
    """Next scheduled run as aware UTC, for display. None = due right now
    (the poller will run it within a minute)."""
    if sync_due(now, mode, daily_time, interval_hours, last_run, tz):
        return None
    if mode == "interval":
        return last_run + timedelta(hours=interval_hours)
    nxt = _daily_boundary(now.astimezone(tz), daily_time) + timedelta(days=1)
    return nxt.astimezone(timezone.utc)
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`: `python -m pytest tests/test_jobs.py -v`
Expected: PASS (new tests and all pre-existing jobs tests)

- [ ] **Step 5: Commit**

```bash
git add backend/jobs.py backend/tests/test_jobs.py
git commit -m "feat: pure schedule due-check for broker auto-sync"
```

---

### Task 3: DB-backed schedule config (load / persist / timezone)

**Files:**
- Modify: `backend/jobs.py` (same "Sync schedule" section)
- Test: `backend/tests/test_jobs.py` (append)

**Interfaces:**
- Consumes: `app_settings.get_setting` / `set_setting` (Task 1); constants from Task 2.
- Produces (used by Task 4 and Task 6):
  - `sync_timezone() -> ZoneInfo` — env `BROKER_SYNC_TIMEZONE`, default/fallback `Europe/Prague`.
  - `load_sync_schedule(db: Session) -> dict` — keys `mode: str`, `daily_time: str`, `interval_hours: int`, `last_run: datetime | None` (aware UTC); invalid/missing stored values fall back to defaults.
  - `mark_sync_ran(db: Session, when: datetime) -> None` — persists last-run, commits.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_jobs.py`:

```python
# -------- schedule config persistence ----------------------------------------

from app_settings import set_setting
from jobs import (SYNC_MODE_KEY, SYNC_DAILY_TIME_KEY, SYNC_INTERVAL_HOURS_KEY,
                  SYNC_LAST_RUN_KEY, load_sync_schedule, mark_sync_ran, sync_timezone)


def test_sync_timezone_default_and_override(monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)
    assert sync_timezone().key == "Europe/Prague"
    monkeypatch.setenv("BROKER_SYNC_TIMEZONE", "America/New_York")
    assert sync_timezone().key == "America/New_York"
    monkeypatch.setenv("BROKER_SYNC_TIMEZONE", "Not/AZone")
    assert sync_timezone().key == "Europe/Prague"  # bad value falls back


def test_load_schedule_defaults_on_empty_db(db_session):
    s = load_sync_schedule(db_session)
    assert s == {"mode": "daily", "daily_time": "02:00",
                 "interval_hours": 6, "last_run": None}


def test_load_schedule_falls_back_on_garbage(db_session):
    set_setting(db_session, SYNC_MODE_KEY, "weekly")
    set_setting(db_session, SYNC_DAILY_TIME_KEY, "25:99")
    set_setting(db_session, SYNC_INTERVAL_HOURS_KEY, "lots")
    set_setting(db_session, SYNC_LAST_RUN_KEY, "yesterday-ish")
    db_session.commit()
    s = load_sync_schedule(db_session)
    assert s == {"mode": "daily", "daily_time": "02:00",
                 "interval_hours": 6, "last_run": None}


def test_load_schedule_reads_valid_values(db_session):
    set_setting(db_session, SYNC_MODE_KEY, "interval")
    set_setting(db_session, SYNC_DAILY_TIME_KEY, "04:30")
    set_setting(db_session, SYNC_INTERVAL_HOURS_KEY, "12")
    db_session.commit()
    s = load_sync_schedule(db_session)
    assert (s["mode"], s["daily_time"], s["interval_hours"]) == ("interval", "04:30", 12)


def test_mark_sync_ran_roundtrip(db_session):
    when = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)
    mark_sync_ran(db_session, when)
    assert load_sync_schedule(db_session)["last_run"] == when


def test_load_schedule_treats_naive_last_run_as_utc(db_session):
    set_setting(db_session, SYNC_LAST_RUN_KEY, "2026-07-13T00:05:00")
    db_session.commit()
    assert load_sync_schedule(db_session)["last_run"] == \
        datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`: `python -m pytest tests/test_jobs.py -v -k "schedule or timezone or mark_sync"`
Expected: FAIL — `ImportError: cannot import name 'load_sync_schedule' from 'jobs'`

- [ ] **Step 3: Write the implementation**

In `backend/jobs.py` add to the top-level imports (with the other stdlib imports):

```python
import os
import re
from zoneinfo import ZoneInfo
```

and below the existing imports:

```python
from app_settings import get_setting, set_setting
```

Then add to the "Sync schedule" section (after `next_sync_run`):

```python
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def sync_timezone() -> ZoneInfo:
    """Schedule timezone: BROKER_SYNC_TIMEZONE env var, else Europe/Prague.
    A bad env value falls back rather than killing the poller."""
    name = os.environ.get("BROKER_SYNC_TIMEZONE", "Europe/Prague")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Prague")


def load_sync_schedule(db: Session) -> dict:
    """Schedule config from AppSetting rows; anything missing or invalid
    silently falls back to the defaults (the poller must never crash on a
    hand-edited row)."""
    mode = get_setting(db, SYNC_MODE_KEY)
    if mode not in ("daily", "interval"):
        mode = DEFAULT_SYNC_MODE

    daily_time = get_setting(db, SYNC_DAILY_TIME_KEY) or DEFAULT_SYNC_DAILY_TIME
    if not _TIME_RE.match(daily_time):
        daily_time = DEFAULT_SYNC_DAILY_TIME

    raw_hours = get_setting(db, SYNC_INTERVAL_HOURS_KEY)
    try:
        interval_hours = int(raw_hours) if raw_hours else DEFAULT_SYNC_INTERVAL_HOURS
    except ValueError:
        interval_hours = DEFAULT_SYNC_INTERVAL_HOURS
    interval_hours = max(1, min(interval_hours, 168))

    last_run = None
    raw_last = get_setting(db, SYNC_LAST_RUN_KEY)
    if raw_last:
        try:
            last_run = datetime.fromisoformat(raw_last)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except ValueError:
            last_run = None

    return {"mode": mode, "daily_time": daily_time,
            "interval_hours": interval_hours, "last_run": last_run}


def mark_sync_ran(db: Session, when: datetime) -> None:
    set_setting(db, SYNC_LAST_RUN_KEY, when.isoformat())
    db.commit()
```

Note: `tzdata` (the IANA database for `zoneinfo` on Windows) is already installed transitively via `pandas>=2`; Task 5 makes it an explicit requirement since the scheduler now depends on it directly.

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`: `python -m pytest tests/test_jobs.py tests/test_app_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/jobs.py backend/tests/test_jobs.py
git commit -m "feat: persist broker sync schedule in AppSetting rows"
```

---

### Task 4: `autosync_tick` — the per-minute gate

Bundles load-config → due-check → run pass → mark ran into one coroutine with the same `(db) -> list` shape as the other passes, so main.py's existing `_periodic_loop` can drive it unchanged.

**Files:**
- Modify: `backend/jobs.py` (end of the "Broker auto-sync" section, after `broker_autosync_pass`)
- Test: `backend/tests/test_jobs.py` (append)

**Interfaces:**
- Consumes: `load_sync_schedule`, `sync_due`, `mark_sync_ran`, `sync_timezone` (Tasks 2–3), `broker_autosync_pass` (existing).
- Produces: `async def autosync_tick(db: Session, now: datetime | None = None) -> list[dict]` — `[]` when not due; otherwise the pass results. Task 5 registers exactly this in main.py.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_jobs.py`:

```python
# -------- autosync_tick -------------------------------------------------------

from jobs import autosync_tick


def test_tick_skips_when_not_due(db_session):
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    mark_sync_ran(db_session, now - timedelta(hours=1))  # ran after today's 02:00 boundary
    with patch("jobs.broker_autosync_pass", new=AsyncMock()) as p:
        out = _run(autosync_tick(db_session, now=now))
    assert out == []
    p.assert_not_awaited()
    # last_run untouched
    assert load_sync_schedule(db_session)["last_run"] == now - timedelta(hours=1)


def test_tick_runs_pass_and_marks_ran_when_due(db_session):
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    mark_sync_ran(db_session, now - timedelta(days=1))
    results = [{"portfolio_id": 1, "broker": "trading212", "ok": True, "imported": 2}]
    with patch("jobs.broker_autosync_pass", new=AsyncMock(return_value=results)) as p:
        out = _run(autosync_tick(db_session, now=now))
    p.assert_awaited_once()
    assert out == results
    assert load_sync_schedule(db_session)["last_run"] == now


def test_tick_marks_ran_even_when_no_connections(db_session):
    # An empty pass still consumes the boundary — no minute-by-minute retries.
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    with patch("jobs.broker_autosync_pass", new=AsyncMock(return_value=[])):
        out = _run(autosync_tick(db_session, now=now))
    assert out == []
    assert load_sync_schedule(db_session)["last_run"] == now
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`: `python -m pytest tests/test_jobs.py -v -k tick`
Expected: FAIL — `ImportError: cannot import name 'autosync_tick' from 'jobs'`

- [ ] **Step 3: Write the implementation**

In `backend/jobs.py`, add right after `broker_autosync_pass`:

```python
async def autosync_tick(db: Session, now: datetime | None = None) -> list[dict]:
    """One poller tick: run broker_autosync_pass iff the configured schedule
    says a sync is due, then persist the run timestamp. Same (db) -> list shape
    as the other passes so main.py's _periodic_loop drives it directly.

    If the pass raises, last_run is NOT advanced — the next tick retries
    (per-connection failures are already contained inside the pass, so a
    whole-pass exception means something systemic like a dead DB)."""
    now = now or datetime.now(timezone.utc)
    s = load_sync_schedule(db)
    if not sync_due(now, s["mode"], s["daily_time"], s["interval_hours"],
                    s["last_run"], sync_timezone()):
        return []
    results = await broker_autosync_pass(db)
    mark_sync_ran(db, now)
    return results
```

Also update the module docstring (lines 1–19): in the sentence listing the passes, change "Two passes live here:" to "Three passes live here:" and add a bullet:

```
* :func:`autosync_tick` — the minutely scheduler gate around
  ``broker_autosync_pass``: reads the configured schedule (daily at HH:MM in
  the local timezone, or every N hours) from the AppSetting table and runs
  the pass only when due, persisting a last-run stamp so restarts and
  downtime catch up instead of double- or never-running.
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`: `python -m pytest tests/test_jobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/jobs.py backend/tests/test_jobs.py
git commit -m "feat: schedule-gated autosync_tick for the poller"
```

---

### Task 5: Rewire the main.py poller + explicit tzdata dependency

**Files:**
- Modify: `backend/main.py:422-435` (comment block) and `backend/main.py:480-487` (autosync registration), `backend/main.py:467` (import line)
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: `jobs.autosync_tick` (Task 4), existing `_periodic_loop`.
- Produces: the running scheduler. No new symbols.

- [ ] **Step 1: Update the poller comment block**

In `backend/main.py`, replace the comment block (currently lines 422–435):

```python
# --- background pollers --------------------------------------------------------
# The app has no external scheduler, so asyncio tasks handle the recurring work:
#   * price alerts  — every ALERT_CHECK_INTERVAL_SECONDS (default 15 min),
#                     opt-out ALERT_POLLER_ENABLED=0
#   * broker sync   — 60 s heartbeat; jobs.autosync_tick runs the sync when the
#                     configured schedule says so (Settings → Auto-sync
#                     schedule: daily at HH:MM — default 02:00 Europe/Prague,
#                     BROKER_SYNC_TIMEZONE overrides — or every N hours).
#                     Opt-out BROKER_AUTOSYNC_ENABLED=0; only connections whose
#                     auto_sync flag is on are synced (per-portfolio opt-in).
#                     Last-run is persisted, so a missed boundary (asleep at
#                     2 AM) catches up at the first tick after startup.
#   * dividends     — every DIVIDEND_NOTIFY_INTERVAL_SECONDS (default 12 h),
#                     opt-out DIVIDEND_NOTIFY_ENABLED=0; announces ex-dates due
#                     within DIVIDEND_NOTIFY_LEAD_DAYS (default 3), each at most
#                     once (dividend_notifications dedup table)
# Each tick uses its own DB session and swallows errors so a bad pass never
# takes the app down. While the process is asleep between ticks nothing fires —
# these are self-hosted convenience pollers, not low-latency feeds.
```

- [ ] **Step 2: Swap the registration**

In `_start_background_pollers`, change the jobs import (line 467):

```python
    from jobs import autosync_tick, dividend_exdate_pass
```

and replace the autosync block (currently lines 480–487):

```python
    if os.environ.get("BROKER_AUTOSYNC_ENABLED", "1") == "1":
        # 60 s heartbeat: each tick asks jobs.autosync_tick whether the
        # configured schedule is due; the sync itself runs only then. Short
        # initial delay so a restart quickly catches up on a missed boundary
        # (the persisted last-run makes early ticks safe).
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("autosync", autosync_tick, interval=60, initial_delay=300)))
```

(`BROKER_AUTOSYNC_INTERVAL_SECONDS` disappears — the DB settings own the cadence now.)

- [ ] **Step 3: Make tzdata explicit**

Append to `backend/requirements.txt` (after `httpx>=0.27`):

```
tzdata>=2024.1
```

- [ ] **Step 4: Verify the app still boots and the suite passes**

From `backend/`: `python -m pytest tests/ -v`
Expected: PASS (no test exercises the loop itself; this catches import errors).

Then boot check: `python -c "import main"` from `backend/` (venv active).
Expected: exits 0, no traceback.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/requirements.txt
git commit -m "feat: drive broker auto-sync from the configurable schedule"
```

---

### Task 6: Settings API — `GET/PUT /api/settings/sync-schedule`

**Files:**
- Create: `backend/routers/settings.py`
- Modify: `backend/main.py:18` (router import) and after `backend/main.py:414` (include_router)
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `jobs.load_sync_schedule`, `jobs.next_sync_run`, `jobs.sync_timezone`, key constants (Tasks 2–3); `app_settings.set_setting` (Task 1).
- Produces: `GET /api/settings/sync-schedule` → `{mode, daily_time, interval_hours, timezone, last_run, next_run}` (ISO strings or null); `PUT` with body `{mode, daily_time, interval_hours}` (all three required) → same payload as GET. Task 7's frontend helpers call these paths.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_settings.py`:

```python
"""Tests for the global settings router (sync schedule)."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jobs import mark_sync_ran
from routers.settings import SyncSchedule, get_sync_schedule, put_sync_schedule


def test_get_returns_defaults_on_fresh_db(db_session, monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)
    out = get_sync_schedule(db_session)
    assert out == {"mode": "daily", "daily_time": "02:00", "interval_hours": 6,
                   "timezone": "Europe/Prague", "last_run": None,
                   "next_run": None}  # never ran -> due now -> next_run null


def test_get_computes_next_run_after_a_sync(db_session):
    mark_sync_ran(db_session, datetime.now(timezone.utc))
    out = get_sync_schedule(db_session)
    assert out["last_run"] is not None
    assert out["next_run"] is not None  # just ran -> not due -> concrete next time


def test_put_persists_and_echoes(db_session):
    out = put_sync_schedule(
        SyncSchedule(mode="interval", daily_time="04:30", interval_hours=12), db_session)
    assert (out["mode"], out["daily_time"], out["interval_hours"]) == ("interval", "04:30", 12)
    # survives a fresh read
    again = get_sync_schedule(db_session)
    assert (again["mode"], again["daily_time"], again["interval_hours"]) == ("interval", "04:30", 12)


@pytest.mark.parametrize("bad", [
    {"mode": "weekly", "daily_time": "02:00", "interval_hours": 6},
    {"mode": "daily", "daily_time": "25:00", "interval_hours": 6},
    {"mode": "daily", "daily_time": "2am", "interval_hours": 6},
    {"mode": "daily", "daily_time": "02:00", "interval_hours": 0},
    {"mode": "daily", "daily_time": "02:00", "interval_hours": 200},
])
def test_put_payload_validation(bad):
    with pytest.raises(ValidationError):
        SyncSchedule(**bad)
```

- [ ] **Step 2: Run tests to verify they fail**

From `backend/`: `python -m pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routers.settings'`

- [ ] **Step 3: Write the implementation**

Create `backend/routers/settings.py`:

```python
"""Global (non-portfolio-scoped) app settings. Currently just the broker
auto-sync schedule; frontend note: '/settings' must stay listed in
PORTFOLIO_AGNOSTIC_PREFIXES in frontend/src/api.js."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app_settings import set_setting
from database import get_db
from jobs import (SYNC_DAILY_TIME_KEY, SYNC_INTERVAL_HOURS_KEY, SYNC_MODE_KEY,
                  load_sync_schedule, next_sync_run, sync_timezone)

router = APIRouter(prefix="/settings", tags=["settings"])


class SyncSchedule(BaseModel):
    mode: Literal["daily", "interval"]
    daily_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    interval_hours: int = Field(ge=1, le=168)


@router.get("/sync-schedule")
def get_sync_schedule(db: Session = Depends(get_db)):
    s = load_sync_schedule(db)
    tz = sync_timezone()
    nxt = next_sync_run(datetime.now(timezone.utc), s["mode"], s["daily_time"],
                        s["interval_hours"], s["last_run"], tz)
    return {
        "mode": s["mode"],
        "daily_time": s["daily_time"],
        "interval_hours": s["interval_hours"],
        "timezone": tz.key,
        "last_run": s["last_run"].isoformat() if s["last_run"] else None,
        "next_run": nxt.isoformat() if nxt else None,
    }


@router.put("/sync-schedule")
def put_sync_schedule(payload: SyncSchedule, db: Session = Depends(get_db)):
    set_setting(db, SYNC_MODE_KEY, payload.mode)
    set_setting(db, SYNC_DAILY_TIME_KEY, payload.daily_time)
    set_setting(db, SYNC_INTERVAL_HOURS_KEY, str(payload.interval_hours))
    db.commit()
    return get_sync_schedule(db)
```

In `backend/main.py` line 18, add `settings` to the routers import:

```python
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, dividend_calendar, cash, alerts, settings
```

and after the last `include_router` (line 414):

```python
app.include_router(settings.router, prefix="/api")
```

- [ ] **Step 4: Run tests to verify they pass**

From `backend/`: `python -m pytest tests/test_settings.py tests/ -v`
Expected: PASS (whole suite)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/settings.py backend/main.py backend/tests/test_settings.py
git commit -m "feat: sync-schedule settings API"
```

---

### Task 7: Frontend — API helpers + `SyncScheduleSettings` card

**Files:**
- Modify: `frontend/src/api.js:21` (agnostic prefixes) and add two helpers near the broker section
- Create: `frontend/src/components/SyncScheduleSettings.jsx`
- Test: `frontend/src/components/SyncScheduleSettings.test.jsx`

**Interfaces:**
- Consumes: `GET/PUT /api/settings/sync-schedule` (Task 6 payload shapes).
- Produces: `fetchSyncSchedule()` / `updateSyncSchedule(data)` exports in `api.js`; default-export React component `SyncScheduleSettings` (no props). Task 8 mounts it.

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/components/SyncScheduleSettings.test.jsx`:

```jsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SyncScheduleSettings from "./SyncScheduleSettings";

// vi.mock factories are hoisted above top-level consts — a plain `const spy`
// referenced inside the factory would hit a TDZ error. vi.hoisted() runs first.
const mocks = vi.hoisted(() => ({
  updateSyncSchedule: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../api", () => ({
  fetchSyncSchedule: () =>
    Promise.resolve({
      mode: "daily",
      daily_time: "02:00",
      interval_hours: 6,
      timezone: "Europe/Prague",
      last_run: null,
      next_run: null,
    }),
  updateSyncSchedule: mocks.updateSyncSchedule,
}));

function mount() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SyncScheduleSettings />
    </QueryClientProvider>
  );
}

describe("SyncScheduleSettings", () => {
  it("seeds the form from the API and shows the timezone", async () => {
    mount();
    expect(await screen.findByText(/Auto-sync schedule/i)).toBeInTheDocument();
    expect(await screen.findByDisplayValue("02:00")).toBeInTheDocument();
    expect(screen.getByText(/Europe\/Prague/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /daily at/i })).toBeChecked();
  });

  it("saves the edited schedule", async () => {
    mount();
    await screen.findByDisplayValue("02:00");
    fireEvent.click(screen.getByRole("radio", { name: /every/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(mocks.updateSyncSchedule).toHaveBeenCalledWith({
        mode: "interval",
        daily_time: "02:00",
        interval_hours: 6,
      })
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

From `frontend/`: `npm test -- SyncScheduleSettings`
Expected: FAIL — cannot resolve `./SyncScheduleSettings`

- [ ] **Step 3: Add the API helpers**

In `frontend/src/api.js`, change line 21 to:

```js
const PORTFOLIO_AGNOSTIC_PREFIXES = ["/portfolios", "/market", "/watchlists", "/settings"];
```

and add (near the broker/T212 helpers section):

```js
// ----- Global settings (not portfolio-scoped) ---------------------------------

export const fetchSyncSchedule = () => api.get("/settings/sync-schedule").then((r) => r.data);
export const updateSyncSchedule = (data) => api.put("/settings/sync-schedule", data).then((r) => r.data);
```

- [ ] **Step 4: Write the component**

Create `frontend/src/components/SyncScheduleSettings.jsx`:

```jsx
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { fetchSyncSchedule, updateSyncSchedule } from "../api";

// Global card on the Settings page: when do brokers with auto-sync enabled
// check for new trades. Mirrors GET/PUT /api/settings/sync-schedule.
export default function SyncScheduleSettings() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState(null); // null = form not seeded from the server yet
  const [dailyTime, setDailyTime] = useState("02:00");
  const [intervalHours, setIntervalHours] = useState(6);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const { data: schedule, isLoading } = useQuery({
    queryKey: ["sync-schedule"],
    queryFn: fetchSyncSchedule,
  });

  useEffect(() => {
    if (schedule && mode === null) {
      setMode(schedule.mode);
      setDailyTime(schedule.daily_time);
      setIntervalHours(schedule.interval_hours);
    }
  }, [schedule, mode]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateSyncSchedule({ mode, daily_time: dailyTime, interval_hours: Number(intervalHours) }),
    onSuccess: () => {
      setError(null);
      setSuccess("Schedule saved");
      queryClient.invalidateQueries({ queryKey: ["sync-schedule"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to save schedule");
    },
  });

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Auto-sync schedule</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          When connected brokers with auto-sync enabled check for new trades.
          {schedule?.timezone && <> Times are in {schedule.timezone}.</>}
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 text-sm text-emerald-600 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
          <CheckCircle2 size={16} className="shrink-0" />
          {success}
        </div>
      )}

      {isLoading || mode === null ? (
        <Loader2 size={18} className="animate-spin text-slate-400" />
      ) : (
        <div className="space-y-4">
          <div className="space-y-3">
            <label className="flex items-center gap-3 text-sm text-slate-700">
              <input
                type="radio"
                name="sync-mode"
                checked={mode === "daily"}
                onChange={() => setMode("daily")}
              />
              <span>Daily at</span>
              <input
                type="time"
                value={dailyTime}
                onChange={(e) => setDailyTime(e.target.value)}
                disabled={mode !== "daily"}
                className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:border-brand disabled:opacity-40"
              />
            </label>
            <label className="flex items-center gap-3 text-sm text-slate-700">
              <input
                type="radio"
                name="sync-mode"
                checked={mode === "interval"}
                onChange={() => setMode("interval")}
              />
              <span>Every</span>
              <input
                type="number"
                min="1"
                max="168"
                value={intervalHours}
                onChange={(e) => setIntervalHours(e.target.value)}
                disabled={mode !== "interval"}
                className="w-20 bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:border-brand disabled:opacity-40"
              />
              <span>hours</span>
            </label>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Clock size={16} />
              )}
              Save schedule
            </button>
            <div className="text-xs text-slate-400 space-y-0.5">
              <div>
                Last sync:{" "}
                {schedule?.last_run ? new Date(schedule.last_run).toLocaleString() : "never"}
              </div>
              <div>
                Next sync:{" "}
                {schedule?.next_run
                  ? new Date(schedule.next_run).toLocaleString()
                  : "at the next check (within a minute)"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

From `frontend/`: `npm test -- SyncScheduleSettings`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/components/SyncScheduleSettings.jsx frontend/src/components/SyncScheduleSettings.test.jsx
git commit -m "feat: sync schedule settings card + API helpers"
```

---

### Task 8: Mount the card + fix stale copy (Settings page, README)

**Files:**
- Modify: `frontend/src/pages/Settings.jsx` (import, mount before `<DiscordSettings />`, two copy strings at lines 355 and 507)
- Modify: `README.md:138`

**Interfaces:**
- Consumes: `SyncScheduleSettings` component (Task 7).
- Produces: user-visible feature; no new symbols.

- [ ] **Step 1: Mount the card**

In `frontend/src/pages/Settings.jsx` add to the imports:

```jsx
import SyncScheduleSettings from "../components/SyncScheduleSettings";
```

and just above `<DiscordSettings />` (line 549) add:

```jsx
      <SyncScheduleSettings />
```

- [ ] **Step 2: Fix the stale "every 6 h" copy**

Two occurrences (lines 355 and 507), both currently:

```jsx
<span className="text-xs text-slate-400 ml-2">checks for new trades every 6 h</span>
```

change both to:

```jsx
<span className="text-xs text-slate-400 ml-2">checks for new trades on the auto-sync schedule below</span>
```

- [ ] **Step 3: Update the README feature line**

`README.md` line 138, currently:

```
- **Background auto-sync** — opt-in per broker connection (T212 + IBKR); a poller syncs every 6 h and announces imports on Discord
```

change to:

```
- **Background auto-sync** — opt-in per broker connection (T212 + IBKR); syncs on a configurable schedule (daily at a set time — default 02:00 Europe/Prague — or every N hours; Settings → Auto-sync schedule) and announces imports on Discord
```

- [ ] **Step 4: Run the frontend suite and build**

From `frontend/`: `npm test` then `npm run build`
Expected: all tests PASS; build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Settings.jsx README.md
git commit -m "feat: surface auto-sync schedule on the Settings page"
```

---

### Task 9: End-to-end verification

**Files:** none created/modified (fixes go into the task that owns the file).

- [ ] **Step 1: Full backend suite**

From `backend/`: `python -m pytest tests/ -v`
Expected: PASS, zero failures.

- [ ] **Step 2: Full frontend suite + build**

From `frontend/`: `npm test` and `npm run build`
Expected: PASS / build OK.

- [ ] **Step 3: Live check via Playwright MCP (per project CLAUDE.md)**

Start the dev servers (`start.bat` from the repo root, or backend `uvicorn main:app --reload --port 8000` + frontend `npm run dev`), then drive `http://localhost:5173`:

1. Log in (dev password `snowball-dev` unless `APP_PASSWORD` is set).
2. Open Settings → confirm the "Auto-sync schedule" card renders with "Daily at 02:00" selected and "Times are in Europe/Prague."
3. Switch to "Every N hours", set 12, Save → "Schedule saved" banner appears; reload the page → form shows interval/12 (persisted).
4. Switch back to "Daily at", set 02:00, Save.
5. Confirm the backend log shows the `portfyl.autosync` poller running without errors (it ticks every 60 s after a 5-minute initial delay).

Expected: all five observations hold. Screenshot the card for the record.

- [ ] **Step 4: Report**

Summarize test results and the Playwright observations; do NOT push or merge — integration is decided via superpowers:finishing-a-development-branch.
