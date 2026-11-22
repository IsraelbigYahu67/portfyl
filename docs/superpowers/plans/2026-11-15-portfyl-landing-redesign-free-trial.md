# Landing Redesign + 10-Day Free Trial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the public landing page (portfyl.com, `/en/`, `/de/`) with a flat, left-aligned, fact-first page that shows the whole product, and add a 10-day Pro trial that every new cloud workspace gets without a card.

**Architecture:** The landing stays a prerendered React page outside `App.jsx`, split into small section components under `frontend/src/components/landing/`. The trial is Portfyl-owned state (four new tables, one new backend module), guarded by Cloudflare Turnstile at registration and by a broker-account check at the first import, resolved inside `entitlements.resolve_entitlements`; Stripe is not involved, so checkout, consent text and the webhook stay as they are.

**Tech Stack:** React 18 + Vite 6, plain CSS with the existing Clay tokens, FastAPI + SQLAlchemy 2.0, Alembic, PostgreSQL RLS, Vitest, pytest.

**Spec:** No separate spec. The approved visual direction is the mockup at https://claude.ai/artifact/BPVCZ43BDm2v2U1P9Wr1Kr; the sections "Design decisions" and "Trial rules" below are the spec. Read `DESIGN.md` and `CLAUDE.md` first. This plan supersedes the look described in `2026-10-16-portfyl-landing-clay.md`.

## Global Constraints

- Cloud edition only. Local edition has no landing, no trial, no banner (`_local_entitlements` is untouched).
- Never mention Tax Report, Screener, Options or Polymarket in landing copy.
- Landing copy lives only in `frontend/src/pages/welcomeCopy.js`, in `cs`, `en`, `de`. All three languages change in the same task.
- No hex colors in `Welcome.css` / `Legal.css`; colors come from tokens in `frontend/src/lib/clayStyle.js`.
- The landing must render without JavaScript (it is prerendered): menu and FAQ use `<details>`, nothing reads `window` during render.
- Trial length: `PORTFYL_TRIAL_DAYS`, default `10`; `0` switches the trial off. Trial tier: `PlanTier.PRO`.
- Bot check: `VITE_TURNSTILE_SITE_KEY` (build) and `PORTFYL_TURNSTILE_SECRET` (Secret Manager). Outbound calls (Turnstile siteverify) run after `database.release_connection`.
- Migrations are additive only. The market-data store plan (`2026-11-12-portfyl-market-data-cache.md`) also claims a revision after `0026_broker_requests`; whichever lands second renumbers itself. After adding `0027_free_trial`, `backend/database.py` `EXPECTED_ALEMBIC_HEAD = "0027_free_trial"` in the same commit.
- Database code is plain `def`, never `async def`.
- Hotspots, one task at a time: `backend/alembic/versions/`, `backend/database.py`, `frontend/src/i18n/messages/*.js`, `frontend/src/pages/welcomeCopy.js`.
- Each task works on its own branch/worktree off `main`: `feat/free-trial` (Tasks 1, 3) and `feat/landing-redesign` (Tasks 2, 4, 5). Nobody commits to `main` directly.

## Design decisions

1. **Flat page, one raised object.** No pills with dots, no two-tone headings, no decorative icons, no blobs, no `01/02/03` on features, no arrow icons on in-page links. The only elevated elements are product screenshots (16px radius, hairline border, one soft shadow).
2. **Left-aligned, one 1120px column.** Headings are one plain statement in Plus Jakarta Sans 700; hero `clamp(2.25rem, 5.2vw, 3.75rem)`.
3. **Header:** logo · Features · Brokers · Pricing · FAQ · language links (CZ EN DE) · "Log in" · one primary button. Sticky, 64px, hairline bottom border. Below 860px: logo + primary button + `<details>` menu.
4. **Section order:** hero → brokers → features → how it works + data facts → pricing → FAQ → closing → footer.
5. **Primary call to action depends on `VITE_PUBLIC_SIGNUP`** (already used by `BrokerCheck`):
   - `"true"`: primary "Vyzkoušet 10 dní zdarma" → `registerUrl({ source, lang })`; secondary text link "Prohlédnout demo" → `/demo`.
   - otherwise: primary "Vyzkoušet živé demo" → `/demo`; status line "Uzavřená beta. Demo je otevřené všem."; no link to `/register` anywhere on the page.
6. **`BrokerCheck` stays**, because it records demand for unsupported brokers. It moves under the broker list as a quiet one-line field ("Nevidíte svého brokera?"), restyled flat.
7. **Screenshots are English UI, EUR, Clay appearance**, one set for all three languages (the app itself is translated into 9 languages, but one picture set keeps Task 5 small). Caption under the first one says the pictures show the English interface.
8. **Pricing is shown on the landing** even while billing is off. Prices come from one shared constant; no `offers` in structured data until billing is enabled.

## Trial rules

1. A trial starts when a workspace is created by registration (`routers/auth.py::_provision_identity`). Existing workspaces get none.
2. It lasts `PORTFYL_TRIAL_DAYS` days and grants Pro capabilities and limits. No card, no Stripe object.
3. One trial per mailbox, ever. A global table keeps an HMAC-SHA256 of the **canonical** e-mail, so deleting the account and registering again grants nothing, and neither does an alias of the same mailbox. Rows older than 12 months are purged by the daily job. Canonical form (used only for the trial fingerprint; login, `beta_access` and the stored e-mail keep the address exactly as typed):
   - `lower(trim(email))`;
   - drop everything from the first `+` to the `@` in the local part (all domains: Gmail, Outlook, iCloud, Proton, Fastmail, Seznam… a false match only costs a trial, never an account);
   - `googlemail.com` → `gmail.com`, and for `gmail.com` remove every `.` in the local part.
4. Resolution order in `resolve_entitlements` (cloud): live subscription → private test selection (only while billing is off and a selection is stored) → active trial → Free.
5. An active trial resolves with `source="trial"` and `effective_until=ends_at`. `/billing/status` and `/test-plans` already return `payload()`, so the frontend needs no new endpoint.
6. When the trial ends the workspace is Free. Nothing is deleted: the existing overflow rules (`resource_read_only`, `quota_exceeded`, broker sync stops) apply.
7. Subscribing during the trial is a normal checkout; the subscription wins from that moment.
8. No e-mails are sent (the backend has no mail sender). The reminder is in-app only.
9. **No trial, but a normal Free account**, when any check below fails. Registration itself is never blocked by these rules, so a false positive costs a real user only the trial:
   - the e-mail domain is on the disposable-mail list (`backend/data/disposable_domains.txt`, copied from the open-source `disposable-email-domains` list, refreshed by hand);
   - more than 3 trials were granted from the same client IP (`CF-Connecting-IP`, HMAC'd, same key) in the last 30 days; IP rows are purged after 30 days.
   The e-mail must already be verified: `/auth/session` refuses unverified identities before any workspace exists (`routers/auth.py`), so no new check is needed.
10. Every withheld trial writes an audit event `trial.withheld` with the reason (`email_reused`, `disposable_domain`, `ip_limit`), and every trial ended by item 11 writes `trial.ended_early` with `broker_account_reused` or `history_reused`. No e-mail, account number or IP in the event. The counts decide whether a card-required trial is ever needed.
11. **Broker check: the decisive test.** At registration the broker account is unknown, so it runs at every import commit and every broker sync in a workspace whose trial is active, and it overrides items 3 and 9 (a trial that passed them still ends here):
   - **Account number**, where the data carries one: Trading 212 API (the `id` from `/equity/account/summary`, which `routers/broker.py` already turns into a fingerprint when a connection is made); IBKR `FlexStatement@accountId` (Flex API sync and Flex XML upload); eToro: **checked in Task 1b, no stable account id** (the Public API client `etoro_client.py` calls only trade history, positions, instruments and the eToro Money cash endpoint; none returns a trading-account or customer id, and the cash endpoint takes an account id as input rather than returning one), so eToro falls under the next point and uses the history fingerprint of the oldest stored eToro rows; XTB: the importer reads only the account currency and the cash-operations table, no account number (the layout is still unverified until plan Task 0 samples), so XTB also uses the history fingerprint. IBKR paper accounts (ids starting with `D`: DU, DF, DI) and masked ids (containing `*`) are skipped like Trading 212 `demo`, because anyone can open paper accounts without limit and a mask would match strangers. Fingerprint = the existing `account_identity.account_fingerprint(broker, environment, provider_account_id)` with its key `PORTFYL_ACCOUNT_FINGERPRINT_KEY`. No new key. Trading 212 `demo` connections are skipped, because anyone can open unlimited demo accounts.
   - **Not the API key or secret.** A user can revoke a key and create a new one in seconds, so comparing keys catches nothing, and a lasting hash of a credential that survives account deletion is a liability. The key only serves to read the account `id`, and the `id` stays the same whatever key is used.
   - **History** for files without an account number (T212 CSV, Degiro): HMAC of each of the 5 oldest `(source, source_event_stream, source_event_id)` rows. The same person re-importing their own export into a new account produces the same oldest rows. Rows that match `sample_portfolio.csv` or the onboarding demo data are never fingerprinted.
   - Stored in the global table `trial_broker_marks(fingerprint primary key, kind, workspace_id nullable, first_seen_at)`; `workspace_id` becomes `NULL` when that workspace is deleted. Purged after 12 months, like `trial_identities`.
   - The trial ends now (`trial_grants.ended_reason` set, `ends_at = now`) when the account-number fingerprint, or at least 3 of the 5 history fingerprints, already belong to a different or deleted workspace. The import itself always completes; only the plan changes.
   - The payload of `/billing/status` and `/test-plans` gains `trial_ended_reason` (`null`, `"expired"`, `"broker_account_reused"`, `"history_reused"`), so the app can say why.
   - Couples sharing one broker account get one trial between them. Accepted.
12. **Bot check at registration.** In the cloud edition, `/auth/session` requires a valid Turnstile token (action `signup`, hostname checked, single use) only when it is about to provision a new identity. Existing users log in without it. Failure → `403 bot_check_failed` and nothing is created. This blocks the account itself, unlike item 9, because it stops scripts, not people (a human who fails gets Cloudflare's interactive challenge). With `PORTFYL_TURNSTILE_SECRET` unset, the check is off and `/api/health` reports the `turnstile` subsystem as `disabled`; public signup must not open in that state.

## Review Focus

1. **Trial ends while the app is open.** `plan-capabilities` is cached for 60s, so a Pro endpoint can return `403 plan_upgrade_required`. Expected: the app refetches the plan and shows the ended notice, not an error screen. Test in Task 3.
2. **Same e-mail registers again after account deletion.** Expected: no second trial, workspace starts on Free. Test in Task 1.
3. **Repeat trial through a new e-mail.** Account A imports an IBKR Flex XML during its trial; account B (other e-mail, other IP) imports the same file: B's trial ends at once with `broker_account_reused`, B's import is complete, A is untouched. The same with a T212 CSV gives `history_reused`. Importing `sample_portfolio.csv` into both ends nothing. Test in Task 1b.
4. **Workspace above Free limits at expiry** (40 positions, 2 broker connections). Expected: everything stays readable, rows beyond the limit are read-only, nothing is removed. Test in Task 1.
5. **`VITE_PUBLIC_SIGNUP` unset.** Expected: prerendered HTML of all three languages contains no `/register` link and no "10 dní zdarma" button. Test in Task 2.
6. **Day counting near the end.** Expected: the banner never shows "0 days" or a negative number; under 24 hours it reads "ends today". All comparisons in UTC. Test in Task 3.

## File structure

Backend (Task 1):
- Create `backend/trials.py`: grant, lookup, purge. Nothing else knows the tables.
- Create `backend/alembic/versions/0027_free_trial.py`: tables `trial_grants` (tenant, RLS forced, with nullable `ended_reason`), and the global tables `trial_identities`, `trial_ip_marks` (IP fingerprint, granted_at) and `trial_broker_marks` (item 11). All four tables land in this one migration so Task 1b needs none.
- Modify `backend/models.py`, `backend/database.py`, `backend/entitlements.py`, `backend/routers/auth.py`, `backend/jobs.py`, `backend/account_deletion.py` (and the export module if it enumerates tenant tables), `docs/security/tenant-isolation-matrix.md`, `deploy/cloudrun.md`.
- Tests: `backend/tests/test_trials.py`, `backend/tests/test_entitlements.py`, `backend/tests/postgres/test_trial_rls.py`.

Broker check (Task 1b):
- Modify `backend/trials.py` (add `record_broker_marks`), `backend/importers/formats/ibkr_flex.py` (return the account ids it saw), `backend/routers/ibkr.py`, `backend/routers/etoro.py`, `backend/routers/broker.py` (Trading 212 connection), the router that serves `/portfolio/import-csv/commit`, `backend/entitlements.py` (`trial_ended_reason` in the payload).
- Tests: `backend/tests/test_trial_broker_check.py`.

Bot check (Task 1c):
- Create `backend/turnstile.py` (siteverify call), `frontend/src/auth/TurnstileWidget.jsx` (+ test).
- Modify `backend/routers/auth.py`, `backend/security_headers.py` (CSP `script-src` and `frame-src` add `https://challenges.cloudflare.com`), the subsystem health module, the register and login pages in `frontend/src/auth/`, `frontend/src/i18n/messages/*.js` (error text), `deploy/cloudrun.md`.
- Tests: `backend/tests/test_turnstile.py`, the CSP test, the auth page tests.

Landing (Task 2):
- Create in `frontend/src/components/landing/`: `LandingHeader.jsx`, `LandingHero.jsx`, `BrokerList.jsx`, `FeatureList.jsx`, `HowItWorks.jsx`, `PricingTeaser.jsx`, `LandingFaq.jsx`, `LandingFooter.jsx`, `landingImages.js`.
- Create `frontend/src/lib/planPrices.js`.
- Rewrite `frontend/src/pages/Welcome.jsx` (keeps language, analytics and demo-click logic; only composes sections), `Welcome.css`, `welcomeCopy.js`, `Welcome.test.jsx`.
- Modify `frontend/src/components/landing/BrokerCheck.jsx` (+ test), `frontend/src/lib/clayStyle.js`, `frontend/src/pages/Pricing.jsx` (import prices).

In-app trial (Task 3):
- Create `frontend/src/components/billing/TrialBanner.jsx` (+ test), `frontend/src/lib/trial.js` (+ test).
- Modify the app shell that renders the top of `#main-content`, `frontend/src/pages/Pricing.jsx`, `frontend/src/api.js` (403 handling), `frontend/src/i18n/messages/*.js`.

Legal + docs (Task 4), screenshots (Task 5), verification (Task 6): listed in the tasks.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 0 | Owner captures screenshots (see "Screenshot list") | Runs alongside everything; only Task 5 waits for it |
| 1 | Task 1 and Task 2 in parallel | Disjoint files |
| 2 | Task 1b (after 1), Task 3 (after 1) and Task 4 (after 2) in parallel | Task 1b is backend only, on `feat/free-trial-broker`; Task 3 owns `i18n/messages`, Task 4 owns `welcomeCopy.js` legal labels |
| 3 | Task 1c and Task 5 in parallel, then Task 6 | Task 1c on `feat/turnstile` takes over `i18n/messages` after Task 3; Task 5 waits for screenshots; Task 6 merges all branches into one integration branch |

---

### Task 1: Trial backend

**Files:** see "File structure → Backend".

**Interfaces:**
- Produces, in `backend/trials.py`:
  - `trial_days(env: Mapping[str, str]) -> int`: reads `PORTFYL_TRIAL_DAYS`, default 10; raises `RuntimeError` for a negative or non-integer value.
  - `canonical_email(email: str) -> str`: the canonical form from "Trial rules" item 3.
  - `trial_block_reason(db, *, email, client_ip, now, env) -> str | None`: `"email_reused"`, `"disposable_domain"`, `"ip_limit"` or `None` ("Trial rules" item 9).
  - `identity_fingerprint(email: str, env: Mapping[str, str]) -> str`: hex HMAC-SHA256 of `canonical_email(email)` keyed by `PORTFYL_TRIAL_FINGERPRINT_KEY`; raises `RuntimeError` when the key is missing and `trial_days(env) > 0`.
  - `grant_trial(db: Session, *, workspace_id: UUID, email: str, now: datetime, env: Mapping[str, str]) -> TrialGrant | None`: returns `None` when trials are off or the fingerprint already exists.
  - `active_trial(db: Session, workspace_id: UUID, now: datetime) -> TrialGrant | None`
  - `purge_old_identities(db: Session, now: datetime) -> int`: deletes `trial_identities` rows granted more than 365 days ago.
- Produces, in `backend/models.py`: `TrialGrant(id, public_id, workspace_id unique, started_at, ends_at)` with check `ends_at > started_at`; `TrialIdentity(fingerprint primary key, granted_at)`.
- Produces: `EffectiveEntitlements.source == "trial"` with `effective_until == ends_at`.

- [ ] **Step 1: Write failing tests in `backend/tests/test_trials.py`**
  - `test_new_workspace_gets_ten_day_pro_trial`: after `grant_trial(..., now=T)`, `resolve_entitlements` returns `plan == PlanTier.PRO`, `source == "trial"`, `effective_until == T + 10 days`.
  - `test_trial_expires_to_free`: at `T + 10 days + 1s` → `plan == FREE`, `source == "free"`.
  - `test_second_grant_for_same_email_returns_none`: second `grant_trial` with `" Alice@Example.com "` after one for `"alice@example.com"` returns `None` and creates no `TrialGrant`.
  - `test_canonical_email`: `"Jan.Novak+1@GoogleMail.com"` → `"jannovak@gmail.com"`; `"jan+x@seznam.cz"` → `"jan@seznam.cz"`; `"jan.novak@outlook.com"` keeps its dot.
  - `test_alias_gets_no_second_trial`: after a grant for `jan@gmail.com`, `j.a.n+2@gmail.com` gets `None`, the account still exists on Free, and an audit event `trial.withheld` with `reason="email_reused"` is written.
  - `test_disposable_domain_gets_no_trial` and `test_fourth_trial_from_same_ip_in_30_days_is_withheld`.
  - `test_trial_days_zero_grants_nothing` and `test_missing_fingerprint_key_fails_closed`.
  - `test_expired_trial_keeps_overflow_rows_read_only`: 40 positions and 2 broker connections created during the trial; after expiry `ensure_final_count_limit` rejects an increase, allows a decrease, and no row is deleted.
  - `test_purge_removes_only_identities_older_than_365_days`.
- [ ] **Step 2: Add to `backend/tests/test_entitlements.py`**
  - `test_live_subscription_wins_over_trial` (Investor subscription + active trial → `investor`, `source == "subscription"`).
  - `test_test_selection_wins_over_trial_when_billing_off` and `test_trial_wins_over_free_when_billing_on`.
  - `test_local_edition_ignores_trial`.
- [ ] **Step 3: Run** `cd backend && python -m pytest tests/test_trials.py tests/test_entitlements.py -v` → new tests FAIL (module missing).
- [ ] **Step 4: Migration `0027_free_trial.py`** (revises `0026_broker_requests`). `trial_grants`: copy the RLS, policy and grant statements used for the tenant table in `0026_broker_requests.py`. `trial_identities`, `trial_ip_marks`, `trial_broker_marks`: no RLS, grants as for `beta_invites` in `0013_private_beta_invites.py`; `trial_broker_marks.workspace_id` references `workspaces.id` with `ON DELETE SET NULL`. Set `EXPECTED_ALEMBIC_HEAD = "0027_free_trial"`.
- [ ] **Step 5: Implement `backend/trials.py` and the models.** `grant_trial` inserts the identity with `ON CONFLICT DO NOTHING` (PostgreSQL) and creates the grant only when a row was inserted; on SQLite use select-then-insert.
- [ ] **Step 6: Wire it in.** `entitlements.resolve_entitlements`: order from "Trial rules" item 4. `routers/auth.py::_provision_identity`: call `grant_trial` after the membership flush, cloud edition only, same transaction. `jobs.py`: call `purge_old_identities` in the existing daily pass. `account_deletion.py` and the export: include `trial_grants`; keep `trial_identities`.
- [ ] **Step 7: PostgreSQL test `backend/tests/postgres/test_trial_rls.py`**: Alice cannot read or insert Bob's `trial_grants` row; the runtime role can insert into `trial_identities`. Add the table to `docs/security/tenant-isolation-matrix.md`.
- [ ] **Step 8: Run** the fast suite and `python -m pytest tests/postgres/ -v`; `alembic heads` prints exactly `0027_free_trial`. All PASS.
- [ ] **Step 9: Document** `PORTFYL_TRIAL_DAYS` and `PORTFYL_TRIAL_FINGERPRINT_KEY` (Secret Manager) in `deploy/cloudrun.md`. Commit: `feat(billing): 10-day Pro trial for new workspaces`.

### Task 1b: Broker check

**Files:** see "File structure → Broker check". Depends on Task 1. Branch `feat/free-trial-broker`.

**Interfaces:**
- Produces in `backend/trials.py`: `record_broker_marks(db, *, workspace_id, account_fingerprints: list[str], oldest_event_keys: list[tuple[str, str, str]], now, env) -> str | None`. Returns the `ended_reason` when it ended the trial, else `None`. Does nothing when the workspace has no active trial.
- Produces in the payload: `trial_ended_reason` ("Trial rules" item 11). Task 3 consumes it.

- [ ] **Step 1: Check eToro.** Read the eToro API client in `backend/` and the eToro API docs for a stable account or customer id. Write the finding into "Trial rules" item 11. No id → eToro uses the history fingerprint.
- [ ] **Step 2: Failing tests `backend/tests/test_trial_broker_check.py`**: the three cases from "Review Focus" item 3; the same workspace re-importing its own file ends nothing; a mark whose workspace was deleted (`workspace_id NULL`) still ends a new trial; a workspace without an active trial records nothing; 2 of 5 history matches end nothing, 3 of 5 do; the audit event carries no account number.
- [ ] **Step 3: Implement** `record_broker_marks` (it takes ready fingerprints from `account_identity.account_fingerprint`, never raw ids or API keys); make `ibkr_flex.py` return account ids next to the rows; call `record_broker_marks` after the rows are written in the import commit, the IBKR Flex sync and the eToro sync, and in `routers/broker.py` where a Trading 212 live connection is saved (the fingerprint is already computed there), inside the same transaction. Extra test: a second workspace connecting the same Trading 212 live account with a newly generated API key ends its trial; a `demo` connection ends nothing.
- [ ] **Step 4: Run** the fast suite and the PostgreSQL suite. Commit `feat(billing): end a repeat trial on a known broker account`.

### Task 1c: Bot check (Cloudflare Turnstile)

**Files:** see "File structure → Bot check". Depends on Task 1 (shares `routers/auth.py`) and on Task 3 (hands over `i18n/messages`). Branch `feat/turnstile`. Use the `cloudflare:turnstile-spin` skill; create the Turnstile widget for `app.portfyl.com` and `localhost` through the Cloudflare plugin (managed mode).

- [x] **Step 1: Failing tests.** `test_turnstile.py`: a new identity without a token → `403 bot_check_failed` and no `User` row; with a token that siteverify accepts → provisioned; a wrong `action` or hostname → 403; an existing user without a token → session issued; secret unset → check skipped and health reports `disabled`; local edition never checks. Siteverify is stubbed, never called for real. CSP test expects `https://challenges.cloudflare.com` in `script-src` and `frame-src`. Frontend: register and login pages send `turnstile_token` with the session exchange; the widget is not rendered when `VITE_TURNSTILE_SITE_KEY` is empty.
- [x] **Step 2: Implement** `turnstile.py` (sync `httpx`, 5 s timeout; a timeout counts as failure), the check in `/auth/session` just before `_provision_identity`, the widget, the CSP and the health entry.
- [x] **Step 3: Strings** for `bot_check_failed` in all nine `i18n/messages` files.
- [x] **Step 4: Run** the fast suite, `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`. Document both settings in `deploy/cloudrun.md`. Commit `feat(auth): Cloudflare Turnstile on new sign-ups`.

### Task 2: Landing structure, copy and styles

**Files:** see "File structure → Landing".

**Interfaces:**
- Produces `frontend/src/lib/planPrices.js`: `export const PLAN_PRICES_CENTS = { investor: 599, pro: 999 }` and `formatPlanPrice(cents, language) -> string` ("5,99 €" for cs/de, "€5.99" for en). `Pricing.jsx` imports the constant instead of its own literals.
- Produces `landingImages.js`: `LANDING_IMAGES = { hero, allocation, sectors, dividends, stock, valuation, analytics, importPreview, onboardingBrokers, phoneDashboard, phoneAllocation }`, each `{ src, width, height }`. Until Task 5 the existing `*-live-20260911.png` files fill `hero`, `allocation`, `stock`; the other keys are `null` and their figures do not render.
- Produces props: `LandingHeader({ copy, language, signupOpen, onDemo })`, `LandingFooter({ copy, language })`. Task 4 reuses both.
- Produces in `clayStyle.js`: token `--landing-paper` (`#FAF5ED`), used as the page background; bands use `--bg`.
- Consumes: `registerUrl` from `lib/signupIntent.js`, `VITE_PUBLIC_SIGNUP`.

- [ ] **Step 1: Rewrite `Welcome.test.jsx` first (failing).** For each of `cs`, `en`, `de`:
  - one `h1`; header nav has exactly four in-page links targeting `#funkce`, `#brokeri`, `#cenik`, `#otazky`, and those ids exist;
  - a "Log in" link points to `${APP_ORIGIN}/login`;
  - with `signupOpen` false: no `a[href*="/register"]`, primary button links to `/demo`, the beta status line is present;
  - with `signupOpen` true: primary button `href` equals `registerUrl({ source: "landing_hero", lang })`, and the text contains "10";
  - pricing shows three plans and the prices equal `formatPlanPrice` of `PLAN_PRICES_CENTS`;
  - no element has class `welcome-eyebrow`, `welcome-orbit` or `welcome-float`;
  - copy contains none of: "Tax", "Daň", "Steuer", "Screener", "Options", "Polymarket";
  - existing behaviour kept: language links, language suggestion, demo click analytics (`landing_hero`, `landing_closing`), legal links.
- [ ] **Step 2: Run** `cd frontend && npm test -- Welcome` → FAIL.
- [ ] **Step 3: Rewrite `welcomeCopy.js`.** Keep keys used by `publicPages.js` (`title`). Czech text is fixed by the mockup; write `en` and `de` to the same meaning, plain sentences, no slogan pairs. New keys: `nav` (4), `login`, `status`, `heading` (string), `lead`, `trialCta`, `trialNote` ("10 dní plánu Pro zdarma. Bez platební karty."), `demoCta`, `demoNote`, `brokers { api, file, missing }`, `features` (3 with screenshots + 2 text), `steps` (3), `dataFacts` (3), `pricing { heading, note, trial, plans[3] }`, `questions` (5, adding "Co se stane po 10 dnech?" → "Účet přejde na plán Free. Data zůstanou, jen nad limit Free budou pouze ke čtení."), `closing`, `footer`.
- [ ] **Step 4: Build the section components and `Welcome.jsx`.** One component per section from "Design decisions" item 4; `BrokerList` renders the two groups from `lib/onboardingBrokers.js` (API vs. file) and `BrokerCheck` below them. The data fact "you can delete your account and data any time" is included only after confirming `account_deletion.py` is reachable from Settings; otherwise drop that line.
- [ ] **Step 5: Rewrite `Welcome.css`** from the mockup's stylesheet, with tokens instead of literals. Delete every rule for removed classes. Respect `prefers-reduced-motion`; focus ring 3px `--brand`.
- [ ] **Step 6: Run** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`. Confirm `dist/prerendered/` has the three pages and that with `VITE_PUBLIC_SIGNUP` unset `grep -c "/register" dist/prerendered/index.html` is `0`.
- [ ] **Step 7: Commit** `feat(landing): flat fact-first landing page`.

### Task 3: Trial in the app

**Files:** see "File structure → In-app trial". Depends on Task 1.

**Interfaces:**
- Consumes: `/billing/status` and `/test-plans` payload fields `plan`, `source`, `effective_until`, `trial_ended_reason` (produced by Task 1b; build against the field even if 1b is not merged yet).
- Produces `frontend/src/lib/trial.js`: `trialState(entitlements, now) -> { phase: "none" | "active" | "ended", daysLeft: number | null }`. `daysLeft = Math.ceil((effective_until - now) / 86_400_000)`; `phase === "ended"` when the stored key `portfyl_trial_until` is in the past and `source !== "trial"` and `plan === "free"`.

- [x] **Step 1: Failing tests `lib/trial.test.js`**: 10 days left → `{active, 10}`; 23 hours left → `{active, 1}` and the banner text is the "ends today" message; 1 second after the end with `source: "free"` → `ended`; subscription source → `none`.
- [x] **Step 2: Failing tests `TrialBanner.test.jsx`**: active → text with days left and a link to `/pricing`; ended → one notice with "See plans" and a dismiss button that writes `portfyl_trial_ended_seen`; with `trial_ended_reason` `broker_account_reused` or `history_reused` the notice says the trial was already used for this broker account; never rendered in the local edition.
- [x] **Step 3: Failing test in `api.auth.test.js`**: a `403` with `code: "plan_upgrade_required"` invalidates the `plan-capabilities` query once.
- [x] **Step 4: Implement** `trial.js`, `TrialBanner.jsx` (uses `Badge` tone `brand`, no new colors), mount it in the app shell above page content, add the 403 handling in `api.js`.
- [x] **Step 5: `Pricing.jsx`**: during a trial show "Pro trial until {date}" above the plans and mark Pro as current; plan buttons stay enabled.
- [x] **Step 6: Add the new strings to all nine files in `frontend/src/i18n/messages/`.**
- [x] **Step 7: Run** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`. Commit `feat(billing): trial banner and pricing state`.

### Task 4: Legal pages and legal text

**Files:** `frontend/src/pages/Legal.jsx`, `Legal.css`, `Legal.test.jsx`, `docs/legal/podminky-uzivani-cs.md`, `docs/legal/terms-of-service-en.md`, `docs/legal/zasady-ochrany-osobnich-udaju-cs.md`, `docs/legal/privacy-policy-en.md`, `docs/legal/poznamky-pro-pravnika.md`. Depends on Task 2.

- [x] **Step 1:** `Legal.jsx` renders `LandingHeader` and `LandingFooter`; the text card becomes a flat column with the sticky contents list. Update `Legal.test.jsx` for the new header links.
- [x] **Step 2:** Terms (cs, en): add the trial clause from "Trial rules" items 1, 2, 6, 7, marked `[[TODO]]` for lawyer review.
- [x] **Step 3:** Privacy (cs, en): add the trial identity record (keyed hash of the canonical e-mail, of the broker account number and of the 5 oldest imported transactions, kept 12 months and surviving account deletion; keyed hash of the client IP, kept 30 days; purpose: one trial per person, legitimate interest in preventing abuse; Cloudflare Turnstile as processor for the bot check at registration), marked `[[TODO]]`. Add both points to `poznamky-pro-pravnika.md`.
- [x] **Step 4:** Run the frontend test and build commands from Task 2 Step 6. Commit `feat(legal): flat legal pages, trial terms`.

### Task 5: Screenshots, social images, docs

> **Deferred (2026-11-15):** the owner sends the screenshots later. Until then the landing runs on the existing `*-live-20260911.png` files (see Task 2 interfaces). Step 3 (DESIGN.md, CLAUDE.md) is not deferred: Task 2 updates `DESIGN.md` section 10 and Task 1 updates `CLAUDE.md`.

Depends on the owner's files in `frontend/public/landing/raw/` (see "Screenshot list") and on Tasks 2–4 being merged.

- [ ] **Step 1:** Convert each raw PNG to WebP (quality 82) at full size and at half width; name them `<key>-20261115.webp` and `<key>-20261115@1x.webp`; fill `landingImages.js` with real `width`/`height`; render `<img srcset>`; hero image `fetchPriority="high"`, the rest `loading="lazy"`. Delete the four `*-live-20260911.png` files and the `raw/` folder.
- [ ] **Step 2:** Regenerate `frontend/public/og/portfyl-{cs,en,de}.jpg` (1200×630) from the hero screenshot with the new headline.
- [ ] **Step 3:** Rewrite `DESIGN.md` section 10 to describe the flat landing. In `CLAUDE.md` change "monthly only, VAT included, no trials" to "monthly only, VAT included, 10-day Pro trial without a card (`backend/trials.py`)".
- [ ] **Step 4:** Commit `feat(landing): new product screenshots`.

### Task 6: Integration and verification

- [x] **Step 1:** Merge `feat/free-trial`, `feat/free-trial-broker`, `feat/turnstile` and `feat/landing-redesign` into one integration branch off current `main`; resolve conflicts in `Pricing.jsx`.
- [x] **Step 2:** Backend: fast suite on Python 3.12 and 3.14, PostgreSQL suite, `alembic heads` equals `EXPECTED_ALEMBIC_HEAD`, backend starts.
- [x] **Step 3:** Frontend: `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`, once with `VITE_PUBLIC_SIGNUP=true` and once without.
- [ ] **Step 4:** In a browser at 1440×900 and 390×844, all three languages: no horizontal scroll, header one row on phone, every nav link scrolls to its section, screenshots legible, keyboard focus visible. Lighthouse on `/`: performance and accessibility at least 90.
- [x] **Step 5:** Register a fresh account locally: banner shows 10 days; set `ends_at` to the past in the test database: app shows the ended notice and Free limits; register again with the same e-mail after deleting the account: no trial; a second account (other e-mail) importing the first account's IBKR file: trial ends with the broker notice; a new sign-up with the Turnstile test key that always fails: `bot_check_failed`.
- [ ] **Step 6:** Deploy order: migration Job (`deploy/run-migrations.ps1`) → set `PORTFYL_TRIAL_FINGERPRINT_KEY` and `PORTFYL_TURNSTILE_SECRET` → build with `VITE_TURNSTILE_SITE_KEY` → service deploy. Ask the owner before deploying.

---

## Screenshot list (owner)

**Setup, once:**
1. A fresh account that is not your personal e-mail (the account menu is visible in the pictures).
2. Import `sample_portfolio.csv` from the repository root into one portfolio named "Main portfolio". Do not use the 3-position demo.
3. Pricing page → switch the test plan to **Pro**, so every widget shows.
4. Settings → Preferences: appearance **Clay**, language **English**, currency **EUR**.
5. Chrome → F12 → device toolbar (Ctrl+Shift+M) → "Responsive", width × height as below, DPR **2** (phone: **3**). Capture with Ctrl+Shift+P → "Capture screenshot". This gives a sharp picture without the mouse cursor or browser frame.
6. Wait until charts finish drawing. Nothing hovered, no open tooltip, no error or loading state, demo-data banner closed.
7. Save as PNG into `frontend/public/landing/raw/` under the file name in the table.

| # | File name | Size | Page and state | What must be visible | Used in |
|---|---|---|---|---|---|
| 1 | `hero.png` | 1440×900 | Dashboard, top of page, period **All**, benchmark **S&P 500** on | Sidebar, net worth figure with gain, performance chart with the benchmark line | Hero |
| 2 | `allocation.png` | 1440×900 | Allocation, positions view | Donut and the first 8–10 rows of holdings with weight and value | Feature 1 |
| 3 | `sectors.png` | 1440×900 | Allocation, breakdown by sector (currency or country next to it if they fit) | At least two breakdown charts | Feature 1, second image |
| 4 | `dividends.png` | 1440×900 | Dividends | Monthly bars for the current year and the yearly total | Feature 2 |
| 5 | `stock.png` | 1440×900 | Stock detail of **JNJ** (in the sample portfolio, pays dividends), top of page | Name, price, key figures (P/E, EPS, dividend yield), price chart | Feature 3 |
| 6 | `valuation.png` | 1440×900 | Same stock, Valuation History, **P/E** chart open, range **5Y** | Opened P/E chart with the average line and the strip of tiles below | Feature 3, second image |
| 7 | `analytics.png` | 1440×900 | Analytics, performance against benchmarks | Portfolio versus two indexes and the period switch | Text feature "Performance against indexes" |
| 8 | `import-preview.png` | 1440×900 | Import, after choosing a CSV, **before** confirming. Upload `sample_portfolio.csv` a second time so duplicates are flagged | Preview table, the duplicate marks, the confirm button | How it works, step 2 |
| 9 | `onboarding-brokers.png` | 1440×900 | Settings → Preferences → replay onboarding (`/onboarding/preview`), broker step | The broker choices | How it works, step 1 |
| 10 | `phone-dashboard.png` | 390×844, DPR 3 | Dashboard on phone, top of page | Top bar, net worth, first widget, bottom bar | Features, phone inset |
| 11 | `phone-allocation.png` | 390×844, DPR 3 | Allocation on phone | Donut and holding cards | Features, phone inset |

Optional, only if they look good: `transactions.png` (Transactions list, 1440×900) and `watchlist.png` (a watchlist with 6–8 symbols).

Not needed: pricing and FAQ (built into the page as text), social preview images (generated from `hero.png` in Task 5).

## Open risks for the owner

- **Market data in public screenshots.** The pictures show real tickers and prices. That is the same exposure as today's landing, but it belongs to the open market-data-rights question (Workstream A).
- **Trial abuse.** Scripts are stopped by Turnstile (item 12); aliases and disposable mailboxes by items 3 and 9; a repeat trial with a new real mailbox by the broker check (item 11) as soon as the same account or history is imported. What remains: someone who never imports their real portfolio during the trial, or imports a different file each time. That person gets little from a portfolio app, so we accept it; `trial.withheld` and `trial.ended_early` counts tell us if a card-required trial is ever needed.
- **Legal text** for the trial and for the e-mail hash needs the lawyer before public signup opens.

## Related

- Architecture: [[Free trial]] · [[Frontend structure]] · [[Billing and Stripe]]
- Code: [[trials]] · [[lib.trial]] · [[0027_free_trial]] · [[trial_grants (table)]] · [[pages.Welcome]] · [[components.landing (folder)]] · [[pages.Pricing]]
