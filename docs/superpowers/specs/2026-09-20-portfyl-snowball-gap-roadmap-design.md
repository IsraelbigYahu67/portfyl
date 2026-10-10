# Portfyl vs. Snowball Product Gap Roadmap — Design Specification

**Date:** 2026-09-20  
**Status:** Ready for implementation planning  
**Scope:** Existing Portfyl web application, local and cloud editions

## 1. Purpose

This specification turns a live, authenticated Snowball Analytics walkthrough into
an implementation roadmap for Portfyl. The goal is not screen-for-screen parity.
Portfyl should adopt the functions that help a user answer a concrete portfolio
decision, improve weaker existing flows, and explicitly reject Snowball patterns
that would reduce financial-data trust.

The walkthrough covered Snowball's Dashboard, Portfolio Analytics tabs, Holdings,
Transactions, Cash, Dividend Analytics, My Goal, Corporate Actions, Portfolio
Rebalancing, Portfolio Lab, and Find the Dip. The comparison target is the current
Portfyl repository, including the September UX overhaul and the current Trading 212
cash-snapshot worktree changes.

## 2. Product principles

1. **Decision support before feature count.** Every new surface must answer a user
   question such as “what should I buy?”, “am I on track?”, or “where is risk
   concentrated?”.
2. **Snapshots are not history.** Current broker balances may power current-value
   views, but never historical returns, IRR, tax lots, or cash-flow charts.
3. **No invented transactions.** Broker-versus-ledger differences are shown as a
   reconciliation state. Portfyl must not create synthetic buys, deposits, or cash
   adjustments to force equality.
4. **Explain every score.** A rating exposes its inputs, unavailable fields, formula,
   source, and freshness. It is a quality signal, not investment advice.
5. **Extend existing information architecture.** Prefer tabs and progressive
   disclosure over adding a top-level navigation item for every tool.
6. **Tenant isolation and capability boundaries remain mandatory.** Every persisted
   row is workspace- and portfolio-scoped; local-only functionality stays out of the
   cloud bundle unless explicitly enabled.

## 3. Evidence and gap decisions

| Snowball capability observed | Portfyl today | Decision | Priority |
|---|---|---|---|
| Current broker cash shown with portfolio value | Backend snapshot work is present; the Cash page is not routed and does not distinguish snapshot from ledger | Finish the user-facing current-cash flow, freshness, and reconciliation | P0 |
| Synthetic transactions reconcile broker balances and holdings | Portfyl deduplicates imported history and protects performance calculations | Do not copy; add a non-mutating reconciliation report | P0 |
| Holdings views for general, dividends, and returns; sold toggle; CSV export | Portfyl has holdings on Dashboard/Allocation and closed positions, but fewer task-specific views and no holdings export | Extend Allocation into the full holdings workspace | P1 |
| Target allocations and buy-in view | Portfyl shows actual allocation only | Add per-holding targets, grouped targets, drift, and unassigned state | P1 |
| Deposit, withdrawal, and sale-aware rebalancing | Missing | Add a deterministic recommendation engine after targets exist | P1 |
| Goal planning for portfolio value or passive income | Missing | Add saved goals and transparent scenario projection | P1 |
| Dividend yield on cost, passive-income concentration, dividend quality rating | Forecast and dividend-growth data exist; no portfolio concentration or explainable score | Add concentration first, then an explainable quality signal | P2 |
| Find the Dip using 10/50/100/200-day moving averages | Movers and price history exist; no SMA-relative holdings table | Add a holdings-only technical context tool with neutral wording | P2 |
| Portfolio Lab backtesting with benchmark comparison | Strong realized-portfolio analytics and benchmarks exist; no hypothetical portfolios | Add a stateless total-return backtest lab | P3 |
| Corporate-actions register | Split handling is internal to import/sync and invisible | Add reviewable corporate-action records and explicit application | P3 |
| Portfolio report | Analytics exist but no consolidated exportable portfolio report | Add a printable HTML report after the underlying data contracts stabilize | P3 |
| Top dividend stocks and general dividend payout calendar | Screener and portfolio dividend calendar already cover the useful jobs | Improve existing pages; do not add duplicate routes | No new product |
| Quotes widget and watchlist | Portfyl already has Watchlists and quote-backed stock pages | Improve watchlist presentation only when evidence shows a usability gap | No parity work |
| AI assistant and “why is it moving?” | Portfyl already has a privacy-explicit portfolio assistant; news explanation would need a licensed source | Keep assistant; defer news causality until a source contract exists | Deferred |
| Community profiles, blogs, likes, and feed | Portfyl is a private portfolio tool | Do not copy in this roadmap | Out of scope |

## 4. Target product architecture

### 4.1 Activity and reconciliation

`Transactions` becomes an activity workspace with `Trades`, `Income`, `Cash`, and
`All` views. The current `Cash.jsx` functionality is reused rather than duplicated.
The Cash view has two deliberately separate concepts:

- **Current broker balance:** latest Trading 212/IBKR snapshot, timestamp, native
  currency, and component breakdown where the broker provides it.
- **Recorded cash history:** deposits, withdrawals, trades, dividends, fees,
  interest, and FX legs from the transaction ledger.

The API returns a reconciliation object containing broker amount, ledger amount,
difference, tolerance, source timestamps, and status (`matched`, `different`, or
`unavailable`). The UI explains that a difference usually means incomplete history.
It offers import and sync actions, never “fix automatically”.

### 4.2 Holdings workspace and targets

Allocation remains the home for holdings and diversification. Its table gains
task-specific column presets: `General`, `Income`, and `Returns`. Search, active/sold
state, sortable columns, and CSV export are shared across presets.

Allocation targets are persisted per portfolio and ticker. Each target has an
optional user-defined group, a target percentage, and display order. The API returns
current weight, target weight, and drift. Missing targets are explicit; they are not
silently treated as zero. The sum must equal 100% within 0.01 percentage points before
rebalancing is enabled.

### 4.3 Rebalancing

The rebalancing service is a pure calculation layer. Inputs are current holdings,
current cash snapshot, targets, a deposit or withdrawal, whether sales are allowed,
minimum order value, and fractional-share support. Outputs are suggested buys/sells,
unallocated cash, before/after weights, and warnings.

The service never places trades. Recommendations are explicitly informational and
can be exported as CSV. Buy-only mode spends toward the largest underweights first;
full rebalance allows sales but never creates a sale larger than the current holding.

### 4.4 Goal planning

A portfolio may have one active saved goal. Goal type is either portfolio value or
annual passive income. Inputs include target amount, currency, target date, monthly
contribution, expected nominal return, inflation, and expected dividend yield.

The projection returns base, conservative, and optimistic scenarios, the expected
goal date, required monthly contribution, and yearly points. Assumptions are always
visible and editable. No scenario is labelled a forecast or promise.

### 4.5 Dividend decision support

The dividend page adds:

- current yield and yield on cost;
- annual and monthly income;
- income concentration by holding, including top-one and top-three shares;
- an explainable 0–100 quality signal composed only from available inputs.

The quality signal uses dividend-growth history, payout ratio, free-cash-flow payout
coverage, and payment continuity. Missing inputs reduce confidence, not the score by
default. The UI shows component scores and freshness.

### 4.6 Find the Dip

A stateless endpoint calculates current price relative to 10-, 50-, 100-, and
200-session simple moving averages for current holdings. It returns data coverage and
as-of timestamps. The page calls this “Price vs. moving averages”, not a buy signal.
It supports sorting and watchlist handoff but does not create alerts or trades.

### 4.7 Portfolio Lab

Portfolio Lab accepts 2–20 tickers with weights, a date range, starting capital,
optional monthly contribution, rebalance frequency, and benchmark. The simulation
uses adjusted total-return prices because it models hypothetical wealth rather than
replaying Portfyl's explicit dividend ledger.

The first release is stateless. It returns an equity curve, contributions, CAGR,
annualized volatility, Sharpe, Sortino, maximum drawdown, and benchmark comparison.
Saving/sharing scenarios is excluded until usage proves it is needed.

### 4.8 Corporate actions

Corporate actions are stored separately from transactions with provider/source,
effective date, ratio or cash terms, review state, and application metadata. Detection
may propose a split, symbol change, merger, spin-off, or cash-in-lieu event. Applying
an action is explicit, idempotent, audited, and produces traceable ledger rows only
after confirmation.

## 5. Delivery sequence

1. **P0 — Trustworthy cash and reconciliation.** Finish current cash in the UI and
   separate snapshot from history.
2. **P1 — Allocation decisions.** Holdings views, targets, rebalancing, and goals.
3. **P2 — Income and price context.** Dividend concentration/quality and moving
   averages.
4. **P3 — Advanced analysis.** Corporate actions, Portfolio Lab, and report export.

**Status (2026-10-10):** P0 cash reconciliation shipped. P1 target allocation (targets, groups, drift) implemented per `docs/superpowers/plans/2026-10-10-portfyl-allocation-targets.md`; rebalancing is next.

Each stage is independently releasable. P1 rebalancing cannot start before targets
are validated. P3 report export cannot start before the preceding API contracts are
stable.

## 6. Cross-cutting acceptance criteria

- All new persistence has Alembic migrations, PostgreSQL RLS coverage, workspace
  ownership tests, cascade behavior, and workspace export/account-deletion coverage.
- New API routes return explicit `source`, `as_of`, and warning fields for derived or
  provider-backed financial data.
- Currency conversion occurs on the server using the existing CZK-pivot helpers.
- Historical analytics remain transaction-ledger based; broker snapshots affect only
  current-value surfaces.
- Every page implements loading, error, empty, and populated states and remains usable
  at 390, 768, 1024, and 1440 CSS pixels.
- Charts include text or table alternatives. Scores include formulas and missing-data
  explanations.
- Local and cloud frontend test/build gates pass. PostgreSQL/RLS tests are mandatory
  for tasks that add tables.

## 7. Explicit non-goals

- Trade execution, broker order submission, or automatic portfolio management.
- Fabricated reconciliation transactions.
- Social profiles, community feeds, public likes/comments, or creator publishing.
- A second screener or second dividend calendar.
- Real-time streaming quotes.
- News-causality claims without a contracted news source and citation model.
- Persisted/shared backtest scenarios in the first Portfolio Lab release.
