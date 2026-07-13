# Broker auto-sync schedule — design

**Date:** 2026-07-13
**Status:** Approved

## Problem

Broker auto-sync currently runs on a fixed 6-hour interval (`BROKER_AUTOSYNC_INTERVAL_SECONDS`,
poller in `backend/main.py`). The user wants it to run once a day at 02:00 in
their timezone (Europe/Prague), and wants the schedule configurable from the
Settings page rather than via env vars.

## Decisions (from brainstorming)

- **Timezone:** hardcoded `Europe/Prague` backend constant, overridable with the
  `BROKER_SYNC_TIMEZONE` env var. No timezone UI.
- **Missed runs:** catch up. If the app was down/asleep at 02:00, the sync runs
  at the first opportunity afterwards (startup or next tick). Import dedup makes
  early/extra runs safe.
- **Settings scope:** one global schedule with a mode choice — "daily at HH:MM"
  (new default, 02:00) or "every N hours" (preserves current behavior as an
  option). Per-broker `auto_sync` toggles remain the on/off switches; the
  schedule only controls *when* opted-in connections sync.

## Approach

Heartbeat + due-check. The autosync background task ticks every 60 seconds;
each tick reads the schedule config and a persisted last-run timestamp from the
DB and runs the sync pass when it is due. Chosen over sleep-until-next-run
(needs task wake/restart machinery on settings change) and external cron /
Cloud Scheduler (infra outside the repo; the codebase deliberately uses
self-hosted convenience pollers). Settings changes take effect within a minute,
no restart needed.

## Data model

No schema change. Four keys in the existing `AppSetting` key/value store:

| Key | Values | Default |
| --- | --- | --- |
| `broker_sync_mode` | `daily` \| `interval` | `daily` |
| `broker_sync_daily_time` | `HH:MM` (24h) | `02:00` |
| `broker_sync_interval_hours` | int 1–168 | `6` |
| `broker_sync_last_run` | ISO-8601 UTC timestamp | absent (= never ran) |

`broker_sync_last_run` is written after each completed pass (in both modes).
Missing/invalid values fall back to defaults.

## Scheduler (backend/main.py + backend/jobs.py)

- The autosync registration in `_start_background_pollers` becomes a 60-second
  heartbeat loop, keeping the existing 5-minute initial delay.
- Each tick evaluates a pure function in `jobs.py`:

  `sync_due(now, mode, daily_time, interval_hours, last_run, tz) -> bool`

  - **daily:** due when `now` ≥ the most recent `daily_time` boundary in `tz`
    (today's, or yesterday's if `now` is before today's) **and** `last_run` is
    missing or older than that boundary. This rule *is* the catch-up: the first
    tick after downtime sees the missed boundary and fires.
  - **interval:** due when `last_run` is missing or `now − last_run` ≥ the
    interval. Because `last_run` is persisted, restarts no longer reset the
    countdown (improves on the current in-memory behavior).
- When due: run the existing `broker_autosync_pass` unchanged, then persist
  `last_run = now (UTC)`. If the pass raises, `last_run` is not written and the
  next tick retries — consistent with the existing "swallow errors, never take
  the app down" poller ethos (whole-pass exceptions are already rare because
  per-connection errors are caught inside the pass).
- **DST:** `zoneinfo` handles CET/CEST. On the spring-forward night 02:00 does
  not exist in Europe/Prague; the boundary resolves to the shifted instant and
  the sync still fires exactly once.
- **Env vars:** `BROKER_AUTOSYNC_ENABLED=0` remains the kill switch.
  `BROKER_AUTOSYNC_INTERVAL_SECONDS` is retired; the DB settings own the
  schedule (interval mode default is 6 h, matching the old default).

## API (new backend/routers/settings.py, prefix /settings)

- `GET /api/settings/sync-schedule` → `{mode, daily_time, interval_hours,
  timezone, last_run, next_run}` (`next_run` computed from the same boundary
  logic, for display).
- `PUT /api/settings/sync-schedule` → validates `mode ∈ {daily, interval}`,
  `daily_time` matches `HH:MM`, `1 ≤ interval_hours ≤ 168`; upserts the
  `AppSetting` rows.
- `/settings` is global config, not portfolio-scoped → add it to
  `PORTFOLIO_AGNOSTIC_PREFIXES` in `frontend/src/api.js` (per the CLAUDE.md
  gotcha, otherwise the axios interceptor injects `portfolio_id`).

## Frontend (frontend/src/pages/Settings.jsx)

One new "Auto-sync schedule" card:

- Radio choice: **Daily at** `[time input]` / **Every** `[N]` **hours**.
- Save button (react-query mutation, matching existing Settings patterns).
- Status line: last sync time and computed next run (from the GET payload).
- Existing per-broker auto-sync toggles are unchanged.

## Testing

- `backend/tests/test_jobs.py`: unit tests for `sync_due` — daily boundary
  crossing, missed-boundary catch-up, interval mode, no-`last_run` first sync,
  and the DST spring-forward date.
- Router tests for `GET`/`PUT /settings/sync-schedule` validation and
  defaults (direct-call style against in-memory SQLite, like the other suites).

## Out of scope

- Per-broker schedules.
- Timezone picker UI.
- Guaranteed-time execution on Cloud Run scale-to-zero (would need Cloud
  Scheduler; catch-up covers the daily-import use case).
