# Portfyl Demo, Activation, and Readability Roadmap

**Approved design:** `docs/superpowers/specs/2026-09-19-portfyl-public-demo-activation-readability-design.md`

This file is the execution index. Implement the three linked plans in order. Do not
start the next plan until the preceding plan's final verification task is green and
its changes are committed.

## Required execution order

1. [Readability system](2026-09-19-portfyl-readability-system.md)
2. [Public demo](2026-09-19-portfyl-public-demo.md)
3. [Activation analytics](2026-09-19-portfyl-activation-analytics.md)

The order is deliberate. The public demo consumes the semantic typography and chart
styles established by Plan 1. Analytics attaches to stable landing/demo/application
boundaries created by Plans 1 and 2.

## Executor rules

- Start from a clean worktree created from the commit containing these plans. Do not
  execute against the currently dirty checkout.
- Use `superpowers:test-driven-development` for every implementation task and
  `superpowers:verification-before-completion` before claiming a plan complete.
- Run exactly the narrow failing test shown by a step before writing production code.
- Make the named checkpoint commit after each task; do not combine plan tasks into one
  large commit.
- Preserve the local/cloud edition boundary. Public landing and demo routes exist only
  in the cloud build; the local build still enters the tracker at `/`.
- Do not alter the approved portfolio, activation definitions, event allowlist,
  consent behavior, privacy constraints, or typography/contrast floors.
- If a test fails outside the file under change, stop and determine whether it is a
  pre-existing failure or a regression. Record the command and output in the handoff.
- Do not add session replay, autocapture, form capture, user e-mail, workspace names,
  portfolio IDs, holdings, balances, transactions, or real ticker symbols to analytics.
- Do not use live market data, Firebase, authenticated providers, or backend portfolio
  endpoints from `/demo`.

## Cross-plan release gates

After all three plans are committed, run from the repository root:

```powershell
Push-Location frontend
npm ci
npm test
npm run test:cloud
npm run build
npm run build:cloud
Pop-Location

Push-Location backend
python -m pytest tests/ -v --ignore=tests/postgres
Pop-Location
```

Run the PostgreSQL suite in an environment with `TEST_DATABASE_URL` configured:

```powershell
Push-Location backend
python -m pytest tests/postgres/ -v
Pop-Location
```

Then complete the browser matrix documented by the analytics plan and archive the
screenshots under `artifacts/readability-demo-analytics/`. The artifact directory is
evidence only and must not be committed.

## Definition of done

- All automated gates above pass in both editions.
- `/demo` and its four child experiences work anonymously in the cloud build without
  portfolio API or Firebase activity.
- The ten-asset fixture validates and every displayed total reconciles.
- Pending consent sends nothing; rejection is cookieless; acceptance joins the public
  and app subdomains without capturing personal or financial data.
- Demo and registered activation each fire once under the approved definitions.
- The PostHog project stays on the no-card free tier and stops ingesting at the free
  limit without affecting Portfyl.
- Critical numbers meet the 16/14/12 px floors and all supported appearances meet the
  approved contrast targets at every viewport in the browser matrix.
