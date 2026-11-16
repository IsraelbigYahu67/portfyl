# Portfyl's Own E-mails, Wave 2 (Account Notices) Implementation Plan

**Status:** plan, execution started 2026-11-16 on the integration branch `feat/own-emails-w2` (cut from `main` after wave 1 and its review fixes A–C). Tasks 1 and 2 merged into `feat/own-emails-w2` (wave A). Task 5 documentation written on `feat/own-emails-w2-t5` while Tasks 3 and 4 ran in parallel; the full verification of Task 5 is still open until Tasks 3 and 4 are merged and re-run (a partial run on the Task 1+2 state is recorded in the Task 5 hand-off, not here). Not merged to `main`, not deployed, no real e-mail sent.

**Goal:** Send three more e-mails through the wave 1 sender: `password_changed`, `account_deletion_scheduled`, `account_deleted`. Close the gap that a password reset does not end existing Portfyl sessions.

**Spec:** `docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md` — read §5.4–5.6, §5.9, §6, §7 (wave 2 notes), §8 (Wave 2 copy: EN and CS are given there verbatim) and §10. Read `CLAUDE.md` first.

## Global Constraints

- Branch per task off `feat/own-emails-w2`; nobody commits to `main` or to `feat/own-emails-w2` directly. The orchestrator merges task branches back between waves.
- Exactly **one** migration in this wave, owned by Task 2 (`0028_…`, one nullable column on `users`, additive and safe next to old instances). `EXPECTED_ALEMBIC_HEAD` in `backend/database.py` changes in the same commit. No other task touches `backend/alembic/versions/`, `backend/database.py`, `requirements*.txt` / `*.lock` or `package.json`.
- Only Task 2 runs the PostgreSQL suite (`backend/tests/postgres/`, Docker test database). Every other task runs the fast suite only (`cd backend && python -m pytest tests/ -q --ignore=tests/postgres`). Task 5 runs both.
- Every endpoint and dependency stays a plain `def`, never `async def`; database work never runs on the event loop.
- No e-mail address, link, one-time code or API key in any log line, exception text or audit metadata. Logs carry a kind and a reason code only.
- **Sending a notice is best effort.** A mailer that is missing, unavailable or failing must never fail, delay beyond the 5 s Brevo timeout, or roll back the user's action (deletion request, sign-in, purge). The notice is attempted after the state change is committed.
- Languages are exactly `cs en de fr es it pt pl nl`; English is source and fallback. Czech uses formal address (vykání). Plan names, broker names and "Portfyl" stay untranslated. Colors only through the constants in `backend/emails/render.py`.
- The backend stores no language (spec §3). Decisions made here, open to correction by the founder:
  - `account_deletion_scheduled` takes `lang` from the request body (frontend sends the app language, like wave 1) and **stores `lang` inside the workspace deletion state** so the purge job can use it for `account_deleted`.
  - `password_changed` takes `lang` from an optional `lang` field of the `/auth/session` body; missing or garbage → English.
- Commit messages follow the repo style (`feat(auth): …`, `test(emails): …`, `docs(deploy): …`). Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File ownership (disjoint per task)

| Task | Owns |
|---|---|
| 1 | `backend/emails/catalog.py`, `backend/emails/locales/*.py`, `backend/emails/notify.py` (new), `backend/tests/test_emails_*.py` |
| 2 | `backend/models.py` (User column), `backend/alembic/versions/0028_*.py`, `backend/database.py`, `backend/routers/auth.py`, `backend/auth.py` if needed, their tests incl. `backend/tests/postgres/` |
| 3 | `backend/account_deletion.py`, the router that calls `schedule_workspace_deletion`, `frontend/src/api.js` + the Settings deletion call site (only to add `lang`), their tests |
| 4 | the single hook in `backend/routers/auth.py` left by Task 2, tests for it |
| 5 | `deploy/cloudrun.md`, `CLAUDE.md`, spec §7/§8 status lines, this plan's status |

## Execution Waves

- **Wave A (parallel):** Task 1, Task 2.
- **Wave B (parallel, after A is merged into `feat/own-emails-w2`):** Task 3, Task 4.
- **Wave C:** Task 5.

---

### Task 1: Copy for the three e-mails, and a best-effort send helper

**Files:** see ownership table.

- Add `EmailKind.PASSWORD_CHANGED`, `ACCOUNT_DELETION_SCHEDULED`, `ACCOUNT_DELETED` and their English copy in `catalog.py` exactly as in spec §8 Wave 2 (placeholders `{email}`, `{date}`, `{datetime}` already exist in `PLACEHOLDERS`; `account_deleted` has no button, `password_changed` and `account_deletion_scheduled` have one; footer reason `account` for all three).
- Add the Czech copy from §8 verbatim and translate the other seven languages in `emails/locales/*.py`. Dates and datetimes are formatted per language by the small formatter in the locale files (spec §6); extend it if it cannot yet format a datetime.
- Extend the existing parity and render tests (every kind × every language renders, values escaped, same optional parts everywhere). An e-mail with a button must raise `TemplateError` without `action_url`, one without a button must not require it.
- New `backend/emails/notify.py` with `send_account_notice(kind, *, to, lang, params, action_url=None, mailer=None) -> bool`: renders, sends through the wave 1 transport (`build_mailer` / `get_mailer` live in `backend/routers/auth_email.py`; avoid a circular import, move the minimum into `emails/` if needed and keep wave 1 tests green), **never raises**, returns whether Brevo accepted it, honours the health flag, logs a reason code only. Tests: mailer missing, unavailable, raising, success; nothing sensitive in captured logs.
- Done when: fast suite green, `git diff` touches only owned files.

### Task 2: Detect a password change on the server, end other sessions

**Files:** see ownership table.

- Spec §7 note: the page that sets a password cannot be trusted as the trigger (a Firebase code works directly against Firebase). At `/auth/session`, compare Firebase's "password last changed" time for the user with the value Portfyl last saw. Research how to read it with the Firebase Admin SDK already in use (the REST `accounts:lookup` field is `passwordUpdatedAt`, milliseconds; check what `UserRecord` exposes in the installed version and what `FirebaseIdentityVerifier` / `VerifiedIdentity` already carry). Users without a password (Google only) are skipped.
- Migration `0028_…`: one nullable timestamp column on `users` (suggested name `password_changed_seen_at`). Update `EXPECTED_ALEMBIC_HEAD`; exactly one Alembic head; real migration test on PostgreSQL. Forward-compatible (nullable, no default backfill).
- **First sight must not notify:** when the stored value is NULL, store the current Firebase value and do nothing else, so deploying does not e-mail every existing user.
- When the value moved forward: revoke the user's other Portfyl sessions (not the one being created), write audit `auth.password_changed` (no address in metadata), and call one clearly named hook, `_on_password_changed(db, user, lang)`, which in this task is a documented no-op that Task 4 fills in. The call happens after commit and cannot fail the sign-in.
- `/auth/session` accepts an optional `lang` (garbage never gives a 422, same normalisation as wave 1).
- Tests: first sight, unchanged, changed, Google-only user, other sessions revoked and current one kept, tenant isolation unchanged (RLS suite).
- Done when: fast suite and PostgreSQL suite green, `alembic heads` equals `EXPECTED_ALEMBIC_HEAD`.

### Task 3: Deletion e-mails

**Needs:** Task 1 merged.

- `account_deletion_scheduled`: sent after `schedule_workspace_deletion` committed, in the same request, to the requesting owner. Button → Settings page where deletion is cancelled. Facts: account address, deletion date (`now + DELETION_GRACE_DAYS`). Takes `lang` from the request; add it to the request body and make the frontend send the current app language (smallest possible change at the call site). Store `lang` inside the serialized `WorkspaceDeletion` state (`_serialize` / `_parse`, bump nothing that breaks already-stored states: a state without `lang` parses as English).
- `account_deleted`: sent by `purge_due_workspace_deletions` **just before** it deletes the user (the address is gone afterwards), directly through the helper, not an outbox, in the stored `lang`. Idempotency: a purge that is retried after a crash must not send twice for an already-deleted user; a send failure must not stop or roll back the purge.
- Tests: scheduled (sent once, not on repeat request that returns the existing state, not when the mailer is down), purge (sent before deletion with the right address and language, failure does not block purge), old state without `lang`.
- Done when: fast suite green.

### Task 4: Send the `password_changed` notice

**Needs:** Tasks 1 and 2 merged.

- Fill in `_on_password_changed`: send `password_changed` through the helper to the user's address; facts row `{datetime}`; button "That wasn't me" → `/forgot-password`. Best effort, after commit, never fails the sign-in.
- Tests: notice sent once when the hook fires, not when the mailer is down, not on first sight, address never in logs or audit metadata.
- Done when: fast suite green.

### Task 5: Runbook, docs, full verification

**Needs:** Tasks 1–4 merged.

- `deploy/cloudrun.md`: wave 2 behaviour and the first-real-send check for the three e-mails (spec §11); note that session revocation after a password change is now live. `CLAUDE.md`: one sentence in the e-mails paragraph. Spec §7 table and this plan's status line.
- Full verification: fast suite on Python 3.12, PostgreSQL suite, `alembic heads` vs `EXPECTED_ALEMBIC_HEAD`, `npm test` and `npm run test:cloud`, `npm run build` and `npm run build:cloud`.
- Report anything that fails, do not paper over it.
