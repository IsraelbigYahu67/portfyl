# Portfyl's Own E-mails, Wave 1: Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** plan, waiting for the founder's approval. No code written.

**Goal:** Close all seven findings of the 2026-11-16 review of wave 1 (`docs/superpowers/plans/2026-11-15-portfyl-own-emails-wave1.md`, Task 9 report).

**Spec:** `docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md` (§ below refers to it). Task 6 amends the spec where this plan changes its rules.

**Tech stack:** unchanged. No new dependency, no migration.

## Findings and the fix chosen for each

| # | Severity | Finding | Fix | Task |
|---|---|---|---|---|
| 1 | Medium | While Brevo is failing, only a reset for an **existing** account attempts a send, and only attempted sends move the health flag. `202` turning into `503 email_unavailable` therefore reveals the account. | Every reset path that does not send makes one **health probe** to Brevo that moves the flag exactly like a send would. The flag then moves the same way whether or not the account exists. | 1, 4 |
| 2 | Low | A missing, non-string or over-long `email` answers `422`, not the `202` the spec promises for malformed input. | `email` is accepted as anything; the handler treats a non-string or over-long value as an invalid address (`202`, no send). | 4 |
| 3 | Low | Above the 1.5 s floor the existing-account path is slower (one more outbound call). | The probe from fix 1 gives both paths one Firebase call and one Brevo call. The response time is additionally rounded up to a 0.5 s step. | 4 |
| 4 | Low | No PostgreSQL test covers the `auth.email.sent` audit row under real RLS (the wave 1 plan claimed the suite proves it). | New test in `tests/postgres/`. | 3 |
| 5 | Low | For an address known to Firebase but with no Portfyl user, the audit lookup leaves its transaction open during the floor sleep (a pooled connection held up to 1.5 s). | `database.release_connection(db)` before the sleep. | 4 |
| 6 | Low | The reset e-mail is sent to, and shows, the lower-cased address instead of the one typed (wave 1 review focus 1). | Send to and show the typed address (trimmed). The normalized form stays for the rate-limit bucket and the `User` lookup. | 4 |
| 7 | Note | The one-time code is in the query of `/auth/action`, so Cloud Run and Cloudflare request logs record it. | Portfyl-built links carry their parameters in the URL **fragment** (`/auth/action#mode=…`), which browsers never send to a server. The page reads the fragment first and the query second (Firebase's fallback e-mails and links already sent keep working). | 2, 5 |

Residuals that stay, and why:

- **Fix 1:** if Brevo's send endpoint fails while its account endpoint works (a partial outage), the probe succeeds and the oracle remains for that period. A wrong or revoked key and a full outage, the realistic cases, are closed.
- **Fix 2:** a body that is not a JSON object at all still gets FastAPI's `422`. It cannot depend on an account.
- **Fix 3:** differences smaller than one 0.5 s step can still cross a step boundary. Registration already tells a caller that an address is taken (§5.3).
- **Fix 7:** Firebase's own fallback e-mails keep the code in the query; Portfyl cannot change those. It ends when the fallback is removed (§5.10 step 5).

Alternative considered for fix 1 and rejected: reset sends do not count toward the health flag at all. It removes the oracle completely and needs no probe, but with a revoked key every reset is silently lost until a verification e-mail happens to fail, which is exactly what the flag exists to prevent (§5.3).

## Global Constraints

- All constraints of the wave 1 plan still hold (plain `def`, no address / link / code / key in logs, exceptions or audit rows, a wrong setting never stops a start, colors only in `backend/emails/render.py`).
- Branch `fix/own-emails-review`, created from `main`. Nobody commits to `main`. No push, merge or deploy without the founder's word.
- No migration, no change to `requirements*.txt` / `*.lock` / `package.json`.
- Brevo timeouts stay connect 3 s, total 5 s, no retry, for the probe too.
- The probe never sends an e-mail and never puts the key or a response body in a log or exception.
- **Deploy order matters for fix 7:** the frontend that reads the fragment (Task 2) must be live before the backend starts sending fragment links (Task 5). They ship in two separate deploys.

## Review Focus

1. **The flag moves the same for both kinds of address.** With a transport whose every call answers `401`: one reset for an unknown address, then a second request → `503`. Same with an existing address. With `5xx`: two failures from any mix of existing and unknown addresses plus one more of either kind → `503`.
2. **A successful probe must not heal the flag.** Two failed sends, one successful probe, one failed send → the mailer is off (the count is still 3).
3. **Old links still open.** `/auth/action?mode=verifyEmail&oobCode=x` (query) and `/auth/action#mode=verifyEmail&oobCode=x` (fragment) both reach the same code path; with both present the fragment wins.
4. **Nothing new in the logs.** The probe logs a reason code only; the log test from wave 1 covers the new paths.
5. **The typed address.** ` Jana@Example.com ` → recipient and e-mail body `Jana@Example.com`, bucket and `User` lookup `jana@example.com`.

## File Structure

| File | Change |
|---|---|
| `backend/emails/transport.py` | `probe()` on `BrevoTransport` and `ConsoleTransport`, in the `EmailTransport` protocol |
| `backend/routers/auth_email.py` | reset handler: probe on non-send paths, lenient `email`, time step, release before sleep, typed address |
| `backend/emails/links.py` | action URL parameters in the fragment |
| `frontend/src/pages/AuthAction.jsx` | read fragment, then query; clean both from the address bar |
| `backend/tests/test_email_transport.py`, `test_auth_email_routes.py`, `test_email_links.py`, `frontend/src/pages/AuthAction.test.jsx` | tests |
| `backend/tests/postgres/test_auth_email_audit.py` | new |
| `deploy/cloudrun.md`, the spec, `CLAUDE.md` (only if a sentence becomes wrong) | docs |

## Execution Waves

- **Wave A (parallel, disjoint files):** Task 1 (`transport.py`), Task 2 (`AuthAction.jsx`), Task 3 (new PostgreSQL test file).
- **Wave B:** Task 4 (`auth_email.py`; needs Task 1's `probe()`).
- **Deploy 1** (founder): Waves A and B. From here the page reads fragment links.
- **Wave C:** Task 5 (`links.py`), then Task 6 (docs, full verification).
- **Deploy 2** (founder): Wave C.

Tasks in one wave use separate worktrees off `fix/own-emails-review` and are merged back before the next wave. The test PostgreSQL (port 55441) is used by one task at a time: Task 3 in Wave A, Task 6 in Wave C.

---

### Task 1: Health probe on the transport

**Files:** `backend/emails/transport.py`, `backend/tests/test_email_transport.py`

**Interface produced:** `EmailTransport.probe() -> None`. Never raises.

- `BrevoTransport.probe()`: `GET https://api.brevo.com/v3/account` with the `api-key` header and the same `_TIMEOUT`. Outcome handling mirrors `send`:
  - timeout / network error → `_record_failure("brevo_timeout" | "brevo_network")`
  - `401` / `403` → `_record_failure(reason, auth=True)`
  - `429` / `5xx` → `_record_failure(reason)`
  - anything else, `200` included → **nothing** (no `_record_success`: only a real send proves sending works).
- `ConsoleTransport.probe()`: no-op.

- [ ] **Step 0:** Open Brevo's API reference and confirm `GET /v3/account` exists, takes the `api-key` header and answers `401` for a bad key. If it does not, stop and report; do not pick another endpoint silently.
- [ ] **Step 1: Failing tests** in `test_email_transport.py`: request shape (method, URL, header, timeout); `401` switches the mailer off at once; three `503` probes switch it off; two failed sends + a `200` probe + one failed send switch it off (review focus 2); a `400` probe is not counted; a timeout is counted and does not raise; the key is in no log record.
- [ ] **Step 2:** Run `python -m pytest tests/test_email_transport.py -q` — the new tests FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file again — PASS.
- [ ] **Step 5:** Commit `fix(emails): health probe so the mailer flag does not depend on who is asked`

### Task 2: The action page reads the fragment

**Files:** `frontend/src/pages/AuthAction.jsx`, `frontend/src/pages/AuthAction.test.jsx`

- `readActionParams(location)`: if `location.hash` (without `#`) parses to a `mode` or an `oobCode`, use the fragment; otherwise use `location.search` as today. Same four fields (`mode`, `code`, `continueUrl`, `lang`). The same-origin check on `continueUrl` is unchanged.
- The address-bar cleanup runs when either `location.search` or `location.hash` is non-empty.
- No visual change, so `DESIGN.md` is not touched (read it anyway, per `CLAUDE.md`).

- [ ] **Step 1: Failing tests:** fragment link verifies the e-mail; fragment link opens the reset form; `lang` from the fragment drives `previewLanguage`; both present → the fragment's code is used; a fragment with no known key (`#top`) falls back to the query; the address bar ends as `/auth/action` with no query and no fragment.
- [ ] **Step 2:** Run `npx vitest run src/pages/AuthAction.test.jsx` — the new tests FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `npm test` and `npm run test:cloud` — PASS.
- [ ] **Step 5:** Commit `fix(auth): the e-mail action page accepts its parameters in the URL fragment`

### Task 3: PostgreSQL test for the audit row

**Files:** create `backend/tests/postgres/test_auth_email_audit.py` (nothing else)

Use `postgres_engine`, `matrix_tenants` and the app built like `_matrix_app` in `tests/postgres/conftest.py`, with `app.state.portfyl_mailer` set to a fake transport and fake links (copy the two small fakes from `tests/test_auth_email_routes.py`; do not import across test packages if the suite does not already do so). Patch `_sleep` so the test does not wait.

- [ ] **Step 1: Tests**
  - reset for Alice's address → `202`; exactly one `audit_logs` row with `action = 'auth.email.sent'`, `actor_user_id` = Alice, `workspace_id IS NULL`, metadata exactly `{"kind": "password_reset", "lang": "cs"}`.
  - that row is visible in a runtime session with Alice's RLS context and **not** with Bob's.
  - reset for an address with no Portfyl user → `202`, no row.
  - no column of the new `audit_logs` row and no `rate_limit_buckets` key contains the address.
- [ ] **Step 2:** `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`, then `python -m pytest tests/postgres/test_auth_email_audit.py -q` — PASS. If a test fails, that is a real bug in wave 1: stop and report it, do not bend the test.
- [ ] **Step 3:** Commit `test(auth): audit row of a password-reset e-mail under real RLS`

### Task 4: The reset handler

**Files:** `backend/routers/auth_email.py`, `backend/tests/test_auth_email_routes.py` (extend `FakeTransport` with `probe()` and a call counter)

Changes, all inside the password-reset path; the verification endpoint is not touched.

1. **Lenient body (finding 2).** `PasswordResetRequest.email: Any = None`. In the handler: not a `str`, or longer than 320 characters after trimming → log `outcome=invalid_address`, no limiter call, no Firebase call. `lang` stays as it is.
2. **Typed address (finding 6).** `typed = raw.strip()`; `normalized = normalize_email(typed)`. Limiter identity `reset:{normalized}` and the `User` lookup use `normalized`; `password_reset_url`, `render(params={"email": …})` and `transport.send(to=…)` use `typed`. The plausibility check runs on `typed`.
3. **Probe (findings 1 and 3).** Every path of `_attempt_password_reset` that returns **without calling `transport.send`** calls `mailer.transport.probe()` exactly once before returning: `invalid_address`, `target_limited`, `limiter_unavailable`, `no_account`, `ActionLinkError`. Implement it once (a `sent` boolean and one `probe()` at the end, or a `try/finally`), not five times. An unexpected exception caught by the endpoint's outer `except` also probes if no send was attempted.
4. **Time step (finding 3).** New constant `RESET_STEP_SECONDS = 0.5`. After the work: `elapsed = _now() - start`; `target = max(RESET_MIN_SECONDS, ceil(elapsed / RESET_STEP_SECONDS) * RESET_STEP_SECONDS)`; `_sleep(max(0.0, target - elapsed))`.
5. **Release before the sleep (finding 5).** `release_connection(db)` right before `_sleep` (import from `database`). It must not raise into the answer: wrap like the audit failure path.

- [ ] **Step 1: Failing tests**
  - `email` missing, `null`, `123`, a list, 400 characters → `202 {"status":"accepted"}`, no send, floor applied.
  - parametrised over *existing / unknown / invalid / target-limited*: with a transport answering `401` to everything, the **next** request is `503 email_unavailable` in every case (review focus 1); same for three `503`s across mixed cases.
  - exactly one Brevo call (send **or** probe) per reset request on every path; the verification endpoint never probes.
  - ` Jana@Example.com ` → `send(to="Jana@Example.com")`, the rendered text contains `Jana@Example.com`, limiter identity is `reset:jana@example.com`, the audit row is still written for the user stored as `jana@example.com` (review focus 5).
  - clock tests: work of 0.2 s → answer at 1.5 s; 1.6 s → 2.0 s; 2.0 s → 2.0 s; 4.9 s → 5.0 s.
  - the session holds no open transaction when `_sleep` is called, on the "Firebase account, no Portfyl user" path (assert with the test's `Session`: `db.in_transaction()` is false inside a patched `_sleep`).
  - the existing "same answer for every outcome" and "logs never contain the address, the link or the code" tests extended to the new paths.
- [ ] **Step 2:** Run `python -m pytest tests/test_auth_email_routes.py -q` — the new tests FAIL.
- [ ] **Step 3:** Implement. Update the module docstring's third rule.
- [ ] **Step 4:** Run `python -m pytest tests/ --ignore=tests/postgres -q` — PASS, `tests/test_event_loop_not_blocked.py` included.
- [ ] **Step 5:** Run Task 3's file against the test PostgreSQL again — PASS.
- [ ] **Step 6:** Commit `fix(auth): password-reset answer and mailer flag no longer depend on the account`

### Task 5: Links carry the code in the fragment (after deploy 1)

**Files:** `backend/emails/links.py`, `backend/tests/test_email_links.py`, `backend/tests/test_auth_email_routes.py` (link assertions only)

- `_action_url` returns `f"{app_url}/auth/action#{urlencode(params)}"`. Parameters and their order are unchanged.
- `logging_setup`'s `oobCode=` redaction already matches inside a fragment; add one assertion for a `#…oobCode=` URL to `tests/test_logging_setup.py` if none covers it (that file is then part of this task).

- [ ] **Step 0:** Confirm with the founder that deploy 1 is live (the page reads fragments). Do not start otherwise.
- [ ] **Step 1: Failing tests:** the built URL has no query; `urlsplit(url).fragment` parses to `mode`, `oobCode`, `lang` (and `continueUrl` for verification); the plain-text e-mail carries the full link with the fragment; the HTML still shows no raw URL.
- [ ] **Step 2–4:** Run (FAIL), implement, run the fast suite (PASS).
- [ ] **Step 5:** Commit `fix(emails): one-time code in the link's fragment, out of request logs`

### Task 6: Docs and full verification

**Files:** `docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md`, `deploy/cloudrun.md`, `CLAUDE.md` only if a sentence in it became wrong

- [ ] **Step 1: Spec.** §5.2: the link form with `#`, and why. §5.3: malformed `email` → `202`; the probe and the rule "the flag moves the same for every address"; the 0.5 s step; the residuals listed at the top of this plan. §5.9: the typed address is used for sending, the normalized one for limits and lookup. §9: the new tests. §11: two new checklist items (below).
- [ ] **Step 2: `deploy/cloudrun.md`, "Portfyl e-mails".**
  - "When it fails": the probe (`GET /v3/account`) also moves the flag.
  - Checklist additions: (8) the link in the received e-mail has `#`, opens the page from Gmail web, Gmail phone, Outlook and Seznam, and the new revision's Cloud Run request log shows `/auth/action` **without** a code; (9) if a mail client or Brevo's click tracking drops the fragment, revert Task 5's commit and redeploy (the page still reads query links).
  - "E-mail action links", step 1: the anonymous test URL works in both forms.
- [ ] **Step 3: Run everything.**
  - `cd backend && python -m pytest tests/ --ignore=tests/postgres -q` on Python 3.12 **and** 3.14 — PASS
  - `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && python -m pytest tests/postgres/ -q` — PASS. If Docker is not running, say so; do not claim the suite passed.
  - `cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud` — PASS
- [ ] **Step 4: By hand,** local edition with `PORTFYL_EMAIL_TRANSPORT=console`: forgot-password for an unknown address and a malformed body → `202` at 1.5 s; the console link has `#`; opening it in the browser at `http://localhost:5173` shows the reset form and leaves `/auth/action` in the address bar; an old-style `?mode=…` link still opens.
- [ ] **Step 5:** Commit `docs(auth): review fixes for Portfyl's own e-mails`
- [ ] **Step 6: Stop.** Report commits, test counts per command, what was and was not verified by hand, and what production needs: deploy 1, then deploy 2, then checklist items 8 and 9 with a real inbox.

## What the founder decides or does

1. Approve the fix for finding 1 (probe) or choose the rejected alternative (reset sends do not move the flag).
2. Approve fix 7. It changes the link format in every e-mail and needs two deploys; the alternative is to accept the code in request logs (it is single-use and short-lived).
3. Run deploy 1 and deploy 2, and checklist items 8 and 9.

Independent of this plan and still open from Task 9: production needs the four `RATE_LIMIT_AUTH_EMAIL_*` values before the next routine redeploy of `main` ("Portfyl e-mails" in `deploy/cloudrun.md`).
