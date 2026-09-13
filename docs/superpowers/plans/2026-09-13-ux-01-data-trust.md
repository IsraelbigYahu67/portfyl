# UX Plan 1: Data Trust — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dividend estimates provenance-aware and deterministic, eliminate misleading tiny FIFO rows, and centralize the precision rules the rest of the UX program consumes.

**Architecture:** Add pure dividend-normalization and tax-row serialization helpers around the existing endpoints; keep the dividend array response and tax endpoint shape compatible. Extend the existing formatting module rather than introducing page-local formatters, then update Dividends and Tax Report to expose uncertainty instead of presenting it as fact.

**Tech Stack:** FastAPI, SQLAlchemy, yfinance adapter, pytest, React 18, TanStack Query, Vitest/Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md` (§4.1, §7.4, §8)

## Global Constraints

- Existing response fields remain for one compatibility cycle; dividend rows gain only additive provenance/status fields and the the first implementation retains the array response.
- `date_status` is exactly `complete | ex_date_only | pay_date_only | unavailable | inconsistent`; `income_status` is exactly `estimated | unavailable | review`.
- Warning strings are exactly `pay_date_before_ex_date`, `non_positive_rate`, `implausible_implied_yield`, and `provider_fields_disagree`.
- Implied yield above 35% is review-only. Provider/implied yields disagree only when their absolute gap exceeds five percentage points and their relative gap exceeds 50% of the smaller positive value.
- `as_of` is created once per dividend endpoint response and all returned rows share it. Source is `yahoo_finance`.
- FIFO uses `LOT_EPSILON = 1e-8`; quantities serialize to eight decimals, monetary lot values to six, and `gain_pct` is null when `abs(cost_basis) < 0.005`.
- Summary arithmetic uses unrounded internal values and rounds only at the response boundary. Trade-date FX remains authoritative.
- New financial/date formatting lives in `frontend/src/lib/format.js`; CZK uses `cs-CZ`, USD uses `en-US`, and tiny non-zero money never renders as exact zero.
- No schema migration, new vendor, tax-law change, response envelope, or live-FX substitution is in scope.
- Work on `codex/ux-01-data-trust`, based on current `codex/portfyl-ux-overhaul`; merge back there, never to `main`.

Run before editing:

```powershell
$branch = (git branch --show-current).Trim()
if ($branch -eq 'main') { throw 'Refusing to work on main' }
git status --short
```

## File Structure

- Modify `frontend/src/lib/format.js` and `.test.js`: locale, quantity, long-date, and sub-cent rules.
- Modify `backend/routers/portfolio.py`; add `backend/tests/test_dividend_trust.py`: pure row normalization and endpoint timestamp wiring.
- Modify `frontend/src/pages/Dividends.jsx`; add `Dividends.trust.test.jsx`: honest estimate/date grouping and provenance disclosure.
- Modify `backend/routers/analytics.py` and `backend/tests/test_analytics.py`: FIFO epsilon, precision, and reconciliation.
- Modify `frontend/src/pages/TaxReport.jsx`; add `TaxReport.precision.test.jsx`: shared formatting, null percentages, and CSV precision.

---

## Task 1: Shared financial/date formatting contract

**Files:**
- Modify: `frontend/src/lib/format.js`
- Modify: `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces: `formatMoney(value, currency)`, `formatQuantity(value)`, `formatShortDate(iso)`, `formatLongDate(iso)`, and existing `formatPercent`; later plans import these names unchanged.

- [ ] **Step 1: Add failing tests**

Append cases that assert the exact boundary behavior:

```js
import { formatLongDate, formatQuantity } from "./format";

it("uses the currency locale and exposes non-zero sub-cent values", () => {
  expect(formatMoney(1234.5, "USD")).toBe("$1,234.50");
  expect(formatMoney(1234.5, "CZK")).toMatch(/^1[\s\u00a0]234,50\sKč$/);
  expect(formatMoney(0.004, "USD")).toBe("<$0.01");
  expect(formatMoney(-0.004, "USD")).toBe(">-$0.01");
  expect(formatMoney(0.004, "CZK")).toBe("<0,01 Kč");
  expect(formatMoney(-0.004, "CZK")).toBe(">-0,01 Kč");
});

it("formats quantities with at most eight decimals and no trailing zeroes", () => {
  expect(formatQuantity(1)).toBe("1");
  expect(formatQuantity(0.00000001)).toBe("0.00000001");
  expect(formatQuantity(1.23000000)).toBe("1.23");
});

it("formats date-only values without a timezone shift", () => {
  expect(formatLongDate("2026-09-13")).toMatch(/September 13, 2026/);
  expect(formatLongDate(null)).toBe("—");
});
```

- [ ] **Step 2: Prove the tests fail**

Run: `cd frontend && npm test -- format.test.js`

Expected: missing `formatQuantity`/`formatLongDate`, old CZK grouping, and exact-zero rendering for sub-cent values.

- [ ] **Step 3: Implement the shared helpers**

Use `Intl.NumberFormat` with this exact locale mapping and sub-cent branch:

```js
const LOCALE_BY_CURRENCY = { CZK: "cs-CZ", USD: "en-US" };

export function formatMoney(value, currency = "USD") {
  if (value == null || !Number.isFinite(Number(value))) return DASH;
  const n = Number(value);
  const code = currency === "GBp" || currency === "GBX" ? currency : String(currency || "USD").toUpperCase();
  const threshold = 0.01;
  if (n !== 0 && Math.abs(n) < threshold) {
    if (code === "CZK") return n > 0 ? "<0,01 Kč" : ">-0,01 Kč";
    const { prefix = "", suffix = "" } = currencyParts(code);
    return n > 0 ? `<${prefix}0.01${suffix}` : `>-${prefix}0.01${suffix}`;
  }
  if (code === "GBp" || code === "GBX") {
    return `${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} p`;
  }
  try {
    return new Intl.NumberFormat(LOCALE_BY_CURRENCY[code] || "en-US", {
      style: "currency", currency: code, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
  }
}

export function formatQuantity(value) {
  if (value == null || !Number.isFinite(Number(value))) return DASH;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 8, useGrouping: true }).format(Number(value));
}

export function formatLongDate(iso) {
  return formatShortDate(iso, { year: "numeric", month: "long", day: "numeric" });
}
```

Keep `currencyParts`, `formatPercent`, `formatCompact`, `formatNumber`, and the spaced-format exports compatible. Update old CZK assertions to the new locale-aware output.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- format.test.js`

```powershell
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(format): centralize locale and sub-cent financial formatting"
```

## Task 2: Pure dividend normalization rules

**Files:**
- Modify: `backend/routers/portfolio.py`
- Create: `backend/tests/test_dividend_trust.py`

**Interfaces:**
- Produces: `_normalize_dividend_row(*, ticker, name, shares, currency, dividend_rate, provider_yield, price, ex_date, pay_date, as_of) -> dict | None`.

- [ ] **Step 1: Write table-driven failing tests**

```python
from routers.portfolio import _normalize_dividend_row

BASE = dict(ticker="MSFT", name="Microsoft", shares=10.5, currency="USD",
            dividend_rate=3.32, provider_yield=0.72, price=460,
            ex_date="2026-08-20", pay_date="2026-09-10",
            as_of="2026-09-13T10:30:00Z")

def row(**patch):
    return _normalize_dividend_row(**(BASE | patch))

def test_valid_row_is_estimated_and_complete():
    out = row()
    assert out["date_status"] == "complete"
    assert out["income_status"] == "estimated"
    assert out["annual_income"] == 34.86
    assert out["warnings"] == []

def test_payment_before_ex_date_is_sanitized():
    out = row(pay_date="2026-08-01")
    assert out["pay_date"] is None
    assert out["date_status"] == "inconsistent"
    assert "pay_date_before_ex_date" in out["warnings"]

@pytest.mark.parametrize("rate", [None, 0, -1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_rate_is_unavailable(rate):
    out = row(dividend_rate=rate, provider_yield=None)
    assert out["annual_income"] is None
    assert out["income_status"] == "unavailable"

def test_implied_yield_above_35_percent_requires_review():
    out = row(dividend_rate=40, price=100, provider_yield=None)
    assert out["annual_income"] is None
    assert out["income_status"] == "review"
    assert "implausible_implied_yield" in out["warnings"]

def test_provider_disagreement_requires_both_thresholds():
    out = row(dividend_rate=10, price=100, provider_yield=2)
    assert out["income_status"] == "review"
    assert "provider_fields_disagree" in out["warnings"]

def test_provenance_is_additive():
    out = row()
    assert out["source"] == "yahoo_finance"
    assert out["as_of"] == BASE["as_of"]
```

Import `pytest`. Add date-status cases for ex-only, pay-only, neither, and complete.

- [ ] **Step 2: Prove the tests fail**

Run: `cd backend && python -m pytest tests/test_dividend_trust.py -v`

Expected: import failure for `_normalize_dividend_row`.

- [ ] **Step 3: Implement the helper**

Add `math.isfinite`, parse ISO dates with `date.fromisoformat`, and use percentage units consistently (`0.72` means 0.72%, matching the response contract):

```python
def _positive_finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None

def _normalize_dividend_row(*, ticker, name, shares, currency, dividend_rate,
                            provider_yield, price, ex_date, pay_date, as_of):
    rate = _positive_finite(dividend_rate)
    quoted_yield = _positive_finite(provider_yield)
    market_price = _positive_finite(price)
    warnings = []
    if ex_date and pay_date and date.fromisoformat(pay_date) < date.fromisoformat(ex_date):
        pay_date = None
        date_status = "inconsistent"
        warnings.append("pay_date_before_ex_date")
    elif ex_date and pay_date:
        date_status = "complete"
    elif ex_date:
        date_status = "ex_date_only"
    elif pay_date:
        date_status = "pay_date_only"
    else:
        date_status = "unavailable"

    income_status = "estimated" if rate else "unavailable"
    implied_yield = rate / market_price * 100 if rate and market_price else None
    if rate is None and dividend_rate is not None:
        warnings.append("non_positive_rate")
    if implied_yield is not None and implied_yield > 35:
        income_status = "review"
        warnings.append("implausible_implied_yield")
    if implied_yield and quoted_yield:
        gap = abs(implied_yield - quoted_yield)
        if gap > 5 and gap / min(implied_yield, quoted_yield) > 0.5:
            income_status = "review"
            warnings.append("provider_fields_disagree")
    annual_income = shares * rate if rate and income_status == "estimated" else None
    return {
        "ticker": ticker, "name": name, "shares": round(float(shares), 8),
        "currency": currency, "dividend_rate": round(rate, 4) if rate else None,
        "dividend_yield": round(quoted_yield, 2) if quoted_yield else None,
        "annual_income": round(annual_income, 2) if annual_income is not None else None,
        "ex_date": ex_date, "pay_date": pay_date, "date_status": date_status,
        "income_status": income_status, "warnings": warnings,
        "source": "yahoo_finance", "as_of": as_of,
    }
```

- [ ] **Step 4: Verify and commit**

Run: `cd backend && python -m pytest tests/test_dividend_trust.py -v`

```powershell
git add backend/routers/portfolio.py backend/tests/test_dividend_trust.py
git commit -m "feat(dividends): add deterministic provenance and validation rules"
```

## Task 3: Wire normalization into the dividends endpoint

**Files:**
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/tests/test_dividend_trust.py`

**Interfaces:**
- Consumes: `_normalize_dividend_row` from Task 2.
- Produces: compatible `GET /portfolio/dividends` array with additive trust fields.

- [ ] **Step 1: Add a failing endpoint test**

Seed one buy, monkeypatch `market_data.get_infos`, `market_data.get_info`, and `_pay_date_from_calendar`, then assert:

```python
def test_endpoint_uses_one_timestamp_and_excludes_review_income_from_rows(
    db_session, pid, default_portfolio, monkeypatch
):
    db_session.add(make_txn("SAFE", "buy", 10, 100, portfolio_id=pid))
    db_session.add(make_txn("RISK", "buy", 10, 100, portfolio_id=pid))
    db_session.commit()
    infos = {
        "SAFE": {"dividendRate": 2, "dividendYield": 2, "regularMarketPrice": 100,
                 "currency": "USD", "exDividendDate": 1787184000, "dividendDate": 1788998400},
        "RISK": {"dividendRate": 40, "dividendYield": 40, "regularMarketPrice": 100,
                 "currency": "USD"},
    }
    monkeypatch.setattr(portfolio.market_data, "get_infos", lambda _: infos)
    monkeypatch.setattr(portfolio.market_data, "get_info", lambda ticker: infos[ticker])
    monkeypatch.setattr(portfolio, "_pay_date_from_calendar", lambda _: None)
    rows = portfolio.get_dividends(db=db_session, portfolio=default_portfolio)
    assert len({r["as_of"] for r in rows}) == 1
    assert next(r for r in rows if r["ticker"] == "RISK")["annual_income"] is None
```

- [ ] **Step 2: Prove it fails**

Run: `cd backend && python -m pytest tests/test_dividend_trust.py -v`

Expected: old rows have no `as_of` and implausible income remains numeric.

- [ ] **Step 3: Replace row construction**

At the start of `get_dividends`, create one timestamp:

```python
as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

Use the already batched `infos = market_data.get_infos(...)` result instead of warming and re-fetching, pass `currentPrice or regularMarketPrice` to the helper, and append normalized rows whenever either provider rate or provider yield is present. Preserve current exception isolation and sorting. Do not add an envelope.

- [ ] **Step 4: Run endpoint and compatibility tests**

Run: `cd backend && python -m pytest tests/test_dividend_trust.py tests/test_portfolio.py -v`

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/portfolio.py backend/tests/test_dividend_trust.py
git commit -m "feat(api): expose validated dividend estimates with shared provenance"
```

## Task 4: Dividends page trust presentation

**Files:**
- Modify: `frontend/src/pages/Dividends.jsx`
- Create: `frontend/src/pages/Dividends.trust.test.jsx`

**Interfaces:**
- Consumes: Task 3 dividend fields and Task 1 formatters.

- [ ] **Step 1: Write failing UI tests**

Mock `fetchDividends`, `fetchDividendForecast`, and `fetchDividendGrowth`. Render with QueryClientProvider and assert:

```jsx
it("does not call inconsistent or undated events upcoming", async () => {
  fetchDividends.mockResolvedValue([
    dividend({ ticker: "BAD", date_status: "inconsistent", ex_date: "2026-10-01", pay_date: null }),
    dividend({ ticker: "OK", date_status: "complete", ex_date: "2099-10-01" }),
  ]);
  renderPage();
  expect(await screen.findByRole("heading", { name: /known upcoming dates/i })).toBeInTheDocument();
  expect(screen.getByText("OK").closest("section")).toHaveTextContent(/upcoming/i);
  expect(screen.getByText("BAD").closest("section")).toHaveTextContent(/needs review/i);
});

it("shows review instead of suspect annual income and names provenance", async () => {
  fetchDividends.mockResolvedValue([dividend({ ticker: "RISK", income_status: "review", annual_income: null,
    warnings: ["implausible_implied_yield"], as_of: "2026-09-13T10:30:00Z" })]);
  renderPage();
  expect(await screen.findByText(/review estimate/i)).toBeInTheDocument();
  expect(screen.getByText(/Yahoo Finance/i)).toBeInTheDocument();
  expect(screen.getByText(/not guaranteed payments/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Prove the tests fail**

Run: `cd frontend && npm test -- Dividends.trust.test.jsx`

- [ ] **Step 3: Implement the grouping and disclosure**

Define `isKnownUpcoming(row, today)` as `row.date_status !== "inconsistent" && row.ex_date && row.ex_date >= today`. Build `knownUpcoming`, `past`, and `needsReview` arrays without overlap. Sum only `income_status === "estimated" && annual_income != null` rows. Rename the total to **Estimated annual income**. In the table render `Review estimate` plus a warning icon for `income_status === "review"`, and `Unavailable` for unavailable values.

Add one disclosure after the total:

```jsx
<details className="text-xs text-muted">
  <summary>Estimate source and freshness</summary>
  <p className="mt-2">
    Estimates come from Yahoo Finance and are not guaranteed payments.
    {latestAsOf && <> Data retrieved {new Date(latestAsOf).toLocaleString()}.</>}
  </p>
</details>
```

Use `formatMoney`, `formatQuantity`, and `formatShortDate`; remove local date/money formatting in changed rows.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- Dividends.trust.test.jsx Dividends.growth.test.jsx format.test.js`

```powershell
git add frontend/src/pages/Dividends.jsx frontend/src/pages/Dividends.trust.test.jsx
git commit -m "feat(dividends): separate known dates from estimates needing review"
```

## Task 5: FIFO epsilon and precise realized/unrealized serialization

**Files:**
- Modify: `backend/routers/analytics.py`
- Modify: `backend/tests/test_analytics.py`

**Interfaces:**
- Produces: `LOT_EPSILON = 1e-8`; `_consume_fifo` never returns a match at or below it; tax rows follow the eight/six/null precision contract.

- [ ] **Step 1: Add failing precision tests**

```python
from routers.analytics import LOT_EPSILON, _consume_fifo

def test_consume_fifo_clamps_residuals_at_epsilon():
    lots = [{"remaining": 1.0, "shares": 1.0, "price": 10.0}]
    matched = _consume_fifo(lots, 1.0 - LOT_EPSILON / 2)
    assert lots[0]["remaining"] == 0.0
    assert matched[0][1] == pytest.approx(1.0 - LOT_EPSILON / 2)

def test_consume_fifo_does_not_emit_dust_match():
    lots = [{"remaining": LOT_EPSILON / 2, "shares": 1.0, "price": 10.0}]
    assert _consume_fifo(lots, 1) == []

def test_realized_row_precision_and_tiny_basis_percentage():
    txns = [
        make_txn("DUST", "buy", 0.00000002, 100, date=date(2024, 1, 1), fx_to_czk=20),
        make_txn("DUST", "sell", 0.00000002, 200, date=date(2024, 2, 1), fx_to_czk=20),
    ]
    row = _compute_capital_gains(txns)[0]
    assert row["shares"] == 0.00000002
    assert row["cost_basis"] == 0.000002
    assert row["proceeds"] == 0.000004
    assert row["gain"] == 0.000002
    assert row["gain_pct"] is None
```

Add a multi-lot and split-adjusted case asserting detailed unrounded values reconcile with `tax_report(...)["summary"]` to one cent, plus missing-FX assertions that remain null/incomplete.

- [ ] **Step 2: Prove the tests fail**

Run: `cd backend && python -m pytest tests/test_analytics.py -v`

- [ ] **Step 3: Implement clamping and response-boundary rounding**

```python
LOT_EPSILON = 1e-8

def _consume_fifo(ticker_lots, shares):
    matched = []
    remaining = float(shares or 0.0)
    if abs(remaining) <= LOT_EPSILON:
        return matched
    for lot in ticker_lots:
        if remaining <= LOT_EPSILON:
            break
        if lot["remaining"] <= LOT_EPSILON:
            lot["remaining"] = 0.0
            continue
        sold = min(remaining, lot["remaining"])
        if sold <= LOT_EPSILON:
            continue
        lot["remaining"] -= sold
        remaining -= sold
        if abs(lot["remaining"]) <= LOT_EPSILON:
            lot["remaining"] = 0.0
        if abs(remaining) <= LOT_EPSILON:
            remaining = 0.0
        matched.append((lot, sold))
    return matched
```

Keep raw `cost_basis`, `proceeds`, and `gain` variables for summary accumulation. Serialize realized and unrealized row quantities with `round(..., 8)`, monetary values with `round(..., 6)`, and percentages with:

```python
gain_pct = None if abs(cost_basis) < 0.005 else round(gain / cost_basis * 100, 2)
```

Change open-lot checks from `> 0` to `> LOT_EPSILON`. Round only the final summary fields to two decimals.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && python -m pytest tests/test_analytics.py -v`

```powershell
git add backend/routers/analytics.py backend/tests/test_analytics.py
git commit -m "fix(tax): clamp FIFO dust and preserve lot precision"
```

## Task 6: Tax Report precision, accessible null percentages, and CSV parity

**Files:**
- Modify: `frontend/src/pages/TaxReport.jsx`
- Create: `frontend/src/pages/TaxReport.precision.test.jsx`

**Interfaces:**
- Consumes: Task 1 formatters and Task 5 response precision.

- [ ] **Step 1: Write failing tests**

Mock `fetchTaxReport` with a realized row containing `shares: 0.00000002`, `cost_basis: 0.000002`, `proceeds: 0.000004`, `gain: 0.000002`, and `gain_pct: null`. Assert the row contains `0.00000002`, `<$0.01`, and an em dash whose title is exactly `Percentage is not meaningful for a basis below one cent.`. Spy on `URL.createObjectURL` and assert exported CSV contains the six/eight-decimal serialized values and an empty percentage cell rather than `null%`.

- [ ] **Step 2: Prove the tests fail**

Run: `cd frontend && npm test -- TaxReport.precision.test.jsx`

- [ ] **Step 3: Replace changed-cell formatters and CSV interpolation**

```jsx
const GainPercent = ({ value }) => value == null ? (
  <span title="Percentage is not meaningful for a basis below one cent." aria-label="Percentage is not meaningful for a basis below one cent.">—</span>
) : formatPercent(value, { sign: false });
```

Use `formatQuantity`, `formatMoney`, `formatShortDate`, and `GainPercent` in realized and unrealized rows. In CSV rows use `g.gain_pct == null ? "" : g.gain_pct` and raw serialized API values; do not recalculate or substitute current FX.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- TaxReport.precision.test.jsx format.test.js`

```powershell
git add frontend/src/pages/TaxReport.jsx frontend/src/pages/TaxReport.precision.test.jsx
git commit -m "fix(tax-report): render and export precise tiny lots honestly"
```

## Task 7: Phase verification and browser evidence

**Files:**
- Create: `docs/superpowers/plans/ux-01-data-trust-verification.md`

- [ ] **Step 1: Run complete gates**

```powershell
cd backend
python -m pytest tests/ -v --ignore=tests/postgres
cd ..\frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

Expected: all green. This phase does not change schema/RLS; PostgreSQL remains CI-mandatory but need not run locally.

- [ ] **Step 2: Browser matrix**

At 390×844, 768×1024, 1024×768, and 1440×900 verify Dividends valid/review/unavailable states and Tax Report tiny/null-percent rows; force a dividends request failure and confirm it is not presented as a legitimate empty list. Check keyboard focus, horizontal overflow, console errors, and failed requests.

- [ ] **Step 3: Record and commit evidence**

The verification document records commands, exit codes, viewport results, CI-only PostgreSQL note, warnings, and deferrals.

```powershell
git add docs/superpowers/plans/ux-01-data-trust-verification.md
git commit -m "docs(ux): record data-trust phase verification"
```

## Self-review notes

- Spec §7.4 maps to Task 1; §8.1 to Tasks 2–4; §8.2 to Tasks 5–6.
- The response envelope, vendor replacement, new tax rules, and legal claims remain excluded.
- Cross-task names are stable: `formatQuantity`, `formatLongDate`, `LOT_EPSILON`, and `_normalize_dividend_row` have one definition and one meaning.
