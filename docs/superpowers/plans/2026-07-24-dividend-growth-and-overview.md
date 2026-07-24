# Dividend-growth, cross-portfolio Overview & calendar-removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dead forward dividend-calendar, add a cross-portfolio Overview page (total net worth + combined allocation), and add dividend-growth analytics (streak / CAGR / YoY / payout-ratio table + per-share history chart).

**Architecture:** Three independent slices over existing data + yfinance, no schema changes. A new leaf module `dividend_growth.py` computes per-ticker growth stats (cached). Two new read endpoints surface it. Overview reuses `get_summary` per-portfolio and a newly-extracted `_allocation_totals` helper, summing raw values before weighting. Calendar removal relocates one shared helper into `jobs.py` and deletes the router.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, yfinance, pandas — backend. React 18 + Vite, recharts, @tanstack/react-query, vitest + @testing-library — frontend.

## Global Constraints

- **Branch:** `feat/dividend-growth-and-overview` (already checked out; the frontend calendar-page deletion is already staged in the working tree here).
- **All API routes are mounted under `/api`** in `main.py`. Router files omit the `/api` prefix.
- **Portfolio scoping is implicit** via the axios interceptor. `/portfolios`, `/market`, `/watchlists`, `/settings` are in `PORTFOLIO_AGNOSTIC_PREFIXES` and must NOT receive `portfolio_id`. The Overview endpoint lives under `/portfolios` deliberately so it stays cross-portfolio.
- **Money is CZK-default at portfolio level; per-share amounts stay native** — do NOT convert per-share dividend amounts to CZK.
- **`owner_id` is always `"default"`** — untouched here.
- **No Alembic; no schema changes in this plan.**
- **Backend tests** call router/helper functions directly against an in-memory SQLite session (`tests/helpers.py` / `tests/conftest.py`), never `TestClient`. Run from `backend/`: `python -m pytest tests/ -v`. pytest is not in `requirements.txt` — assume it is already installed in the venv.
- **Frontend tests**: vitest + jsdom, mock `../api`, render inside `QueryClientProvider`. Run from `frontend/`: `npm run test`. Build check: `npm run build`.
- **yfinance is noisy**: thin/non-paying tickers must yield well-formed empty/null results, never exceptions.

---

## Phase 1 — Remove the forward dividend calendar

### Task 1: Relocate the shared helper and delete the calendar router

The frontend page/route/api-call/nav-link are already removed (uncommitted on this branch). This task removes the backend router while preserving `_next_dividend_info`, which `jobs.py` uses for Discord ex-date notifications.

**Files:**
- Modify: `backend/jobs.py` (add `_next_dividend_info` + its imports; drop the lazy import of it)
- Delete: `backend/routers/dividend_calendar.py`
- Modify: `backend/main.py` (drop the import + `include_router`)
- Modify: `backend/tests/test_jobs.py` (re-point patch targets to `jobs._next_dividend_info`)
- Delete: `backend/tests/test_dividend_calendar.py`

**Interfaces:**
- Produces: `jobs._next_dividend_info(symbol: str) -> dict` with keys `ticker, ex_date, pay_date, amount_per_share, frequency, trailing_yield_pct, dividend_rate_annual` (identical shape to today).

- [ ] **Step 1: Add `_next_dividend_info` to `jobs.py`.** Open `backend/routers/dividend_calendar.py`, copy the entire `_next_dividend_info` function body (lines 30–146) verbatim into `backend/jobs.py`, placing it just above the `# -------- Dividend ex-date notifications` banner (line ~233). Add the imports it needs to the top of `jobs.py` if not already present:

```python
from datetime import date, timedelta   # `date` is already imported; add timedelta
import pandas as pd
import yfinance as yf
from ticker_map import yf_symbol
```

(Keep `_next_dividend_info` as a module-level private function. Do not change its logic.)

- [ ] **Step 2: Point `_upcoming_dividends` at the local helper.** In `backend/jobs.py`, inside `_upcoming_dividends`, delete the lazy import line `from routers.dividend_calendar import _next_dividend_info` (leave `from routers.portfolio import _build_holdings`). The bare call `_next_dividend_info(...)` now resolves to the module-level function.

- [ ] **Step 3: Delete the router file.**

```bash
git rm backend/routers/dividend_calendar.py
```

- [ ] **Step 4: Deregister the router in `main.py`.** Edit `backend/main.py`:
  - On the `from routers import …` line (~line 18), remove `dividend_calendar,` from the list.
  - Delete the line `app.include_router(dividend_calendar.router, prefix="/api")` (~line 439).

- [ ] **Step 5: Re-point the job tests.** In `backend/tests/test_jobs.py`, replace every `patch("routers.dividend_calendar._next_dividend_info", …)` with `patch("jobs._next_dividend_info", …)`. There are 9 occurrences (lines ~191, 209, 225, 231, 241, 263, 275, 282, 293 — replace all). The docstring in `_div_info` ("Stand-in for _next_dividend_info") stays.

```bash
# sanity: no stale references remain anywhere
grep -rn "routers.dividend_calendar\|import dividend_calendar\|dividend_calendar.router" backend/ && echo "STILL REFERENCED" || echo "clean"
```

Expected: `clean`.

- [ ] **Step 6: Delete the obsolete calendar test module.**

```bash
git rm backend/tests/test_dividend_calendar.py
```

(Its `_next_dividend_info` structure test is superseded — `test_jobs.py` already exercises the helper end-to-end through `dividend_exdate_pass`.)

- [ ] **Step 7: Run the backend suite.**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS, all modules green (notably `test_jobs.py`). No import errors for a missing `dividend_calendar`.

- [ ] **Step 8: Commit.**

```bash
git add -A
git commit -m "refactor(dividends): remove dead forward calendar, keep the Discord ex-date helper

Relocates _next_dividend_info into jobs.py (its only real consumer) and deletes
the unreachable /analytics/dividend-calendar router. Frontend page/route/nav were
already removed on this branch.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 2 — Dividend-growth analytics

### Task 2: `dividend_growth.py` core computation

**Files:**
- Create: `backend/dividend_growth.py`
- Create: `backend/tests/test_dividend_growth.py`

**Interfaces:**
- Produces: `dividend_growth.compute_dividend_growth(symbol: str) -> dict` with keys:
  `ticker: str`, `streak_years: int`, `cagr_pct: float|None`, `cagr_years_used: int`,
  `yoy_pct: float|None`, `payout_ratio_pct: float|None`,
  `annual: list[{"year": int, "dps": float}]` (ascending),
  `payments: list[{"ex_date": str ISO, "amount": float}]` (ascending by date).
  Non-payers / errors return the same shape with `annual == []` and `payments == []`.
- Note: this is a **leaf module** — it must NOT import from `routers.*` (avoids a cycle, since `routers/market.py` and `routers/portfolio.py` import it). Payout-ratio normalization is inlined here on purpose rather than importing `routers.market._to_pct`.

- [ ] **Step 1: Write the failing tests.** Create `backend/tests/test_dividend_growth.py`:

```python
"""Tests for compute_dividend_growth (yfinance mocked, cache cleared per test)."""

from __future__ import annotations

import pandas as pd
import pytest

from cache import cache_clear
import dividend_growth


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_clear()
    yield
    cache_clear()


def _patch_ticker(monkeypatch, series: pd.Series, info: dict | None = None):
    class _Tk:
        def __init__(self, symbol):
            self.symbol = symbol
        @property
        def dividends(self):
            return series
        @property
        def info(self):
            return info or {}
    monkeypatch.setattr(dividend_growth.yf, "Ticker", _Tk)


def _series(pairs):
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([a for _, a in pairs], index=idx)


def test_rising_series_streak_cagr_yoy(monkeypatch):
    # 2019..2023, strictly rising annual DPS -> 4 consecutive increases.
    s = _series([("2019-06-01", 1.0), ("2020-06-01", 1.1), ("2021-06-01", 1.2),
                 ("2022-06-01", 1.3), ("2023-06-01", 1.4)])
    _patch_ticker(monkeypatch, s, {"payoutRatio": 0.42})
    # current year is well past 2023 in this project's timeline
    g = dividend_growth.compute_dividend_growth("RISE", _current_year=2026)
    assert g["streak_years"] == 4
    assert g["cagr_years_used"] == 4
    assert g["cagr_pct"] == pytest.approx(8.78, abs=0.05)   # (1.4/1.0)**(1/4)-1
    assert g["yoy_pct"] == pytest.approx(7.69, abs=0.05)    # 1.4/1.3-1
    assert g["payout_ratio_pct"] == 42.0
    assert [a["year"] for a in g["annual"]] == [2019, 2020, 2021, 2022, 2023]
    assert len(g["payments"]) == 5


def test_cut_breaks_streak(monkeypatch):
    s = _series([("2019-06-01", 1.0), ("2020-06-01", 1.1), ("2021-06-01", 1.2),
                 ("2022-06-01", 1.1), ("2023-06-01", 1.3)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("CUT", _current_year=2026)
    # From 2023 back: 2023>2022 (+1), 2022<2021 -> stop.
    assert g["streak_years"] == 1


def test_short_history_reports_years_used(monkeypatch):
    s = _series([("2022-06-01", 1.0), ("2023-06-01", 1.1)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("SHORT", _current_year=2026)
    assert g["cagr_years_used"] == 1
    assert g["cagr_pct"] == pytest.approx(10.0, abs=0.01)


def test_quarterly_payments_aggregate_by_year(monkeypatch):
    s = _series([("2022-03-01", 0.25), ("2022-06-01", 0.25), ("2022-09-01", 0.25),
                 ("2022-12-01", 0.25), ("2023-03-01", 0.30), ("2023-06-01", 0.30),
                 ("2023-09-01", 0.30), ("2023-12-01", 0.30)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("QTR", _current_year=2026)
    annual = {a["year"]: a["dps"] for a in g["annual"]}
    assert annual[2022] == pytest.approx(1.0)
    assert annual[2023] == pytest.approx(1.2)
    assert g["yoy_pct"] == pytest.approx(20.0, abs=0.01)


def test_empty_history_is_wellformed(monkeypatch):
    _patch_ticker(monkeypatch, pd.Series(dtype=float), {})
    g = dividend_growth.compute_dividend_growth("NONE", _current_year=2026)
    assert g["annual"] == []
    assert g["payments"] == []
    assert g["streak_years"] == 0
    assert g["cagr_pct"] is None
    assert g["yoy_pct"] is None


def test_yfinance_exception_is_swallowed(monkeypatch):
    class _Boom:
        def __init__(self, symbol): raise RuntimeError("delisted")
    monkeypatch.setattr(dividend_growth.yf, "Ticker", _Boom)
    g = dividend_growth.compute_dividend_growth("BOOM", _current_year=2026)
    assert g["annual"] == [] and g["streak_years"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd backend && python -m pytest tests/test_dividend_growth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dividend_growth'`.

- [ ] **Step 3: Implement `dividend_growth.py`.** Create `backend/dividend_growth.py`:

```python
"""Per-ticker dividend-growth analytics: annual DPS series, growth streak,
CAGR, YoY, and payout ratio. Pure function of a ticker's yfinance dividend
history; cached in-process. Leaf module — must not import from routers.*."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from cache import ttl_cache
from ticker_map import yf_symbol

_GROWTH_TTL = 3600  # 1h — dividend schedules change slowly


def _to_pct(v: Optional[float]) -> Optional[float]:
    """Decimal fraction (0.42) -> percent (42.0)."""
    return None if v is None else round(v * 100, 2)


def _annual_dps(dividends: pd.Series) -> list[dict]:
    """Sum per-share payments into calendar-year totals, ascending by year."""
    totals: dict[int, float] = defaultdict(float)
    for ts, amt in dividends.items():
        try:
            year = pd.Timestamp(ts).year
            totals[year] += float(amt)
        except (TypeError, ValueError):
            continue
    return [{"year": y, "dps": round(totals[y], 4)} for y in sorted(totals)]


def _closed(annual: list[dict], current_year: int) -> list[dict]:
    """Only fully-elapsed years — the in-progress year has partial data."""
    return [a for a in annual if a["year"] < current_year]


def _streak(annual: list[dict], current_year: int) -> int:
    """Consecutive most-recent closed years with a strictly higher DPS than
    the prior year (dividend-aristocrat style count of consecutive raises)."""
    closed = _closed(annual, current_year)
    streak = 0
    for i in range(len(closed) - 1, 0, -1):
        if closed[i]["dps"] > closed[i - 1]["dps"]:
            streak += 1
        else:
            break
    return streak


def _cagr(annual: list[dict], current_year: int, max_years: int = 5) -> tuple[Optional[float], int]:
    """CAGR of annual DPS over up to the last `max_years` closed years.
    Returns (cagr_pct, years_spanned). None cagr if start<=0 or <2 points."""
    closed = _closed(annual, current_year)
    if len(closed) < 2:
        return None, 0
    window = closed[-(max_years + 1):]
    start = window[0]["dps"]
    end = window[-1]["dps"]
    years = window[-1]["year"] - window[0]["year"]
    if start <= 0 or years <= 0:
        return None, max(years, 0)
    cagr = (end / start) ** (1.0 / years) - 1.0
    return round(cagr * 100, 2), years


def _yoy(annual: list[dict], current_year: int) -> Optional[float]:
    """Last closed year vs. the year before it, in percent."""
    closed = _closed(annual, current_year)
    if len(closed) < 2:
        return None
    prev, last = closed[-2]["dps"], closed[-1]["dps"]
    if prev <= 0:
        return None
    return round((last / prev - 1.0) * 100, 2)


@ttl_cache(_GROWTH_TTL)
def compute_dividend_growth(symbol: str, _current_year: int | None = None) -> dict:
    """Growth stats for one ticker. Best-effort; never raises on bad data.

    `_current_year` is injectable for tests; defaults to today's year.
    """
    current_year = _current_year if _current_year is not None else date.today().year
    empty = {
        "ticker": symbol, "streak_years": 0, "cagr_pct": None,
        "cagr_years_used": 0, "yoy_pct": None, "payout_ratio_pct": None,
        "annual": [], "payments": [],
    }
    try:
        tk = yf.Ticker(yf_symbol(symbol))
        div = tk.dividends
    except Exception:
        return empty

    # Payout ratio from .info (best-effort, independent of history).
    payout = None
    try:
        info = tk.info or {}
        pr = info.get("payoutRatio")
        payout = _to_pct(float(pr)) if pr is not None else None
    except Exception:
        payout = None

    if div is None or getattr(div, "empty", True):
        return {**empty, "payout_ratio_pct": payout}

    annual = _annual_dps(div)
    payments = sorted(
        (
            {"ex_date": pd.Timestamp(ts).date().isoformat(), "amount": round(float(a), 4)}
            for ts, a in div.items()
        ),
        key=lambda p: p["ex_date"],
    )
    cagr_pct, years_used = _cagr(annual, current_year)
    return {
        "ticker": symbol,
        "streak_years": _streak(annual, current_year),
        "cagr_pct": cagr_pct,
        "cagr_years_used": years_used,
        "yoy_pct": _yoy(annual, current_year),
        "payout_ratio_pct": payout,
        "annual": annual,
        "payments": payments,
    }
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd backend && python -m pytest tests/test_dividend_growth.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Register the module in CLAUDE.md's test list.** Edit `CLAUDE.md`, in the "Backend tests" section, add `test_dividend_growth` to the parenthesized module list (change "7 modules" → "8 modules" and append the name).

- [ ] **Step 6: Commit.**

```bash
git add backend/dividend_growth.py backend/tests/test_dividend_growth.py CLAUDE.md
git commit -m "feat(dividends): add compute_dividend_growth (streak/CAGR/YoY/payout)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Portfolio dividend-growth endpoint (table)

**Files:**
- Modify: `backend/routers/portfolio.py` (add endpoint near the existing `/dividends` routes, ~line 805)
- Modify: `backend/tests/test_portfolio.py` (add endpoint tests)

**Interfaces:**
- Consumes: `dividend_growth.compute_dividend_growth`, `_build_holdings` (existing, returns open positions keyed by ticker).
- Produces: `GET /api/portfolio/dividends/growth` → `list[{ticker, name, streak_years, cagr_pct, cagr_years_used, yoy_pct, payout_ratio_pct}]`; only dividend-paying holdings (those whose `annual` history is non-empty).

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_portfolio.py`:

```python
def test_dividends_growth_lists_only_payers(db_session, pid, monkeypatch):
    from routers.portfolio import get_dividend_growth
    from tests.helpers import make_txn
    import dividend_growth

    db_session.add(make_txn("AAPL", "buy", 10, 150.0, portfolio_id=pid))
    db_session.add(make_txn("ZZZZ", "buy", 5, 20.0, portfolio_id=pid))
    db_session.commit()

    def fake_growth(symbol, _current_year=None):
        if symbol == "AAPL":
            return {"ticker": "AAPL", "streak_years": 3, "cagr_pct": 7.5,
                    "cagr_years_used": 5, "yoy_pct": 5.0, "payout_ratio_pct": 25.0,
                    "annual": [{"year": 2023, "dps": 0.9}], "payments": []}
        return {"ticker": symbol, "streak_years": 0, "cagr_pct": None,
                "cagr_years_used": 0, "yoy_pct": None, "payout_ratio_pct": None,
                "annual": [], "payments": []}

    monkeypatch.setattr(dividend_growth, "compute_dividend_growth", fake_growth)
    rows = get_dividend_growth(db=db_session, pid=pid)
    assert [r["ticker"] for r in rows] == ["AAPL"]      # ZZZZ (no history) filtered out
    assert rows[0]["name"] == "AAPL"
    assert rows[0]["streak_years"] == 3
    assert "annual" not in rows[0] and "payments" not in rows[0]   # lightweight payload


def test_dividends_growth_empty_portfolio(db_session, pid):
    from routers.portfolio import get_dividend_growth
    assert get_dividend_growth(db=db_session, pid=pid) == []
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend && python -m pytest tests/test_portfolio.py -k dividends_growth -v`
Expected: FAIL — `cannot import name 'get_dividend_growth'`.

- [ ] **Step 3: Implement the endpoint.** In `backend/routers/portfolio.py`, add after the existing `get_dividend_forecast` endpoint (after line ~805 block):

```python
@router.get("/dividends/growth")
def get_dividend_growth(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Per-holding dividend-growth stats (streak / CAGR / YoY / payout) for the
    active portfolio. Only dividend-paying holdings are returned."""
    from dividend_growth import compute_dividend_growth

    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == pid)
        .order_by(Transaction.date)
        .all()
    )
    if not transactions:
        return []

    active = _build_holdings(transactions)
    names = {t.ticker: t.name for t in transactions if t.ticker}

    rows = []
    for ticker in sorted(active.keys()):
        g = compute_dividend_growth(ticker)
        if not g.get("annual"):
            continue  # not a dividend payer — skip
        rows.append({
            "ticker": ticker,
            "name": names.get(ticker, ticker),
            "streak_years": g["streak_years"],
            "cagr_pct": g["cagr_pct"],
            "cagr_years_used": g["cagr_years_used"],
            "yoy_pct": g["yoy_pct"],
            "payout_ratio_pct": g["payout_ratio_pct"],
        })
    return rows
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend && python -m pytest tests/test_portfolio.py -k dividends_growth -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit.**

```bash
git add backend/routers/portfolio.py backend/tests/test_portfolio.py
git commit -m "feat(dividends): GET /portfolio/dividends/growth (per-holding growth table)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Stock-detail dividend-growth endpoint (chart)

**Files:**
- Modify: `backend/routers/market.py` (add endpoint; `router` prefix is `/market`)
- Modify: `backend/tests/test_market.py` (add endpoint test)

**Interfaces:**
- Produces: `GET /api/market/dividend-growth/{ticker}` → the full `compute_dividend_growth(ticker)` dict (including `annual` and `payments`). Path is literal-first (`/dividend-growth/{ticker}`) to match this router's existing convention (`/quote/{ticker}`, `/history/{ticker}`) and avoid any path-param-first ambiguity.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_market.py`:

```python
def test_stock_dividend_growth_returns_full_payload(monkeypatch):
    from routers.market import stock_dividend_growth
    import dividend_growth

    payload = {"ticker": "AAPL", "streak_years": 12, "cagr_pct": 8.0,
               "cagr_years_used": 5, "yoy_pct": 6.0, "payout_ratio_pct": 15.0,
               "annual": [{"year": 2023, "dps": 0.96}],
               "payments": [{"ex_date": "2023-02-10", "amount": 0.23}]}
    monkeypatch.setattr(dividend_growth, "compute_dividend_growth",
                        lambda symbol: {**payload, "ticker": symbol})
    out = stock_dividend_growth("AAPL")
    assert out["ticker"] == "AAPL"
    assert out["payments"] == [{"ex_date": "2023-02-10", "amount": 0.23}]
    assert out["annual"][0]["year"] == 2023
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend && python -m pytest tests/test_market.py -k stock_dividend_growth -v`
Expected: FAIL — `cannot import name 'stock_dividend_growth'`.

- [ ] **Step 3: Implement the endpoint.** In `backend/routers/market.py`, add (near the other per-ticker routes, e.g. after the fundamentals endpoint):

```python
@router.get("/dividend-growth/{ticker}")
def stock_dividend_growth(ticker: str):
    """Full dividend-growth payload for one ticker (annual series + per-payment
    history for the chart, plus streak/CAGR/YoY/payout)."""
    from dividend_growth import compute_dividend_growth
    return compute_dividend_growth(ticker)
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend && python -m pytest tests/test_market.py -k stock_dividend_growth -v`
Expected: PASS.

- [ ] **Step 5: Run the whole backend suite** (guards against route-ordering regressions).

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add backend/routers/market.py backend/tests/test_market.py
git commit -m "feat(market): GET /market/dividend-growth/{ticker} (chart payload)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Dividends page — growth table (frontend)

**Files:**
- Modify: `frontend/src/api.js` (add two fetchers)
- Modify: `frontend/src/pages/Dividends.jsx` (add a "Dividend growth" section)
- Create: `frontend/src/pages/Dividends.growth.test.jsx`

**Interfaces:**
- Consumes: `GET /portfolio/dividends/growth`, `GET /market/dividend-growth/{ticker}`.
- Produces: `fetchDividendGrowth()`, `fetchStockDividendGrowth(ticker)` in `api.js`.

- [ ] **Step 1: Add the API fetchers.** In `frontend/src/api.js`, after the existing `fetchDividendForecast` (line ~105), add:

```javascript
export const fetchDividendGrowth = () =>
  api.get("/portfolio/dividends/growth").then((r) => r.data);
export const fetchStockDividendGrowth = (ticker) =>
  api.get(`/market/dividend-growth/${ticker}`).then((r) => r.data);
```

- [ ] **Step 2: Write the failing test.** Create `frontend/src/pages/Dividends.growth.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dividends from "./Dividends";

vi.mock("../api", () => ({
  fetchDividends: () => Promise.resolve([]),
  fetchDividendForecast: () => Promise.resolve({ months: [], year: 2026, total_paid: 0, total_estimated: 0 }),
  fetchDividendGrowth: () => Promise.resolve([
    { ticker: "AAPL", name: "Apple Inc.", streak_years: 12, cagr_pct: 8.4,
      cagr_years_used: 5, yoy_pct: 6.1, payout_ratio_pct: 15.0 },
  ]),
}));

vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

describe("Dividends growth table", () => {
  it("renders a row per dividend-paying holding", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Dividends />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Dividend growth/i)).toBeInTheDocument();
    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(await screen.findByText(/12 yrs/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run to verify it fails.**

Run: `cd frontend && npm run test -- Dividends.growth`
Expected: FAIL — no "Dividend growth" text (and `fetchDividendGrowth` unused by the page yet).

- [ ] **Step 4: Implement the growth section.** In `frontend/src/pages/Dividends.jsx`:

  (a) Extend the import from `../api` to include the new fetcher:

```javascript
import { fetchDividends, fetchDividendForecast, fetchDividendGrowth } from "../api";
```

  (b) Add a query inside the `Dividends` component (next to the existing `useQuery` calls):

```javascript
  const { data: growth, isLoading: growthLoading } = useQuery({
    queryKey: ["dividend-growth"],
    queryFn: fetchDividendGrowth,
    staleTime: 5 * 60 * 1000,
  });
```

  (c) Render `<GrowthSection rows={growth} loading={growthLoading} />` in the returned JSX, immediately after `<ForecastChart … />` (line ~86).

  (d) Add these two components at the bottom of the file:

```jsx
function fmtPct(v) {
  if (v == null) return <span className="text-muted">—</span>;
  const cls = v > 0 ? "text-gain" : v < 0 ? "text-loss" : "text-muted";
  return <span className={`tabular-nums ${cls}`}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}

function GrowthSection({ rows, loading }) {
  const { openStock } = useStockDetail();
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-muted">
        Loading dividend growth…
      </div>
    );
  }
  if (!rows?.length) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-2">
        <TrendingUp size={13} /> Dividend growth
      </h2>
      <div className="rounded-xl border border-surface-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border bg-surface-card">
              {["Ticker", "Company", "Streak", "CAGR", "YoY", "Payout"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => openStock(r.ticker)}
                className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 font-mono font-semibold text-ink">{r.ticker}</td>
                <td className="px-4 py-3 text-muted max-w-[180px] truncate">{r.name}</td>
                <td className="px-4 py-3 text-ink tabular-nums">
                  {r.streak_years > 0 ? `${r.streak_years} yrs` : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {r.cagr_pct != null ? (
                    <span className="flex items-baseline gap-1">
                      {fmtPct(r.cagr_pct)}
                      <span className="text-[10px] text-muted">{r.cagr_years_used}yr</span>
                    </span>
                  ) : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">{fmtPct(r.yoy_pct)}</td>
                <td className="px-4 py-3 tabular-nums text-muted">
                  {r.payout_ratio_pct != null ? `${r.payout_ratio_pct.toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
```

  (`TrendingUp` and `useStockDetail` are already imported at the top of `Dividends.jsx`.)

- [ ] **Step 5: Run to verify it passes.**

Run: `cd frontend && npm run test -- Dividends.growth`
Expected: PASS.

- [ ] **Step 6: Build check.**

Run: `cd frontend && npm run build`
Expected: build succeeds, no unresolved imports.

- [ ] **Step 7: Commit.**

```bash
git add frontend/src/api.js frontend/src/pages/Dividends.jsx frontend/src/pages/Dividends.growth.test.jsx
git commit -m "feat(dividends): dividend-growth table on the Dividends page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Stock detail — dividend history chart (frontend)

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (add + export `DividendGrowthSection`, register it in the `sections` dict inside `StockOverview`, ~line 779–1110)
- Modify: `frontend/src/hooks/useStockReportConfig.js` (register the new section id + label; make a stored order tolerate newly-added sections)
- Create: `frontend/src/components/StockDetail.divgrowth.test.jsx`

**Interfaces:**
- Consumes: `fetchStockDividendGrowth(ticker)` (added in Task 5).
- The section renders a per-payment bar chart from `payments` (native currency, as many years as returned) plus three stat tiles (streak / CAGR / YoY). Renders nothing when the stock pays no dividend (`payments` empty).
- **Section wiring:** `StockOverview` renders a `sections` dict keyed by id, iterated in `reportConfig.config.order` (from `useStockReportConfig`). A new section only appears if it is (a) added to the `sections` dict AND (b) present in `ALL_SECTIONS` so it lands in `DEFAULT_ORDER`. The stock's symbol is `data.ticker`; its native currency is `data.currency`.

- [ ] **Step 1: Write the failing test.** Create `frontend/src/components/StockDetail.divgrowth.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DividendGrowthSection } from "./StockDetail";

vi.mock("../api", () => ({
  fetchStockDividendGrowth: () => Promise.resolve({
    ticker: "AAPL", streak_years: 12, cagr_pct: 8.0, cagr_years_used: 5,
    yoy_pct: 6.0, payout_ratio_pct: 15.0,
    annual: [{ year: 2022, dps: 0.9 }, { year: 2023, dps: 0.96 }],
    payments: [
      { ex_date: "2022-02-10", amount: 0.22 },
      { ex_date: "2023-02-10", amount: 0.23 },
    ],
  }),
}));

describe("DividendGrowthSection", () => {
  it("shows growth stats when the stock pays a dividend", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <DividendGrowthSection ticker="AAPL" currency="USD" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Dividend history/i)).toBeInTheDocument();
    expect(await screen.findByText(/12 yrs/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd frontend && npm run test -- StockDetail.divgrowth`
Expected: FAIL — `DividendGrowthSection` is not exported.

- [ ] **Step 3: Implement the section.** In `frontend/src/components/StockDetail.jsx`:

  (a) Ensure these imports exist at the top (add what's missing):

```javascript
import { useQuery } from "@tanstack/react-query";
import { fetchStockDividendGrowth } from "../api";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { GAIN_COLOR, AXIS_TICK, GRID_STROKE } from "../lib/chartTheme";
```

  (b) Add and export the component (place it above `StockOverview`):

```jsx
export function DividendGrowthSection({ ticker, currency = "USD" }) {
  const { data, isLoading } = useQuery({
    queryKey: ["dividend-growth", ticker],
    queryFn: () => fetchStockDividendGrowth(ticker),
    staleTime: 5 * 60 * 1000,
    enabled: !!ticker,
  });

  if (isLoading || !data || !data.payments?.length) return null;

  const sym = currency === "USD" ? "$" : "";
  const tiles = [
    { label: "Growth streak", value: data.streak_years > 0 ? `${data.streak_years} yrs` : "—" },
    { label: `${data.cagr_years_used || 5}yr CAGR`, value: data.cagr_pct != null ? `${data.cagr_pct.toFixed(1)}%` : "—" },
    { label: "YoY", value: data.yoy_pct != null ? `${data.yoy_pct.toFixed(1)}%` : "—" },
  ];

  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold text-muted uppercase tracking-wider">Dividend history</h3>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border border-surface-border bg-surface-card px-3 py-2">
            <p className="text-[10px] text-muted uppercase tracking-wider">{t.label}</p>
            <p className="text-sm font-semibold text-ink tabular-nums">{t.value}</p>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.payments} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="ex_date" tick={AXIS_TICK} tickFormatter={(d) => String(d).slice(0, 7)} minTickGap={24} />
            <YAxis tick={AXIS_TICK} width={52} tickFormatter={(v) => `${sym}${v}`} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              contentStyle={{ background: "var(--surface-card-elevated)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [`${sym}${v}`, "Per share"]}
            />
            <Bar dataKey="amount" fill={GAIN_COLOR} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
```

  (c) Register the section in `StockOverview`'s `sections` object (the dict defined at ~line 824 that holds `quickStats`, `weekRange`, …). Add one entry:

```jsx
    dividendGrowth: <DividendGrowthSection ticker={data.ticker} currency={data.currency} />,
```

  The render loop at ~line 1105 (`reportConfig.config.order.map((id) => … sections[id] …)`) places it wherever `dividendGrowth` sits in the order — there is no JSX ordering to manage here. The order comes from the config edited in Step 4.

- [ ] **Step 4: Register the section id + label, and make stored orders tolerate new sections.** Edit `frontend/src/hooks/useStockReportConfig.js`:

  (a) Add an entry to `ALL_SECTIONS` (after `weekRange`, so the section renders high up near the dividend info):

```javascript
export const ALL_SECTIONS = [
  { id: "quickStats", label: "Quick Stats" },
  { id: "weekRange", label: "52-Week Range" },
  { id: "dividendGrowth", label: "Dividend History" },
  { id: "financials", label: "Financials" },
  { id: "ratiosAnalyst", label: "Ratios & Analyst" },
  { id: "insiderVolume", label: "Insider Volume" },
  { id: "insiderTx", label: "Insider Transactions" },
  { id: "valuation", label: "Valuation Models" },
  { id: "ownership", label: "Ownership" },
];
```

  (b) In the `useState` initializer (~lines 33–38), append any `ALL_SECTIONS` ids missing from a stored order. Without this, the app's existing user (who already has a persisted `sb_stock_report_sections` in localStorage) would keep their old order and NEVER see the new section:

```javascript
  const [config, setConfig] = useState(() => {
    const stored = load();
    const storedOrder = stored?.order;
    const order = storedOrder
      ? [...storedOrder, ...DEFAULT_ORDER.filter((id) => !storedOrder.includes(id))]
      : DEFAULT_ORDER;
    return {
      order,
      hidden: new Set(stored?.hidden ?? []),
    };
  });
```

- [ ] **Step 5: Run to verify the component test passes.**

Run: `cd frontend && npm run test -- StockDetail.divgrowth`
Expected: PASS.

- [ ] **Step 6: Build check.**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 7: Commit.**

```bash
git add frontend/src/components/StockDetail.jsx frontend/src/hooks/useStockReportConfig.js frontend/src/components/StockDetail.divgrowth.test.jsx
git commit -m "feat(market): dividend-history chart + growth tiles on stock detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 3 — Cross-portfolio Overview

### Task 7: Extract `_allocation_totals` from `sector_breakdown` (behavior-preserving)

**Files:**
- Modify: `backend/routers/analytics.py` (promote `_weighted` to module scope, extract `_allocation_totals`, thin `sector_breakdown`)
- Modify: `backend/tests/test_analytics.py` (add a unit test for the extracted helper)

**Interfaces:**
- Produces: `analytics._allocation_totals(db, pid: int, display_ccy: str) -> dict` with keys
  `sectors, countries, asset_types, currencies` (each `dict[str, float]`, Cash folded into sectors/asset_types/currencies as today, never into countries), plus `total_value: float`.
  `analytics._weighted(totals: dict) -> list[{name, value, weight}]` (module-level).
- `sector_breakdown`'s HTTP response is unchanged.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_analytics.py`:

```python
def test_allocation_totals_returns_raw_values(db_session, pid, mock_yfinance):
    from routers.analytics import _allocation_totals
    from tests.helpers import make_txn

    db_session.add(make_txn("AAPL", "buy", 10, 150.0, portfolio_id=pid))
    db_session.commit()

    raw = _allocation_totals(db_session, pid, "USD")
    # raw values are un-weighted market values (mock price 180 * 10 = 1800), not percentages
    assert raw["total_value"] > 0
    assert sum(raw["sectors"].values()) == pytest.approx(raw["total_value"], rel=0.01)
    # Technology sector from the mock info
    assert "Technology" in raw["sectors"]


def test_weighted_is_module_level_and_percentizes():
    from routers.analytics import _weighted
    out = _weighted({"A": 30.0, "B": 10.0})
    by_name = {r["name"]: r for r in out}
    assert by_name["A"]["weight"] == 75.0
    assert by_name["B"]["weight"] == 25.0
    assert out[0]["name"] == "A"  # sorted desc by value
```

(Ensure `import pytest` is present at the top of `test_analytics.py` — it is used elsewhere in the file already.)

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend && python -m pytest tests/test_analytics.py -k "allocation_totals or weighted_is_module" -v`
Expected: FAIL — `cannot import name '_allocation_totals'` / `'_weighted'`.

- [ ] **Step 3: Refactor.** In `backend/routers/analytics.py`:

  (a) Add a module-level `_weighted` (place it just above the `sector_breakdown` route, ~line 1040). This is the exact function currently nested inside `sector_breakdown`:

```python
def _weighted(totals: dict) -> list:
    """[{name, value, weight%}] sorted desc; weight base is the dict's own sum."""
    denom = sum(totals.values())
    return [
        {"name": name, "value": round(value, 2),
         "weight": round(value / denom * 100, 2) if denom > 0 else 0}
        for name, value in sorted(totals.items(), key=lambda x: -x[1])
    ]
```

  (b) Add `_allocation_totals`, containing the current raw-computation body of `sector_breakdown` (lines ~1047–1155), returning the raw dicts instead of weighting. Full function:

```python
def _allocation_totals(db: Session, pid: int, display_ccy: str) -> dict:
    """Raw (un-weighted) per-dimension market-value totals for one portfolio,
    in `display_ccy` ('CZK' or 'USD'). Cash is folded into sectors/asset_types/
    currencies (never countries), matching get_summary's Cash figure. This is the
    shared core behind both /sector-breakdown and the cross-portfolio Overview."""
    from fx import folded_cash_display
    from models import CashInterestRate

    in_czk = display_ccy.upper() == "CZK"
    display_ccy = "CZK" if in_czk else "USD"

    transactions = _get_transactions(db, pid)

    txns = db.query(Transaction).filter(Transaction.portfolio_id == pid).all()
    cash_by_ccy_display: dict[str, float] = {}
    if has_external_cashflows(txns):
        from cash_ledger import cash_balance_by_currency, accrued_interest
        from fx import cash_amount_to_display

        rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
                  for r in db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()}
        cash_total = folded_cash_display(txns, rates, display_ccy)
        has_cash = abs(cash_total) > 0.005
        balances = cash_balance_by_currency(txns)
        accrued = accrued_interest(txns, rates)
        for ccy in set(balances) | set(accrued):
            v = cash_amount_to_display(balances.get(ccy, 0.0) + accrued.get(ccy, 0.0), ccy, display_ccy)
            if abs(v) > 0.005:
                cash_by_ccy_display[ccy] = v
    else:
        cash_total = 0.0
        has_cash = False

    if not transactions:
        sectors = {"Cash": round(cash_total, 2)} if has_cash else {}
        return {"sectors": sectors, "countries": {}, "asset_types": dict(sectors),
                "currencies": dict(cash_by_ccy_display) if has_cash else {},
                "total_value": 0.0}

    from routers.portfolio import _build_holdings, _live_fx_to_czk, _live_to_usd

    active = _build_holdings(transactions)

    sector_totals: dict[str, float] = defaultdict(float)
    country_totals: dict[str, float] = defaultdict(float)
    type_totals: dict[str, float] = defaultdict(float)
    currency_totals: dict[str, float] = defaultdict(float)
    total_value = 0.0
    fx_cache: dict[str, float] = {}
    infos = market_data.get_infos(list(active.keys()))

    for ticker, data in active.items():
        try:
            info = infos.get(ticker, {})
            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            ticker_ccy = (info.get("currency") or "USD")
            divisor = 100.0 if ticker_ccy == "GBp" else 1.0
            native_value = data["shares"] * float(price) / divisor
            if in_czk:
                live_fx = _live_fx_to_czk("GBP" if ticker_ccy == "GBp" else ticker_ccy, fx_cache)
            else:
                live_fx = _live_to_usd("GBP" if ticker_ccy == "GBp" else ticker_ccy)
            market_value = native_value * live_fx

            sector = _classify_sector(info)
            country = _classify_country(info)
            quote_type = (info.get("quoteType") or "EQUITY").upper()
            type_label = _QUOTE_TYPE_LABEL.get(quote_type, quote_type.title() if quote_type else "Other")
            trade_ccy = "GBP" if ticker_ccy == "GBp" else (ticker_ccy or "USD").upper()

            sector_totals[sector] += market_value
            country_totals[country] += market_value
            type_totals[type_label] += market_value
            currency_totals[trade_ccy] += market_value
            total_value += market_value
        except Exception:
            continue

    if has_cash:
        sector_totals["Cash"] = cash_total
        type_totals["Cash"] = cash_total
        for ccy, v in cash_by_ccy_display.items():
            currency_totals[ccy] += v

    return {
        "sectors": dict(sector_totals),
        "countries": dict(country_totals),
        "asset_types": dict(type_totals),
        "currencies": dict(currency_totals),
        "total_value": total_value,
    }
```

  (c) Replace the body of `sector_breakdown` with a thin wrapper (keep the route decorator and signature):

```python
@router.get("/sector-breakdown")
def sector_breakdown(
    currency: str = "USD",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    display_ccy = "CZK" if currency.upper() == "CZK" else "USD"
    raw = _allocation_totals(db, pid, display_ccy)
    return {
        "currency": display_ccy,
        "sectors": _weighted(raw["sectors"]),
        "countries": _weighted(raw["countries"]),
        "asset_types": _weighted(raw["asset_types"]),
        "currencies": _weighted(raw["currencies"]),
        "total_value": round(raw["total_value"], 2),
    }
```

  Remove the now-duplicated nested `_weighted` and the old inline body. Confirm `defaultdict`, `market_data`, `_get_transactions`, `has_external_cashflows`, `_classify_sector`, `_classify_country`, `_QUOTE_TYPE_LABEL` are already imported/defined at module scope in `analytics.py` (they were used by the original inline code, so they are).

- [ ] **Step 4: Run the new tests + the full analytics suite** (the suite is the real guard that behavior is unchanged).

Run: `cd backend && python -m pytest tests/test_analytics.py -v`
Expected: PASS — new helper tests plus all pre-existing `sector_breakdown` tests.

- [ ] **Step 5: Commit.**

```bash
git add backend/routers/analytics.py backend/tests/test_analytics.py
git commit -m "refactor(analytics): extract _allocation_totals/_weighted for reuse

Behavior-preserving: sector_breakdown now wraps the extracted raw-totals helper.
Enables cross-portfolio aggregation before weighting.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: `/portfolios/overview` endpoint

**Files:**
- Modify: `backend/routers/portfolios.py` (add endpoint + `from collections import defaultdict`)
- Modify: `backend/tests/test_portfolio.py` (or `test_analytics.py`) — add overview tests

**Interfaces:**
- Consumes: `routers.portfolio.get_summary(currency, db, pid)`, `routers.analytics._allocation_totals`, `routers.analytics._weighted`.
- Produces: `GET /api/portfolios/overview?currency=` → `{currency, total_net_worth, total_day_change, total_day_change_percent, portfolio_count, sectors, countries, asset_types}`.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_portfolio.py`:

```python
def test_portfolios_overview_sums_across_portfolios(db_session, mock_yfinance):
    from models import Portfolio
    from routers.portfolios import portfolios_overview
    from routers.portfolio import get_summary
    from tests.helpers import make_txn

    p1 = Portfolio(name="zubik", is_default=True)
    p2 = Portfolio(name="mama")
    db_session.add_all([p1, p2])
    db_session.commit()
    db_session.add(make_txn("AAPL", "buy", 10, 150.0, portfolio_id=p1.id))
    db_session.add(make_txn("MSFT", "buy", 5, 300.0, portfolio_id=p2.id))
    db_session.commit()

    s1 = get_summary(currency="USD", db=db_session, pid=p1.id)
    s2 = get_summary(currency="USD", db=db_session, pid=p2.id)

    ov = portfolios_overview(currency="USD", db=db_session)
    assert ov["portfolio_count"] == 2
    assert ov["total_net_worth"] == round(s1["net_worth"] + s2["net_worth"], 2)
    assert ov["currency"] == "USD"
    # both holdings are Technology in the mock -> one weighted sector at 100%
    assert ov["sectors"] and abs(sum(s["weight"] for s in ov["sectors"]) - 100.0) < 0.1


def test_portfolios_overview_empty_db(db_session):
    from routers.portfolios import portfolios_overview
    ov = portfolios_overview(currency="USD", db=db_session)
    assert ov["portfolio_count"] == 0
    assert ov["total_net_worth"] == 0.0
    assert ov["sectors"] == []
    assert ov["total_day_change_percent"] is None
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend && python -m pytest tests/test_portfolio.py -k portfolios_overview -v`
Expected: FAIL — `cannot import name 'portfolios_overview'`.

- [ ] **Step 3: Implement the endpoint.** In `backend/routers/portfolios.py`:

  (a) Add at the top with the other imports:

```python
from collections import defaultdict
```

  (b) Add the endpoint (place it above the `require_portfolio` dependency, after `delete_portfolio`):

```python
@router.get("/overview")
def portfolios_overview(
    currency: str = "USD",
    db: Session = Depends(get_db),
):
    """Cross-portfolio summary: total net worth + daily change (summed over all
    portfolios) and combined sector/country/asset-type allocation. Deliberately
    NOT portfolio-scoped — /portfolios is in PORTFOLIO_AGNOSTIC_PREFIXES."""
    from routers.portfolio import get_summary
    from routers.analytics import _allocation_totals, _weighted

    display_ccy = "CZK" if currency.upper() == "CZK" else "USD"
    portfolios = db.query(Portfolio).all()

    total_nw = 0.0
    total_dc = 0.0
    sectors: dict[str, float] = defaultdict(float)
    countries: dict[str, float] = defaultdict(float)
    asset_types: dict[str, float] = defaultdict(float)

    for p in portfolios:
        summary = get_summary(currency=currency, db=db, pid=p.id)
        total_nw += summary.get("net_worth") or 0.0
        total_dc += summary.get("day_change") or 0.0

        raw = _allocation_totals(db, p.id, display_ccy)
        for name, value in raw["sectors"].items():
            sectors[name] += value
        for name, value in raw["countries"].items():
            countries[name] += value
        for name, value in raw["asset_types"].items():
            asset_types[name] += value

    # Combined day-change %: today's change over yesterday's net worth
    # (net worth minus today's change). Cash has no intraday move, so this is
    # the net-worth-basis analogue of each portfolio's own day_change_percent.
    base = total_nw - total_dc
    dc_pct = round(total_dc / base * 100, 2) if base > 0 else None

    return {
        "currency": display_ccy,
        "total_net_worth": round(total_nw, 2),
        "total_day_change": round(total_dc, 2),
        "total_day_change_percent": dc_pct,
        "portfolio_count": len(portfolios),
        "sectors": _weighted(sectors),
        "countries": _weighted(countries),
        "asset_types": _weighted(asset_types),
    }
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend && python -m pytest tests/test_portfolio.py -k portfolios_overview -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full backend suite** (route registration + no regressions).

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add backend/routers/portfolios.py backend/tests/test_portfolio.py
git commit -m "feat(portfolios): GET /portfolios/overview (cross-portfolio net worth + allocation)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Overview page (frontend)

**Files:**
- Modify: `frontend/src/api.js` (add `fetchOverview`)
- Create: `frontend/src/pages/Overview.jsx`
- Modify: `frontend/src/App.jsx` (import + route `/overview`)
- Modify: `frontend/src/components/Sidebar.jsx` (nav link in `T212_LINKS`)
- Create: `frontend/src/pages/Overview.test.jsx`

**Interfaces:**
- Consumes: `GET /portfolios/overview`. Reuses `BreakdownChart` (`{ title, data, currencyLabel }`, `data = [{name, value, weight}]`) and `MetricCard`.
- Produces: `fetchOverview(currency)` in `api.js`.

- [ ] **Step 1: Add the API fetcher.** In `frontend/src/api.js`, near `fetchPortfolios` (line ~53):

```javascript
export const fetchOverview = (currency = "USD") =>
  api.get("/portfolios/overview", { params: { currency } }).then((r) => r.data);
```

(`/portfolios` is in `PORTFOLIO_AGNOSTIC_PREFIXES`, so no `portfolio_id` is injected — correct.)

- [ ] **Step 2: Write the failing test.** Create `frontend/src/pages/Overview.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Overview from "./Overview";

vi.mock("../api", () => ({
  fetchOverview: () => Promise.resolve({
    currency: "USD",
    total_net_worth: 12345.67,
    total_day_change: 100.5,
    total_day_change_percent: 0.82,
    portfolio_count: 2,
    sectors: [{ name: "Technology", value: 12345.67, weight: 100 }],
    countries: [{ name: "United States", value: 12345.67, weight: 100 }],
    asset_types: [{ name: "Stock", value: 12345.67, weight: 100 }],
  }),
}));

describe("Overview", () => {
  it("renders total net worth and allocation charts", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Overview />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Total net worth/i)).toBeInTheDocument();
    expect(await screen.findByText(/Technology/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run to verify it fails.**

Run: `cd frontend && npm run test -- Overview`
Expected: FAIL — cannot resolve `./Overview`.

- [ ] **Step 4: Implement `Overview.jsx`.** Create `frontend/src/pages/Overview.jsx`:

```jsx
import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../api";
import { useCurrency } from "../App";
import { formatMoney } from "../lib/format";
import BreakdownChart from "../components/BreakdownChart";
import { Layers, TrendingUp, TrendingDown } from "lucide-react";

export default function Overview() {
  const currencyCtx = useCurrency?.();
  const currency = currencyCtx?.currency || "USD";

  const { data, isLoading } = useQuery({
    queryKey: ["overview", currency],
    queryFn: () => fetchOverview(currency),
    staleTime: 5 * 60 * 1000,
  });

  const dc = data?.total_day_change ?? 0;
  const dcPct = data?.total_day_change_percent;
  const up = dc >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Layers size={18} className="text-brand" />
        <h1 className="text-xl font-semibold">Overview</h1>
        {data?.portfolio_count != null && (
          <span className="text-sm text-muted">· {data.portfolio_count} portfolios</span>
        )}
      </div>

      <div className="card">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">Total net worth</p>
        {isLoading ? (
          <p className="text-3xl font-semibold text-ink mt-2">…</p>
        ) : (
          <>
            <p className="text-3xl font-semibold text-ink mt-2 tabular-nums">
              {formatMoney(data?.total_net_worth ?? 0, currency)}
            </p>
            <p className={`text-sm mt-1 flex items-center gap-1 tabular-nums ${up ? "text-gain" : "text-loss"}`}>
              {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {up ? "+" : ""}{formatMoney(dc, currency)}
              {dcPct != null && <span>({up ? "+" : ""}{dcPct.toFixed(2)}%) today</span>}
            </p>
          </>
        )}
      </div>

      {!isLoading && data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <BreakdownChart title="Sectors" data={data.sectors} currencyLabel={currency} />
          <BreakdownChart title="Countries" data={data.countries} currencyLabel={currency} />
          <BreakdownChart title="Asset types" data={data.asset_types} currencyLabel={currency} />
        </div>
      )}
    </div>
  );
}
```

(`formatMoney(value, currency)` already handles `$`/`Kč`. `BreakdownChart` returns `null` on empty data, so empty dimensions render nothing.)

- [ ] **Step 5: Wire the route.** In `frontend/src/App.jsx`:
  - Add the import next to the other page imports (~line 12): `import Overview from "./pages/Overview";`
  - Add the route inside `AppLayout`'s `<Routes>` (next to the Dashboard route): `<Route path="/overview" element={<Overview />} />`

- [ ] **Step 6: Add the nav link.** In `frontend/src/components/Sidebar.jsx`:
  - Add `Layers` to the lucide import line (line 2).
  - In `T212_LINKS`, add as the second entry (right after Dashboard): `{ to: "/overview", label: "Overview", icon: Layers },`

- [ ] **Step 7: Run to verify the test passes.**

Run: `cd frontend && npm run test -- Overview`
Expected: PASS.

- [ ] **Step 8: Full frontend test + build.**

Run: `cd frontend && npm run test && npm run build`
Expected: all tests PASS, build succeeds.

- [ ] **Step 9: Commit.**

```bash
git add frontend/src/api.js frontend/src/pages/Overview.jsx frontend/src/pages/Overview.test.jsx frontend/src/App.jsx frontend/src/components/Sidebar.jsx
git commit -m "feat(overview): cross-portfolio Overview page (net worth + combined allocation)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] **Backend:** `cd backend && python -m pytest tests/ -v` — all green.
- [ ] **Frontend:** `cd frontend && npm run test && npm run build` — all green.
- [ ] **Manual (Playwright, per CLAUDE.md):** start `start.bat`, drive `http://localhost:5173`, log in with the dev password, then:
  - Overview page: net-worth headline + three allocation pies render; numbers reconcile against the sum of each portfolio's Dashboard.
  - Dividends page: the "Dividend growth" table lists dividend payers; a row click opens the stock detail.
  - Stock detail (a known payer, e.g. AAPL/MSFT): "Dividend history" chart + streak/CAGR/YoY tiles render; a non-payer shows no dividend section.
  - Confirm no "Div. Calendar" nav item remains and `/dividend-calendar` 404s / redirects.

## Notes for the implementer

- Work top-to-bottom: Phase 1 (cleanup) → Phase 2 (dividend growth) → Phase 3 (overview). Phases are independent, but this order keeps each commit self-contained.
- `compute_dividend_growth` is `@ttl_cache`-decorated and keyed on `symbol`; tests must clear the cache between cases (the provided autouse fixture does this) or the first call's result will be reused.
- Do not touch `fetchCombinedSummary` in `api.js` — it's a pre-existing orphan (calls a non-existent `/portfolio/combined-summary`); removing it is out of scope here.
- Keep per-share dividend amounts in native currency on the stock chart — do not convert to CZK.
```
