# Cash Model v2 — design + implementation plan

Branch: `feat/cash-model`. Status legend: `[ ]` todo, `[x]` done. Update this file as tasks
complete so any session can resume without prior context.

## Goal (user-approved design)

Rebuild cash/interest/deposit/withdrawal handling around the real Trading 212 export
(`portfoliodata.csv` at repo root) and fix the USD/CZK display bug:

1. **One-time CSV import now** of `portfoliodata.csv`; afterwards the user adds
   deposits/withdrawals manually and sets the interest **rate** manually (interest then
   accrues automatically). Any future T212 CSV import **replaces everything** for the
   portfolio (user explicitly chose overwrite semantics — no dedupe needed).
2. **Buys pull their exact CZK total out of the cash pile; sells/dividends/interest/cashback
   push in; withdrawals/fees/card debits pull out.** Cash balance must reconcile with
   Trading 212 to the cent (minus ignored lending interest, ~15 CZK).
3. **Skip "Lending interest" rows completely** (user instruction).
4. **Include card debits + spending cashback** as cash movements (user confirmed).
5. **Fix display currency**: today "USD" display sums native amounts with fx=1.0 (CZK cash
   counted as USD → phantom ~70k). Real conversion native→CZK→display everywhere.
   **Default display currency becomes CZK** (broker-comparable, ~64.6k CZK). USD stays in
   the switcher and must show the true ~$3.1k.
6. Interest accrual (existing lazy engine) starts **the day after the last imported
   `interest` row** per currency, so no double-count; explicit `start_date` overrides.

## portfoliodata.csv facts (verified against the file)

539 rows, 2026-01-19 → 2026-07-08. Header:
`Action,Time,ISIN,Ticker,Name,Notes,ID,No. of shares,Price / share,Currency (Price / share),Exchange rate,Result,Currency (Result),Total,Currency (Total),Withholding tax,Currency (Withholding tax),Currency conversion from amount,...,Currency conversion fee,Currency (Currency conversion fee),Merchant name,Merchant category`

Action counts: Market buy 178, Interest on cash 174, Lending interest 88 (SKIP),
Market sell 56, Dividend (Dividend) 14, Card debit 10, Spending cashback 6, Deposit 6,
Limit sell 3, Withdrawal 2, Currency conversion 1.

Everything settles in CZK (`Currency (Total)` = CZK on every row). Semantics verified:

- **Trade rows** (Market buy/sell, Limit sell): `Price / share` in USD, `Total` in CZK.
  `Exchange rate` = **USD per 1 CZK** (e.g. 0.04818109) → `fx_to_czk = 1 / rate`.
  Buy `Total` INCLUDES the FX fee (cash out = Total). Sell `Total` is NET of fee
  (cash in = Total). Verified: 0.67×83.50 USD / 0.04818109 = 1161.14 + fee 1.74 = 1162.88 ✓;
  sell 22.42 USD / 0.04843064 = 462.93 − 0.69 = 462.24 ✓. So `Total` is always the exact
  cash impact; the separate `Currency conversion fee` column is informational for trades.
- **Dividend rows**: `Price / share` = NET dividend per share in USD (withholding already
  deducted; `Withholding tax` column informational). `Exchange rate` here is **CZK per
  USD** (e.g. 20.9675 — INVERTED convention vs trades!) → `fx_to_czk = rate`.
  `Total` (CZK) = credited cash = shares × price × rate ✓.
- **Deposit / Interest on cash / Spending cashback**: `Total` positive CZK → cash in.
- **Withdrawal / Card debit**: `Total` NEGATIVE CZK (−500.00, −388.00) → cash out.
  Card debit rows carry `Merchant name` / `Merchant category` → put into notes.
- **Currency conversion** (1 row): Notes "5.00 USD -> 104.08 CZK", from-amount 5.00 USD,
  to-amount 104.08 CZK, `Total` = −0.16 CZK (the fee). Parse into 3 rows: `fx_out` USD 5.00,
  `fx_in` CZK 104.08, `fee` CZK 0.16. (Internal transfer — must NOT count as external
  cashflow for returns.)
- **Lending interest**: skip entirely.
- Row `ID` column exists but is unused (replace-mode import, no dedupe).

## Current code map (as of commit 6f30b24)

- `backend/cash_ledger.py` — `TRADE_TYPES = {buy,sell,dividend}`,
  `CASH_TYPES = {deposit,withdrawal,fee,interest}`, `signed_cash(txn)` (trades currently
  return shares×price in TRADE currency — this is the core thing to change),
  `has_external_cashflows`, `cash_balance_by_currency`, `accrued_interest` (lazy,
  straight-line, per-currency, gated on enabled rate; start = cfg.start_date or first event).
- `backend/models.py` — `Transaction` (ticker nullable for cash rows; `amount` used by cash
  rows; `fx_to_czk` snapshot). `CashInterestRate` (portfolio_id, currency, annual_rate,
  enabled, start_date).
- `backend/routers/cash.py` — cash CRUD (`CashCreate` type pattern
  `^(deposit|withdrawal|fee|interest)$`), interest-rates GET/PUT, `/cash/balance`.
- `backend/routers/portfolio.py` — T212 CSV normalisation `_normalize_t212` (currently
  SKIPS deposits/withdrawals/interest via `_T212_SKIP_ACTIONS`), `import_csv` (replace
  param exists, deletes+inserts in one txn), `_build_holdings` (`fx if in_czk else 1.0`
  pattern), `get_holdings` (line ~307), `get_summary` (line ~423; cash gate + fold, the
  `live_fx=1.0` mirror-basis comment), `_live_fx_to_czk`.
- `backend/fx.py` — `fetch_fx_to_czk`, `convert_amount` (native→CZK→display pivot, exists
  and works), `cash_amount_to_display` (the "mirror get_summary basis" HACK — converts only
  when display==CZK, else leaves native; DELETE this behavior), `folded_cash_display`,
  `bulk_fetch_fx`.
- `backend/routers/analytics.py` — `_build_value_cashflow_series` (line ~455): cash-aware
  V/C path gated on `has_external_cashflows`; per-type walk at lines ~524-547 (buy/sell
  append to `cash_txns_to_date`; deposit/withdrawal feed C; fee/interest internal; dividend
  excluded from cash balance because auto_adjust already bakes dividends into V — KEEP that
  exclusion). XIRR path ~line 873-978 (`cash_bal_native` excludes dividends similarly).
  Sector breakdown ~line 1043-1117 uses `folded_cash_display` for the Cash slice.
- `frontend/src/App.jsx` line ~107 — `localStorage.getItem("sb_currency") || "USD"` (change
  fallback to "CZK").
- `frontend/src/pages/Cash.jsx` — ledger + rates UI. `frontend/src/pages/Import.jsx` —
  import page. `frontend/src/api.js` — API helpers (`fetchCash`, `fetchCashBalance`, ...;
  axios interceptor auto-injects portfolio_id — do NOT pass it manually).

## Implementation tasks

### [x] T1. Schema: settlement columns + migration
- `models.py` Transaction: add `cash_amount = Column(Float, nullable=True)` (POSITIVE
  magnitude; direction comes from `type`, consistent with existing `amount` convention)
  and `cash_currency = Column(String, nullable=True)` (settlement ccy, "CZK" for T212).
- `main.py`: idempotent `_ensure_transaction_cash_columns()` (raw `ALTER TABLE ADD COLUMN`
  guarded by PRAGMA table_info check, matching existing `_ensure_*` helpers).
- Note: existing cash rows keep using `amount`; `cash_amount` is for trades/dividends
  (and mirrors `amount` semantics). Decide in code: for cash-type rows `cash_amount` stays
  NULL and `amount` remains authoritative.

### [x] T2. cash_ledger core
- `CASH_TYPES` += `card_debit`, `cashback`, `fx_in`, `fx_out`.
- New frozenset `EXTERNAL_FLOW_TYPES = {deposit, withdrawal, card_debit, cashback}`;
  `has_external_cashflows` checks membership in it.
- `signed_cash`: cash rows — deposit/interest/cashback/fx_in → +amount;
  withdrawal/fee/card_debit/fx_out → −amount. Trades/dividends — if `cash_amount` is not
  None: return (`cash_currency` or "CZK", −cash_amount for buy, +cash_amount for
  sell/dividend); else fall back to current shares×price in trade currency (legacy rows).
- `accrued_interest`: default accrual start per currency = max(cfg.start_date,
  day AFTER the last `type=="interest"` txn in that currency) — if no interest rows,
  behave as today (cfg.start_date or first event).

### [x] T3. T212 importer rework (`_normalize_t212` in routers/portfolio.py)
- Emit trade rows for buy/sell/limit/stop actions: ticker, name, shares, price (USD),
  currency (price ccy), `fx_to_czk = 1/Exchange rate` (fallback to yfinance bulk fetch if
  rate missing), `cash_amount = abs(Total)`, `cash_currency = Currency (Total)`.
- Dividend rows: type `dividend`, shares, price (net/share), `fx_to_czk = Exchange rate`
  (CZK-per-USD convention), `cash_amount = abs(Total)`, `cash_currency`.
- Deposit → `deposit`; Withdrawal → `withdrawal`; Interest on cash → `interest`;
  Card debit → `card_debit` (notes = "Merchant (Category)"); Spending cashback → `cashback`.
  All with `amount = abs(Total)`, currency = `Currency (Total)`, fx_to_czk=1.0 for CZK.
- Currency conversion → up to 3 rows: `fx_out` (from amount/ccy), `fx_in` (to amount/ccy),
  `fee` (abs(Total) if nonzero, ccy of Total).
- Lending interest → skip (count as skipped).
- `import_csv`: when format is T212, force `replace=True` regardless of the param
  (documented in response + Import page copy).
- Keep the Native CSV format path working unchanged.

### [x] T4. Display-currency correctness
- `fx.py`: make `cash_amount_to_display(amount, native, display) = convert_amount(amount,
  native, display)` (kill the CZK-only mirror hack); `folded_cash_display` unchanged
  semantics on top. `convert_amount` already pivots via CZK.
- `routers/portfolio.py`: replace the `in_czk`/fx=1.0 pattern with display conversion:
  - `_build_holdings(..., in_czk)` → take `display_ccy`; per-txn factor =
    (txn.fx_to_czk or live) / live_fx_czk_of(display_ccy) — i.e. native→CZK→display.
    Define ONE helper (e.g. `_display_factor(native_ccy, fx_to_czk_snapshot, display_ccy,
    cache)`) and use it in `_build_holdings`, `get_holdings` (live prices:
    live_fx_to_czk(ticker_ccy)/live_fx_to_czk(display)), `get_summary` (`_txn_fx`),
    closed-position math, movers if applicable.
  - Day-change already derives fx from converted market_value — verify it still holds.
- `analytics.py` sector breakdown Cash slice: works via fixed `folded_cash_display`.
- Grep for remaining `in_czk` / `== "CZK"` display gates across backend and fix
  (`routers/analytics.py`, `routers/benchmarks.py`?, `routers/market.py`?).
- Performance endpoints (`/portfolio/performance`, analytics comparison) — check how they
  convert to display currency; the V/C series is USD-internal, display conversion happens
  where? Verify and fix USD→display step.

### [x] T5. Analytics/returns wiring
- `_build_value_cashflow_series` per-type walk: `card_debit` → C −= amt_usd;
  `cashback` → C += amt_usd; both also append to `cash_txns_to_date`. `fx_in`/`fx_out`
  append only (internal). `fee`/`interest` unchanged. Buys/sells now contribute their
  settlement totals to the running cash balance automatically via new `signed_cash`
  (this makes FX fees drag returns — intended).
- Dividend rows: KEEP excluded from the walked cash balance (auto_adjust double-count),
  even though they now carry `cash_amount`. BUT `cash_balance_by_currency` for the
  /cash/balance endpoint and summary MUST include dividend cash. The exclusion in
  analytics is done by filtering `t.type != "dividend"` before calling
  `cash_balance_by_currency` — preserve those filters (lines ~511, 516, 964).
- XIRR path: same external-flow treatment for card_debit/cashback.

### [x] T6. Cash router + manual trade creation
- `routers/cash.py`: `CashCreate` type pattern extended? Manual entry stays
  deposit/withdrawal/fee/interest (user adds those); listing (`list_cash`) returns ALL
  CASH_TYPES incl. card_debit/cashback/fx_in/fx_out so imported rows show in the ledger.
  Edit/delete work on any cash row.
- `create_transaction` (manual trade): populate `cash_amount = shares×price×fx_to_czk`,
  `cash_currency = "CZK"` so manual trades also move the pile.
- `/cash/balance`: totals now use real conversion (T4) — `by_currency` stays native.

### [x] T7. Frontend
- `App.jsx`: default currency fallback → "CZK" (localStorage `sb_currency`; users with a
  stored "USD" keep it — acceptable, tell user to flip the switcher once).
- `Cash.jsx`: type badges/labels for interest, card_debit ("Card"), cashback, fx_in/fx_out
  ("FX"); per-currency balance + accrued (existing endpoint). Manual add form keeps the
  4 manual types.
- `Import.jsx`: copy stating a T212 import replaces all portfolio data.
- Check `Transactions.jsx` still trade-only (backend already filters).

### [x] T8. Tests (backend/tests/, run `python -m pytest tests/ -v` from backend/ with venv;
pytest NOT in requirements — `uv pip install pytest` if missing; conftest patches os.rename)
- Importer: fixture CSV containing one row of EACH action type copied verbatim from
  portfoliodata.csv (incl. lending interest → assert skipped; currency conversion → 3 rows;
  card debit merchant in notes; withdrawal negative Total → positive amount w/ type).
- Reconciliation: import fixture → `cash_balance_by_currency` CZK equals hand-computed sum.
- signed_cash: trades with cash_amount settle in CZK; legacy trades without fall back.
- accrued_interest: starts day after last interest row; start_date override still wins.
- Display conversion: summary/holdings in USD display ≠ native sums (mock fx).
- Update existing tests broken by signature changes (`test_cash_api`, `test_cash_ledger`,
  `test_portfolio`, `test_analytics`, helpers.py).
- Frontend: `npx vitest run` (Cash.test.jsx, PortfolioHero.test.jsx may need updates).

### [x] T9. End-to-end verification
- `start.bat` (or backend uvicorn :8000 + `npm run dev` :5173), login `snowball-dev`.
- Import real `portfoliodata.csv` (replace), then check: Cash page CZK balance and
  Dashboard net worth ≈ broker (~64.6k CZK; small drift = ignored lending interest +
  accrual estimate), USD view ≈ $3.1k, allocation shows Cash slice, Transactions page
  clean (trades only), performance chart renders.
- DB backups exist at `backend/portfyl.db.bak-preTask*` if anything goes wrong.

### [x] T10. Commit(s) + wrap-up
- Conventional commits per logical unit (schema/ledger, importer, display-fix, frontend,
  tests). Do NOT commit portfoliodata.csv unless user asks (contains real financial data).

## Decisions log (from user, 2026-07-08)

- Import: one-time now + manual entries after; rate manual, interest auto-accrues;
  any future CSV import overwrites everything.
- Card debits/cashback: include as cash movements.
- Interest: auto-accrue from rates after last imported interest row.
- Display: CZK default; USD properly converted.
- Lending interest: ignore completely.
- Known accepted imprecision: conversion-fee inside/outside 104.08 CZK ambiguity (±0.16
  CZK), dividend Total assumed net (verified numerically), lending interest excluded.

## Verification results (2026-07-08, all tasks DONE)

- Backend: 106 pytest passed (17 new in tests/test_t212_import.py). Frontend: 24 vitest passed.
- Imported real portfoliodata.csv into portfolio 1 "zubik" via API: imported=452,
  skipped=88 (exactly the lending-interest rows), replaced=true.
- /cash/balance: CZK 10,737.07 + USD 0.63 — matches an independent hand-computation
  from the CSV to the cent. (USD balance comes from USD-denominated interest rows +
  the 5 USD conversion.)
- /portfolio/summary CZK: net_worth 64,976.71 (positions 54,226.27 + cash 10,750.44)
  ~= broker's ~64.6k. USD view: $3,061.67 (phantom 70k gone); implied rate 21.22 ✓.
- Browser-verified Dashboard (both currencies) and Cash page (badges, signed amounts,
  FX legs, deposits). DB backup taken pre-import: backend/portfyl.db.bak-preCashV2-*.
- Known deferred item: /portfolio/performance daily series still only converts USD->CZK
  (fine while all tickers are USD-priced); noted in T4.
- NOTE: first /holdings call after import can return 0-priced tickers (yfinance batch
  deadline); resolves on retry once the quote cache warms.
