# Portfyl Onboarding Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorder and shorten first-run onboarding so a new user learns whether their broker is supported *before* signing up, never has to pick a language as a separate step, gets one recommended route (with the export guide right there) to their first real portfolio, and lands on a dashboard that shows value and the next steps.

**Architecture:** Frontend-led. A small "signup intent" module carries the broker and language from the public landing page (portfyl.com) to registration on the app host (app.portfyl.com) through URL parameters, then keeps the broker in app-origin `localStorage` across e-mail verification. Onboarding drops its language step (language is already auto-detected), shows language and currency as a confirmable chip, and becomes two steps: broker, then first portfolio. One backend addition stores "notify me when broker X is supported" requests per workspace (new RLS table).

**Tech Stack:** React 18 + Vite 6 + Vitest/Testing Library (frontend), FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL RLS (backend), PostHog via the existing analytics event contract.

**Spec:** this document. The product rationale was agreed with the founder on 2026-11-14 (Claude Code session, "onboarding order" discussion). It is recorded in the "Product decisions" section below, and the executor treats that section as the spec.

---

## Product decisions (the spec)

Target order of the whole first-run journey:

| # | Where | What |
|---|-------|------|
| 0 | Landing (portfyl.com, no account) | Language from URL/browser (already exists). **New:** "Is your broker supported?" check. Public demo (already exists at `/demo`). |
| 1 | Registration (app.portfyl.com) | Google or e-mail (Google is already on). **New:** arrives in the landing's language with the broker the visitor checked. |
| 1b | E-mail verification | Still required (backend `email_verification_required`, multi-user foundation spec). **New:** the open tab continues by itself once the link is clicked: no "come back and log in". |
| 2 | Onboarding step 1 of 2 | Broker. **Skipped** when the broker came from the landing page. **New:** brokers ordered for the user's language. **New:** unsupported broker offers "Notify me". |
| 3 | Onboarding step 2 of 2 | First portfolio. One recommended route (API connect when the broker has one, otherwise file import). **New:** that broker's export guide is shown inline. **New:** demo is a secondary text link, not an equal card. |
| — | Throughout onboarding and the onboarding import | **New:** language + currency shown as a chip ("Čeština · CZK"), confirm or change. **Removed:** the separate "Choose your language" step. |
| 4 | Dashboard | **New:** welcome panel with one insight and a "Getting started" checklist (add another broker, check language/currency, see dividends). **New:** a sample-data banner that leads to a real import. |
| — | Funnel | **New:** onboarding step/broker events and a documented PostHog funnel, plus the SQL for broker demand. |

Rationale (why these, kept so later changes don't undo them):
- Every extra screen loses users. Language and currency are low-stakes and changeable later, and they are guessable (browser language → local currency), so they get confirmed, not asked.
- The broker check is worth most *before* the account exists. Today a user with an unsupported broker learns it only after registering.
- The broker list is a good qualifier: it lets step 2 offer exactly one route.
- Demo is for undecided visitors (landing). After signup it should not pull a user with a supported broker away from their own data.
- The biggest drop-off is "where do I find the export file", not the step order. So the guide belongs in onboarding, not only on the Import page.
- No pricing/paywall anywhere in onboarding. Plans appear when a Free limit is hit.
- Unsupported-broker requests are free market research. They are stored per account (no e-mail collected on the landing page: see decisions below).

Decisions made while grounding this in the code:
- **D1 E-mail verification stays mandatory.** `backend/routers/auth.py:194` refuses a session for an unverified identity, and that is a security decision of the multi-user foundation. This plan removes the friction (auto-continue) instead of the check.
- **D2 Cloud signup is private beta** (`require_active_invite`, `auth.py:200-204`). The landing check therefore shows the "Create a free account" CTA only when the build flag `VITE_PUBLIC_SIGNUP=true`. Otherwise a supported broker gets the demo CTA plus a beta note. The flag is off by default.
- **D3 No e-mail capture on the public landing page.** A public, unauthenticated write endpoint brings spam, rate limiting and GDPR consent work. That is out of scope here. Unsupported on the landing page leads to the demo, and "Notify me" exists for signed-in users only.
- **D4 Landing and app are different origins.** `localStorage` on portfyl.com is not readable on app.portfyl.com, so the hand-off is URL parameters (`?broker=&lang=`). The app then stores the broker on its own origin.
- **D5 Screenshots in export guides are optional assets.** Guides render text steps today. Screenshots are added later by the founder (manual task M1) through a registry, with no code change.

## Global Constraints

- Follow `DESIGN.md` for every UI change: tokens only, no hex colors, `card`/`btn-primary`/`btn-ghost` classes, 44px minimum touch targets, `animate-fade-up` for step changes.
- Every user-visible string goes through `t("…")`/`msg("…")` with English source text, and **every** new string gets translations in all 8 dictionaries `frontend/src/i18n/messages/{cs,de,fr,es,it,pt,pl,nl}.js`. Strings that are no longer used are deleted from all 8. `src/i18n/messages.test.js` enforces both. Brand/broker names and the glossary in `src/i18n/languages.js` stay in English.
- Landing page copy lives in `frontend/src/pages/welcomeCopy.js` (cs/en/de), **not** in the app dictionaries.
- `localStorage`/`sessionStorage` access is always wrapped in `try/catch` and has a working fallback (see `src/i18n/languages.js`).
- New `localStorage` keys use the `portfyl_` prefix (never `sb_`): `portfyl_intended_broker`, `portfyl_preferences_confirmed`, `portfyl_getting_started:<workspaceId>`.
- Analytics properties must pass `src/analytics/eventContract.js`. A user-typed broker name never goes to analytics.
- Backend endpoints touching the DB are plain `def` (never `async def`). Tenant tables get forced RLS **and** application-level workspace filtering.
- Any migration updates `backend/database.py` `EXPECTED_ALEMBIC_HEAD` in the same change. `alembic heads` must show exactly one head equal to it.
- Frontend verification for every task: `cd frontend && npm test` and `npm run build`. Tasks 1, 9 and 11 also run `npm run test:cloud` and `npm run build:cloud` (landing/demo/edition-sensitive).

## Parallel-session plan (waves and file ownership)

**Hotspots:** the 8 translation dictionaries, `frontend/src/api.js`, `backend/alembic/versions/` + `backend/database.py`, `backend/main.py`, `docs/legal/*`.
- Alembic/database.py/main.py/docs-legal: owned by **Task 3 only**.
- `api.js`: owned by **Task 3 only**.
- Dictionaries: every task adds its own keys. Each task appends its keys as one block just before the closing `};` of each dictionary, headed `// onboarding-flow Task N`. When merging a wave, the integrator resolves the inevitable end-of-file conflicts by **keeping both blocks**, then re-runs `npx vitest run src/i18n/messages.test.js`.

| Wave | Tasks (parallel unless noted) | Owns |
|------|------------------------------|------|
| 0 | M0: commit or discard the uncommitted currency-`Select` change in `OnboardingView.jsx` / `Onboarding.test.jsx` (found in the working tree on 2026-11-14) | founder |
| 1 | Task 1, Task 2, Task 3, Task 4 | disjoint files, see each task |
| 2 | Track A **sequential**: Task 5 → 6 → 7 → 8 · Track B: Task 9 · Track C: Task 10 | A: onboarding + Import page; B: landing; C: dashboard |
| 3 | Task 11 | analytics contract + call sites |
| any | M1 (screenshots) | founder |

Each session works in its own git worktree/branch (`feat/onboarding-flow-taskN`). Dev servers, if used, run on distinct ports (e.g. `--port 51xx`). Only Task 3 runs `alembic upgrade head`, and only against its own disposable database.

## Review Focus

1. **A broker picked later beats the remembered one.** A user who checked XTB on the landing page but then clicks "Change broker" and picks Degiro must import into Degiro. The remembered broker is cleared once a real (non-demo) first portfolio is created, and kept after a demo so the sample-data banner can point to the right import. Pinned in Task 5, with a test that the demo keeps it.
2. **Storage unavailable** (Safari private mode, blocked site data). Every new helper must return its "nothing stored" value instead of throwing, and onboarding must still work end to end. Pinned in Tasks 1, 4 and 10.
3. **The verification tab after a refresh.** With no in-memory Firebase user, `/verify-email` must not poll, must show the existing "log in again" text, and polling must stop on unmount. Pinned in Task 2.
4. **Hostile or messy free-text broker names** ("  trade   republic ", 300 characters, `<script>`, a different case of an existing request). Stored trimmed and collapsed, at most 60 characters, idempotent case-insensitively, rendered as text. Pinned in Tasks 3 and 7.
5. **Prerendered landing page.** `BrokerCheck` must render identical HTML on the server and the client: no `window`/storage access during render, and the initial state has no result. Pinned in Task 9.

---

### Task 1: Signup intent hand-off (landing/demo → registration)

**Files:**
- Create: `frontend/src/lib/signupIntent.js`
- Create: `frontend/src/lib/signupIntent.test.js`
- Create: `frontend/src/pages/Register.intent.test.jsx`
- Modify: `frontend/src/pages/Register.jsx` (mount effect, near the existing `SIGNUP_STARTED` effect at line 52)
- Modify: `frontend/src/i18n/languages.js` (add `hasSavedLanguage`)
- Modify: `frontend/src/demo/DemoShell.jsx:8` (`REG_TARGET` → `registerUrl`)

**Interfaces:**
- Produces (`lib/signupIntent.js`):
  - `APP_ORIGIN: string` = `import.meta.env.VITE_APP_ORIGIN || "https://app.portfyl.com"` (moved from `DemoShell.jsx`)
  - `INTENDED_BROKER_KEY = "portfyl_intended_broker"`
  - `registerUrl({ origin = APP_ORIGIN, source = null, broker = null, lang = null } = {}) -> string`: `${origin}/register` plus only the params that are set and valid (`broker` must satisfy `findSupportedBroker`, `lang` must satisfy `isAppLanguage`), in the order `source, broker, lang`.
  - `readSignupIntent(searchParams: URLSearchParams) -> { broker: string|null, lang: string|null }` (invalid values → `null`)
  - `rememberIntendedBroker(key: string) -> void` (ignores unsupported keys)
  - `intendedBroker() -> string|null` (re-validates what is stored)
  - `clearIntendedBroker() -> void`
- Produces (`i18n/languages.js`): `hasSavedLanguage() -> boolean` (true when `portfyl_language` holds a valid app language)

- [ ] **Step 1: Write the failing tests** in `signupIntent.test.js`:

```js
it("builds the register URL with only valid params", () => {
  expect(registerUrl({ origin: "https://app.test", source: "demo", broker: "xtb", lang: "cs" }))
    .toBe("https://app.test/register?source=demo&broker=xtb&lang=cs");
  expect(registerUrl({ origin: "https://app.test", broker: "robinhood", lang: "xx" }))
    .toBe("https://app.test/register");
});
it("reads only supported brokers and app languages", () => {
  expect(readSignupIntent(new URLSearchParams("broker=degiro&lang=de"))).toEqual({ broker: "degiro", lang: "de" });
  expect(readSignupIntent(new URLSearchParams("broker=<x>&lang=klingon"))).toEqual({ broker: null, lang: null });
});
it("remembers, re-validates and clears the intended broker", () => {
  rememberIntendedBroker("xtb"); expect(intendedBroker()).toBe("xtb");
  localStorage.setItem(INTENDED_BROKER_KEY, "robinhood"); expect(intendedBroker()).toBeNull();
  rememberIntendedBroker("ibkr"); clearIntendedBroker(); expect(intendedBroker()).toBeNull();
});
it("survives storage that throws", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(() => rememberIntendedBroker("xtb")).not.toThrow();
  expect(intendedBroker()).toBeNull();
});
```

`Register.intent.test.jsx` (render `Register` at `/register?broker=xtb&lang=de` inside `I18nProvider initial="en"` and a `MemoryRouter`, with the Firebase module mocked as in `AuthPages.test.jsx`):
- `test("stores the broker from the URL")`: `localStorage.getItem("portfyl_intended_broker") === "xtb"`.
- `test("switches to the URL language when none is saved")`: the heading renders the German translation of "Create your Portfyl account".
- `test("keeps a saved language over the URL")`: with `localStorage.portfyl_language = "cs"`, the heading is Czech.

- [ ] **Step 2: Run them and see them fail.** `cd frontend && npx vitest run src/lib/signupIntent.test.js src/pages/Register.intent.test.jsx` should FAIL (module not found).
- [ ] **Step 3: Implement `lib/signupIntent.js` and `hasSavedLanguage()`**, with try/catch storage access as in `languages.js`.
- [ ] **Step 4: Wire `Register.jsx`.** In a mount-only effect: `const intent = readSignupIntent(searchParams)`. If `intent.broker`, call `rememberIntendedBroker(intent.broker)`. If `intent.lang && !hasSavedLanguage()`, call `setLanguage(intent.lang)` (from `useI18n()`). Keep `sourceSurfaceFrom` unchanged (Task 11 widens it).
- [ ] **Step 5: Use it in `DemoShell.jsx`.** `REG_TARGET` becomes `registerUrl({ source: "demo", lang: <demo language> })`. The demo's language comes from whatever `DemoShell` already uses for its copy. If it has none, pass `null`.
- [ ] **Step 6: Run the tests.** `npx vitest run src/lib/signupIntent.test.js src/pages/Register.intent.test.jsx src/demo` should PASS. Then run `npm test && npm run test:cloud && npm run build && npm run build:cloud`.
- [ ] **Step 7: Commit.** `git commit -m "feat(onboarding): carry broker and language from landing/demo into registration"`

---

### Task 2: E-mail verification continues by itself

**Files:**
- Modify: `frontend/src/auth/firebase.js` (add `reloadFirebaseUser`; `sendVerificationEmail` gains a continue URL)
- Modify: `frontend/src/pages/VerifyEmail.jsx`
- Modify: `frontend/src/pages/Login.jsx` (`?verified=1` notice)
- Create: `frontend/src/pages/VerifyEmail.test.jsx`

**Interfaces:**
- Produces: `reloadFirebaseUser(user) -> Promise<boolean>`: `await user.reload()`, then returns `user.emailVerified === true`.
- Produces: `sendVerificationEmail(user)` now calls `sendEmailVerification(user, { url: \`${window.location.origin}/login?verified=1\` })`. The domain must be an authorized Firebase domain. app.portfyl.com and localhost already are (Google sign-in uses them), and the executor confirms this in the Firebase console notes in `deploy/cloudrun.md`.
- Consumes: `useAuth().loginWithIdToken`, `getIdToken`, `TRACKER_HOME`.
- Constants in `VerifyEmail.jsx`: `VERIFY_POLL_MS = 4000`, `VERIFY_POLL_LIMIT = 225` (15 minutes).

- [ ] **Step 1: Write the failing tests** (fake timers; mock `../auth/firebase` and `../auth/AuthProvider`):
  - `test("continues into the app once the address is verified")`: `getCurrentFirebaseUser` returns a user; `reloadFirebaseUser` resolves `false` then `true`. After advancing 2 × 4000 ms, `loginWithIdToken` was called once with the token from `getIdToken(user, true)` and `navigate` was called with `"/dashboard"` (cloud) / `TRACKER_HOME`.
  - `test("checks again when the tab regains focus")`: a `focus` event on `window` triggers `reloadFirebaseUser` without waiting for the interval.
  - `test("does not poll without an in-memory user")`: `getCurrentFirebaseUser` returns `null`, so `reloadFirebaseUser` is never called and the text "Sign in again to resend the verification e-mail." is shown.
  - `test("stops polling on unmount and after the limit")`: unmount, advance 10 min, and the call count stays the same. Separately, after 225 polls there are no more calls.
  - In `AuthPages.test.jsx`'s existing style, but in the new file: `test("login shows the verified notice")`: `/login?verified=1` shows "E-mail verified. Log in to continue."
- [ ] **Step 2: Run them.** `npx vitest run src/pages/VerifyEmail.test.jsx` should FAIL.
- [ ] **Step 3: Implement `reloadFirebaseUser` and the continue URL** in `firebase.js`.
- [ ] **Step 4: Implement the polling** in `VerifyEmail.jsx`. Use an interval plus a `window` focus listener, both cleared on unmount and on success. On a successful login call `navigate(TRACKER_HOME, { replace: true })`. A failed exchange shows `t(mapFirebaseAuthError(err))` and stops polling. Change the main paragraph for the in-memory-user case to `t("We sent a verification link to <b>{email}</b>. Click it and this page continues by itself.")`. Keep the existing strings for the no-user case.
- [ ] **Step 5: Add the Login notice.** When `searchParams.get("verified") === "1"`, render `<p role="status">{t("E-mail verified. Log in to continue.")}</p>` above the form.
- [ ] **Step 6: Add translations** for the 2 new strings (8 dictionaries) and remove the replaced string if it is no longer used.
- [ ] **Step 7: Run the tests.** `npx vitest run src/pages/VerifyEmail.test.jsx src/pages/AuthPages.test.jsx src/i18n/messages.test.js` should PASS. Then run `npm test && npm run build`.
- [ ] **Step 8: Commit.** `git commit -m "feat(auth): verification tab continues into the app once the link is clicked"`

---

### Task 3: Backend: "notify me when my broker is supported"

**Files:**
- Create: `backend/alembic/versions/0026_broker_requests.py` (use the next free number if `0026` is taken at execution time; copy the RLS/grant pattern from `0023_allocation_targets.py`)
- Modify: `backend/database.py` (`EXPECTED_ALEMBIC_HEAD`)
- Modify: `backend/models.py` (add `BrokerRequest`)
- Create: `backend/routers/broker_requests.py`
- Modify: `backend/main.py` (mount under `/api`)
- Create: `backend/tests/test_broker_requests.py`
- Create: `backend/tests/postgres/test_broker_requests_rls.py`
- Modify: `frontend/src/api.js` (prefix + client function)
- Modify: `docs/legal/privacy-policy-en.md`, `docs/legal/zasady-ochrany-osobnich-udaju-cs.md`

**Interfaces:**
- Table `broker_requests`: `id` integer PK; `public_id` UUID unique not null; `workspace_id` FK `workspaces.id` **ON DELETE CASCADE**; `user_id` FK `users.id` **ON DELETE CASCADE**; `broker_name` `String(60)` not null; `created_at` timestamptz default now. Unique index `uq_broker_requests_workspace_name` on `(workspace_id, lower(broker_name))`. RLS enabled and forced with the same workspace policy as `allocation_targets`.
- `POST /api/broker-requests`, body `{"broker_name": str}`. The name is normalized by `" ".join(name.split())`, then 1–60 characters are required (otherwise 422 `{"code": "invalid_broker_name"}`). Responses: 201 `{"broker_name": <normalized>, "created": true}`, or 200 `{"broker_name": <stored>, "created": false}` when the same name already exists case-insensitively. At most 20 rows per workspace; beyond that the response is 429 `{"code": "broker_request_limit"}`. Workspace comes from `get_request_context()`, and the CSRF rules are the same as for other mutating routes. Plain `def`.
- Frontend (`api.js`): `"/broker-requests"` is appended to `PORTFOLIO_AGNOSTIC_PREFIXES`. `export const requestBrokerSupport = (brokerName) => api.post("/broker-requests", { broker_name: brokerName }).then((r) => r.data)`, following the file's existing style.

- [ ] **Step 1: Write the failing unit tests** (`tests/test_broker_requests.py`, helpers from `tests/helpers.py`):

```python
def test_creates_normalized_request(ctx): assert post(ctx, "  trade   republic ") == (201, {"broker_name": "trade republic", "created": True})
def test_same_name_other_case_is_idempotent(ctx): post(ctx, "Revolut"); assert post(ctx, "REVOLUT") == (200, {"broker_name": "Revolut", "created": False})
def test_rejects_empty_and_too_long(ctx): assert post(ctx, "   ")[0] == 422 and post(ctx, "x" * 61)[0] == 422
def test_markup_is_stored_as_plain_text(ctx): assert post(ctx, "<script>")[1]["broker_name"] == "<script>"
def test_limit_per_workspace(ctx): [post(ctx, f"b{i}") for i in range(20)]; assert post(ctx, "b21")[0] == 429
```

- [ ] **Step 2: Run them.** `cd backend && python -m pytest tests/test_broker_requests.py -v` should FAIL (no route).
- [ ] **Step 3: Implement** the model, the migration (with `downgrade`), the router, the mount, and `EXPECTED_ALEMBIC_HEAD = "0026_broker_requests"`.
- [ ] **Step 4: Write the PostgreSQL tests** (`tests/postgres/test_broker_requests_rls.py`, `matrix_client` style): Alice's request is invisible to Bob through the API **and** through a raw query under Bob's RLS context, and deleting Alice's workspace removes her rows.
- [ ] **Step 5: Run everything.** Run `python -m pytest tests/test_broker_requests.py -v`, then with the disposable test DB (`docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`) run `python -m pytest tests/postgres/test_broker_requests_rls.py -v` and `alembic heads`. Expected: PASS, and exactly one head `0026_broker_requests` equal to the constant. Then run `python -m pytest tests/test_event_loop_not_blocked.py -v` (PASS).
- [ ] **Step 6: Add the frontend client.** Add the prefix and `requestBrokerSupport`. In the existing api interceptor test (if `api.test.js` exists, otherwise create `src/api.brokerRequests.test.js`): a POST to `/broker-requests` carries no `portfolio_id`.
- [ ] **Step 7: Update the privacy policies** (en + cs). In §2 (data categories), add "brokers you ask us to support (the name you typed), linked to your account". In §6 (retention), add "deleted together with your account". In §8 (browser storage), add the three new keys from Global Constraints with a one-line purpose each. Add a line to `docs/legal/poznamky-pro-pravnika.md` saying these changes need the lawyer's review.
- [ ] **Step 8: Commit.** `git commit -m "feat(api): store unsupported-broker requests per workspace"`

---

### Task 4: Broker order by language and the preference-confirmation helper

**Files:**
- Modify: `frontend/src/lib/onboardingBrokers.js`
- Create: `frontend/src/lib/onboardingBrokers.test.js`
- Create: `frontend/src/lib/preferencesConfirmation.js`
- Create: `frontend/src/lib/preferencesConfirmation.test.js`

**Interfaces:**
- Produces (`onboardingBrokers.js`):
  - `BROKER_ORDER_BY_LANGUAGE` (frozen):
    - `cs: ["trading212","xtb","degiro","ibkr","etoro","schwab","fidelity"]`
    - `pl: ["xtb","trading212","degiro","ibkr","etoro","schwab","fidelity"]`
    - `de`, `fr`, `es`, `it`, `pt`, `nl`: `["trading212","degiro","ibkr","xtb","etoro","schwab","fidelity"]`
    - `en: ["trading212","ibkr","etoro","degiro","xtb","schwab","fidelity"]`
  - `brokersForLanguage(language: string) -> SupportedBroker[]`: that order. Unknown language → the `en` order. Brokers missing from an order list go last in `SUPPORTED_BROKERS` order.
  - `filterBrokers(query: string, language = "en") -> { supported, unsupported }`: `supported` follows `brokersForLanguage(language)`.
- Produces (`preferencesConfirmation.js`): `PREFERENCES_CONFIRMED_KEY = "portfyl_preferences_confirmed"`, `preferencesConfirmed() -> boolean`, `confirmPreferences() -> void` (both storage-safe).

- [ ] **Step 1: Write the failing tests.** `brokersForLanguage("cs").map(b => b.key)` equals the `cs` list; `brokersForLanguage("xx")` equals the `en` list; `filterBrokers("", "pl").supported[0].key === "xtb"`; `filterBrokers("de", "cs").supported.map(b => b.key)` equals `["degiro"]`. Also: `confirmPreferences(); preferencesConfirmed() === true`, and with a throwing `getItem`, `preferencesConfirmed() === false`.
- [ ] **Step 2: Run them.** `npx vitest run src/lib/onboardingBrokers.test.js src/lib/preferencesConfirmation.test.js` should FAIL.
- [ ] **Step 3: Implement both modules.**
- [ ] **Step 4: Run them again.** Same command should PASS, then `npm test`.
- [ ] **Step 5: Commit.** `git commit -m "feat(onboarding): order brokers by language; preference confirmation flag"`

---

### Task 5: Two-step onboarding with a language/currency chip (Track A, first)

Prerequisite: M0 done (the uncommitted currency-`Select` change is committed or discarded).

**Files:**
- Create: `frontend/src/components/onboarding/PreferencesChip.jsx`
- Create: `frontend/src/components/onboarding/PreferencesChip.test.jsx`
- Modify: `frontend/src/components/onboarding/OnboardingView.jsx`
- Modify: `frontend/src/components/onboarding/OnboardingView.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`, `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/pages/OnboardingPreview.jsx`, `frontend/src/pages/OnboardingPreview.test.jsx`

**Interfaces:**
- Consumes: `brokersForLanguage`/`filterBrokers(query, language)` (Task 4), `preferencesConfirmed`/`confirmPreferences` (Task 4), `intendedBroker`/`clearIntendedBroker` (Task 1).
- Produces: `PreferencesChip({ currency: string, onCurrencyChange: (code) => void })`, the default export of `components/onboarding/PreferencesChip.jsx`. Collapsed, it is a button labelled `"{languageName} · {currency}"` (e.g. `Čeština · CZK`). Expanded, it shows a language `Select` (`APP_LANGUAGES`, native names) and a currency `Select` (`DISPLAY_CURRENCIES`, `"{symbol} · {code}"`), the note `t("You can change both later in Settings → Preferences.")` and a button `t("Looks good")` that calls `confirmPreferences()` and collapses. Picking a language calls `setLanguage(code)` **and** `onCurrencyChange(localCurrencyForLanguage(code))` (today's behaviour). Picking a currency only changes the currency.
- `OnboardingView` props: **remove** `languageChosen` and `onLanguageChosen`. Keep `currency`/`onCurrencyChange`; when `onCurrencyChange` is passed, the chip renders top-right inside `<main>`. Steps:
  - broker pick: eyebrow `t("Step 1 of 2")`
  - choices: eyebrow `t("Step 2 of 2 · {broker}", { broker })`
- `onboardingChoices(broker, t)` **no longer returns the demo card**. It returns `[connect (primary), fileImport]` for API brokers and `[fileImport (primary)]` otherwise. `ONBOARDING_CHOICE_KEYS` stays `["broker","demo","import"]` (demo is still a handler, reached through the link below).
- `Choices` renders under the cards a text button `t("Just look around with sample data first")` that calls `onChoose("demo")`, with a spinner while `busy === "demo"`, followed by the existing sample-data note.
- `Onboarding.jsx`: on mount, if the URL has no `broker` and `intendedBroker()` returns a key, call `setSearchParams` with that broker (`replace: true`). Call `clearIntendedBroker()` after a successful **real** portfolio creation (`beginImport`, `startBlank`, and `activate` with kind `"broker"`). Do **not** clear it for the demo: Task 10's sample-data banner uses it to offer "Import your own portfolio" for the right broker.

- [ ] **Step 1: Write the failing tests.**
  - `PreferencesChip.test.jsx`: it shows `English · GBP` for `en`/`GBP`; picking `Čeština` calls `onCurrencyChange("CZK")` and switches the language; picking `EUR` in the currency select calls `onCurrencyChange("EUR")` only; "Looks good" sets `portfyl_preferences_confirmed`.
  - `OnboardingView.test.jsx`: with defaults, the first screen is "Which broker do you use?" with "Step 1 of 2"; there is no "Choose your language" heading; with `onCurrencyChange` the chip button is present; for `xtb`, exactly one card plus the "Just look around with sample data first" button; for `trading212`, two cards with the connect card first; `onboardingChoices(findSupportedBroker("ibkr")).map(c => c.key)` equals `["broker","import"]`; the broker list for `language="cs"` starts with Trading 212, XTB.
  - `test("onboarding never links to pricing")`: `container.querySelector('a[href*="pricing"]')` is null on every step.
  - `Onboarding.test.jsx`: `test("starts at step 2 with the broker from the landing page")` (localStorage `portfyl_intended_broker=xtb` → "Step 2 of 2 · XTB"); `test("a broker picked later wins and the remembered one is cleared")` (intended `xtb`, click "Change broker", pick Degiro, choose import → navigate to `/import?broker=degiro` and `intendedBroker()` is `null`); `test("choosing the demo keeps the remembered broker")` (intended `xtb`, click "Just look around with sample data first" → `intendedBroker() === "xtb"`).
  - `OnboardingPreview.test.jsx`: update to the new props; it still never calls the API.
- [ ] **Step 2: Run them.** `npx vitest run src/components/onboarding src/pages/Onboarding.test.jsx src/pages/OnboardingPreview.test.jsx` should FAIL.
- [ ] **Step 3: Implement.** Write `PreferencesChip.jsx` with the `Select` from `../ui/Select`, `card`, `animate-fade-up`. Delete `LanguagePick` and `CurrencyPick` from `OnboardingView.jsx`. Update `Choices`, `BrokerPick` (pass `language` from `useI18n()` to `filterBrokers`), `Onboarding.jsx` and `OnboardingPreview.jsx`.
- [ ] **Step 4: Update the dictionaries.** Add: "Step 1 of 2", "Step 2 of 2 · {broker}", "Just look around with sample data first", "You can change both later in Settings → Preferences.", "Looks good", "Language", "Display currency". Delete every string that is no longer in the code (e.g. "Step 1 of 3", "Choose your language", "Portfyl will use it everywhere in the app…", "Show my portfolio in", "Display only in USD (you can change this later)", "Languages"). `messages.test.js` lists them.
- [ ] **Step 5: Run the tests.** Same command plus `src/i18n/messages.test.js` should PASS, then `npm test && npm run build`.
- [ ] **Step 6: Check it in the browser.** Run `start.bat` with this session's own ports and the `run` skill / Playwright. Register a test account and check: two steps, the chip changes language and currency live, and the demo is a link. Take screenshots at desktop and 390px width.
- [ ] **Step 7: Commit.** `git commit -m "feat(onboarding): two steps, language/currency chip, demo as secondary link"`

---

### Task 6: The broker's export guide inside step 2 (Track A, after Task 5)

**Files:**
- Modify: `frontend/src/components/import/BrokerGuides.jsx`, `frontend/src/components/import/BrokerGuides.test.jsx`
- Create: `frontend/src/lib/brokerGuideImages.js`
- Modify: `frontend/src/components/onboarding/OnboardingView.jsx` (`Choices` only), `OnboardingView.test.jsx`

**Interfaces:**
- `BrokerGuides({ initialOpen = null, only = null })`. With `only` set to a guide id, it renders just that guide, expanded, without the accordion button, under the heading `t("How to get the file from {broker}", { broker: guide.name })`. An unknown `only` renders nothing.
- A new guide `id: "trading212"`, `name: "Trading 212"`, `file: "CSV"`, steps:
  - `ink(t("In Trading 212 open <b>History</b> and choose <b>Export history</b>."))`
  - `t("Choose the whole period and every data type, then download the CSV and upload it here.")`
  
  `GUIDE_IDS` gains `"trading212"` (first).
- `lib/brokerGuideImages.js`: `export const BROKER_GUIDE_IMAGES = Object.freeze({})`, shaped `{ [guideId]: [{ src, alt }] }` (`alt` is a `msg("…")` string). `BrokerGuides` renders `<img loading="lazy" className="rounded-xl" alt={t(alt)}>` after the steps when the guide has images.
- `Choices`: when `!broker.api`, render `<BrokerGuides only={broker.key} />` directly under the cards, replacing the `broker.hint` sentence in the card description. API brokers keep `T212ApiGuide` for Trading 212 and no file guide.

- [ ] **Step 1: Write the failing tests.**
  - `BrokerGuides.test.jsx`: `only="xtb"` renders the XTB steps with no accordion `button[aria-expanded]`; `only="nope"` renders nothing; the default list includes "Trading 212"; with `vi.mock("../../lib/brokerGuideImages", () => ({ BROKER_GUIDE_IMAGES: { xtb: [{ src: "/x.png", alt: "XTB export menu" }] } }))`, an `img` with that alt renders.
  - `OnboardingView.test.jsx`: the `xtb` step shows "How to get the file from XTB"; the `trading212` step does not show it.
- [ ] **Step 2: Run them.** `npx vitest run src/components/import/BrokerGuides.test.jsx src/components/onboarding` should FAIL.
- [ ] **Step 3: Implement.** Make the changes above. The Import page keeps calling `<BrokerGuides initialOpen=… />`, unchanged.
- [ ] **Step 4: Add the new strings to the dictionaries**, then run the same tests plus `messages.test.js` (PASS), then `npm test && npm run build`.
- [ ] **Step 5: Commit.** `git commit -m "feat(onboarding): show the picked broker's export guide inline"`

---

### Task 7: "Notify me" for unsupported brokers (Track A, after Task 6; needs Task 3 merged)

**Files:**
- Modify: `frontend/src/components/onboarding/OnboardingView.jsx` (`Unsupported` only), `OnboardingView.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`, `Onboarding.test.jsx`
- Modify: `frontend/src/pages/OnboardingPreview.jsx`

**Interfaces:**
- Consumes: `requestBrokerSupport(name)` (Task 3).
- `OnboardingView` gains the props `onNotify: () => void` and `notifyState: "idle"|"sending"|"sent"|"error"` (default `"idle"`). `Unsupported` shows, as the first and primary button, `t("Notify me when {name} is supported", { name })`. While sending it is disabled with a spinner. Once sent, the button is replaced by `<p role="status">{t("Thanks, we'll e-mail you when {name} is supported.", { name })}</p>`. On error it shows `<p role="alert">{t("We couldn't save that. Please try again.")}</p>` and the button stays.
- `Onboarding.jsx`: `notifyState` is held in state and reset to `"idle"` whenever `unsupportedName` changes. `onNotify` calls `requestBrokerSupport(unsupportedName)`.
- `OnboardingPreview.jsx`: `onNotify` sets `"sent"` locally (no API).

- [ ] **Step 1: Write the failing tests.** Clicking "Notify me when Revolut is supported" calls `requestBrokerSupport("Revolut")` once and then shows the thanks status. A rejected promise shows the alert and the button stays. A name with markup (`"<b>x</b>"`) renders literally (`getByText("Notify me when <b>x</b> is supported")`). Switching to another unsupported name resets to idle.
- [ ] **Step 2: Run them.** `npx vitest run src/components/onboarding src/pages/Onboarding.test.jsx` should FAIL.
- [ ] **Step 3: Implement**, then add the 3 strings to the dictionaries.
- [ ] **Step 4: Run them again** plus `messages.test.js` (PASS), then `npm test && npm run build`.
- [ ] **Step 5: Commit.** `git commit -m "feat(onboarding): notify-me request for unsupported brokers"`

---

### Task 8: Language/currency chip on the onboarding import page (Track A, last)

**Files:**
- Modify: `frontend/src/pages/Import.jsx` (header, around line 292–297), `frontend/src/pages/Import.test.jsx`

**Interfaces:**
- Consumes: `PreferencesChip` (Task 5), `preferencesConfirmed` (Task 4), `useCurrency()` from `../App`.
- When `focused` (the onboarding import, `App.jsx:431`) **and** `!preferencesConfirmed()`, render `<PreferencesChip currency={currency} onCurrencyChange={setCurrency} />` at the right of the header row. The normal in-app Import page never shows it.

- [ ] **Step 1: Write the failing tests.** `<Import focused />` shows the chip; `<Import />` does not; with `portfyl_preferences_confirmed=1`, `<Import focused />` does not either.
- [ ] **Step 2: Run them.** `npx vitest run src/pages/Import.test.jsx` should FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them again** (PASS), then `npm test && npm run build`.
- [ ] **Step 5: Commit.** `git commit -m "feat(import): confirm language and currency while the first import runs"`

---

### Task 9: "Is your broker supported?" on the landing page (Track B)

**Files:**
- Create: `frontend/src/components/landing/BrokerCheck.jsx`
- Create: `frontend/src/components/landing/BrokerCheck.test.jsx`
- Modify: `frontend/src/pages/Welcome.jsx` (new section between the ribbon and `#funkce`), `frontend/src/pages/Welcome.css`, `frontend/src/pages/welcomeCopy.js`, `frontend/src/pages/Welcome.test.jsx`

**Interfaces:**
- Consumes: `filterBrokers(query, language)` (Task 4), `registerUrl` (Task 1).
- `BrokerCheck({ copy, language, signupOpen = import.meta.env.VITE_PUBLIC_SIGNUP === "true", onDemo })`. `copy` is `COPY[language].brokerCheck`, and `onDemo` is the landing's existing demo click handler factory result for entry point `"landing_hero"`.
- State: the query string. The result is derived: empty query → no result. An exact or unique supported match → `supported`. A query matching an unsupported name, or nothing → `unsupported`. Supported matches render as clickable chips (logo + name); clicking one selects it.
- `supported` result:
  - Text `copy.supported.replace("{name}", broker.name)`.
  - If `signupOpen`: a primary link to `registerUrl({ source: "landing_broker_check", broker: key, lang: language })` labelled `copy.signup`, plus a secondary demo link.
  - Else: a primary demo link labelled `copy.demo` and the note `copy.betaNote`.
- `unsupported` result: `copy.unsupported.replace("{name}", typed)` plus the demo link.
- No `window`/storage access during render.
- `welcomeCopy.js` gets `brokerCheck` for each language. Match each language's existing form of address:
  - **cs:** `title: "Podporujeme tvého brokera?"`, `placeholder: "Např. XTB, Trading 212…"`, `supported: "{name} podporujeme. Svoje data nahraješ hned po registraci."`, `signup: "Založit účet zdarma"`, `demo: "Prohlédnout demo"`, `betaNote: "Portfyl je teď v uzavřené betě. Demo si ale můžeš projít hned."`, `unsupported: "{name} zatím neumíme načíst. Podívej se aspoň na ukázkové portfolio."`
  - **en:** `"Is your broker supported?"`, `"e.g. XTB, Trading 212…"`, `"{name} is supported. You can bring your data right after signing up."`, `"Create a free account"`, `"Open the demo"`, `"Portfyl is in private beta right now, but you can explore the demo straight away."`, `"We can't read {name} yet. Take a look at the sample portfolio instead."`
  - **de:** `"Wird dein Broker unterstützt?"`, `"z. B. XTB, Trading 212…"`, `"{name} wird unterstützt. Deine Daten importierst du direkt nach der Registrierung."`, `"Kostenloses Konto erstellen"`, `"Demo öffnen"`, `"Portfyl ist gerade in einer geschlossenen Beta – die Demo kannst du aber sofort ansehen."`, `"{name} können wir noch nicht einlesen. Sieh dir stattdessen das Beispielportfolio an."`

- [ ] **Step 1: Write the failing tests** (`BrokerCheck.test.jsx`):
  - Typing "xtb" with `signupOpen` shows the cs supported text and a link whose `href` equals `registerUrl({ source: "landing_broker_check", broker: "xtb", lang: "cs" })`.
  - With `signupOpen={false}`, the same query shows no register link, and shows the demo link and the beta note.
  - "Revolut" shows the unsupported text and the demo link.
  - `test("renders the same HTML on the server")`: `renderToString(<BrokerCheck copy={COPY.cs.brokerCheck} language="cs" />)` contains the title and no result region.
  - `Welcome.test.jsx`: the cs/en/de pages each contain their `brokerCheck.title`.
- [ ] **Step 2: Run them.** `npx vitest run src/components/landing src/pages/Welcome.test.jsx` should FAIL.
- [ ] **Step 3: Implement.** Style it in `Welcome.css` with the landing's existing classes/tokens (`welcome-container`, `welcome-cta`, Clay surfaces). Broker logos come from `onboardingBrokers.js`.
- [ ] **Step 4: Run the tests and builds.** Same tests should PASS, then `npm test && npm run test:cloud && npm run build && npm run build:cloud`. The prerender output `dist/prerendered/index.html` contains "Podporujeme tvého brokera?".
- [ ] **Step 5: Commit.** `git commit -m "feat(landing): check broker support before signing up"`

---

### Task 10: Dashboard welcome panel, "Getting started" checklist, sample-data banner (Track C)

**Files:**
- Create: `frontend/src/lib/gettingStarted.js`, `frontend/src/lib/gettingStarted.test.js`
- Create: `frontend/src/components/dashboard/WelcomePanel.jsx`, `frontend/src/components/dashboard/WelcomePanel.test.jsx`
- Create: `frontend/src/components/dashboard/DemoDataBanner.jsx`, `frontend/src/components/dashboard/DemoDataBanner.test.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx` (render both above `PortfolioHero`)

**Interfaces:**
- Consumes: `preferencesConfirmed` (Task 4), `intendedBroker` (Task 1), `usePortfolio()` (`portfolios`, `current`), `useAuth().currentWorkspace.id`, the Dashboard's existing `summary`, `holdings`, `dividends` queries, and `summarizePassiveIncome` (`lib/dashboardSummaries.js`).
- `lib/gettingStarted.js`:
  - `GETTING_STARTED_IDS = ["first_portfolio","second_broker","preferences","dividends"]`
  - `gettingStartedItems({ portfolios, preferencesConfirmed, visited }) -> Array<{ id, done: boolean, to: string }>`, where:
    - `first_portfolio`: done when any portfolio's `brokers` has a key other than `"demo"`; `to: "/import"`
    - `second_broker`: done when ≥ 2 distinct non-demo broker keys exist across portfolios; `to: "/import"`
    - `preferences`: done when `preferencesConfirmed`; `to: "/settings?section=preferences"`
    - `dividends`: done when `visited.includes("dividends")`; `to: "/dividends"`
  - `readGettingStarted(workspaceId) -> { dismissed: boolean, visited: string[] }`, `markGettingStartedVisited(workspaceId, id) -> void`, `dismissGettingStarted(workspaceId) -> void`. Key `portfyl_getting_started:<workspaceId>`, JSON, storage-safe (malformed JSON → defaults).
- `WelcomePanel({ items, insight, onVisit, onDismiss })`. It renders only when not dismissed and not every item is done. Heading `t("Getting started")`, progress `t("{done} of {total} done", …)`. Item labels:
  - `first_portfolio`: `t("Add your first portfolio")`
  - `second_broker`: `t("Add another broker for one combined view")`
  - `preferences`: `t("Check language and currency")`
  - `dividends`: `t("See your dividend calendar")`
  
  Items are `Link`s; clicking one calls `onVisit(id)`. Dismiss is `t("Hide")`. `insight`: when the trailing-12-month dividend income from `summarizePassiveIncome` is > 0, show `t("Over the last 12 months your dividends brought you {amount}.", { amount: formatMoney(...) })`. Otherwise show `t("You hold {count} positions.", { count: holdings.length })`.
- `DemoDataBanner({ portfolio })`. It renders when `portfolio?.brokers?.includes("demo")`: `t("You're looking at sample data.")` plus a `Link` `t("Import your own portfolio")` to `/import?broker=<intendedBroker()>`, or `/import` when no broker is remembered.

- [ ] **Step 1: Write the failing tests.**
  - `gettingStarted.test.js`: demo-only portfolios → `first_portfolio` not done; `xtb` + `degiro` → `second_broker` done; malformed stored JSON → `{ dismissed: false, visited: [] }`; a throwing storage → defaults and no throw.
  - `WelcomePanel.test.jsx`: it shows "1 of 4 done"; clicking "See your dividend calendar" calls `onVisit("dividends")`; it renders nothing when all items are done; "Hide" calls `onDismiss`.
  - `DemoDataBanner.test.jsx`: it renders for `brokers: ["demo"]` with href `/import?broker=xtb` when `portfyl_intended_broker=xtb`; it renders nothing for `brokers: ["xtb"]`.
- [ ] **Step 2: Run them.** `npx vitest run src/lib/gettingStarted.test.js src/components/dashboard` should FAIL.
- [ ] **Step 3: Implement** the three units and wire them into `Dashboard.jsx` (state from `readGettingStarted`, re-read after `markGettingStartedVisited`/`dismissGettingStarted`).
- [ ] **Step 4: Add the dictionaries**, then run the same tests plus `messages.test.js` and `src/pages/Dashboard.async.test.jsx` (PASS), then `npm test && npm run build`.
- [ ] **Step 5: Check it in the browser.** A demo workspace shows the banner. Importing a real file shows the panel with "1 of 4 done".
- [ ] **Step 6: Commit.** `git commit -m "feat(dashboard): getting-started checklist and sample-data banner"`

---

### Task 11: Funnel analytics and the funnel doc (Wave 3)

**Files:**
- Modify: `frontend/src/analytics/eventContract.js`, `frontend/src/analytics/eventContract.test.js`
- Modify: `frontend/src/pages/Onboarding.jsx`, `frontend/src/components/landing/BrokerCheck.jsx`, `frontend/src/pages/Register.jsx`, and the matching tests
- Create: `docs/operations/onboarding-funnel.md`

**Interfaces:**
- New events in `ANALYTICS_EVENTS`:
  - `ONBOARDING_STEP_VIEWED: "onboarding_step_viewed"` with `step ∈ {"broker","choices","unsupported"}`
  - `ONBOARDING_BROKER_PICKED: "onboarding_broker_picked"` with `broker_key ∈ {supported keys…, "unsupported"}` (never the typed name)
  - `BROKER_CHECK_USED: "broker_check_used"` with `result ∈ {"supported","unsupported"}` and `language` (cs/en/de)
  - `BROKER_REQUEST_SENT: "broker_request_sent"` with no properties (schema `[]`)
- `sourceSurfaces` gains `"landing_broker_check"`. `Register.jsx`'s `sourceSurfaceFrom` maps `source=landing_broker_check` to it (allowlist; anything else is still `"direct"`).
- Call sites:
  - `Onboarding.jsx` emits `onboarding_step_viewed` once per step change (keyed by step, not by re-render), `onboarding_broker_picked` on a pick, and `broker_request_sent` after a successful notify.
  - `BrokerCheck` emits `broker_check_used` once per distinct result (debounced on result change, not per keystroke).

- [ ] **Step 1: Write the failing tests.** The contract accepts each new event with valid properties and rejects `broker_key: "Revolut"` and `step: "language"`. Onboarding emits `["onboarding_step_viewed",{step:"broker"}]` once even after re-renders. BrokerCheck typing "x","xt","xtb" emits a single `broker_check_used` `{result:"supported", language:"cs"}`. Register with `?source=landing_broker_check` emits `signup_started` with that surface.
- [ ] **Step 2: Run them.** `npx vitest run src/analytics src/pages/Onboarding.test.jsx src/components/landing src/pages/Register.intent.test.jsx` should FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them again** (PASS), then `npm test && npm run test:cloud && npm run build && npm run build:cloud`.
- [ ] **Step 5: Write `docs/operations/onboarding-funnel.md`.**
  - The PostHog funnel, in order: `landing_viewed → broker_check_used (optional branch) → signup_started → signup_completed → onboarding_step_viewed(step=broker) → onboarding_step_viewed(step=choices) → portfolio_created → portfolio_data_imported → user_activation_reached`, plus the demo branch `demo_started → signup_cta_clicked`.
  - The broker-demand query, run with the migration-owner credential: `SELECT lower(broker_name) AS broker, count(*) FROM broker_requests GROUP BY 1 ORDER BY 2 DESC;`
  - A note that creating the funnel in PostHog is a manual step that needs the founder's approval.
- [ ] **Step 6: Commit.** `git commit -m "feat(analytics): onboarding funnel events and runbook"`

---

### Manual tasks (founder)

- **M0:** decide on the uncommitted currency-`Select` change in `OnboardingView.jsx`/`Onboarding.test.jsx` before Track A starts. Task 5 removes `CurrencyPick` anyway.
- **M1:** capture export screenshots per broker (XTB, Degiro, IBKR, Schwab, Fidelity, Trading 212) from your own accounts, with personal data blurred. Save them to `frontend/src/assets/broker-guides/<broker>/<n>.png`, import them, and register them in `lib/brokerGuideImages.js` with an `alt` `msg("…")` (plus translations). No other code changes are needed.
- **M2:** when private beta ends, set `VITE_PUBLIC_SIGNUP=true` in the cloud build (`Dockerfile` build-arg + `deploy/cloudrun.md`) so the landing check offers signup.
- **M3:** have the lawyer review the privacy-policy additions from Task 3 Step 7.

### Final integration (after Wave 3)

- [ ] Rebase onto the latest `main`. Re-run `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`, `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`, the PostgreSQL suite, and `alembic heads` vs `EXPECTED_ALEMBIC_HEAD`.
- [ ] Walk the whole journey in a browser at desktop and at 390px width: landing check (cs) → register → verification tab continues → onboarding starts at "Step 2 of 2 · XTB" → guide visible → import → dashboard panel and checklist. Save the screenshots for the founder.
- [ ] Run the Cloud Run migration Job before deploying (`deploy/run-migrations.ps1`), per `deploy/cloudrun.md`.
