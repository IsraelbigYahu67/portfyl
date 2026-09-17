# Portfyl UX Reliability and Product Coherence — Delivery Roadmap

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md`

This roadmap is the execution index for the eight stacked implementation phases. The
integration branch is `codex/portfyl-ux-overhaul`; each phase starts from its current
HEAD after the previous phase has merged. No phase branch targets `main`.

## Sequence

| Order | Plan | Branch | Required input | Acceptance result |
|---:|---|---|---|---|
| 1 | [Data trust: dividends and tax precision](2026-09-13-ux-01-data-trust.md) | `codex/ux-01-data-trust` | integration HEAD | Dividend provenance/validation and reconciling FIFO rows |
| 2 | [Platform removal and async-state foundation](2026-09-13-ux-02-platform-state.md) | `codex/ux-02-platform-state` | plan 1 merged | Direct Dashboard routing and shared loading/error/empty contracts |
| 3 | [Responsive shell, navigation, and accessibility](2026-09-13-ux-03-responsive-a11y.md) | `codex/ux-03-responsive-a11y` | plan 2 merged | One nav model, responsive shell, focus/dialog accessibility floor |
| 4 | [Scalable collections](2026-09-13-ux-04-scalable-collections.md) | `codex/ux-04-scalable-collections` | plan 3 merged | Server-paged transactions and bounded large views |
| 5 | [Non-blocking screener](2026-09-13-ux-05-screener-jobs.md) | `codex/ux-05-screener-jobs` | plan 4 merged | Owned in-process scan jobs with progress/cancel/retry |
| 6 | [Portfolio insight decisions](2026-09-13-ux-06-portfolio-insights.md) | `codex/ux-06-portfolio-insights` | plans 1–5 merged | Distinct Dashboard, Allocation, and Analytics purposes |
| 7 | [Product flows](2026-09-13-ux-07-product-flows.md) | ~~`codex/ux-07-product-flows`~~ superseded, see note | plan 6 merged | Tabbed stock research and coherent Watchlists/Import/Settings flows |
| 8 | [Assistant privacy and performance](2026-09-13-ux-08-assistant-performance.md) | `codex/ux-08-assistant-performance` | plan 7 merged | Explicit assistant context, lazy routes, intent prefetch, final QA |

**Phase 7 branch decision (2026-09-17):** phase 7 was implemented twice, independently, from the
same `main` baseline (`e252933`): the standalone `codex/ux-07-product-flows` (6 commits) and a
second lineage folded directly into `codex/ux-08-assistant-performance`. The second lineage is
canonical — it carries phase 7 and phase 8 together with full browser-QA evidence
(`docs/superpowers/plans/ux-08-browser-closeout-2026-09-17.md`) and green CI on draft
[PR #7](https://github.com/IsraelbigYahu67/portfyl/pull/7) (base `codex/portfyl-ux-overhaul`).
`codex/ux-07-product-flows` is superseded; do not build further phase-7 work on it.

## Per-phase branch protocol

1. Fetch and create the named phase worktree from the current
   `codex/portfyl-ux-overhaul` HEAD.
2. Run the branch/status guard printed in the phase plan. Stop on unexplained
   overlapping changes; never reset or stage them.
3. Execute tasks in order with a failing test before each behavioral change.
4. Run the phase's focused tests, full local/cloud frontend gates, and any stated
   backend gate.
5. Complete the browser matrix at 390×844, 768×1024, 1024×768, and 1440×900 against
   the phase worktree ports.
6. Push the phase branch and open a PR targeting `codex/portfyl-ux-overhaul`.
7. Merge only after review and required CI. Delete only that phase's worktree.

## Integration gates

- Do not start a phase while its predecessor is merely open for review.
- Treat `frontend/src/lib/format.js`, shared async primitives, `AppShell`,
  `Pagination`, and edition manifests as cross-phase APIs. Later phases extend them;
  they do not fork local copies.
- Keep Tax Report and Screener out of the cloud build. Every frontend phase runs both
  edition tests and builds.
- The PostgreSQL/RLS suite remains a required CI gate throughout. Run it locally in
  any phase that changes persistence, authentication, owner/workspace scoping,
  migrations, or RLS.
- After phase 8, repeat the entire route/browser walkthrough and compare the initial
  authenticated-shell transfer against the recorded ~372 KB gzip baseline. The final
  integration PR targets `main` only after owner approval.

## Recovery rule

If a phase must be reverted before final integration, revert the whole phase commit
range so frontend and API contracts stay aligned. Resume from the last merged phase;
never skip ahead and silently recreate a predecessor's interface.
