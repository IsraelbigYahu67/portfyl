# Portfyl Cash / Cash-Flow Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tolerant, per-currency cash ledger to Portfyl so it shows true net worth (positions + cash), accrues configurable interest without a scheduler, exposes cash as an allocation slice, and (behind a fallback) feeds deposits/withdrawals into money-weighted returns.

**Architecture:** Cash lives in the existing `Transaction` table, discriminated by `type` (new `deposit|withdrawal|fee|interest`), with a new nullable `amount` column and a relaxed-nullable `ticker`. Pure, tested functions in a new `backend/cash_ledger.py` compute per-currency balances and lazy interest accrual; a new `backend/routers/cash.py` exposes CRUD + settings + balance. Every existing `Transaction` consumer is guarded so cash rows can't leak into holdings/returns. Frontend adds a `Cash` page (ledger + interest sub-section), net worth on the Dashboard hero, and a cash slice in Allocation.

**Tech Stack:** Backend: FastAPI + SQLAlchemy 2.0 + SQLite (no Alembic — idempotent `_ensure_*` migrations in `main.py`); pytest via `backend/.venv`. Frontend: React 18 + Vite 6, @tanstack/react-query 5, axios, recharts, Vitest; UX-overhaul primitives (`Card`, `SectionHeader`, `DeltaPill`, `EmptyState`, `SkeletonRows`, `lib/format`).

## Global Constraints

- **No Alembic.** Schema changes are idempotent helpers in `backend/main.py` after `Base.metadata.create_all()`, using raw `conn.execute(text("ALTER TABLE ..."))` (SQLite now, Postgres later). Register new helpers in the startup call block (`main.py:254-274`).
- **Portfolio scoping is implicit.** The axios interceptor injects `portfolio_id` for every non-agnostic prefix. `PORTFOLIO_AGNOSTIC_PREFIXES = ["/portfolios", "/market", "/watchlists"]` (`frontend/src/api.js`). The new `/cash` prefix is NOT agnostic, so it receives `portfolio_id` automatically — backend reads it via `Depends(require_portfolio)` (`from routers.portfolios import require_portfolio`).
- **`owner_id` is always `"default"`.** Single-user; keep the column, don't thread it.
- **Money/FX normalized to CZK.** Each row carries native `currency` + `fx_to_czk`; get it via `fetch_fx_to_czk(currency, date)` (as `create_transaction` does at `portfolio.py:181`). Display-currency conversion mirrors whatever `get_summary` already applies to `total_value`.
- **pytest is NOT in `requirements.txt`.** Run the suite with the project venv: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`. Tests call router functions directly against an in-memory session (`tests/helpers.py::make_txn`, `tests/conftest.py`); no live server.
- **Do not commit `frontend/dist`, `__pycache__`, `*.pyc`, `*.db`.** Stage only source. Never `git add -A`.
- **Sign convention:** cash `amount` is stored **positive**; direction is carried by `type`.
- **Cash types are non-trade.** `CASH_TYPES = {"deposit","withdrawal","fee","interest"}`, `TRADE_TYPES = {"buy","sell","dividend"}` — the single source of truth (Task 1). Every `Transaction` consumer filters to `TRADE_TYPES` (or `ticker is not None`).

---

## File Structure

**New (backend):**
- `backend/cash_ledger.py` — `CASH_TYPES`/`TRADE_TYPES` constants + pure functions `signed_cash(txn)`, `cash_balance_by_currency(txns)`, `accrued_interest(txns, rates, as_of)`.
- `backend/routers/cash.py` — `/cash` router: CRUD, interest-rate settings, balance.
- `backend/tests/test_cash_ledger.py` — unit tests for the pure functions.
- `backend/tests/test_cash_api.py` — router-level tests (CRUD, balance, leak-guard, summary net worth).

**Modified (backend):**
- `backend/models.py` — `Transaction.amount` (nullable), `Transaction.ticker` nullable; new `CashInterestRate` model.
- `backend/main.py` — migrations (`_ensure_cash_columns`, `_ensure_cash_interest_rate_table`) + `include_router(cash.router, prefix="/api")`.
- `backend/schemas.py` — cash schemas (or keep them in the cash router; this plan keeps them in `routers/cash.py`).
- `backend/routers/portfolio.py` — guard `_build_holdings`/`get_summary`/movers to `TRADE_TYPES`; add `cash`/`accrued_interest`/`net_worth` to `get_summary`.
- `backend/routers/analytics.py` — guard transaction consumers to `TRADE_TYPES`; add `Cash` bucket to allocation; returns integration (Task 10).

**New (frontend):**
- `frontend/src/pages/Cash.jsx` — Cash page (balance card + ledger + interest sub-section).
- `frontend/src/pages/Cash.test.jsx` — render smoke test.

**Modified (frontend):**
- `frontend/src/api.js` — cash fetch/mutation helpers.
- `frontend/src/App.jsx` — `/cash` route.
- `frontend/src/components/Sidebar.jsx` — `Cash` nav item.
- `frontend/src/components/PortfolioHero.jsx` — net worth headline + positions/cash split.
- `frontend/src/pages/Dashboard.jsx` — pass net-worth fields to the hero.
- `frontend/src/pages/Allocation.jsx` (and/or `AllocationChart.jsx`) — cash slice.

---

## Phase 0 — Data model & migrations

### Task 1: Extend `Transaction` (cash types, `amount`, nullable `ticker`) + constants + migration

**Files:**
- Modify: `backend/models.py` (Transaction)
- Create: `backend/cash_ledger.py` (constants only in this task)
- Modify: `backend/main.py` (migration + call)

**Interfaces:**
- Produces: `Transaction.amount: float | None`; `Transaction.ticker` nullable; `cash_ledger.CASH_TYPES`, `cash_ledger.TRADE_TYPES` (frozensets).

- [ ] **Step 1: Add the column + relax ticker in `backend/models.py`**

In `class Transaction` (`models.py:20-35`) change:

```python
    ticker = Column(String, index=True, nullable=True)   # was nullable=False; NULL for cash rows
```

and add after `price`:

```python
    amount = Column(Float, nullable=True)   # cash amount (native ccy) for deposit/withdrawal/fee/interest; NULL for trades
```

- [ ] **Step 2: Create `backend/cash_ledger.py` with the type constants**

```python
"""Cash ledger: pure balance/interest math + the trade/cash type discriminator.

Cash flows share the Transaction table (discriminated by `type`). These frozensets
are the single source of truth used everywhere to keep cash rows out of holdings /
returns math.
"""
from __future__ import annotations

from datetime import date

TRADE_TYPES = frozenset({"buy", "sell", "dividend"})
CASH_TYPES = frozenset({"deposit", "withdrawal", "fee", "interest"})
```

- [ ] **Step 3: Add the idempotent migration in `backend/main.py`**

After the other `_ensure_*` defs (near `main.py:266`), add:

```python
def _ensure_cash_columns():
    """Add Transaction.amount and relax ticker NOT NULL for cash rows (SQLite rebuild)."""
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(transactions)"))}
        if "amount" not in cols:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN amount FLOAT"))
        # Relax ticker NOT NULL if the existing table still enforces it.
        info = list(conn.execute(text("PRAGMA table_info(transactions)")))
        ticker_notnull = any(r[1] == "ticker" and r[3] == 1 for r in info)  # r[3] = notnull
        if ticker_notnull:
            conn.execute(text("ALTER TABLE transactions RENAME TO transactions_old"))
            Base.metadata.tables["transactions"].create(bind=conn)
            old_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(transactions_old)"))]
            collist = ", ".join(old_cols)
            conn.execute(text(f"INSERT INTO transactions ({collist}) SELECT {collist} FROM transactions_old"))
            conn.execute(text("DROP TABLE transactions_old"))
```

Then register it in the startup block (after `_ensure_commission_column()` at `main.py:274`):

```python
_ensure_cash_columns()
```

- [ ] **Step 4: Verify the app imports and migrates cleanly**

Run: `cd backend && ./.venv/Scripts/python.exe -c "import main; print('ok')"`
Expected: prints `ok` with no traceback (migration ran idempotently against the dev DB).

- [ ] **Step 5: Verify the full suite still passes (no regression from the schema change)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all existing tests pass (57 today).

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/cash_ledger.py backend/main.py
git commit -m "feat(cash): extend Transaction with amount + nullable ticker; add TRADE/CASH type constants"
```

---

### Task 2: `CashInterestRate` model + table migration

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `CashInterestRate(id, portfolio_id, currency, annual_rate, enabled, start_date, created_at)` with unique `(portfolio_id, currency)`.

- [ ] **Step 1: Add the model to `backend/models.py`**

```python
class CashInterestRate(Base):
    __tablename__ = "cash_interest_rates"
    __table_args__ = (UniqueConstraint("portfolio_id", "currency", name="uq_cash_rate_pid_ccy"),)

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    currency = Column(String, nullable=False)          # "USD" | "GBP" | "EUR" | "CZK" ...
    annual_rate = Column(Float, nullable=False, default=0.0)  # decimal, e.g. 0.045 = 4.5% APY
    enabled = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=True)           # accrual start; NULL => first cash event
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Ensure `UniqueConstraint` is imported at the top of `models.py` (add to the existing `from sqlalchemy import ...` line if absent).

- [ ] **Step 2: Add the create-table migration in `backend/main.py`**

```python
def _ensure_cash_interest_rate_table():
    """create_all() builds it for fresh DBs; this is a no-op safety net for existing DBs."""
    with engine.begin() as conn:
        exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cash_interest_rates'"
        )).first()
        if not exists:
            Base.metadata.tables["cash_interest_rates"].create(bind=conn)
```

Register after `_ensure_cash_columns()`:

```python
_ensure_cash_interest_rate_table()
```

- [ ] **Step 3: Verify import + migration**

Run: `cd backend && ./.venv/Scripts/python.exe -c "import main; from models import CashInterestRate; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/models.py backend/main.py
git commit -m "feat(cash): add CashInterestRate model + table migration"
```

---

## Phase 1 — Pure cash logic (TDD)

### Task 3: `signed_cash` + `cash_balance_by_currency`

**Files:**
- Modify: `backend/cash_ledger.py`
- Create: `backend/tests/test_cash_ledger.py`

**Interfaces:**
- Consumes: `Transaction`-like objects with `.type`, `.currency`, `.amount`, `.shares`, `.price`.
- Produces:
  - `signed_cash(txn) -> tuple[str, float]` — `(currency, signed_native_amount)`; `+deposit/+interest/+sell/+dividend`, `−withdrawal/−fee/−buy`.
  - `cash_balance_by_currency(transactions) -> dict[str, float]` — per-currency net cash (native), negatives allowed.

- [ ] **Step 1: Write the failing test `backend/tests/test_cash_ledger.py`**

```python
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from cash_ledger import signed_cash, cash_balance_by_currency
from tests.helpers import make_txn


def _cash(type, amount, currency="USD", d=date(2024, 1, 1)):
    return make_txn(ticker=None, type=type, shares=None, price=None,
                    currency=currency, date=d, amount=amount)


def test_signed_cash_directions():
    assert signed_cash(_cash("deposit", 1000)) == ("USD", 1000.0)
    assert signed_cash(_cash("withdrawal", 300)) == ("USD", -300.0)
    assert signed_cash(_cash("fee", 5)) == ("USD", -5.0)
    assert signed_cash(_cash("interest", 12)) == ("USD", 12.0)


def test_signed_cash_trades_use_shares_price():
    assert signed_cash(make_txn(type="buy", shares=10, price=100, currency="USD")) == ("USD", -1000.0)
    assert signed_cash(make_txn(type="sell", shares=4, price=150, currency="USD")) == ("USD", 600.0)
    assert signed_cash(make_txn(type="dividend", shares=10, price=2, currency="USD")) == ("USD", 20.0)


def test_cash_balance_by_currency_mixes_flows_and_trades_per_currency():
    txns = [
        _cash("deposit", 5000, "USD"),
        make_txn(type="buy", shares=10, price=100, currency="USD"),   # -1000
        make_txn(type="sell", shares=2, price=150, currency="USD"),   # +300
        _cash("fee", 20, "USD"),                                      # -20
        _cash("deposit", 1000, "GBP"),
        _cash("withdrawal", 250, "GBP"),
    ]
    bal = cash_balance_by_currency(txns)
    assert round(bal["USD"], 2) == 4280.0   # 5000 -1000 +300 -20
    assert round(bal["GBP"], 2) == 750.0


def test_cash_balance_allows_negative():
    txns = [make_txn(type="buy", shares=1, price=100, currency="USD")]
    assert round(cash_balance_by_currency(txns)["USD"], 2) == -100.0
```

Note: this requires `make_txn` to accept `amount` and `None` ticker/shares/price — Task 3 Step 2 updates the helper.

- [ ] **Step 2: Extend `tests/helpers.py` to support cash rows**

In `backend/tests/helpers.py::make_txn` add an `amount` param and allow `None` fields:

```python
def make_txn(
    ticker: str | None = "AAPL",
    type: str = "buy",
    shares: float | None = 10,
    price: float | None = 150.0,
    currency: str = "USD",
    date: date | None = None,
    fx_to_czk: float | None = None,
    name: str | None = None,
    notes: str | None = None,
    source: str | None = "manual",
    portfolio_id: int = 1,
    amount: float | None = None,
) -> Transaction:
    return Transaction(
        portfolio_id=portfolio_id,
        ticker=ticker.upper() if ticker else None,
        name=name or (ticker.upper() if ticker else None),
        type=type,
        shares=shares,
        price=price,
        amount=amount,
        currency=currency,
        date=date or __import__("datetime").date(2024, 1, 15),
        fx_to_czk=fx_to_czk,
        notes=notes,
        source=source,
    )
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_ledger.py -v`
Expected: FAIL — `ImportError: cannot import name 'signed_cash'`.

- [ ] **Step 4: Implement in `backend/cash_ledger.py`**

```python
def signed_cash(txn) -> tuple[str, float]:
    """(currency, signed native amount) for one row. Cash rows use `amount`;
    trades use shares*price. Direction by type."""
    ccy = (txn.currency or "USD").upper()
    t = txn.type
    if t == "deposit" or t == "interest":
        return ccy, float(txn.amount or 0.0)
    if t == "withdrawal" or t == "fee":
        return ccy, -float(txn.amount or 0.0)
    value = float(txn.shares or 0.0) * float(txn.price or 0.0)
    if t == "buy":
        return ccy, -value
    if t == "sell" or t == "dividend":
        return ccy, value
    return ccy, 0.0


def cash_balance_by_currency(transactions) -> dict[str, float]:
    """Per-currency net cash (native). Negative balances are allowed (tolerant)."""
    out: dict[str, float] = {}
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        out[ccy] = out.get(ccy, 0.0) + amt
    return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_ledger.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/cash_ledger.py backend/tests/test_cash_ledger.py backend/tests/helpers.py
git commit -m "feat(cash): pure signed_cash + cash_balance_by_currency with tests"
```

---

### Task 4: `accrued_interest` (lazy, no scheduler)

**Files:**
- Modify: `backend/cash_ledger.py`
- Modify: `backend/tests/test_cash_ledger.py`

**Interfaces:**
- Consumes: `cash_balance_by_currency`, `signed_cash`.
- Produces: `accrued_interest(transactions, rates, as_of=None) -> dict[str, float]` where
  `rates: dict[str, dict]` keyed by currency, each `{"annual_rate": float, "enabled": bool, "start_date": date | None}`. Returns per-currency accrued interest (native). Only positive balances accrue; straight-line `balance * rate * days/365`.

- [ ] **Step 1: Write the failing test (append to `test_cash_ledger.py`)**

```python
from cash_ledger import accrued_interest


def test_accrued_interest_straight_line_on_positive_balance():
    # 10,000 USD deposited 2024-01-01, 5% APY, as_of exactly one year later.
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": None}}
    acc = accrued_interest(txns, rates, as_of=date(2025, 1, 1))
    # 366 days in 2024 (leap): 10000 * 0.05 * 366/365 ≈ 501.37
    assert 500.0 <= acc["USD"] <= 503.0


def test_accrued_interest_disabled_currency_is_zero():
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": False, "start_date": None}}
    assert accrued_interest(txns, rates, as_of=date(2025, 1, 1)) == {}


def test_accrued_interest_only_positive_balances():
    txns = [make_txn(type="buy", shares=1, price=100, currency="USD", date=date(2024, 1, 1))]  # -100
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": None}}
    assert accrued_interest(txns, rates, as_of=date(2025, 1, 1)).get("USD", 0.0) == 0.0


def test_accrued_interest_respects_start_date():
    txns = [_cash("deposit", 10000, "USD", d=date(2024, 1, 1))]
    rates = {"USD": {"annual_rate": 0.05, "enabled": True, "start_date": date(2024, 7, 1)}}
    acc = accrued_interest(txns, rates, as_of=date(2025, 1, 1))
    # only ~184 days accrue: 10000 * 0.05 * 184/365 ≈ 252
    assert 240.0 <= acc["USD"] <= 260.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_ledger.py -k accrued -v`
Expected: FAIL — `cannot import name 'accrued_interest'`.

- [ ] **Step 3: Implement in `backend/cash_ledger.py`**

```python
def _balance_timeline(transactions, currency):
    """Sorted [(date, running_balance)] for `currency`, one point per event date."""
    events = []
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        if ccy == currency and amt:
            events.append((txn.date, amt))
    events.sort(key=lambda e: e[0])
    timeline, running = [], 0.0
    for d, amt in events:
        running += amt
        if timeline and timeline[-1][0] == d:
            timeline[-1] = (d, running)
        else:
            timeline.append((d, running))
    return timeline


def accrued_interest(transactions, rates, as_of=None):
    """Lazy straight-line interest per currency: sum(balance * rate * days/365)
    over each segment where balance > 0, from max(start_date, first event) to as_of.
    Only currencies with an enabled rate accrue."""
    as_of = as_of or date.today()
    out: dict[str, float] = {}
    for ccy, cfg in rates.items():
        if not cfg.get("enabled") or not cfg.get("annual_rate"):
            continue
        rate = float(cfg["annual_rate"])
        timeline = _balance_timeline(transactions, ccy)
        if not timeline:
            continue
        start = cfg.get("start_date") or timeline[0][0]
        total = 0.0
        for i, (seg_start, bal) in enumerate(timeline):
            seg_end = timeline[i + 1][0] if i + 1 < len(timeline) else as_of
            lo = max(seg_start, start)
            if seg_end <= lo or bal <= 0:
                continue
            days = (seg_end - lo).days
            total += bal * rate * days / 365.0
        if total:
            out[ccy] = round(total, 2)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_ledger.py -v`
Expected: PASS (all cash-ledger tests).

- [ ] **Step 5: Commit**

```bash
git add backend/cash_ledger.py backend/tests/test_cash_ledger.py
git commit -m "feat(cash): lazy per-currency accrued_interest (no scheduler) with tests"
```

---

## Phase 2 — Defensive audit

### Task 5: Guard every `Transaction` consumer + leak-guard test

**Files:**
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/routers/analytics.py`
- Create: `backend/tests/test_cash_api.py` (leak-guard portion)

**Interfaces:**
- Consumes: `cash_ledger.TRADE_TYPES`.
- Produces: holdings/summary/analytics ignore cash rows entirely.

- [ ] **Step 1: Write the failing leak-guard test `backend/tests/test_cash_api.py`**

```python
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from routers.portfolio import _build_holdings
from tests.helpers import make_txn


def test_cash_rows_do_not_affect_holdings():
    trades = [make_txn(type="buy", shares=10, price=100, currency="USD")]
    cash = [make_txn(ticker=None, type="deposit", shares=None, price=None,
                     currency="USD", amount=5000, date=date(2024, 1, 1))]
    only_trades = _build_holdings(trades)
    with_cash = _build_holdings(trades + cash)
    assert with_cash.keys() == only_trades.keys()
    assert with_cash == only_trades
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_api.py -v`
Expected: FAIL — cash `deposit` row currently flows into `_build_holdings` (KeyError on `ticker`/`shares`, or a stray key).

- [ ] **Step 3: Guard `_build_holdings` in `backend/routers/portfolio.py`**

At the top of the transaction loop in `_build_holdings` (`portfolio.py:~124`), skip non-trades. Add the import near the top of the file (`from cash_ledger import TRADE_TYPES`) and, inside the `for txn in ...` loop, first line:

```python
        if txn.type not in TRADE_TYPES or not txn.ticker:
            continue
```

- [ ] **Step 4: Guard the other consumers**

Add `from cash_ledger import TRADE_TYPES` to `backend/routers/analytics.py`, then in `_get_transactions` (`analytics.py:114`) return only trades:

```python
    return [t for t in q.all() if t.type in TRADE_TYPES and t.ticker]
```

(Adjust to the actual query/return shape at `analytics.py:114-131`.) Audit these call sites and confirm each only sees trades after the filter: `_compute_capital_gains`, `_build_lot_queue`, `_compute_unrealized_gains`, `_build_value_cashflow_series` (`held_tickers`), `_lifetime_money_weighted`, sector/country breakdown, correlation. Also confirm `portfolio.py` `total_dividends` sum (`portfolio.py:429-430`, already filters `type == "dividend"`) and `get_movers` operate on trades only.

- [ ] **Step 5: Run the leak-guard + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: leak-guard passes; all pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/portfolio.py backend/routers/analytics.py backend/tests/test_cash_api.py
git commit -m "fix(cash): guard all Transaction consumers against cash rows (leak-guard test)"
```

---

## Phase 3 — Backend endpoints

### Task 6: Cash CRUD router

**Files:**
- Create: `backend/routers/cash.py`
- Modify: `backend/main.py` (register router)
- Modify: `backend/tests/test_cash_api.py` (CRUD tests)

**Interfaces:**
- Produces (all under `/api/cash`, portfolio-scoped):
  - `GET /cash` → `list[CashRow]` (cash rows only, newest first).
  - `POST /cash` `{type, amount, currency, date, note?}` → created row.
  - `PUT /cash/{id}` → updated row.
  - `DELETE /cash/{id}` → `{ok: true}`.
- Types: `CashRow = {id, type, amount, currency, date, note, fx_to_czk}`.

- [ ] **Step 1: Create `backend/routers/cash.py`**

```python
from datetime import date as date_type
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Transaction
from routers.portfolios import require_portfolio
from fx import fetch_fx_to_czk
from cash_ledger import CASH_TYPES

router = APIRouter(prefix="/cash", tags=["cash"])


class CashCreate(BaseModel):
    type: str = Field(pattern="^(deposit|withdrawal|fee|interest)$")
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    date: date_type
    note: Optional[str] = None


class CashRow(BaseModel):
    id: int
    type: str
    amount: float
    currency: str
    date: date_type
    note: Optional[str] = None
    fx_to_czk: Optional[float] = None

    class Config:
        from_attributes = True


def _to_row(t: Transaction) -> CashRow:
    return CashRow(id=t.id, type=t.type, amount=t.amount, currency=t.currency,
                   date=t.date, note=t.notes, fx_to_czk=t.fx_to_czk)


@router.get("", response_model=List[CashRow])
def list_cash(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    rows = (db.query(Transaction)
              .filter(Transaction.portfolio_id == pid, Transaction.type.in_(list(CASH_TYPES)))
              .order_by(Transaction.date.desc(), Transaction.id.desc())
              .all())
    return [_to_row(t) for t in rows]


@router.post("", response_model=CashRow)
def create_cash(body: CashCreate, db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    ccy = body.currency.upper()
    row = Transaction(
        portfolio_id=pid, ticker=None, name=None, type=body.type,
        shares=None, price=None, amount=body.amount, currency=ccy,
        date=body.date, notes=body.note, source="manual",
        fx_to_czk=fetch_fx_to_czk(ccy, body.date),
    )
    db.add(row); db.commit(); db.refresh(row)
    return _to_row(row)


@router.put("/{cash_id}", response_model=CashRow)
def update_cash(cash_id: int, body: CashCreate, db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    row = (db.query(Transaction)
             .filter(Transaction.id == cash_id, Transaction.portfolio_id == pid,
                     Transaction.type.in_(list(CASH_TYPES)))
             .first())
    if not row:
        raise HTTPException(404, "Cash entry not found")
    ccy = body.currency.upper()
    row.type, row.amount, row.currency, row.date, row.notes = body.type, body.amount, ccy, body.date, body.note
    row.fx_to_czk = fetch_fx_to_czk(ccy, body.date)
    db.commit(); db.refresh(row)
    return _to_row(row)


@router.delete("/{cash_id}")
def delete_cash(cash_id: int, db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    row = (db.query(Transaction)
             .filter(Transaction.id == cash_id, Transaction.portfolio_id == pid,
                     Transaction.type.in_(list(CASH_TYPES)))
             .first())
    if not row:
        raise HTTPException(404, "Cash entry not found")
    db.delete(row); db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Register the router in `backend/main.py`**

After `app.include_router(options.router, prefix="/api")` (`main.py:348`), and add the import next to the other router imports:

```python
from routers import cash
app.include_router(cash.router, prefix="/api")
```

- [ ] **Step 3: Write CRUD tests (append to `backend/tests/test_cash_api.py`)**

```python
from routers.cash import create_cash, list_cash, delete_cash, CashCreate
from tests.helpers import get_session  # if present; else use the conftest session fixture


def test_create_and_list_cash(db_session):
    pid = 1
    create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    create_cash(CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, pid)
    rows = list_cash(db_session, pid)
    assert {r.type for r in rows} == {"deposit", "fee"}
    assert len(rows) == 2
```

Use the existing session fixture from `tests/conftest.py` (match its fixture name; the suite already uses an in-memory session — mirror one of the existing `test_portfolio.py` tests for the exact fixture usage).

- [ ] **Step 4: Run the cash API tests + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_api.py -v && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: cash CRUD tests pass; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/cash.py backend/main.py backend/tests/test_cash_api.py
git commit -m "feat(cash): CRUD router for cash flows (deposit/withdrawal/fee/interest)"
```

---

### Task 7: Interest-rate settings + balance endpoints

**Files:**
- Modify: `backend/routers/cash.py`
- Modify: `backend/tests/test_cash_api.py`

**Interfaces:**
- Produces:
  - `GET /cash/interest-rates` → `list[{currency, annual_rate, enabled, start_date}]`.
  - `PUT /cash/interest-rates` `{rates: [...]}` → upserts.
  - `GET /cash/balance` `?currency=USD` → `{by_currency: {ccy: {balance, accrued}}, total, total_accrued, currency}` where `total`/`total_accrued` are in the display currency.

- [ ] **Step 1: Add the display-currency helper note**

Cash balances are native. Convert native→display using the **same conversion `get_summary` applies to `total_value`**. In this task, locate that path (grep `def get_summary` in `portfolio.py`; it accepts `currency` and converts CZK-normalized figures). Reuse it via a small shared helper `convert_amount(amount_native, from_ccy, to_ccy)` — if `get_summary` already has such a helper, import it; otherwise add `convert_amount` to `fx.py` using live rates and reuse it in both places (DRY). The plan's Task 8 also needs this helper, so define it once here.

- [ ] **Step 2: Add settings + balance endpoints to `backend/routers/cash.py`**

```python
from models import CashInterestRate
from cash_ledger import cash_balance_by_currency, accrued_interest
from fx import convert_amount  # native->display; added in Step 1 if missing


class RateItem(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    annual_rate: float = Field(ge=0)
    enabled: bool = False
    start_date: Optional[date_type] = None


class RatesPayload(BaseModel):
    rates: List[RateItem]


@router.get("/interest-rates", response_model=List[RateItem])
def get_rates(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    rows = db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()
    return [RateItem(currency=r.currency, annual_rate=r.annual_rate, enabled=r.enabled,
                     start_date=r.start_date) for r in rows]


@router.put("/interest-rates", response_model=List[RateItem])
def put_rates(body: RatesPayload, db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    for item in body.rates:
        ccy = item.currency.upper()
        row = (db.query(CashInterestRate)
                 .filter(CashInterestRate.portfolio_id == pid, CashInterestRate.currency == ccy)
                 .first())
        if not row:
            row = CashInterestRate(portfolio_id=pid, currency=ccy)
            db.add(row)
        row.annual_rate, row.enabled, row.start_date = item.annual_rate, item.enabled, item.start_date
    db.commit()
    return get_rates(db, pid)


@router.get("/balance")
def get_balance(currency: str = "USD", db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    txns = db.query(Transaction).filter(Transaction.portfolio_id == pid).all()
    rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
             for r in db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()}
    balances = cash_balance_by_currency(txns)
    accrued = accrued_interest(txns, rates)
    disp = currency.upper()
    by_currency, total, total_accrued = {}, 0.0, 0.0
    for ccy in set(balances) | set(accrued):
        bal, acc = balances.get(ccy, 0.0), accrued.get(ccy, 0.0)
        by_currency[ccy] = {"balance": round(bal, 2), "accrued": round(acc, 2)}
        total += convert_amount(bal, ccy, disp)
        total_accrued += convert_amount(acc, ccy, disp)
    return {"by_currency": by_currency, "total": round(total, 2),
            "total_accrued": round(total_accrued, 2), "currency": disp}
```

- [ ] **Step 3: Write tests (append to `test_cash_api.py`)**

```python
from routers.cash import get_rates, put_rates, get_balance, RatesPayload, RateItem


def test_put_and_get_interest_rates(db_session):
    pid = 1
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.045, enabled=True)]), db_session, pid)
    rows = get_rates(db_session, pid)
    assert rows[0].currency == "USD" and rows[0].enabled is True


def test_balance_endpoint_sums_flows(db_session):
    pid = 1
    create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    create_cash(CashCreate(type="fee", amount=50, currency="USD", date=date(2024, 1, 2)), db_session, pid)
    res = get_balance("USD", db_session, pid)
    assert res["by_currency"]["USD"]["balance"] == 950.0
```

- [ ] **Step 4: Run tests + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cash_api.py -v && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/cash.py backend/fx.py backend/tests/test_cash_api.py
git commit -m "feat(cash): interest-rate settings + per-currency balance endpoint"
```

---

### Task 8: Net worth in `get_summary`

**Files:**
- Modify: `backend/routers/portfolio.py` (`get_summary` return block, `portfolio.py:479-489`)
- Modify: `backend/tests/test_cash_api.py`

**Interfaces:**
- Produces: `get_summary` response gains `cash`, `accrued_interest`, `net_worth` (display currency). `total_value` unchanged.

- [ ] **Step 1: Compute cash in `get_summary`**

Before the `return {` at `portfolio.py:479`, add (reusing the same `currency` param `get_summary` already has, and the balance logic):

```python
    from cash_ledger import cash_balance_by_currency, accrued_interest
    from models import CashInterestRate
    from fx import convert_amount

    _rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
              for r in db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()}
    _balances = cash_balance_by_currency(transactions)
    _accrued = accrued_interest(transactions, _rates)
    cash_total = sum(convert_amount(v, ccy, currency) for ccy, v in _balances.items())
    accrued_total = sum(convert_amount(v, ccy, currency) for ccy, v in _accrued.items())
```

(`transactions` is the full list already loaded in `get_summary`; `cash_balance_by_currency` ignores nothing — it sums trades + cash, which is correct for the cash balance. `pid`/`db`/`currency` are already in scope.)

- [ ] **Step 2: Add the fields to the return dict**

In the `return {` block (`portfolio.py:479-489`) add:

```python
        "cash": round(cash_total, 2),
        "accrued_interest": round(accrued_total, 2),
        "net_worth": round(total_value + cash_total + accrued_total, 2),
```

- [ ] **Step 3: Test net worth (append to `test_cash_api.py`)**

```python
from routers.portfolio import get_summary


def test_summary_net_worth_adds_cash(db_session):
    pid = 1
    create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    s = get_summary(currency="USD", db=db_session, pid=pid)  # match get_summary's real signature
    assert s["cash"] == 1000.0
    assert s["net_worth"] == round(s["total_value"] + s["cash"] + s["accrued_interest"], 2)
```

Match `get_summary`'s actual parameter names/order (check `portfolio.py` `def get_summary(...)`).

- [ ] **Step 4: Run + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/portfolio.py backend/tests/test_cash_api.py
git commit -m "feat(cash): add cash/accrued_interest/net_worth to /portfolio/summary"
```

---

### Task 9: Cash slice in Allocation

**Files:**
- Modify: `backend/routers/analytics.py` (allocation/sector breakdown, `analytics.py:890-957`)
- Modify: `backend/tests/test_cash_api.py`

**Interfaces:**
- Produces: the allocation/sector-breakdown response includes a `Cash` bucket = blended cash total (display currency).

- [ ] **Step 1: Read the breakdown shape**

Read `analytics.py:890-957` (`sector_breakdown` / `to_breakdown`) to learn the exact response item shape (e.g., `{"name", "value", "pct"}`).

- [ ] **Step 2: Append a Cash bucket**

In the allocation endpoint, after building the holdings buckets and before returning, add a `Cash` entry using the same cash total as Task 8 (extract a shared `portfolio_cash_total(db, pid, currency)` helper into `cash_ledger.py` or `fx.py` and reuse in Task 8 + here — DRY):

```python
    cash_total = portfolio_cash_total(db, pid, currency)
    if abs(cash_total) > 0.005:
        buckets.append({"name": "Cash", "value": round(cash_total, 2)})
    # recompute pct across buckets so Cash is included in the denominator
```

Match the real bucket key names and the pct recomputation to the code read in Step 1.

- [ ] **Step 3: Test (append to `test_cash_api.py`)**

```python
def test_allocation_includes_cash_bucket(db_session):
    pid = 1
    create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    # call the allocation function with its real signature; assert a "Cash" bucket exists
    # (fill in the exact function name/args from analytics.py:890)
```

Complete the assertion against the real allocation function signature found in Step 1.

- [ ] **Step 4: Run + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/analytics.py backend/cash_ledger.py backend/tests/test_cash_api.py
git commit -m "feat(cash): add Cash bucket to allocation breakdown"
```

---

### Task 10: Returns integration (deposits/withdrawals as external cashflows, gated)

**Files:**
- Modify: `backend/routers/analytics.py` (`_build_value_cashflow_series` `analytics.py:451`, `_lifetime_money_weighted` `analytics.py:784`)
- Modify: `backend/tests/test_cash_api.py` (characterization tests)

**Interfaces:**
- Produces: when the portfolio has ≥1 `deposit`/`withdrawal` row, external cashflows `C` come from deposits(+)/withdrawals(−) and the value series `V` includes the cash balance; otherwise behavior is byte-for-byte the current buys/sells-derived one.

- [ ] **Step 1: Read both functions fully**

Read `analytics.py:451-530` (`_build_value_cashflow_series`) and `analytics.py:784-860` (`_lifetime_money_weighted`) so the change is applied against the real code (they are non-trivial). This task modifies existing complex functions — do not rewrite them wholesale; make the two targeted changes below.

- [ ] **Step 2: Write characterization tests FIRST (append to `test_cash_api.py`)**

```python
def _perf_series(txns):
    # call the real analytics entry that builds V/C or returns money-weighted metrics
    # capture output for a fixed set of trade-only txns (no cash)
    ...

def test_returns_unchanged_without_cash(db_session):
    """Fallback: with no deposit/withdrawal rows, returns match the pre-cash baseline."""
    # Seed trade-only txns, snapshot the money-weighted result, assert it equals the
    # known baseline (compute the baseline from the current implementation first).
    ...

def test_returns_use_deposits_as_external_cashflows(db_session):
    """With deposits present, external cashflows switch to deposits/withdrawals and V
    includes cash — the money-weighted return reflects contributed capital."""
    ...
```

Fill these in against the real analytics entry points during Step 1 (they define the exact functions/signatures). The first test pins the fallback; the second pins the new path.

- [ ] **Step 3: Gate + apply the transformation**

Add a helper `has_external_cashflows(txns) -> bool` (any `deposit`/`withdrawal`) to `cash_ledger.py`. Then:
- In `_build_value_cashflow_series`: when `has_external_cashflows(txns)`, build `C` from deposit(+)/withdrawal(−) rows (converted to USD like the existing flows) and add the per-day cash balance (from `cash_balance_by_currency` walked over the date index, converted to USD) into `V`. Otherwise leave the current buys/sells-derived `C` and holdings-only `V` untouched.
- In `_lifetime_money_weighted`: when gated on, build `xirr_flows` from deposits/withdrawals against ending net worth; otherwise keep the current buys/sells/dividends flows.

Keep both branches so the fallback path is the exact current code.

- [ ] **Step 4: Run characterization tests + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: fallback test proves no change without cash; new-path test passes; existing analytics tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/analytics.py backend/cash_ledger.py backend/tests/test_cash_api.py
git commit -m "feat(cash): deposits/withdrawals as external cashflows in returns (fallback-gated)"
```

---

## Phase 4 — Frontend

### Task 11: API helpers + Cash page (balance + ledger CRUD) + route + nav

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/pages/Cash.jsx`
- Create: `frontend/src/pages/Cash.test.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/components/Sidebar.jsx`

**Interfaces:**
- Consumes: `Card`, `SectionHeader`, `DeltaPill`, `EmptyState`, `SkeletonRows` from `../components/ui`; `formatMoney` from `../lib/format`.
- Produces: `/cash` route + nav item; ledger list with add/edit/delete; balance card.

- [ ] **Step 1: Add API helpers to `frontend/src/api.js`** (after the summary helpers)

```js
// ----- Cash (portfolio-scoped) ------------------------------------------------
export const fetchCash = () => api.get("/cash").then((r) => r.data);
export const createCash = (data) => api.post("/cash", data).then((r) => r.data);
export const updateCash = (id, data) => api.put(`/cash/${id}`, data).then((r) => r.data);
export const deleteCash = (id) => api.delete(`/cash/${id}`).then((r) => r.data);
export const fetchCashBalance = (currency = "USD") =>
  api.get("/cash/balance", { params: { currency } }).then((r) => r.data);
export const fetchInterestRates = () => api.get("/cash/interest-rates").then((r) => r.data);
export const saveInterestRates = (rates) =>
  api.put("/cash/interest-rates", { rates }).then((r) => r.data);
```

- [ ] **Step 2: Create `frontend/src/pages/Cash.jsx`** (balance card + ledger; interest section added in Task 12)

```jsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Wallet, Plus, Trash2 } from "lucide-react";
import { Card, SectionHeader, SkeletonRows, EmptyState } from "../components/ui";
import { formatMoney } from "../lib/format";
import { fetchCash, createCash, deleteCash, fetchCashBalance } from "../api";
import { useCurrency } from "../context/CurrencyContext"; // match the app's currency hook

const CASH_TYPES = ["deposit", "withdrawal", "fee", "interest"];

export default function Cash() {
  const currency = useCurrency?.() ?? "USD";
  const qc = useQueryClient();
  const rows = useQuery({ queryKey: ["cash"], queryFn: fetchCash });
  const balance = useQuery({ queryKey: ["cash-balance", currency], queryFn: () => fetchCashBalance(currency) });
  const add = useMutation({
    mutationFn: createCash,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["cash"] }); qc.invalidateQueries({ queryKey: ["cash-balance"] }); qc.invalidateQueries({ queryKey: ["summary"] }); },
  });
  const del = useMutation({
    mutationFn: deleteCash,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["cash"] }); qc.invalidateQueries({ queryKey: ["cash-balance"] }); qc.invalidateQueries({ queryKey: ["summary"] }); },
  });

  const [form, setForm] = useState({ type: "deposit", amount: "", currency: "USD", date: "", note: "" });
  const submit = (e) => {
    e.preventDefault();
    add.mutate({ ...form, amount: Number(form.amount) });
    setForm((f) => ({ ...f, amount: "", note: "" }));
  };

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-bold text-ink">Cash</h1>

      <Card>
        <SectionHeader icon={Wallet}>Balance</SectionHeader>
        {balance.isLoading ? <SkeletonRows rows={2} cols={2} /> : (
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-2xl font-bold text-ink tnum">
              {formatMoney(balance.data?.total, currency)}
            </span>
            {balance.data?.total_accrued > 0 && (
              <span className="font-mono text-xs text-gain">
                +{formatMoney(balance.data.total_accrued, currency)} interest
              </span>
            )}
          </div>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Plus}>Add cash flow</SectionHeader>
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end">
          <select className="input w-auto" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {CASH_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="input w-28" type="number" step="0.01" placeholder="Amount" value={form.amount}
                 onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
          <input className="input w-20" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
          <input className="input w-40" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
          <input className="input flex-1" placeholder="Note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <button className="btn-primary" type="submit">Add</button>
        </form>
      </Card>

      <Card>
        <SectionHeader icon={Wallet}>Ledger</SectionHeader>
        {rows.isLoading ? <SkeletonRows rows={5} cols={4} /> :
         (rows.data?.length ?? 0) === 0 ? (
          <EmptyState icon={Wallet} title="No cash flows yet" hint="Add an opening balance deposit to start." />
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.id} className="border-b border-hairline">
                  <td className="py-2 text-slate-500">{r.date}</td>
                  <td className="py-2">{r.type}</td>
                  <td className="py-2 font-mono tnum text-right">{formatMoney(r.amount, r.currency)}</td>
                  <td className="py-2 text-slate-400">{r.note}</td>
                  <td className="py-2 text-right">
                    <button onClick={() => del.mutate(r.id)} aria-label="Delete" className="text-slate-400 hover:text-loss">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
```

Match the real currency hook import (grep how `Dashboard.jsx` reads `currency`; replace the `useCurrency` line accordingly). Reuse `.input`/`.btn-primary` classes from `index.css`.

- [ ] **Step 3: Add the route + nav**

`frontend/src/App.jsx`: add `import Cash from "./pages/Cash";` (with the other page imports) and `<Route path="/cash" element={<Cash />} />` in the main route group (near `App.jsx:299`).
`frontend/src/components/Sidebar.jsx`: add `Wallet` to the lucide import and `{ to: "/cash", label: "Cash", icon: Wallet }` to the `links` array (after Transactions, `Sidebar.jsx:10`).

- [ ] **Step 4: Render smoke test `frontend/src/pages/Cash.test.jsx`**

```jsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Cash from "./Cash";

// Mock the api module so no network is hit
vi.mock("../api", () => ({
  fetchCash: () => Promise.resolve([]),
  fetchCashBalance: () => Promise.resolve({ total: 0, total_accrued: 0, by_currency: {} }),
  createCash: vi.fn(), deleteCash: vi.fn(),
}));

it("Cash page mounts and shows the ledger empty state", async () => {
  const qc = new QueryClient();
  render(<QueryClientProvider client={qc}><Cash /></QueryClientProvider>);
  expect(await screen.findByText(/No cash flows yet/i)).toBeInTheDocument();
});
```

If `Cash.jsx` imports a currency context that throws without a provider, mock it too (add to the `vi.mock` block) or default `currency` safely.

- [ ] **Step 5: Run tests + build**

Run: `cd frontend && npx vitest run src/pages/Cash.test.jsx` → PASS.
Run: `cd frontend && npm run build` → succeeds (route/import resolve).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/pages/Cash.jsx frontend/src/pages/Cash.test.jsx frontend/src/App.jsx frontend/src/components/Sidebar.jsx
git commit -m "feat(cash): Cash page (balance + ledger CRUD), route and nav"
```

---

### Task 12: Interest sub-section on the Cash page

**Files:**
- Modify: `frontend/src/pages/Cash.jsx`

**Interfaces:**
- Consumes: `fetchInterestRates`, `saveInterestRates` from `../api`.
- Produces: per-currency rate rows (enabled toggle + annual-rate % input + start date) that persist.

- [ ] **Step 1: Add an Interest section to `Cash.jsx`**

Add below the Ledger card:

```jsx
      <Card>
        <SectionHeader icon={Percent}>Interest (T212-style accrual)</SectionHeader>
        <InterestRates currency={currency} />
      </Card>
```

and the component (same file or a sibling), using react-query:

```jsx
function InterestRates() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cash-rates"], queryFn: fetchInterestRates });
  const [draft, setDraft] = useState(null);
  const rows = draft ?? (q.data ?? []);
  const save = useMutation({
    mutationFn: saveInterestRates,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["cash-rates"] }); qc.invalidateQueries({ queryKey: ["cash-balance"] }); qc.invalidateQueries({ queryKey: ["summary"] }); setDraft(null); },
  });
  const set = (i, patch) => setDraft(rows.map((r, j) => j === i ? { ...r, ...patch } : r));
  const addRow = () => setDraft([...rows, { currency: "USD", annual_rate: 0, enabled: true, start_date: null }]);

  if (q.isLoading) return <SkeletonRows rows={2} cols={3} />;
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <input className="input w-20" value={r.currency} onChange={(e) => set(i, { currency: e.target.value.toUpperCase() })} />
          <input className="input w-24" type="number" step="0.01" value={(r.annual_rate * 100).toFixed(2)}
                 onChange={(e) => set(i, { annual_rate: Number(e.target.value) / 100 })} /> <span className="text-xs text-slate-400">% p.a.</span>
          <label className="text-xs flex items-center gap-1">
            <input type="checkbox" checked={r.enabled} onChange={(e) => set(i, { enabled: e.target.checked })} /> enabled
          </label>
          <input className="input w-40" type="date" value={r.start_date ?? ""} onChange={(e) => set(i, { start_date: e.target.value || null })} />
        </div>
      ))}
      <div className="flex gap-2">
        <button className="btn-ghost" onClick={addRow}>+ Currency</button>
        <button className="btn-primary" disabled={!draft} onClick={() => save.mutate(rows)}>Save</button>
      </div>
    </div>
  );
}
```

Add `Percent` to the lucide import in `Cash.jsx`.

- [ ] **Step 2: Run the smoke test + build**

Run: `cd frontend && npx vitest run src/pages/Cash.test.jsx` (extend the api mock with `fetchInterestRates: () => Promise.resolve([])`, `saveInterestRates: vi.fn()`) → PASS.
Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Cash.jsx frontend/src/pages/Cash.test.jsx
git commit -m "feat(cash): per-currency interest-rate settings on the Cash page"
```

---

### Task 13: Net worth on the Dashboard hero

**Files:**
- Modify: `frontend/src/components/PortfolioHero.jsx`
- Modify: `frontend/src/components/PortfolioHero.test.jsx`

**Interfaces:**
- Consumes: `summary.net_worth`, `summary.cash`, `summary.total_value`.
- Produces: hero headline = net worth; a "Positions · Cash" split line; existing day pill unchanged (stays on positions).

- [ ] **Step 1: Update the count-up target + add the split line**

In `PortfolioHero.jsx`, change the animated value to `summary?.net_worth ?? summary?.total_value ?? 0`, keep the eyebrow but change it to "Net Worth", and under the value add a split line:

```jsx
        <div className="flex items-center gap-3 mt-1 text-xs font-mono tnum text-slate-500">
          <span>Positions {formatMoney(summary.total_value, currency)}</span>
          <span aria-hidden="true">·</span>
          <span>Cash {formatMoney(summary.cash, currency)}</span>
        </div>
```

Keep the `DeltaPill` bound to `summary.day_change`/`day_change_percent` (day change is on positions). Update the eyebrow text from "Portfolio Value" to "Net Worth".

- [ ] **Step 2: Update the smoke test**

In `PortfolioHero.test.jsx`, add `net_worth`, `cash` to the `summary` fixture and assert the hero renders "Net Worth" and a positions/cash split:

```jsx
const summary = { total_value: 248310.55, cash: 12000, net_worth: 260310.55, /* ...existing fields... */
  total_invested: 190000, total_pnl: 58310.55, total_pnl_percent: 30.7, total_dividends: 2100,
  holdings_count: 23, day_change: 5820.12, day_change_percent: 2.41 };

it("renders net worth and the positions/cash split", () => {
  render(<PortfolioHero summary={summary} loading={false} currency="USD" series={[]} />);
  expect(screen.getByText(/Net Worth/i)).toBeInTheDocument();
  expect(screen.getByText(/Cash/i)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests + build**

Run: `cd frontend && npx vitest run src/components/PortfolioHero.test.jsx` → PASS.
Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PortfolioHero.jsx frontend/src/components/PortfolioHero.test.jsx
git commit -m "feat(cash): net worth headline + positions/cash split on the Dashboard hero"
```

---

### Task 14: Cash slice in Allocation

**Files:**
- Modify: `frontend/src/pages/Allocation.jsx` (and/or `frontend/src/components/AllocationChart.jsx`)

**Interfaces:**
- Consumes: the allocation endpoint response (now includes the `Cash` bucket from Task 9).
- Produces: cash rendered as its own slice/row.

- [ ] **Step 1: Read `Allocation.jsx` / `AllocationChart.jsx`**

Confirm how the allocation data is fetched and rendered (it maps the breakdown array to a chart + legend). Since Task 9 appended a `Cash` bucket server-side, the chart should already render it — verify it isn't filtered out client-side (e.g., a hardcoded ticker-only assumption).

- [ ] **Step 2: Ensure Cash renders and is visually distinct**

If the legend/chart color-maps by ticker, give the `Cash` bucket a neutral slate color so it reads as non-equity. Apply the minimal change needed (a color lookup fallback for `name === "Cash"`).

- [ ] **Step 3: Verify in build + browser**

Run: `cd frontend && npm run build` → succeeds.
With dev servers running, open `/allocation` and confirm a `Cash` slice appears after adding a deposit.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Allocation.jsx frontend/src/components/AllocationChart.jsx
git commit -m "feat(cash): render cash as an allocation slice"
```

---

## Phase 5 — QA sweep

### Task 15: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass (57 baseline + new cash tests).

- [ ] **Step 2: Frontend suite + build**

Run: `cd frontend && npx vitest run` → all pass.
Run: `cd frontend && npm run build` → succeeds.

- [ ] **Step 3: Live smoke (dev servers via `start.bat`, login `snowball-dev`)**

- Add an opening-balance deposit on `/cash`; confirm the balance card and ledger update.
- Set a USD interest rate (e.g., 4.5%, enabled); confirm accrued interest appears.
- Dashboard hero shows Net Worth = positions + cash; day pill still reflects positions.
- `/allocation` shows a Cash slice.
- Confirm no console errors and no failed `/api/cash*` calls.

- [ ] **Step 4: Regression check on returns**

Confirm Analytics returns are unchanged for a portfolio with no cash rows (fallback), and reflect deposits when present.

- [ ] **Step 5: Final commit (only if QA fixes were made)**

```bash
git add backend/ frontend/src
git commit -m "fix(cash): QA sweep polish"
```

---

## Out of Scope (later)

- CSV / T212 import of cash events (deposits/withdrawals/interest/fees) over this same model.
- Daily-compounded interest; per-currency rate history; reconciling derived accrual vs imported real interest (double-count logic).
- Cash in the tax report.
- This unblocks Feature (c) target allocation + rebalancing (task #2), which relies on cash-available.

---

## Self-Review

**Spec coverage:**
- Extend Transaction (cash types, `amount`, nullable ticker) → Task 1. ✓
- CashInterestRate table → Task 2. ✓
- Pure `cash_balance_by_currency` + lazy `accrued_interest` → Tasks 3–4. ✓
- Defensive audit of all Transaction consumers + leak guard → Task 5. ✓
- Cash CRUD + interest settings + balance endpoints → Tasks 6–7. ✓
- Net worth in summary → Task 8. ✓
- Cash asset-class in Allocation → Tasks 9 (backend) + 14 (frontend). ✓
- Returns integration behind fallback → Task 10. ✓
- Cash page + Interest sub-section → Tasks 11–12. ✓
- Dashboard net worth → Task 13. ✓
- Manual-entry-first, no import → honored (no import task; Out of Scope). ✓
- Per-currency, blended display → `convert_amount` in Tasks 7/8. ✓

**Placeholder scan:** Tasks 9, 10, 14 contain "read the real function/shape then apply this specific change" steps — these are modifications of existing complex code (`sector_breakdown`, `_build_value_cashflow_series`, `_lifetime_money_weighted`, `AllocationChart`) where the exact surrounding lines must be read at execution time; each still states the precise transformation and provides complete test code. All net-new code (models, migrations, pure functions, cash router, Cash page) is shown in full. No "TBD"/"add error handling"/"similar to Task N".

**Type consistency:** `signed_cash`, `cash_balance_by_currency(txns) -> dict`, `accrued_interest(txns, rates, as_of) -> dict`, `TRADE_TYPES`/`CASH_TYPES`, `convert_amount(amount, from_ccy, to_ccy)`, and the `/cash` endpoint shapes (`CashRow`, `RateItem`, `/cash/balance` → `{by_currency,total,total_accrued,currency}`) are used consistently across backend tasks and the frontend `api.js` helpers.
