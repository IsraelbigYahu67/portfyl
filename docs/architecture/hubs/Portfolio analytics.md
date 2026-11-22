---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Portfolio analytics

This is the "what do I own and how is it doing" part of Portfyl. It takes the transaction ledger (see [[Broker importers and sync]]) plus live prices (see [[Market data]]) and turns them into holdings, performance, allocation, dividends, cash balances and risk numbers. Everything is scoped to one portfolio at a time, inside one workspace.

Two rules matter when touching this code. Money is normalized to CZK through each transaction's `fx_to_czk` and then converted to the display currency. And yfinance is noisy, so missing data must give an empty or null answer, never an error.

## How it works
- **Ledger first.** [[routers.portfolio]] holds the biggest set of endpoints: transactions (list, page, add, delete), `holdings`, `summary`, `performance`, `dividends` (with `forecast` and `growth`), `earnings`, `movers`, `heatmap`, `benchmarks` and `insider-buys`. The CSV preview, commit and undo endpoints live in the same router (see [[Onboarding and CSV import]]).
- **Ordering and trade types.** [[transaction_ordering]] gives one chronological order for all code that replays the ledger. [[cash_ledger]] separates position types from cash types and does the cash balance and interest maths.
- **CZK normalization.** Each [[transactions (table)]] row has an `fx_to_czk` snapshot. [[fx]] pivots amounts native currency to CZK to display currency, using the rate for the transaction date, and falls back to the unconverted amount when no rate exists. The frontend side is [[lib.displayCurrency]] and [[lib.format]]. Preserve this when you change valuation or performance code.
- **Cash.** [[routers.cash]] stores manual cash rows and interest rates ([[cash_interest_rates (table)]]), returns balance and history, and reconciles against the broker's own cash ([[broker_cash]]). The cash model is described in the 2026-07-04 spec below.
- **Dividends.** The dividends endpoints in [[routers.portfolio]] list received dividends and forecast upcoming ones. [[dividend_growth]] adds per-ticker growth streak, CAGR and payout ratio. Importers store one net dividend per payment (see [[importers.dividends]]). The ex-dividend Discord digest is in [[Alerts and integrations]].
- **Allocation and targets.** [[routers.allocation_targets]] saves a target weight per ticker (replacing the whole set at once) and `GET /api/allocation-targets/drift` compares it with actual weights using [[allocation_targets]] (`validate_target_set`, `compute_drift`). Targets live in [[allocation_targets (table)]].
- **Analytics.** [[routers.analytics]] returns risk metrics, sector breakdown and correlation. These are gated by the `portfolio_analytics` capability (Investor plan or higher, see [[Billing and Stripe]]). Benchmark comparison is in [[routers.benchmarks]].
- **Valuation note.** CLAUDE.md says valuation deliberately uses the 5-year average P/E instead of the current P/E. In the code I read, the fair-value builder in [[routers.market]] multiplies analyst EPS by the stock's current multiple and by the sector median, and the 5-year-average P/E idea appears only in the landing page demo. Treat the CLAUDE.md rule as a methodology intent that is not confirmed in the backend.
- **Edition.** The Tax Report page ([[pages.TaxReport]]) exists only in the local edition and is never part of the cloud build (see [[Edition boundary]]).
- **Frontend.** Pages: [[pages.Dashboard]], [[pages.Allocation]], [[pages.Analytics]], [[pages.Dividends]], [[pages.Cash]], [[pages.Transactions]]. Dashboard pieces: [[components.DashboardGrid]], [[components.PortfolioHero]], [[components.PerformanceChart]], [[components.MetricCard]], [[components.Heatmap]], [[components.dashboard (folder)]]. Allocation pieces: [[components.AllocationChart]], [[components.BreakdownChart]], [[components.AllocationTargets]], [[components.HoldingCards]]. Cash chart: [[components.CashBalanceChart]]. Notes on trades use [[components.TradeNoteModal]]. Chart look and colours come from [[lib.chartTheme]] and the design file `DESIGN.md`.

## Key code
- [[routers.portfolio]]: transactions, holdings, summary, performance, dividends.
- [[routers.analytics]]: risk metrics, sector breakdown, correlation.
- [[routers.cash]]: cash rows, interest, balance, reconciliation.
- [[cash_ledger]]: cash and position type logic, balances and interest.
- [[fx]]: currency conversion through CZK.
- [[dividend_growth]]: dividend growth maths.
- [[allocation_targets]] and [[routers.allocation_targets]]: target weights and drift.
- [[transaction_ordering]]: chronological ordering key.
- [[broker_cash]]: broker cash snapshots.
- [[pages.Dashboard]]: main overview page.
- [[pages.Allocation]]: allocation page.
- [[pages.Analytics]]: risk and benchmark page.
- [[pages.Dividends]]: dividends page.
- [[pages.Cash]]: cash page.
- [[pages.Transactions]]: ledger table.
- [[lib.dashboardSummaries]]: dashboard summary helpers.

## Data
- [[transactions (table)]]: the ledger, with `fx_to_czk`.
- [[portfolios (table)]]: portfolios inside a workspace.
- [[cash_interest_rates (table)]]: interest rates used by the cash model.
- [[allocation_targets (table)]]: target weights.
- [[dividend_notifications (table)]]: which ex-dividend dates were already announced.
- [[trade_notes (table)]]: notes the user attaches to a transaction.
- Migration [[0023_allocation_targets]] added the targets table.

## Related hubs
- [[Market data]]
- [[Broker importers and sync]]
- [[Onboarding and CSV import]]
- [[Alerts and integrations]]
- [[Billing and Stripe]]
- [[Frontend structure]]
- [[Tenancy and RLS]]

## Docs
- [[superpowers/specs/2026-07-04-portfyl-cash-model-design]]: how cash balances and interest are modelled.
- [[superpowers/specs/2026-07-24-dividend-growth-and-overview-design]]: dividend growth and overview design.
- [[superpowers/specs/2026-07-12-fundamentals-change-row-and-positions-pie-design]]: positions pie and fundamentals row.
- [[superpowers/specs/2026-08-01-insider-transactions-weekly-dot-chart-design]]: insider buys chart.
- [[superpowers/plans/ux-06-portfolio-insights-verification]]: verification of portfolio insights.
- [[superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design]]: product coherence across these pages.
