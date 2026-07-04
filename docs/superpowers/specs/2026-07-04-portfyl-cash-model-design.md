# Portfyl Cash / Cash-Flow Model — Design Spec

**Date:** 2026-07-04
**Status:** Approved design (brainstorming) — pending implementation plan
**Feature:** (a) Cash / cash-flow model — the first of four queued features (a cash, c rebalancing, d dividend upgrade, e alerts). Rebalancing (c) is blocked on this.

## Goal

Give Portfyl a **cash balance** so it can show true **net worth** (positions + cash),
surface cash drag, and — later — feed accurate rebalancing and money-weighted
returns. Cash is a *tolerant ledger*: trades move cash automatically, but the app
never panics on incomplete deposit history — it shows a best-effort balance and
flags when it would go negative.

## Decisions locked in brainstorming

1. **Tolerant ledger, not strict reconciliation.** Balance =
   `+deposits +interest +sell proceeds +dividends −withdrawals −fees −buy cost`,
   per currency. Missing deposits degrade gracefully (best-effort balance, negative
   flagged, never an error).
2. **Per-currency cash, blended display.** Each cash row carries a native
   `currency` + `fx_to_czk` (same pattern as trades). Balances are held per currency
   (USD/GBP/EUR/CZK…) and shown blended in the active display currency, with an
   optional per-currency breakdown.
3. **Manual entry first.** No CSV / T212 cash import in v1 — that's a later step over
   the same model. An "opening balance" deposit is enough to start.
4. **Dedicated Cash section** (new nav page), including an **Interest** sub-section
   where the user sets a per-currency annual rate (as T212 offers) so cash accrues
   interest **without any import**.
5. **Data model: extend `Transaction`** (user's choice over a separate table). Cash
   rows live in the same table, discriminated by `type`. Because existing consumers
   iterate `Transaction` assuming `ticker`/`shares`, the design is **defensive**:
   a single `CASH_TYPES`/`TRADE_TYPES` source of truth and an audited guard on every
   consumer so cash rows can never leak into holdings/returns math.
6. **Surfaces in v1:** net worth on Dashboard, cash as an asset-class row in
   Allocation, and deposits/withdrawals wired into money-weighted / Modified-Dietz
   returns (the heaviest, most sensitive piece — gated by a fallback).

## Out of scope (v1)

- CSV / T212 API import of cash events (deposits/withdrawals/interest/fees).
- Daily-compounded interest (v1 uses a straight-line estimate) and per-currency
  **rate history** (v1 = one current rate per currency).
- Reconciling derived interest accrual against later-imported real interest (no
  double-count logic yet — v1 uses either derived accrual OR manual interest rows).
- Cash in the tax report.

---

## 1. Data model — `Transaction` extension

`backend/models.py` — `Transaction`:

- `type` gains `deposit | withdrawal | fee | interest` (existing: `buy | sell | dividend`).
- **New column** `amount = Column(Float, nullable=True)` — the cash amount in the
  row's native `currency`, stored **positive**; direction is carried by `type`.
  Trades keep using `shares * price` and leave `amount` NULL.
- `ticker` becomes **nullable** (cash rows have no ticker). `shares` / `price` are
  NULL for cash rows.
- Reuses existing `currency`, `fx_to_czk`, `date`, `notes`, `source`.

**Discriminators (single source of truth), e.g. in a small `backend/cash.py` or at
the top of `portfolio.py`:**

```python
TRADE_TYPES = {"buy", "sell", "dividend"}
CASH_TYPES  = {"deposit", "withdrawal", "fee", "interest"}
```

**Migration** — idempotent helper in `main.py` following the existing imperative
`_ensure_*` pattern (there is no Alembic):

- Add `amount` column if missing (`ALTER TABLE transactions ADD COLUMN amount FLOAT`).
- Relax `ticker` NOT NULL. SQLite can't drop NOT NULL in place, so use the existing
  table-rebuild approach (create new table, copy, swap) — mirror how other
  `_ensure_*`/`_backfill_*` helpers rebuild tables. If a rebuild is judged too heavy,
  the fallback is a sentinel `ticker = "$CASH"` for cash rows (documented, but the
  nullable rebuild is preferred for cleanliness).

**New table `CashInterestRate`** (for the Interest sub-section):

```
CashInterestRate:
  id            int pk
  portfolio_id  fk -> portfolios (CASCADE), indexed
  currency      str            # "USD" | "GBP" | "EUR" | "CZK" ...
  annual_rate   float          # decimal, e.g. 0.045 for 4.5% APY
  enabled       bool default False
  start_date    date nullable  # accrual starts here; default = first cash event
  created_at    datetime
  # unique (portfolio_id, currency)
```

Its own `_ensure_*` create-table helper at startup.

### Defensive audit (the mitigation for the shared-table choice)

Every current consumer that iterates `Transaction` gets an explicit
`type in TRADE_TYPES` (or `ticker is not None`) guard. Known consumers to audit:

- `portfolio.py`: `_build_holdings`, `get_summary`, `get_movers`, `_two_day_closes`
  callers, `_build_holdings`-derived endpoints.
- `analytics.py`: `_get_transactions` consumers — capital gains (`_compute_capital_gains`,
  `_build_lot_queue`), `_compute_unrealized_gains`, `_build_value_cashflow_series`
  (`held_tickers`), `_lifetime_money_weighted`, sector/country breakdown, correlation.
- Anywhere `total_dividends` / holdings aggregation sums `shares * price`.

A regression test asserts cash rows never change holdings count or holdings value.

---

## 2. Cash balance + interest accrual (pure, tested)

Pure functions (no DB / no network), home e.g. `backend/cash.py`:

### `cash_balance_by_currency(transactions) -> dict[str, float]`

Per currency:

```
+ deposit.amount
+ interest.amount            # manual interest rows
+ sell.shares * sell.price   # proceeds (native)
+ dividend.shares * dividend.price
- withdrawal.amount
- fee.amount
- buy.shares * buy.price     # cost (native)
```

(Dividend cash = `shares * price`, matching the existing valuation at
`portfolio.py:144,430`.) Result is per native currency; negative balances are
allowed and surfaced (tolerant).

### `accrued_interest(events_by_ccy, rates, as_of=today) -> dict[str, float]`

Derived, **no scheduler**. For each currency with an enabled `CashInterestRate`:

1. Build the balance timeline: all cash-affecting events (trades + cash rows) in that
   currency sorted by date; the running balance is piecewise-constant between events.
2. From `max(start_date, first event)` to `as_of`, for each segment where
   `balance > 0`, add `balance * annual_rate * days / 365`.
3. Sum segments → accrued interest to date for that currency.

Straight-line estimate (not daily-compounded). Only positive balances accrue.
Computed lazily on read; never stored. If manual `interest` rows exist, v1 assumes
the user uses *either* derived accrual *or* manual interest for a currency (no
double-count reconciliation — deferred).

### Blended total

`cash_total_display = Σ_ccy (balance_ccy + accrued_ccy) * fx(ccy → display)`.
FX reuses the existing conversion path (live/`fx_to_czk` as elsewhere).

---

## 3. Backend endpoints

Portfolio-scoped (axios auto-injects `portfolio_id`; keep the agnostic-prefix rules).
New router `backend/routers/cash.py` mounted under `/api`, plus additions to
`portfolio.py` and `analytics.py`.

**Cash CRUD** (new `cash` router):
- `GET  /cash` — list cash rows (deposit/withdrawal/fee/interest) for the portfolio.
- `POST /cash` — add a row `{type, amount, currency, date, note}` (fx backfilled like trades).
- `PUT  /cash/{id}` — edit.
- `DELETE /cash/{id}` — delete.
- `GET  /cash/balance` — per-currency balances + accrued interest + blended total.

**Interest settings:**
- `GET /cash/interest-rates` — per-currency `{currency, annual_rate, enabled, start_date}`.
- `PUT /cash/interest-rates` — upsert the set.

**Summary (`portfolio.py:get_summary`)** gains:
- `cash` (blended, display currency),
- `accrued_interest` (blended),
- `net_worth` = `total_value + cash + accrued_interest`.
- Optional `cash_by_currency` breakdown for the Cash page.
(`total_value` / `total_invested` / `total_pnl` semantics stay **unchanged** — cash is
additive on top.)

**Allocation** (`analytics.py` sector/allocation breakdown): add a `Cash` bucket equal
to `cash_total` (blended), as its own slice/row alongside holdings.

**Returns integration (heaviest, gated):**
- Today: `_build_value_cashflow_series` uses V = holdings market value and C derived
  from buy/sell; `_lifetime_money_weighted` builds XIRR flows from buys/sells/dividends.
- New: when cash tracking is **active for the portfolio** (≥1 deposit/withdrawal row),
  external cashflows `C` = **deposits (+) / withdrawals (−)**; buys/sells become
  *internal* (they move value between cash and holdings, not in/out of the account),
  and the value series `V` = holdings market value **+ cash balance** on each date.
- **Fallback:** with no deposit/withdrawal rows, behavior is byte-for-byte the current
  buys/sells-derived one — existing users' return numbers don't change.
- Covered by characterization tests (capture current output, assert fallback identical,
  assert new path with deposits).

---

## 4. Frontend

New **Cash** page + Dashboard/Allocation touch-ups, built on the UX-overhaul primitives
(`Card`, `SectionHeader`, `DeltaPill`, `EmptyState`, `lib/format`).

**Cash page** (`frontend/src/pages/Cash.jsx`, route `/cash`, nav item in `Sidebar.jsx`):
- **Balance card**: blended net cash (display currency) + per-currency breakdown + an
  "Accrued interest (est.)" line. Negative balances shown in loss tone with a hint.
- **Ledger table**: date, type, amount, currency, note; add / edit / delete via a modal
  (reuse `TradeNoteModal`-style pattern). Empty state directs to "Add opening balance".
- **Interest sub-section**: one row per currency with an enabled toggle, an annual-rate
  input (shown as %), and a start date; Save persists to `CashInterestRate`.

**Dashboard** (`PortfolioHero`): headline becomes **net worth** (`summary.net_worth`),
with a split line/chips "Positions `total_value` · Cash `cash`". The existing day-change
pill stays on positions (cash has no day change). Count-up animates net worth.

**Allocation** (`Allocation.jsx` / `AllocationChart.jsx`): render the `Cash` bucket as
its own asset-class slice/row so cash drag is visible.

---

## 5. Testing

- **Pure functions** (pytest, the meat): `cash_balance_by_currency` (per-currency,
  signs, negative tolerance, dividend/sell/buy contributions) and `accrued_interest`
  (segments, start_date, positive-only, rate math, disabled currency).
- **Leak guard**: a test that adding cash rows leaves holdings count / holdings value
  unchanged (verifies the defensive audit).
- **Returns**: characterization tests — current output captured; fallback identical
  with no cash; new external-cashflow path with deposits.
- **Frontend**: render smoke for `Cash.jsx` (mounts, shows balance card + ledger +
  interest section) using the existing Vitest harness.

---

## Open verification points for the plan (not blockers)

- Confirm dividend rows always store cash as `shares * price` in every path (assumed
  from `portfolio.py:144,430`).
- Confirm the exact set of `Transaction`-iterating consumers during the audit (grep
  `\.type ==` / `for t in transactions`); the list in §1 is the known set.
- Decide table-rebuild vs `$CASH` sentinel for the `ticker` NOT NULL relaxation during
  the plan, based on how invasive the rebuild helper is.
