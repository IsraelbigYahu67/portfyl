# Free Trial Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the 10-day Pro trial: show it in the app (days left, ended notice, Pricing), stop sign-up bots with Cloudflare Turnstile, draft the legal text, and prove the whole thing with recorded verification. This plan closes Tasks 1c, 3, 4 and 6 of `2026-11-15-portfyl-landing-redesign-free-trial.md`.

**Architecture:** The backend already resolves the trial (`entitlements.resolve_entitlements`: live subscription → private test selection → active trial → Free) and returns `source`, `effective_until` and `trial_ended_reason` from `/api/billing/status`. The frontend reads that one endpoint through a shared query and renders a cloud-only banner through the edition manifest's `EditionShell`. Turnstile is checked **on demand**: `/auth/session` asks for a token only when it is about to create a new Portfyl identity, and the SPA's `AuthProvider` then shows the challenge and retries, so existing users never load Turnstile. Legal work is draft text only.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (sync `def`), `httpx` (sync client), PostgreSQL RLS, React 18 + Vite 6, `@tanstack/react-query`, Vitest, pytest.

**Spec:** `docs/superpowers/plans/2026-11-15-portfyl-landing-redesign-free-trial.md` ("Trial rules", "Review Focus", Tasks 1c/3/4/6). Executors read that plan, `CLAUDE.md` and `DESIGN.md` before starting.

## Verified state (2026-11-19, read-only)

These facts were checked while writing this plan. They change what "done" means.

- **Production has the trial switched off.** Cloud Run service `portfyl` (project `portfyl-prod-f6shqb`, `europe-west1`) is at revision **`portfyl-00032-cpq`** (not 00029) and runs with `PORTFYL_TRIAL_DAYS=0`. Nobody gets a trial today.
- **`PORTFYL_TRIAL_FINGERPRINT_KEY` does not exist** on the service, and there is no `portfyl-trial-fingerprint-key` secret in Secret Manager (only `portfyl-account-fingerprint-key`). With `PORTFYL_TRIAL_DAYS=0` this is harmless: `grant_trial` returns before it needs the key. **Raising `PORTFYL_TRIAL_DAYS` above 0 without first creating the secret makes every new registration fail with a 500** (`trials._key` raises `RuntimeError` inside `/auth/session`). The owner must create the secret first, using the recipe in `deploy/cloudrun.md` "Free trial".
- **Billing is on in production with Stripe sandbox keys** (`PORTFYL_BILLING_ENABLED=1`, `STRIPE_SECRET_KEY` → `portfyl-stripe-secret-key-sandbox`). So `/api/test-plans` is **not mounted** in prod.
- **Existing bug 1, which hides the trial:** `editions/cloud.jsx` `fetchEditionPlanCapabilities` reads `/api/test-plans`. With billing on, that call 404s, and `Dashboard.jsx` fails closed to the Free widgets for every cloud workspace, paid or trial. Task 2 fixes it by reading `/api/billing/status`.
- **Existing bug 2, which blocks conversion:** in `Pricing.jsx` `PaidPlans`, a trial workspace has `status.plan === "pro"`, so the Pro card shows a disabled "Current plan" button. A trial user cannot subscribe to Pro. Task 2 fixes it.
- **Withheld trials are invisible.** When a guard withholds the trial (`email_reused`, `disposable_domain`, `ip_limit`), only an audit event is written. The payload then looks exactly like "trials off". Task 1 adds a marker so the UI can say why.
- Alembic has one head, `0028_password_changed_seen`, equal to `EXPECTED_ALEMBIC_HEAD`. **This plan needs no migration** (see Global Constraints).
- `/auth/session` is the only place that creates a `User` (`routers/auth.py::_provision_identity`). The register page does not call it. The first exchange happens later in `VerifyEmail.jsx`, `Login.jsx` or `GoogleSignInButton.jsx`, often more than 300 s after the register form (a Turnstile token's lifetime). That is why the challenge is on demand.
- There is no `/api/health` subsystem module. Health is `GET /health` in `backend/main.py` (`checks.database`, `checks.scheduler`).
- `app.portfyl.com` sits behind Cloudflare Access (outer private-beta gate) plus the app's own `require_active_invite`. Turnstile does not touch Access: the widget runs in the browser against `challenges.cloudflare.com`, and siteverify is an outbound call from Cloud Run. Turnstile must be on **before** Access is opened for public sign-up.
- The app has 9 languages but **8 dictionary files** (`frontend/src/i18n/messages/{cs,de,es,fr,it,nl,pl,pt}.js`). English is the key. `messages.test.js` requires every `t("…")`/`msg("…")` literal in all 8 files with matching `{placeholders}`, and fails on stale keys.

## Global Constraints

- Cloud edition only for every user-visible trial or Turnstile element. Local: `_local_entitlements` and `editions/local.jsx` stay untouched, and `TurnstileConfig` is always `off` in local.
- **No migration.** The withheld marker uses the existing tenant `workspace_settings` table (`app_settings.set_workspace_setting`). Turnstile single use is enforced by Cloudflare siteverify (`timeout-or-duplicate`). If an executor finds a migration is unavoidable, stop and ask. It would be `0029_…` revising `0028_password_changed_seen`, additive only, with `EXPECTED_ALEMBIC_HEAD` updated in the same commit, and owned by Task 1 alone.
- Database code is plain `def`. Siteverify runs after `database.release_connection(db)`, and nothing is flushed at that point.
- Colors: only the tokens and classes in `DESIGN.md` (`.card`, `btn-primary`, `btn-ghost`, `Badge` tones, `text-ink`/`text-muted`/`text-brand`). No hex, no Tailwind palette classes.
- Every UI string goes through `t("…")`/`msg("…")` with a double-quoted English literal, plus an entry in all 8 dictionaries. Day counts use one key with `{days}`, and translators phrase it so any number from 1 to 10 reads correctly without plural forms (e.g. cs "Zkušební Pro – zbývající dny: {days}").
- New `localStorage`/`sessionStorage` keys use the `portfyl_` prefix, and every access is wrapped in try/catch (template: `lib/gettingStarted.js`).
- Legal: drafts only. CS markers `[[PRÁVNÍK: …]]`/`[[ROZHODNOUT: …]]`, EN markers `[[LAWYER: …]]`/`[[DECIDE: …]]`. Do not rename section headings: `#8-cookies-…` anchors are linked from `ConsentBanner.jsx`, and `Legal.test.jsx` pins the H1 titles. Each doc keeps at least one marker.
- Hotspots, one owner each: `frontend/src/i18n/messages/*.js` (Task 2 in wave 1, then Task 4 in wave 2), `deploy/cloudrun.md` + `Dockerfile` + `CLAUDE.md` (Task 4 only), `backend/main.py` (Task 3 only), `DESIGN.md` (Task 5 only), `backend/requirements*`/`package.json` (nobody: no new dependency is allowed; Turnstile loads by script tag, tests use `httpx.MockTransport`).
- Isolation: each task gets its own worktree and branch off current `main` (names below). Never commit to `main`. Do not touch the uncommitted `PreferencesSettings.jsx`/`PreferencesSettings.test.jsx` changes in the main working tree. Worktrees start clean, so leave them out of every merge.
- Resource isolation for live runs: backend on port **8010**, Vite on **5180**, preview on **4180**. Local DB name `portfyl_trial_e2e`. Test PostgreSQL in a container named `ptf-trial-pg` on host port **55461** with database `portfyl_trial_test`, used via `TEST_DATABASE_URL`. Never use the shared `55441` compose container or ports 8000/5173. Only Task 6 runs live servers.
- Never deploy or change Cloud Run, Secret Manager or Cloudflare settings. GCP access is read-only.

## Review Focus

1. **Trial ends while the app is open.** `["billing-status"]` and `["plan-capabilities"]` are cached for 60 s. A Pro endpoint then returns `403 plan_upgrade_required`. Expected: the existing `UpgradePrompt` shows, both queries refetch once, the banner turns into the ended notice, and the Dashboard narrows to Free widgets with no error screen. Tests in Task 2 (`useEntitlementRefresh`). Also, a timer refetches at `effective_until` when it is less than 24 h away.
2. **Trial already used (withheld).** The same e-mail registers again after deleting the account, or a 4th sign-up comes from one IP. Expected: the account works on Free, and a dismissible notice says a trial was already used for this e-mail address or network. Nothing says which. Tests in Task 1 (`not_eligible`) and Task 2 (banner).
3. **`PORTFYL_TRIAL_DAYS=0`.** Expected: no grant, no `trial_withheld` marker, payload `source="free"`, `trial_ended_reason=null`, and no trial element anywhere in the app. A trial granted before the switch keeps running to its `ends_at`. Tests in Task 1 (`test_trial_days_zero_keeps_running_trials_and_marks_nothing`) and Task 2 (`phase "none"`).
4. **Day counting at the edges.** The banner never shows 0 or a negative number. Under 24 h it reads "ends today". All comparisons use UTC milliseconds. Tests in Task 2 (`trialState`).
5. **Turnstile outage or misconfiguration.** Siteverify times out, or the build has no site key while the backend demands a token. Expected: new sign-ups get a clear translated error and nothing is created. Existing users log in normally. The server never lets an unverified new identity through. Tests in Task 3 (timeout → `bot_check_failed`) and Task 4 (no site key → "check unavailable" text).

---

## File structure

| Task | Creates | Modifies | Tests |
|---|---|---|---|
| 1 Trial state (backend) | — | `backend/trials.py` | `backend/tests/test_trials.py`, `backend/tests/test_entitlements.py`, `backend/tests/postgres/test_trial_rls.py` |
| 2 Trial UI (frontend) | `frontend/src/lib/trial.js`, `frontend/src/lib/billingStatusQuery.js`, `frontend/src/components/billing/TrialBanner.jsx`, `frontend/src/components/billing/useEntitlementRefresh.js`, `frontend/src/components/billing/CloudShell.jsx` | `frontend/src/editions/cloud.jsx`, `frontend/src/pages/Pricing.jsx`, `frontend/src/i18n/messages/*.js` | `lib/trial.test.js`, `components/billing/TrialBanner.test.jsx`, `components/billing/useEntitlementRefresh.test.jsx`, `pages/Pricing.test.jsx`, `editions/edition.test.jsx` |
| 3 Turnstile (backend) | `backend/turnstile.py` | `backend/routers/auth.py`, `backend/security_headers.py`, `backend/main.py` | `backend/tests/test_turnstile.py`, `backend/tests/test_auth_session_turnstile.py`, `backend/tests/test_security_headers.py`, `backend/tests/test_health.py` |
| 4 Turnstile (frontend + ops docs) | `frontend/src/auth/TurnstileWidget.jsx`, `frontend/src/auth/BotCheckDialog.jsx`, `frontend/src/auth/turnstileConfig.js` | `frontend/src/auth/AuthProvider.jsx`, `frontend/src/api.js`, `frontend/src/auth/firebase.js`, `frontend/src/i18n/messages/*.js`, `Dockerfile`, `deploy/cloudrun.md`, `CLAUDE.md` | `auth/TurnstileWidget.test.jsx`, `auth/AuthProvider.test.jsx`, `api.auth.test.js`, `pages/AuthPages.test.jsx` |
| 5 Legal drafts + legal page | — | `docs/legal/*.md` (5 files), `docs/compliance/data-processing-inventory.md`, `frontend/src/pages/Legal.jsx`, `Legal.css`, `DESIGN.md` §10 | `frontend/src/pages/Legal.test.jsx` |
| 6 Integration + verification | `docs/superpowers/plans/2026-11-19-free-trial-verification.md` (evidence) | `docs/finished.md`, both plan files (checkboxes/status) | all suites |

## Waves

| Wave | Tasks (parallel, one Sonnet agent each) | Branch / worktree | Why this order |
|---|---|---|---|
| 1 | Task 1, Task 2, Task 3, Task 5 | `feat/trial-state`, `feat/trial-ui`, `feat/turnstile-backend`, `docs/trial-legal` | Disjoint files. Task 2 builds against the payload contract below even before Task 1 merges. Task 2 owns `i18n/messages`. |
| 2 | Task 4 | `feat/turnstile-frontend` (off `main` + merged `feat/turnstile-backend` + `feat/trial-ui`) | Needs Task 3's error codes and takes over `i18n/messages` from Task 2. Sole owner of `deploy/cloudrun.md`, `Dockerfile`, `CLAUDE.md`. |
| 3 | Task 6 | `integrate/free-trial-completion` | Merges everything, re-runs every suite, records evidence. |

**Payload contract (all tasks):** `/api/billing/status` returns `plan`, `source` (`"trial" | "free" | "subscription" | "test_selection"`), `effective_until` (ISO with offset or `null`), and `trial_ended_reason` (`null | "expired" | "broker_account_reused" | "history_reused" | "not_eligible"`). `"not_eligible"` is new in Task 1. All other values exist today.

---

### Task 1: Withheld-trial marker (backend)

**Files:** see table. Branch `feat/trial-state`.

**Interfaces:**
- Produces in `backend/trials.py`: constants `NOT_ELIGIBLE = "not_eligible"` and `TRIAL_WITHHELD_SETTING = "trial_withheld"`. `trial_state(db, workspace_id, now) -> tuple[TrialGrant | None, str | None]` now also returns `(None, "not_eligible")` when the workspace has no grant and its `trial_withheld` setting is `"1"`. Signature unchanged, so `entitlements.py` needs no edit.
- Consumes: `app_settings.get_workspace_setting(db, workspace_id, key) -> str | None` and `set_workspace_setting(db, workspace_id, key, value) -> None`.

- [ ] **Step 1: Write failing tests in `backend/tests/test_trials.py`**
  - `test_withheld_trial_marks_workspace_not_eligible`: grant once for `jan@gmail.com` in workspace A. Then `grant_trial` for `j.a.n+2@gmail.com` in workspace B returns `None`. `trial_state(db, B, now) == (None, "not_eligible")`, and `get_workspace_setting(db, B, "trial_withheld") == "1"`.
  - `test_withheld_marker_written_even_without_actor`: same as above with `actor_user_id=None`. The marker is still written, and no audit event is written.
  - `test_trial_days_zero_keeps_running_trials_and_marks_nothing`: grant with the default env, then call with `PORTFYL_TRIAL_DAYS="0"`. A new workspace gets `None`, its `trial_state` is `(None, None)`, it has no `trial_withheld` setting, and the earlier grant is still active at `T + 5 days`.
  - `test_expired_reason_wins_over_marker`: a workspace with an expired grant reports `"expired"` even if the setting is present.
- [ ] **Step 2: Add to `backend/tests/test_entitlements.py`** `test_not_eligible_payload_is_free`: a withheld workspace with billing on → `payload()["plan"] == "free"`, `["source"] == "free"`, `["trial_ended_reason"] == "not_eligible"`.
- [ ] **Step 3: Run** `cd backend && python -m pytest tests/test_trials.py tests/test_entitlements.py -v` → the new tests FAIL.
- [ ] **Step 4: Implement.** In `_record_withheld`, write `set_workspace_setting(db, workspace_id, TRIAL_WITHHELD_SETTING, "1")` before the `actor_user_id is None` early return. In `trial_state`, read the setting only when no grant exists. Update the module docstring's guard paragraph.
- [ ] **Step 5: PostgreSQL test** in `backend/tests/postgres/test_trial_rls.py`: `test_withheld_registration_writes_marker_under_rls`. Provision a first identity with `_provision_identity(..., grant_trial=True, client_ip="203.0.113.7")`, then a second with the same canonical e-mail. Under the runtime role, the second workspace has `trial_withheld = "1"` and Alice's context cannot read Bob's marker.
- [ ] **Step 6: Run** the fast suite (`python -m pytest tests/ --ignore=tests/postgres -q`) and the PostgreSQL suite against `ptf-trial-pg` (see Global Constraints). `alembic heads` still prints `0028_password_changed_seen`. All PASS.
- [ ] **Step 7: Commit** `feat(billing): tell a workspace its trial was withheld`.

**Acceptance:** the payload distinguishes "withheld" from "trials off", no new table, RLS proven.
**Risk:** low. Watch for `app_settings` importing anything that imports `trials` (circular import). If so, import inside the function.

---

### Task 2: Trial in the app (frontend)

**Files:** see table. Branch `feat/trial-ui`. Read `DESIGN.md` §2, §5, §8 first. Owns `i18n/messages` in wave 1.

**Interfaces:**
- Produces `frontend/src/lib/billingStatusQuery.js`: `export const BILLING_STATUS_KEY = ["billing-status"]` and `export const billingStatusQuery = { queryKey: BILLING_STATUS_KEY, queryFn: fetchBillingStatus, staleTime: 60_000, retry: false }`.
- Produces `frontend/src/lib/trial.js`:
  - `trialState(status, now = Date.now()) -> { phase: "none" | "active" | "ended" | "not_eligible", daysLeft: number | null, endsToday: boolean, endsAt: string | null, reason: string | null }`.
    - `active` when `source === "trial"` and `effective_until` is in the future. Then `daysLeft = Math.max(1, Math.ceil(ms / 86_400_000))` and `endsToday = ms < 86_400_000`.
    - `ended` when `source` is `"free"` or `"test_selection"` and `trial_ended_reason` is `expired`, `broker_account_reused` or `history_reused`.
    - `not_eligible` when `source === "free"` and the reason is `not_eligible`.
    - Otherwise `none`, including a `null` status, `subscription` and `local`.
  - `noticeKey(workspaceId) -> string` = `` `portfyl_trial_notice:${workspaceId}` ``.
  - `readNoticeSeen(workspaceId) -> string | null` and `markNoticeSeen(workspaceId, value: string) -> void`, both try/catch.
  - `noticeValue(state) -> string`: `"active"`, `"active-final"` (when `daysLeft <= 3`), `` `ended:${reason}` `` or `"not_eligible"`. A notice is hidden only while the stored value equals the current one, so a dismissed countdown comes back for the last 3 days and the ended notice comes back for a new reason.
  - `trialMessage(state, t) -> string | null`: the sentence for the current phase and reason, shared by the banner and Pricing.
- Produces `components/billing/useEntitlementRefresh.js`: `useEntitlementRefresh(status)`. It listens to the `portfyl:entitlement-denied` window event (any of the three codes) and invalidates `["billing-status"]` and `["plan-capabilities"]`, at most once per 30 s. While `phase === "active"` and the end is less than 24 h away, it sets one timeout to invalidate both at `effective_until`.
- Produces `components/billing/TrialBanner.jsx`: `export default function TrialBanner()`, no props. It uses `useQuery(billingStatusQuery)`, `useAuth().currentWorkspace?.id` and `useLocation()`, renders nothing on `/pricing`, and calls `useEntitlementRefresh`.
- Produces `components/billing/CloudShell.jsx`: `export default function CloudShell()`, which returns `<><TrialBanner /><UpgradePrompt /></>`.
- Modifies `editions/cloud.jsx`: `EditionShell = CloudShell`, and `fetchEditionPlanCapabilities = async () => (await fetchBillingStatus()).capabilities` (fixes existing bug 1).

**Strings** (exact English keys; add all to the 8 dictionaries):
`"Pro trial: {days} days left"`, `"Pro trial: 1 day left"`, `"Your Pro trial ends today"`, `"Your Pro trial has ended. The account is on the Free plan now: your data stays, and anything over the Free limits is read-only."`, `"Your Pro trial ended early, because this broker account already had a free trial in another Portfyl account. Your data stays; anything over the Free limits is read-only."`, `"Your Pro trial ended early, because the same transaction history already had a free trial in another Portfyl account. Your data stays; anything over the Free limits is read-only."`, `"This account starts on the Free plan, because a free trial was already used for this e-mail address or network."`, `"Dismiss trial notice"`, `"Pro trial until {date}"`, `"When the trial ends, the account moves to the Free plan unless you subscribe. Nothing is charged automatically."`, `"Trial"`. Reuse the existing `"Compare plans"` key for the link.

- [ ] **Step 1: Failing tests `frontend/src/lib/trial.test.js`**
  - 10 days left → `{phase:"active", daysLeft:10, endsToday:false}`.
  - 23 h left → `{phase:"active", daysLeft:1, endsToday:true}`.
  - 1 ms left → `daysLeft:1`, never 0.
  - `effective_until` in the past with `source:"trial"` (a stale payload) → `phase:"none"`.
  - `source:"free"` + `expired` → `ended`.
  - `test_selection` + `history_reused` → `ended` with `reason:"history_reused"`.
  - `free` + `not_eligible` → `not_eligible`.
  - `subscription`, `local`, `null` → `none`.
  - `noticeValue` at `daysLeft` 4 → `"active"`, at 3 → `"active-final"`.
  - `readNoticeSeen` returns `null` when `localStorage.getItem` throws.
- [ ] **Step 2: Failing tests `components/billing/TrialBanner.test.jsx`** (wrap in `QueryClientProvider` + `MemoryRouter`, mock `../../api` `fetchBillingStatus`, mock `useAuth`).
  - Active with 6 days → `role="status"` text "Pro trial: 6 days left" and a "Compare plans" link to `/pricing`.
  - Under 24 h → "Your Pro trial ends today".
  - Each `ended` reason → its sentence, plus the dismiss button (`aria-label` "Dismiss trial notice").
  - Dismissing writes `portfyl_trial_notice:<ws>` and hides the notice.
  - Active dismissed at 5 days → hidden; the same storage with 3 days left → shown again.
  - `not_eligible` → its sentence.
  - Renders nothing on `/pricing`, for `source:"subscription"`, and for `trial_ended_reason:null` with `source:"free"` (the `PORTFYL_TRIAL_DAYS=0` case).
  - When `fetchBillingStatus` rejects, it renders nothing and throws nothing.
- [ ] **Step 3: Failing tests `components/billing/useEntitlementRefresh.test.jsx`**
  - Dispatching `portfyl:entitlement-denied` with `{code:"plan_upgrade_required"}` twice within 30 s calls `invalidateQueries` once each for `["billing-status"]` and `["plan-capabilities"]`.
  - With fake timers and `effective_until` 2 h ahead, advancing 2 h invalidates both.
  - Unmount removes the listener and the timer.
- [ ] **Step 4: Failing edition test** in `editions/edition.test.jsx`.
  - The cloud manifest's `EditionShell` renders `TrialBanner`.
  - The source of `editions/local.jsx` (`?raw`) does not match `/TrialBanner|CloudShell|billingStatusQuery/`.
  - `fetchEditionPlanCapabilities` (cloud) calls `fetchBillingStatus`, not `fetchTestPlan`.
- [ ] **Step 5: Failing tests in `pages/Pricing.test.jsx`** (use the existing `billingStatus(overrides)` fixture).
  - `{plan:"pro", source:"trial", effective_until:"2026-11-28T12:00:00+00:00"}` → a notice "Pro trial until November 28, 2026". The Pro card has the badge "Trial", not "Current plan", and an **enabled** button that calls `startCheckout` for `pro`. The Free card is not marked current.
  - `{source:"free", trial_ended_reason:"broker_account_reused"}` → the broker sentence is shown above the plans.
  - After a plan change, both `["plan-capabilities"]` and `["billing-status"]` are invalidated.
- [ ] **Step 6: Run** `cd frontend && npm test -- trial TrialBanner useEntitlementRefresh Pricing edition` → FAIL.
- [ ] **Step 7: Implement** `billingStatusQuery.js`, `trial.js`, `useEntitlementRefresh.js`, `TrialBanner.jsx` and `CloudShell.jsx`, then `cloud.jsx`.
  - Banner markup follows `DemoDataBanner`: `.card` with `flex flex-wrap items-center justify-between gap-x-4 gap-y-3`, an `Info`/`Clock` icon in `text-brand`, the message in `text-sm font-semibold text-ink`, a `btn-primary inline-flex min-h-11 items-center text-sm` link and a `btn-ghost` circular dismiss with a 44px target.
  - Active uses `<Badge tone="brand">`, ended uses `<Badge tone="neutral">`, not_eligible uses `<Badge tone="info">`.
  - It sits in-flow at the top of `<main>`, with `mb-4 sm:mb-6`. No motion other than the existing `animate-fade-up`, which is off under reduced motion.
- [ ] **Step 8: Implement Pricing.**
  - In `PaidPlans`: `isCurrent = status.plan === plan.id && status.source !== "trial"`. When the source is `trial`, the Pro card gets `<Badge tone="brand">{t("Trial")}</Badge>` and takes the normal upgrade path.
  - Above the grid, reuse the private `Notice` for `phase` `active` (title `"Pro trial until {date}"` with `longDate(status.effective_until, language)`, body: the "When the trial ends…" string) and for `ended`/`not_eligible` (body from `trialMessage`).
  - In `TestPlans` mode, show the same notice from the `fetchBillingStatus` result.
  - Invalidate `BILLING_STATUS_KEY` next to each existing `["plan-capabilities"]` invalidation.
- [ ] **Step 9: Strings.** Add every key above to `cs, de, es, fr, it, nl, pl, pt`. Run `npm test -- messages` → PASS.
- [ ] **Step 10: Run** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud` → all PASS. Run `grep -rE "#[0-9a-fA-F]{3,8}\b" src/components/billing src/lib/trial.js` → no match.
- [ ] **Step 11: Commit** `feat(billing): trial banner, ended notice and trial pricing`.

**Acceptance:**
- Cloud shows the countdown, the ended notice for each reason, and the withheld notice.
- Pro can be bought during a trial.
- The Dashboard shows Pro widgets during a trial with billing on.
- Local is unchanged.
- All 4 frontend commands pass.

**Risks:**
- Medium. `Dashboard.async.test.jsx` and `Onboarding.test.jsx` mock `@edition-manifest` and may need `fetchEditionPlanCapabilities` adjusted.
- `App.routing.test.jsx` spreads the real `api`, so it must mock `fetchBillingStatus` once `CloudShell` calls it, or it hits axios. Fix the mocks; do not weaken assertions.

---

### Task 3: Turnstile check on new identities (backend)

**Files:** see table. Branch `feat/turnstile-backend`. Load the `cloudflare:turnstile-spin` skill first and confirm against Cloudflare's docs: the siteverify URL and response fields (`success`, `action`, `hostname`, `error-codes`), the CSP sources, and the dummy keys listed below.

**Interfaces:**
- Produces `backend/turnstile.py`:
  - Env names: `SECRET_ENV = "PORTFYL_TURNSTILE_SECRET"`, `DISABLED_ENV = "PORTFYL_TURNSTILE_DISABLED"`, `TEST_KEYS_ENV = "PORTFYL_TURNSTILE_TEST_KEYS"`. Constants: `SIGNUP_ACTION = "signup"`, `SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"`, `TIMEOUT = httpx.Timeout(5.0, connect=3.0)`, `CSP_SOURCE = "https://challenges.cloudflare.com"`.
  - `@dataclass(frozen=True) class TurnstileConfig: mode: Literal["on", "off", "test"]; secret: str | None; hostname: str | None`.
  - `TurnstileConfig.from_env(env: Mapping[str, str], edition: Edition) -> TurnstileConfig`:
    - local → `off`.
    - cloud with a real secret → `on`. The hostname comes from `PORTFYL_APP_URL`, and a missing URL raises `RuntimeError`.
    - cloud with a Cloudflare dummy secret (prefix `1x0000`, `2x0000` or `3x0000`) → `test`, but only when `PORTFYL_TURNSTILE_TEST_KEYS == "1"`. Otherwise `RuntimeError`.
    - cloud with `PORTFYL_TURNSTILE_DISABLED == "1"` and no secret → `off`, with one WARNING log line.
    - cloud with no secret and no disable flag, or with both → `RuntimeError`. **Fail closed at startup**, like `BillingConfig.from_env`.
  - `verify_signup_token(config: TurnstileConfig, token: str | None, *, remote_ip: str | None, client: httpx.Client | None = None) -> str | None`. It returns `None` on success, or a reason code: `"missing_token"`, `"rejected"`, `"wrong_action"`, `"wrong_hostname"` or `"unavailable"` (timeout or network error). In `test` mode the action and hostname checks are skipped. It never logs the token or the secret.
  - `csp_enabled(env: Mapping[str, str]) -> bool`: true when the edition is cloud and the secret is set.
  - `health_check(config) -> dict`: `{"status": "ok" | "test" | "disabled"}`.
- Produces in `routers/auth.py`:
  - `SessionExchange.turnstile_token: Any = None`.
  - `_needs_bot_check(db, identity) -> bool`: true when neither the `firebase_uid` nor the `email` lookup that `_provision_identity` performs finds a user. The `_provision_identity` signature is unchanged.
  - Errors: `AuthAPIError(403, "bot_check_required")` when no token is given, and `AuthAPIError(403, "bot_check_failed")` for any failure reason.
- Produces `app.state.turnstile_config`, set in `main.py` at import time next to `billing_config`, and `GET /health` → `checks.turnstile`.

**Dummy keys** (confirm in Step 0):
- Secrets: `1x0000000000000000000000000000000AA` always passes, `2x0000000000000000000000000000000AA` always fails, `3x0000000000000000000000000000000AA` gives "token already spent".
- Site keys: `1x00000000000000000000AA` passes, `2x00000000000000000000AB` blocks, `3x00000000000000000000FF` forces an interactive challenge.

- [ ] **Step 0:** Confirm the facts above in the skill or docs and fix any differing value in this plan before coding.
- [ ] **Step 1: Failing tests `backend/tests/test_turnstile.py`** (stub siteverify with `httpx.Client(transport=httpx.MockTransport(handler))`; never call the network).
  - `from_env`, one test per row of the config rules above, including that `local` with a secret is still `off`.
  - Verify: a success response with the right action and hostname → `None`. Action `"login"` → `"wrong_action"`. Hostname `"evil.example"` → `"wrong_hostname"`. `success:false` → `"rejected"`. `httpx.TimeoutException` → `"unavailable"`. In `test` mode the wrong action passes.
  - The request posts `secret`, `response` and `remoteip` as form fields, with `request.extensions["timeout"] == {"connect": 3.0, "read": 5.0, "write": 5.0, "pool": 5.0}`.
  - `caplog` never contains the token or the secret.
- [ ] **Step 2: Failing tests `backend/tests/test_auth_session_turnstile.py`** (harness from `tests/test_password_change_detection.py`: own `FastAPI()`, `Edition.CLOUD`, an active beta invite, a `CF-Connecting-IP` header, and `turnstile.verify_signup_token` monkeypatched).
  - New identity without a token → `403 {"code":"bot_check_required"}`, and no `User`, `Workspace`, `TrialGrant` or `TrialIdentity` rows.
  - New identity, verify returns `"rejected"` → `403 bot_check_failed`, nothing created.
  - New identity, verify returns `None` → 201, `account_created: true`, trial granted.
  - Existing user (by uid, and separately by e-mail) without a token → 201, and verify is never called.
  - `mode=off` → a new identity without a token gets 201.
  - Local edition → never checked.
  - Verify runs after `release_connection`: monkeypatch `auth_router.release_connection` to record call order.
  - `turnstile_token` given as a number or a dict → treated as missing (`bot_check_required`), never a 422.
- [ ] **Step 3: Failing tests in `backend/tests/test_security_headers.py`**
  - With `{"PORTFYL_EDITION":"cloud","PORTFYL_TURNSTILE_SECRET":"x"*40}`, script-src ends with `https://challenges.cloudflare.com` and frame-src is `frame-src https://challenges.cloudflare.com`.
  - With Google on as well, frame-src is `frame-src https://accounts.google.com/gsi/ https://challenges.cloudflare.com`.
  - The existing no-env assertions stay unchanged.
- [ ] **Step 4: Failing test in `backend/tests/test_health.py`:** `checks.turnstile.status == "disabled"` for an off config. Update the exact-equality degraded test to include the key.
- [ ] **Step 5: Run** `python -m pytest tests/test_turnstile.py tests/test_auth_session_turnstile.py tests/test_security_headers.py tests/test_health.py -v` → FAIL.
- [ ] **Step 6: Implement.**
  - Write `turnstile.py`.
  - In `exchange_session`: after `require_active_invite`, compute `needs_check = is_cloud and config.mode != "off" and _needs_bot_check(db, identity)`. Then the existing `release_connection(db)`, then the Firebase password lookup. Then, if `needs_check`: no string token → `bot_check_required`; otherwise call `verify_signup_token(config, token, remote_ip=_client_ip(request))` and raise `bot_check_failed` on a reason, logging `turnstile_check outcome=<reason>` only. Then `_provision_identity`.
  - Add the CSP via `turnstile.csp_enabled(env)` in `build_content_security_policy`, merging `frame-src` with Google's.
  - Add the health entry.
- [ ] **Step 7: Run** the fast suite and the PostgreSQL suite (on `ptf-trial-pg`). `tests/test_event_loop_not_blocked.py` must pass, so no `async def` sneaks in. All PASS.
- [ ] **Step 8: Commit** `feat(auth): Cloudflare Turnstile on new identities, fail closed`.

**Acceptance:**
- No new identity is created in cloud without a valid token unless the operator explicitly set `PORTFYL_TURNSTILE_DISABLED=1`.
- Existing users are never challenged.
- A misconfiguration stops startup instead of opening a hole.

**Risks:**
- **Medium-high for deploys:** the next image will not start in prod until the owner sets either the secret or `PORTFYL_TURNSTILE_DISABLED=1`. Cloud Run then keeps the old revision serving, so nothing goes down, but the deploy fails. Task 4 writes that step into `deploy/cloudrun.md`.
- The Firebase account itself and `/api/auth/email/verification` (Brevo sends) are not covered by Turnstile. See "Open risks".

---

### Task 4: Turnstile challenge in the SPA + ops docs

**Files:** see table. Branch `feat/turnstile-frontend`. Depends on Tasks 2 and 3 being merged into it. Owns `i18n/messages`, `deploy/cloudrun.md`, `Dockerfile` and `CLAUDE.md`.

**Interfaces:**
- Consumes the codes `bot_check_required` and `bot_check_failed` (Task 3), and the body field `turnstile_token`.
- Produces `auth/turnstileConfig.js`: `turnstileSiteKey() -> string`, from `(import.meta.env.VITE_TURNSTILE_SITE_KEY || "").trim()`.
- Produces `auth/TurnstileWidget.jsx`: `export default function TurnstileWidget({ siteKey, action = "signup", language, onToken, onError })`. It loads `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit` once through a module-level promise and calls `window.turnstile.render(el, { sitekey, action, language, callback, "error-callback", "expired-callback", theme: "light" })`. It removes the widget on unmount.
- Produces `auth/BotCheckDialog.jsx`: `export default function BotCheckDialog({ open, onToken, onCancel })`, built on `components/ui/Modal.jsx` (`.dialog-panel`, focus trap). With an empty site key it shows the "unavailable" text instead of the widget.
- Modifies `api.js`: `exchangeSession(idToken, { turnstileToken } = {})` sends `turnstile_token` only when it is given, so `exchangeSession("id-token-123")` posts exactly `{ id_token }` as today.
- Modifies `AuthProvider.jsx`: `loginWithIdToken(idToken)` (signature unchanged).
  - On `bot_check_required` it opens `BotCheckDialog` through provider state and awaits a token. Cancel rethrows the original error.
  - It retries once with `exchangeSession(idToken, { turnstileToken })`.
  - A `bot_check_failed` on the retry is thrown to the caller, which maps it through `mapFirebaseAuthError`.
- Modifies `firebase.js` `BACKEND_ERROR_MESSAGES`, adding `bot_check_failed` and `bot_check_required`.

**Strings:** `"One quick check"`, `"Confirm you are a person to finish creating your Portfyl account."`, `"The sign-up check did not pass. Please try again."`, `"The sign-up check is not available right now. Please try again later or write to support@portfyl.com."`, `"Cancel"` (reuse if it exists).

- [ ] **Step 1: Failing tests**
  - `auth/TurnstileWidget.test.jsx`: with a stubbed `window.turnstile`, it renders with `sitekey`, `action:"signup"` and the language, `callback("tok")` calls `onToken("tok")`, unmount calls `turnstile.remove`, and the script tag is injected once for two widgets.
  - `auth/AuthProvider.test.jsx`:
    - The first `exchangeSession` rejects with `{response:{status:403,data:{code:"bot_check_required"}}}`. The dialog appears, the widget token is `"tok"`, and the second call is `exchangeSession("id-token-123", { turnstileToken: "tok" })`.
    - Cancel → `loginWithIdToken` rejects with the original error.
    - An existing first-call success never opens the dialog, and the existing `toHaveBeenCalledWith("id-token-123")` assertion stays as it is.
  - `api.auth.test.js`: the body has `turnstile_token` only when it is given.
  - `pages/AuthPages.test.jsx`: `mapFirebaseAuthError` maps `bot_check_failed` to its sentence.
  - With `VITE_TURNSTILE_SITE_KEY` empty (`vi.stubEnv`), the dialog shows the "not available" text and no script tag.
- [ ] **Step 2: Run** `npm test -- Turnstile AuthProvider api.auth AuthPages` → FAIL.
- [ ] **Step 3: Implement** the files above. Use no hex; the widget frame is Cloudflare's own, and the dialog uses `Modal`.
- [ ] **Step 4: Strings** in all 8 dictionaries. Then `npm test -- messages` → PASS.
- [ ] **Step 5: Build wiring.**
  - `Dockerfile`: add `ARG VITE_TURNSTILE_SITE_KEY=` and `ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY` next to the Firebase vars.
  - `deploy/cloudrun.md` "Routine redeploy": widen the regex to `'^(VITE_(?:FIREBASE|POSTHOG|GOOGLE|TURNSTILE)_\w+)=(.*)$'`, add the `--build-arg` line, and check `deploy/cloudbuild-frontend-overlay.yaml` / `Dockerfile.frontend-overlay` for the same build-arg list.
- [ ] **Step 6: Docs in `deploy/cloudrun.md`.**
  - New section `## Sign-up bot check (Cloudflare Turnstile)` after "Free trial". It covers:
    - The three env vars and the startup rule ("the cloud image refuses to start without `PORTFYL_TURNSTILE_SECRET` or an explicit `PORTFYL_TURNSTILE_DISABLED=1`").
    - Creating the widget in the Cloudflare dashboard (managed mode, hostname `app.portfyl.com`, owner action).
    - The `portfyl-turnstile-secret` Secret Manager recipe, mirroring the trial one.
    - `--update-secrets="PORTFYL_TURNSTILE_SECRET=portfyl-turnstile-secret:latest"` and the build arg for the site key.
    - The dev setup with dummy keys and `PORTFYL_TURNSTILE_TEST_KEYS=1`.
    - The CSP, and the fact that Cloudflare Access is unaffected but must not be opened before Turnstile is `on`.
  - In "Free trial":
    - Add `not_eligible` to the `trial_ended_reason` list and fix the "(`null` or `"expired"` today)" sentence.
    - Add a box: "Production on 2026-11-19: `PORTFYL_TRIAL_DAYS=0`, no `PORTFYL_TRIAL_FINGERPRINT_KEY`. Create the secret before raising the value."
    - Add the go-live order: fingerprint key → Turnstile secret + site key → `PORTFYL_TRIAL_DAYS` unset or 10 → `VITE_PUBLIC_SIGNUP=true` → open Access.
- [ ] **Step 7: `CLAUDE.md`:** in "Login", one sentence: new identities pass Cloudflare Turnstile on demand (`backend/turnstile.py`, `auth/BotCheckDialog.jsx`), with the config rule and a pointer to the cloudrun section.
- [ ] **Step 8: Run** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud` (once with `VITE_TURNSTILE_SITE_KEY=1x00000000000000000000AA`, once without) → PASS. Commit `feat(auth): Turnstile challenge when a new account is created`.

**Acceptance:**
- A brand-new account (e-mail or Google) sees one challenge.
- A returning user sees none.
- With no site key the user gets a clear message.
- Ops docs let the owner switch it on without reading code.

**Risks:**
- Medium. A Google first sign-in now has a dialog between the popup and the app. Check that `GoogleSignInButton` keeps its busy state until `loginWithIdToken` resolves.
- `VerifyEmail.jsx` polls. Make sure that only one dialog opens, guarded by provider state.

---

### Task 5: Legal drafts and the flat legal page

**Files:** see table. Branch `docs/trial-legal`. Owns `DESIGN.md` (§10 only). Draft text only: no legal conclusion is stated as settled.

- [ ] **Step 1: Terms §4** (`podminky-uzivani-cs.md`, `terms-of-service-en.md`). Keep the existing card `[[DECIDE]]`/`[[ROZHODNOUT]]`.
  - Rewrite 4.3: the trial is **Pro**, the length is shown at registration (now 10 days), no card, no automatic charge, and Free afterwards.
  - Add 4.5: one trial per person. The trial may be withheld at registration or ended early when the same e-mail mailbox, network address, broker account or transaction history already had one. The account itself stays on Free. Marker: `[[LAWYER: is withholding or ending a trial on these signals compatible with consumer law and with the landing claim "every new account gets 10 days"?]]`.
  - Add 4.6: after the trial, data stays and items beyond the Free limits become read-only (matching 4.4).
  - §3 Account: a sentence that creating an account may require an automated bot check (Cloudflare Turnstile), with `[[LAWYER]]`.
- [ ] **Step 2: Privacy** (`zasady-ochrany-osobnich-udaju-cs.md`, `privacy-policy-en.md`). Keep the headings and numbering unchanged.
  - §2: a new row "Trial abuse-prevention records". It holds a keyed hash (HMAC-SHA256 with a secret key) of the canonical e-mail (lower-case, without `+tag`, Gmail dots folded), of the client IP (IPv6 by /64), of broker account numbers, and of the 5 oldest imported transaction ids. No raw value is stored.
  - §3: the purpose is one free trial per person. The basis is legitimate interest, Art. 6(1)(f), `[[LAWYER: balancing test; are keyed hashes pseudonymous personal data here?]]`.
  - §4: the Cloudflare row gains "bot check when a new account is created (Turnstile)", `[[LAWYER: processor or independent controller; DPA]]`.
  - §6: new retention rows.
    - E-mail and broker hashes: 12 months, kept after account deletion, `[[LAWYER: Art. 17 erasure vs. keeping the hash after deletion]]`.
    - IP hash: 30 days.
    - Trial record of the workspace: deleted with the account.
  - §7: the right to object covers these records.
  - §8: Turnstile and storage, `[[LAWYER: does Turnstile's device check fall under the ePrivacy "strictly necessary" exemption?]]`.
- [ ] **Step 3: `poznamky-pro-pravnika.md`.**
  - Bump "Stav k" to 2026-11-19 and extend point 4.
  - Add `### 10. Ochrana zkušební doby (HMAC otisky, Turnstile)` with numbered open questions:
    1. Legitimate-interest balancing test.
    2. Whether HMACs are personal data, and their retention after deletion vs. Art. 17.
    3. Art. 22: is an automated withholding of a trial a decision with significant effect?
    4. Transparency: review the in-app wording (quote the 4 English strings from Task 2).
    5. Consumer law: the landing's "every new account" claim vs. withholding.
    6. Cloudflare's role and DPA for Turnstile, and the ePrivacy exemption.
    7. Data minimisation for transaction-history fingerprints.
  - Add matching bullets to §9.
- [ ] **Step 4: `docs/compliance/data-processing-inventory.md`:** a record for each of `trial_grants`, `trial_identities`, `trial_ip_marks`, `trial_broker_marks`, the `trial_withheld` workspace setting and the Turnstile siteverify call (fields, retention, purge job `account_deletion_cleanup`). Update "Last technical review".
- [ ] **Step 5: Legal page.**
  - `Legal.jsx` renders `LandingHeader` and `LandingFooter` with `copy = COPY[lang]` from `pages/welcomeCopy.js` (`lang` is `cs` or `en`), `signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true"`, and `anchorBase` `"/"` for cs and `"/en/"` for en. Keep the language switch, the draft banner and the contents list.
  - `Legal.css`: a flat 760px text column on `--landing-paper`, no card shadow, and tokens only.
  - Update `Legal.test.jsx`. Keep the existing title, marker and banner assertions. Add: the header nav has the four section links prefixed by `anchorBase`, and the footer comes from `LandingFooter`.
  - Rewrite the last paragraph of `DESIGN.md` §10 to describe it.
- [ ] **Step 6: Run** `npm test -- Legal legalMarkdown` and the four frontend commands → PASS. `main.textContent` must not leak `[[`, `**`, backticks or `](`, which the parser test enforces. Commit `docs(legal): trial and abuse-prevention drafts; flat legal pages`.

**Acceptance:**
- All five legal docs describe what the code does, with open questions marked rather than answered.
- The legal pages share the landing header and footer.

**Risk:** low. The markdown parser supports only a subset (headings, quote, list, table, strong, em, code, links), so add no nested lists.

---

### Task 6: Integration and verification (evidence)

**Branch** `integrate/free-trial-completion` off current `main`. Record every command and its result in `docs/superpowers/plans/2026-11-19-free-trial-verification.md` (date, branch SHA, pass/fail, numbers).

- [ ] **Step 1:** Merge `feat/trial-state`, `feat/trial-ui`, `feat/turnstile-backend`, `feat/turnstile-frontend` and `docs/trial-legal`. Fetch `main` again and rebase on it if it moved, then resolve conflicts locally.
- [ ] **Step 2: Backend matrix.**
  - Run the fast suite in the existing 3.12 `.venv` and in a 3.14 venv at `$CLAUDE_JOB_DIR/tmp/venv314` (`uv venv --python 3.14`, `uv pip install --require-hashes -r backend/requirements-dev.lock`).
  - Start the PostgreSQL suite container: `docker run -d --name ptf-trial-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=portfyl_trial_test -p 55461:5432 postgres:16`, then run with `TEST_DATABASE_URL` pointing at it.
  - `alembic heads` must equal `EXPECTED_ALEMBIC_HEAD` (`0028_password_changed_seen`).
  - All PASS. Remove the container afterwards.
- [ ] **Step 3: Frontend:** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`, and `VITE_PUBLIC_SIGNUP=true npm run build:cloud`. The bundle guard (`scripts/landing-bundle-guard.mjs`) passes. With `VITE_PUBLIC_SIGNUP` unset, `grep -c "/register" dist/prerendered/index.html` is `0`.
- [ ] **Step 4: Lighthouse** (chrome-devtools `lighthouse_audit`) on `npx vite preview --port 4180` of the cloud build. Check `/`, `/en/` and `/terms?lang=cs` on mobile and desktop. Performance and accessibility must each be at least 90. Record the scores.
- [ ] **Step 5: Live walkthrough** (cloud edition, own resources).
  - Setup:
    - Create a local PostgreSQL DB `portfyl_trial_e2e` and run `alembic upgrade head` on it with the owner credential.
    - Start the backend on :8010 with `PORTFYL_EDITION=cloud`, `PORTFYL_TRIAL_FINGERPRINT_KEY=<random 40 chars>`, `PORTFYL_TURNSTILE_SECRET=1x0000000000000000000000000000000AA`, `PORTFYL_TURNSTILE_TEST_KEYS=1`, `PORTFYL_APP_URL=http://localhost:5180` and billing off.
    - Start Vite with `--mode edition-cloud --port 5180`, `VITE_API_PROXY_TARGET=http://localhost:8010` and `VITE_TURNSTILE_SITE_KEY=1x00000000000000000000AA`.
    - Insert a `beta_invites` row for each test e-mail with SQL against `portfyl_trial_e2e`.
  - Using Playwright, take a screenshot of each step:
    - (a) Register a new Firebase test account. The challenge appears once, then the banner shows "10 days left".
    - (b) Log out and in. No challenge.
    - (c) Set that workspace's `trial_grants.ends_at` to the past. Within 60 s, or after a Pro action, the ended notice appears, the Dashboard shows Free widgets, and rows over the limits are read-only.
    - (d) Delete the account in Settings, then register the same e-mail. The `not_eligible` notice appears.
    - (e) A second account imports the first account's IBKR Flex XML (synthetic fixture). The broker-reused notice appears.
    - (f) Restart with secret `2x0000000000000000000000000000000AA`. A new sign-up shows "The sign-up check did not pass", and no `users` row is created.
    - (g) Restart with `PORTFYL_TRIAL_DAYS=0`. A new sign-up shows no trial element anywhere.
    - (h) Start without the secret and without `PORTFYL_TURNSTILE_DISABLED`. The backend refuses to start.
    - (i) `npm run dev` (local edition). No banner, `/pricing` unchanged.
- [ ] **Step 6: Wrap up.**
  - Mark Tasks 1c, 3, 4 and 6 of the 2026-11-15 plan done (Task 5 stays deferred) and move both plans per the `docs/finished.md` convention.
  - Report to the owner with the evidence file. Do **not** merge into `main` without the owner's OK, and do not deploy.

**Acceptance:** every box in Steps 2–5 has recorded evidence. Any failure is fixed on the owning branch and re-verified here.

---

## Mimo rozsah / čeká na vlastníka (out of scope, waiting for the owner)

- **Turnstile keys.** Create the widget in the Cloudflare dashboard (managed mode, hostname `app.portfyl.com`), store the secret as `portfyl-turnstile-secret` in Secret Manager, and pass the site key as the build arg `VITE_TURNSTILE_SITE_KEY`. Until then, every deploy of the new image needs `PORTFYL_TURNSTILE_DISABLED=1` on the service, or the image will not start.
- **`PORTFYL_TRIAL_FINGERPRINT_KEY`.** Create the secret before setting `PORTFYL_TRIAL_DAYS` above 0 in production (recipe in `deploy/cloudrun.md` "Free trial").
- **Lawyer.** Review the drafts and answer the questions in `poznamky-pro-pravnika.md` point 10 before public sign-up opens.
- **Screenshots (original Task 5).** Still deferred by the owner, not planned here.
- **Deploy and payments go-live.** That covers the migration Job, the service deploy, live Stripe keys instead of sandbox ones, `VITE_PUBLIC_SIGNUP=true` and opening Cloudflare Access. All are the owner's decision.

## Open risks

- **Bots before Portfyl.** Turnstile protects Portfyl identities, workspaces and trials, but not the Firebase account itself or `/api/auth/email/verification` (a Brevo send, rate-limited per IP and per address). A bot can still create Firebase users and trigger verification e-mails. Consider Firebase App Check or Identity Platform reCAPTCHA later. This is not in scope.
- **Landing promise vs. withheld trials.** The landing copy says every new account gets 10 days. That copy is open lawyer question 5. It is not changed here.
- **Test selection hides a trial.** While billing is off, a stored private test plan wins over the trial (by design, `resolve_entitlements`), so no banner shows. Production has billing on, so this matters only for local or cloud test setups.
