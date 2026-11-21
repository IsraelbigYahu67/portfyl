# Free trial completion: verification evidence

Branch `integrate/free-trial-completion`, HEAD `e2a7330`, run on 2026-11-20
(Windows 11, Python 3.12.13 and 3.14, Node 22). It merges `feat/trial-state`,
`feat/trial-ui`, `feat/turnstile-backend`, `feat/turnstile-frontend` and
`docs/trial-legal` (all off `main` = `f23b500`, which had not moved). The
merges were clean. Nothing was deployed and nothing was merged into `main`.

Both venvs were built fresh from the hashed lock
(`uv pip install --require-hashes -r backend/requirements-dev.lock`): the
repository's own `.venv` lacks `openpyxl`, so it cannot import the importers.

## Results

| Step | Command | Result |
|---|---|---|
| 2 | Backend fast suite, Python 3.12: `python -m pytest tests/ --ignore=tests/postgres` | **2394 passed** (first run 17 failed, all in the new `test_auth_session_turnstile.py`: the harness lacked an `auth_session` rate-limit rule; fixed in `d2d3b0f`, 18/18 pass) |
| 2 | Same, Python 3.14 | **2394 passed** (182 s) |
| 2 | PostgreSQL suite against a disposable container `ptf-trial-pg` (`postgres:16`, host port 55461, database `portfyl_trial_test`, `TEST_DATABASE_URL`): `python -m pytest tests/postgres/` | **494 passed** (144 s), including `test_withheld_registration_writes_marker_under_rls`. Container removed afterwards. |
| 2 | `alembic heads` vs `EXPECTED_ALEMBIC_HEAD` | one head `0028_password_changed_seen`, equal to the constant. No migration in this work. |
| 3 | `npm test` (local edition) | 1698 passed, 1 failed: `miniDemos.test.jsx` hit its 12 s `findByRole` timeout while the machine ran 169 files in parallel; **26/26 pass when run alone**. The file is not touched by this work. |
| 3 | `npm run test:cloud` | first run 8 suites failed to load (they mock `../api` without `fetchBillingStatus`, which `billingStatusQuery.js` read at module load); fixed in `e2a7330` (the query function now reads the export when it runs). Second run: 1697 passed, 1 failed: `Root.test.jsx` "/terms" timed out under load; **Root and Legal tests pass alone in both editions** (31/31). |
| 3 | `npm run build` | passes |
| 3 | `npm run build:cloud` (no `VITE_PUBLIC_SIGNUP`) | passes; `grep -c "/register" dist/prerendered/index.html` = **0** |
| 3 | `VITE_PUBLIC_SIGNUP=true npm run build:cloud` | passes; the prerendered home links `/register` (1 match) |
| 3 | `node scripts/landing-bundle-guard.mjs dist` | `violations: []`, exit 0 |

The full local-edition suite was run once before `e2a7330`; after it, the
affected files (`Root`, `Legal`, `TrialBanner`) and the whole cloud suite were
run again.

## Not done (needs the owner or a real browser session)

- **Step 4, Lighthouse** (`/`, `/en/`, `/terms?lang=cs`, mobile and desktop,
  at least 90 for performance and accessibility): not run. No Lighthouse tool
  was available in this session.
- **Step 5, live walkthrough (a to i)**: not run. It needs Firebase test
  accounts (register, verify e-mail, Google), which this session cannot create,
  plus Playwright screenshots. What the automated tests cover instead:
  Turnstile on-demand check and every failure code (`test_turnstile.py`,
  `test_auth_session_turnstile.py`), the dialog and one retry
  (`AuthProvider.test.jsx`), the withheld marker under real RLS, the banner for
  every phase and the Pricing trial card. Not covered: the real Cloudflare
  widget, the 60 s refetch after `trials.ends_at` moves, the Dashboard
  narrowing to Free widgets, the startup refusal (h), and the local edition
  visually (i).
- **Step 6, moving both plans to `docs/finished.md`** and ticking Tasks 1c, 3, 4
  and 6 of the 2026-11-15 plan: left undone because Steps 4 and 5 are open.

## Before anything is deployed

- Set `PORTFYL_TURNSTILE_SECRET` (and `VITE_TURNSTILE_SITE_KEY` at build time),
  or `PORTFYL_TURNSTILE_DISABLED=1`: the cloud image refuses to start without
  one of them.
- Create the `portfyl-trial-fingerprint-key` secret before raising
  `PORTFYL_TRIAL_DAYS` above 0 (production currently runs `0`).
- Lawyer review of the drafts (`docs/legal/poznamky-pro-pravnika.md`, point 10).
