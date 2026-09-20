# Cash Reconciliation (P0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish P0 of the Snowball-gap roadmap — give the user a trustworthy, user-facing current-cash flow that clearly separates the Trading 212 broker snapshot from the recorded transaction-ledger history, and surfaces a non-mutating reconciliation between the two.

**Architecture:** The backend already persists a `BrokerBalance` snapshot on every Trading 212 sync (`backend/broker_cash.py`, `backend/routers/broker.py` — uncommitted but fully tested, see Task 0). This plan adds one new read-only endpoint, `GET /cash/reconciliation`, that compares that snapshot against the existing ledger-derived total (`fx.folded_cash_display`) and returns both amounts, their difference, a fixed tolerance, and a `matched`/`different`/`unavailable` status — never merging or silently overwriting one with the other. The existing `Cash.jsx` page (currently built but unrouted) is extended with a reconciliation card that surfaces this, and the page is routed back into the app.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend/routers/cash.py), React 18 + `@tanstack/react-query` (frontend/src/pages/Cash.jsx), Vitest + Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-roadmap-design.md` — this plan implements section 3's P0 row and section 4.1 in full; later sections (4.2–4.8) are out of scope for this plan.

## Global Constraints

- The API returns a reconciliation object containing broker amount, ledger amount, difference, tolerance, source timestamps, and status (`matched`, `different`, or `unavailable`) — spec §4.1.
- The UI explains that a difference usually means incomplete history. It offers import and sync actions, never "fix automatically" — spec §4.1.
- Currency conversion occurs on the server using the existing CZK-pivot helpers (`fx.py`) — spec §6.
- Historical analytics remain transaction-ledger based; broker snapshots affect only current-value surfaces — spec §6. This plan does not touch any historical/returns calculation.
- Every page implements loading, error, empty, and populated states — spec §6.
- Local frontend test/build gate passes (`npm test`, `npm run build`) — spec §6. This plan does not touch cloud-only code, so `test:cloud`/`build:cloud` are unaffected but should still be run once at the end per project convention.

**Assumption carried into this plan:** the working tree already has substantial *uncommitted* changes unrelated to this plan (an Allocation/chart UI polish pass from a prior session: `BreakdownChart.jsx`, `PerformanceChart.jsx`, `allocationBreakdown.js`/`.test.js`, `Allocation.jsx`, `Settings.jsx`; and a split-adjustment fix mixed into `analytics.py`). This plan does not stage, commit, or otherwise touch those hunks — each task below `git add`s only the exact files it modified. Task 0 below is the one exception: it commits the pre-existing, already-tested broker-cash-snapshot foundation (`broker_cash.py`, the cash-snapshot parts of `broker.py`/`analytics.py`/`portfolio.py`, and their tests) because this plan's new endpoint directly depends on it and leaving it permanently uncommitted risks losing it.

---

### Task 0: Commit the existing broker-cash-snapshot foundation

**Files:**
- Commit (no code changes): `backend/broker_cash.py`, `backend/routers/broker.py`, `backend/tests/test_broker.py`, `backend/tests/test_broker_secrets.py`, `backend/tests/postgres/test_integration_tenancy.py`

This code already exists in the working tree, uncommitted, and its tests already pass (verified: `69 passed` across `test_cash_api.py`, `test_broker.py`, `test_broker_secrets.py`; `689 passed` for the full fast suite). It captures the Trading 212 cash/stock/net-liquidation snapshot into `BrokerBalance` on every sync, clears it on disconnect/reconnect, and hardens `get_status` against an undecryptable stored key. Task 1 below imports `current_t212_cash` from `broker_cash.py` and reads `BrokerBalance.as_of`/`updated_at`, so this needs to be committed first as its own logical unit — separate from this plan's new work, and separate from the unrelated `analytics.py`/`portfolio.py`/frontend hunks that stay uncommitted.

**Interfaces:**
- Produces: `broker_cash.current_t212_cash(db: Session, portfolio: Portfolio, display_currency: str) -> BrokerCashSnapshot | None`, where `BrokerCashSnapshot` has fields `amount: float`, `native_amount: float`, `currency: str`, `as_of: date | None`, `updated_at: datetime | None`. Task 1 consumes this directly.

- [ ] **Step 1: Confirm the tests already pass**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_cash_api.py tests/test_broker.py tests/test_broker_secrets.py -q`
Expected: all tests pass (already verified: 69 passed).

- [ ] **Step 2: Commit exactly these files**

```bash
git add backend/broker_cash.py backend/routers/broker.py backend/tests/test_broker.py backend/tests/test_broker_secrets.py backend/tests/postgres/test_integration_tenancy.py
git commit -m "feat(broker): persist current Trading 212 cash/stock snapshot on sync"
```

Do **not** `git add` `backend/routers/analytics.py`, `backend/routers/portfolio.py`, `backend/tests/test_cash_api.py`, or any frontend file here — `analytics.py`/`portfolio.py` mix this feature's `cash_source` field with the unrelated split-adjustment fix and are handled by Task 1 (which adds new, separate lines to `test_cash_api.py` only); the frontend files belong to a different, unrelated task and are left alone entirely.

---

### Task 1: Backend — `GET /cash/reconciliation` endpoint

**Files:**
- Modify: `backend/routers/cash.py`
- Test: `backend/tests/test_cash_api.py`

**Interfaces:**
- Consumes: `broker_cash.current_t212_cash(db, portfolio, display_currency) -> BrokerCashSnapshot | None` (Task 0). `fx.folded_cash_display(transactions, rates, display_ccy) -> float` (existing, unchanged).
- Produces: `routers.cash.get_reconciliation(currency: str, db: Session, portfolio: Portfolio) -> CashReconciliation`, registered as `GET /cash/reconciliation`. `CashReconciliation` fields: `currency: str`, `broker_amount: float | None`, `broker_currency: str | None`, `broker_as_of: date | None`, `broker_updated_at: str | None`, `ledger_amount: float`, `difference: float | None`, `tolerance: float`, `status: Literal["matched", "different", "unavailable"]`. Task 2 (frontend `fetchCashReconciliation`) consumes this exact shape.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_cash_api.py`, change line 4 from:

```python
from datetime import date
```

to:

```python
from datetime import date, datetime
```

Then add `get_reconciliation` to the existing `routers.cash` import (line 16-19):

```python
from routers.cash import (
    create_cash, list_cash, update_cash, delete_cash, CashCreate,
    get_rates, put_rates, get_balance, get_reconciliation, RatesPayload, RateItem,
)
```

Then add these tests after `test_summary_broker_cash_overrides_older_ledger_balance` (immediately before the `# Cash bucket in the allocation / sector breakdown` comment block):

```python
# ---------------------------------------------------------------------------
# Cash reconciliation: broker snapshot vs. recorded ledger (P0)
# ---------------------------------------------------------------------------


def test_reconciliation_unavailable_without_broker_balance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.broker_amount is None
    assert result.broker_currency is None
    assert result.broker_as_of is None
    assert result.broker_updated_at is None
    assert result.ledger_amount == pytest.approx(1000.0)
    assert result.difference is None
    assert result.tolerance == 1.0
    assert result.status == "unavailable"


def test_reconciliation_matched_within_tolerance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=1000.5,
        as_of=date(2026, 9, 20),
        updated_at=datetime(2026, 9, 20, 10, 0, 0),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.broker_amount == pytest.approx(1000.5)
    assert result.broker_currency == "USD"
    assert result.broker_as_of == date(2026, 9, 20)
    assert result.broker_updated_at == "2026-09-20T10:00:00"
    assert result.ledger_amount == pytest.approx(1000.0)
    assert result.difference == pytest.approx(0.5)
    assert result.tolerance == 1.0
    assert result.status == "matched"


def test_reconciliation_different_outside_tolerance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=1500.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.difference == pytest.approx(500.0)
    assert result.status == "different"


def test_reconciliation_zero_ledger_still_reports_broker_amount(db_session, pid, default_portfolio):
    """No cash rows at all is a legitimate ledger state (e.g. a brand-new
    broker-only portfolio) -- it must not be conflated with 'unavailable',
    which means no BROKER snapshot exists."""
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=250.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.ledger_amount == 0.0
    assert result.broker_amount == pytest.approx(250.0)
    assert result.difference == pytest.approx(250.0)
    assert result.status == "different"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_cash_api.py -k reconciliation -v`
Expected: FAIL — `ImportError: cannot import name 'get_reconciliation' from 'routers.cash'`

- [ ] **Step 3: Implement the endpoint**

In `backend/routers/cash.py`, change the import line (line 12):

```python
from fx import fetch_fx_to_czk, cash_amount_to_display
```

to:

```python
from fx import fetch_fx_to_czk, cash_amount_to_display, folded_cash_display
from broker_cash import current_t212_cash
```

Change the `typing` import (line 2) from:

```python
from typing import Optional, List
```

to:

```python
from typing import Literal, Optional, List
```

Then append this after the `get_balance` endpoint at the end of the file:

```python
# ---------------------------------------------------------------------------
# Broker vs. ledger reconciliation (P0) -- read-only, never merges or
# overwrites either source. See docs/superpowers/specs/2026-09-20-portfyl-
# snowball-gap-roadmap-design.md section 4.1.
# ---------------------------------------------------------------------------


class CashReconciliation(BaseModel):
    currency: str
    broker_amount: Optional[float] = None
    broker_currency: Optional[str] = None
    broker_as_of: Optional[date_type] = None
    broker_updated_at: Optional[str] = None
    ledger_amount: float
    difference: Optional[float] = None
    tolerance: float
    status: Literal["matched", "different", "unavailable"]


# FX pivots through CZK on different dates (the broker snapshot is priced
# today; each ledger row keeps its own historical rate) so a few cents to a
# few currency units of drift is expected even when both sources agree.
CASH_RECONCILIATION_TOLERANCE = 1.0


@router.get("/reconciliation", response_model=CashReconciliation)
def get_reconciliation(
    currency: str = "USD",
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    disp = currency.upper()
    txns = db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
    ).all()
    rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
             for r in db.query(CashInterestRate).filter(
                 CashInterestRate.portfolio_id == portfolio.id,
                 CashInterestRate.workspace_id == portfolio.workspace_id,
             ).all()}
    ledger_amount = round(folded_cash_display(txns, rates, disp), 2)

    broker = current_t212_cash(db, portfolio, disp)
    if broker is None:
        return CashReconciliation(
            currency=disp,
            ledger_amount=ledger_amount,
            tolerance=CASH_RECONCILIATION_TOLERANCE,
            status="unavailable",
        )

    difference = round(broker.amount - ledger_amount, 2)
    status = "matched" if abs(difference) <= CASH_RECONCILIATION_TOLERANCE else "different"
    return CashReconciliation(
        currency=disp,
        broker_amount=round(broker.amount, 2),
        broker_currency=broker.currency,
        broker_as_of=broker.as_of,
        broker_updated_at=broker.updated_at.isoformat() if broker.updated_at else None,
        ledger_amount=ledger_amount,
        difference=difference,
        tolerance=CASH_RECONCILIATION_TOLERANCE,
        status=status,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_cash_api.py -v`
Expected: PASS — all tests in the file, including the 4 new ones.

- [ ] **Step 5: Run the full fast backend suite to confirm no regression**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/ --ignore=tests/postgres -q`
Expected: PASS — same or higher pass count than the pre-plan baseline (689 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/cash.py backend/tests/test_cash_api.py
git commit -m "feat(cash): add non-mutating broker/ledger reconciliation endpoint"
```

---

### Task 2: Frontend — reconciliation UI on the Cash page

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/pages/Cash.jsx`
- Modify: `frontend/src/pages/Cash.test.jsx`

**Interfaces:**
- Consumes: `GET /cash/reconciliation` (Task 1) via new `fetchCashReconciliation(currency)`; existing `fetchT212Status()` and `syncT212()` from `frontend/src/api.js` (already used by `Settings.jsx`, unchanged here).
- Produces: `Cash.jsx` renders a "Current broker balance" card driven by `reconciliation.status` ∈ `{matched, different, unavailable}`. No other file depends on this new UI.

- [ ] **Step 1: Add the API client function**

In `frontend/src/api.js`, immediately after the existing `fetchCashHistory` export (line 353-354), add:

```javascript
export const fetchCashReconciliation = (currency = "USD") =>
  api.get("/cash/reconciliation", { params: { currency } }).then((r) => r.data);
```

- [ ] **Step 2: Write the failing tests**

Replace the full contents of `frontend/src/pages/Cash.test.jsx` with:

```jsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Cash from "./Cash";
import { fetchCashReconciliation, fetchT212Status } from "../api";

// Mock the api module so no network is hit. Cash.jsx reads the active display
// currency via useCurrency() from ../App, which returns null outside of
// CurrencyProvider — Cash.jsx already falls back to "USD" in that case, so no
// mock of ../App is needed here.
vi.mock("../api", () => ({
  fetchCash: () => Promise.resolve([]),
  fetchCashBalance: () => Promise.resolve({ total: 0, total_accrued: 0, by_currency: {} }),
  fetchCashHistory: () => Promise.resolve({ currency: "USD", series: [] }),
  fetchCashReconciliation: vi.fn(),
  fetchT212Status: vi.fn(),
  syncT212: vi.fn(),
  createCash: vi.fn(),
  deleteCash: vi.fn(),
  fetchInterestRates: () => Promise.resolve([]),
  saveInterestRates: vi.fn(),
}));

// Cash.jsx also calls useConfirm()/useToast(), which throw outside their
// providers. The empty-state assertion never exercises delete, so we just need
// the hooks to not throw on render: confirm resolves true, toast is a no-op.
vi.mock("../components/ui/ConfirmDialog", () => ({
  useConfirm: () => () => Promise.resolve(true),
}));
vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), dismiss: vi.fn() }),
}));

const UNAVAILABLE_RECONCILIATION = {
  currency: "USD",
  broker_amount: null,
  broker_currency: null,
  broker_as_of: null,
  broker_updated_at: null,
  ledger_amount: 0,
  difference: null,
  tolerance: 1,
  status: "unavailable",
};

function renderCash() {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <Cash />
    </QueryClientProvider>
  );
}

describe("Cash", () => {
  beforeEach(() => {
    fetchCashReconciliation.mockReset().mockResolvedValue(UNAVAILABLE_RECONCILIATION);
    fetchT212Status.mockReset().mockResolvedValue({ connected: false });
  });

  it("mounts and shows the ledger empty state", async () => {
    renderCash();
    expect(await screen.findByText(/No cash flows yet/i)).toBeInTheDocument();
  });

  it("prompts to connect Trading 212 when no broker is linked", async () => {
    renderCash();
    expect(await screen.findByText(/No broker connected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /connect trading 212/i })).toBeInTheDocument();
  });

  it("offers a sync action when connected but no snapshot exists yet", async () => {
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();
    expect(await screen.findByText(/No Trading 212 balance synced yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
  });

  it("flags a reconciliation difference with sync and import actions, never auto-fixing", async () => {
    fetchCashReconciliation.mockResolvedValue({
      currency: "USD",
      broker_amount: 1500,
      broker_currency: "USD",
      broker_as_of: "2026-09-20",
      broker_updated_at: "2026-09-20T10:00:00",
      ledger_amount: 1000,
      difference: 500,
      tolerance: 1,
      status: "different",
    });
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/Differs from your recorded history/i)).toBeInTheDocument();
    expect(screen.getByText(/usually means your recorded history is incomplete/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /import transactions/i })).toBeInTheDocument();
    expect(screen.queryByText(/fix automatically/i)).not.toBeInTheDocument();
  });

  it("shows a matched badge with no corrective action when balances agree", async () => {
    fetchCashReconciliation.mockResolvedValue({
      currency: "USD",
      broker_amount: 1000.5,
      broker_currency: "USD",
      broker_as_of: "2026-09-20",
      broker_updated_at: "2026-09-20T10:00:00",
      ledger_amount: 1000,
      difference: 0.5,
      tolerance: 1,
      status: "matched",
    });
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/Matches your recorded history/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sync now/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npm test -- run src/pages/Cash.test.jsx`
Expected: FAIL — the new assertions (`No broker connected`, `Differs from your recorded history`, etc.) find nothing, since `Cash.jsx` has no reconciliation card yet.

- [ ] **Step 4: Implement the Cash.jsx reconciliation card**

Replace the full contents of `frontend/src/pages/Cash.jsx` with:

```jsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Percent, Plus, RefreshCw, TrendingUp, Trash2, Wallet } from "lucide-react";
import { Card, SectionHeader, SkeletonRows, EmptyState, ErrorState } from "../components/ui";
import MetricCard from "../components/MetricCard";
import { formatDateTime, formatLongDate, formatMoney } from "../lib/format";
import CashBalanceChart from "../components/CashBalanceChart";
import {
  fetchCash,
  createCash,
  deleteCash,
  fetchCashBalance,
  fetchCashHistory,
  fetchCashReconciliation,
  fetchInterestRates,
  fetchT212Status,
  saveInterestRates,
  syncT212,
} from "../api";
import { useCurrency } from "../App";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";

// Types offered for manual entry; the ledger can additionally contain imported
// rows (card debits, cashback, FX conversion legs) from a Trading 212 CSV.
const CASH_TYPES = ["deposit", "withdrawal", "fee", "interest"];

const TYPE_LABEL = {
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  fee: "Fee",
  interest: "Interest",
  card_debit: "Card",
  cashback: "Cashback",
  fx_in: "FX in",
  fx_out: "FX out",
};

// Direction of each type's cash impact — mirrors backend signed_cash.
const CASH_IN = new Set(["deposit", "interest", "cashback", "fx_in"]);

function TypeBadge({ type }) {
  const inflow = CASH_IN.has(type);
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
        inflow ? "bg-gain/10 text-gain" : "bg-loss/10 text-loss"
      }`}
    >
      {TYPE_LABEL[type] || type}
    </span>
  );
}

// Broker snapshot vs. recorded ledger history are shown side by side, never
// merged — a mismatch must stay visible instead of one source silently
// winning. See docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-
// roadmap-design.md section 4.1.
const STATUS_COPY = {
  matched: {
    icon: CheckCircle2,
    tone: "text-gain",
    badge: "bg-gain/10 text-gain",
    label: "Matches your recorded history",
  },
  different: {
    icon: AlertTriangle,
    tone: "text-loss",
    badge: "bg-loss/10 text-loss",
    label: "Differs from your recorded history",
  },
};

function CashReconciliationCard({ data, isLoading, isError, onRetry, connected, currency, onSync, syncing }) {
  return (
    <Card>
      <SectionHeader icon={Wallet}>Current broker balance</SectionHeader>
      {isLoading ? (
        <SkeletonRows rows={2} cols={2} />
      ) : isError ? (
        <ErrorState message="Couldn't load your broker balance." onRetry={onRetry} />
      ) : !data || data.status === "unavailable" ? (
        <EmptyState
          icon={Wallet}
          title={connected ? "No Trading 212 balance synced yet" : "No broker connected"}
          hint={
            connected
              ? "Sync your Trading 212 connection to see your current broker balance here."
              : "Connect Trading 212 in Settings to see your current broker balance alongside your recorded cash history."
          }
          action={
            connected ? (
              <button type="button" className="btn-primary" onClick={onSync} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync now"}
              </button>
            ) : (
              <Link className="btn-primary" to="/settings?section=connections">Connect Trading 212</Link>
            )
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted">Trading 212 (broker snapshot)</p>
              <p className="text-2xl font-display font-bold tabular-nums text-ink">
                {formatMoney(data.broker_amount, currency)}
              </p>
              {data.broker_as_of && (
                <p className="text-xs text-muted mt-1">
                  As of {formatLongDate(data.broker_as_of)}
                  {data.broker_updated_at && ` · synced ${formatDateTime(data.broker_updated_at)}`}
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-muted">Recorded ledger history</p>
              <p className="text-2xl font-display font-bold tabular-nums text-ink">
                {formatMoney(data.ledger_amount, currency)}
              </p>
            </div>
          </div>

          <div className={`mt-4 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm ${STATUS_COPY[data.status].badge}`}>
            {(() => {
              const StatusIcon = STATUS_COPY[data.status].icon;
              return <StatusIcon size={16} className={STATUS_COPY[data.status].tone} />;
            })()}
            <span className="font-medium">{STATUS_COPY[data.status].label}</span>
            {data.status === "different" && (
              <span className="text-xs opacity-90">({formatMoney(data.difference, currency)} difference)</span>
            )}
          </div>

          {data.status === "different" && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-muted">
                A difference usually means your recorded history is incomplete, not that either number is
                wrong. Import missing transactions or sync your broker connection — Portfyl never adjusts
                the ledger automatically to force a match.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary flex items-center gap-1.5"
                  onClick={onSync}
                  disabled={syncing}
                >
                  <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                  {syncing ? "Syncing…" : "Sync now"}
                </button>
                <Link className="btn-ghost" to="/import">Import transactions</Link>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export default function Cash() {
  // useCurrency() reads CurrencyContext (provided by App's CurrencyProvider);
  // outside that provider (e.g. in tests) the context is null, so fall back to USD.
  const currency = useCurrency()?.currency || "USD";
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();

  const rows = useQuery({ queryKey: ["cash"], queryFn: fetchCash });
  const balance = useQuery({
    queryKey: ["cash-balance", currency],
    queryFn: () => fetchCashBalance(currency),
  });
  const history = useQuery({
    queryKey: ["cash-history", currency],
    queryFn: () => fetchCashHistory(currency),
  });
  const reconciliation = useQuery({
    queryKey: ["cash-reconciliation", currency],
    queryFn: () => fetchCashReconciliation(currency),
  });
  const t212Status = useQuery({ queryKey: ["t212-status"], queryFn: fetchT212Status });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cash"] });
    qc.invalidateQueries({ queryKey: ["cash-balance"] });
    qc.invalidateQueries({ queryKey: ["cash-history"] });
    qc.invalidateQueries({ queryKey: ["cash-reconciliation"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
  };

  const add = useMutation({ mutationFn: createCash, onSuccess: invalidate });
  const del = useMutation({
    mutationFn: deleteCash,
    onSuccess: () => {
      invalidate();
      toast.success("Cash entry deleted");
    },
    onError: (err) =>
      toast.error(err?.response?.data?.detail || "Failed to delete cash entry"),
  });
  const sync = useMutation({
    mutationFn: syncT212,
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["t212-status"] });
      toast.success("Synced with Trading 212");
    },
    onError: (err) => toast.error(err?.response?.data?.detail || "Sync failed"),
  });

  const handleDelete = async (r) => {
    const ok = await confirm({
      title: "Delete this cash entry?",
      message: `${r.type} of ${formatMoney(r.amount, r.currency)} on ${r.date} will be permanently removed.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (ok) del.mutate(r.id);
  };

  const [form, setForm] = useState({ type: "deposit", amount: "", currency: "CZK", date: "", note: "" });

  const submit = (e) => {
    e.preventDefault();
    add.mutate({ ...form, amount: Number(form.amount) });
    setForm((f) => ({ ...f, amount: "", note: "" }));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Cash</h1>

      <CashReconciliationCard
        data={reconciliation.data}
        isLoading={reconciliation.isLoading}
        isError={reconciliation.isError}
        onRetry={reconciliation.refetch}
        connected={t212Status.data?.connected === true}
        currency={currency}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
      />

      <MetricCard
        icon={Wallet}
        label="Recorded balance"
        value={formatMoney(balance.data?.total, currency)}
        sub={balance.data?.total_accrued > 0 ? `+${formatMoney(balance.data.total_accrued, currency)} interest` : null}
        positive={balance.data?.total_accrued > 0}
        loading={balance.isLoading}
      />

      {(history.data?.series?.length ?? 0) >= 2 && (
        <Card>
          <SectionHeader icon={TrendingUp}>Balance over time</SectionHeader>
          <CashBalanceChart data={history.data.series} currency={currency} />
        </Card>
      )}

      <Card>
        <SectionHeader icon={Plus}>Add cash flow</SectionHeader>
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end">
          <select
            className="input w-auto"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
          >
            {CASH_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            className="input w-28"
            type="number"
            step="0.01"
            placeholder="Amount"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
          <input
            className="input w-20"
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
          />
          <input
            className="input w-40"
            type="date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            required
          />
          <input
            className="input flex-1"
            placeholder="Note"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
          <button className="btn-primary" type="submit" disabled={add.isPending}>
            {add.isPending ? "Adding…" : "Add"}
          </button>
        </form>
        {add.isError && (
          <p className="text-loss text-xs mt-2">
            {add.error?.response?.data?.detail || "Failed to add cash flow"}
          </p>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Wallet}>Ledger</SectionHeader>
        {rows.isLoading ? (
          <SkeletonRows rows={5} cols={4} />
        ) : (rows.data?.length ?? 0) === 0 ? (
          <EmptyState icon={Wallet} title="No cash flows yet" hint="Add an opening balance deposit to start." />
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.id} className="border-b border-hairline">
                  <td className="py-2 text-muted">{r.date}</td>
                  <td className="py-2"><TypeBadge type={r.type} /></td>
                  <td className={`py-2 font-sans tabular-nums text-right ${CASH_IN.has(r.type) ? "text-gain" : "text-loss"}`}>
                    {CASH_IN.has(r.type) ? "+" : "−"}{formatMoney(r.amount, r.currency)}
                  </td>
                  <td className="py-2 text-muted">{r.note}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => handleDelete(r)}
                      aria-label={`Delete ${r.type} on ${r.date}`}
                      className="text-muted hover:text-red-600 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <SectionHeader icon={Percent}>Interest (T212-style accrual)</SectionHeader>
        <InterestRates currency={currency} />
      </Card>
    </div>
  );
}

function InterestRates() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cash-rates"], queryFn: fetchInterestRates });
  const [draft, setDraft] = useState(null);
  const rows = draft ?? (q.data ?? []);
  const save = useMutation({
    mutationFn: saveInterestRates,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cash-rates"] });
      qc.invalidateQueries({ queryKey: ["cash-balance"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      setDraft(null);
    },
  });
  const set = (i, patch) => setDraft(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () =>
    setDraft([...rows, { currency: "USD", annual_rate: 0, enabled: true, start_date: null }]);

  if (q.isLoading) return <SkeletonRows rows={2} cols={3} />;
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            className="input w-20"
            value={r.currency}
            onChange={(e) => set(i, { currency: e.target.value.toUpperCase() })}
          />
          <input
            className="input w-24"
            type="number"
            step="0.01"
            value={(r.annual_rate * 100).toFixed(2)}
            onChange={(e) => set(i, { annual_rate: Number(e.target.value) / 100 })}
          />{" "}
          <span className="text-xs text-muted">% p.a.</span>
          <label className="text-xs flex items-center gap-1">
            <input
              type="checkbox"
              checked={r.enabled}
              onChange={(e) => set(i, { enabled: e.target.checked })}
            />{" "}
            enabled
          </label>
          <input
            className="input w-40"
            type="date"
            value={r.start_date ?? ""}
            onChange={(e) => set(i, { start_date: e.target.value || null })}
          />
        </div>
      ))}
      <div className="flex gap-2">
        <button className="btn-ghost" onClick={addRow}>
          + Currency
        </button>
        <button className="btn-primary" disabled={!draft} onClick={() => save.mutate(rows)}>
          Save
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- run src/pages/Cash.test.jsx`
Expected: PASS — all 6 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/pages/Cash.jsx frontend/src/pages/Cash.test.jsx
git commit -m "feat(cash): show broker-vs-ledger reconciliation on the Cash page"
```

---

### Task 3: Re-route `/cash` into navigation

**Files:**
- Modify: `frontend/src/routes/authenticatedRoutes.jsx`
- Modify: `frontend/src/components/layout/navigation.js`
- Modify: `frontend/src/routes/authenticatedRoutes.test.jsx`
- Modify: `frontend/src/components/layout/navigation.test.js`
- Modify: `frontend/src/App.routing.test.jsx`
- Modify: `docs/operations/2026-09-10-public-landing.md`

**Interfaces:**
- Consumes: `Cash.jsx` (Task 2), already default-exported and route-shaped like every other page in `SHARED_AUTHENTICATED_ROUTES`.
- Produces: `/cash` reachable from `App.jsx`'s route table and visible as a "Cash" link in the "portfolio" nav group. No other task depends on this task's output.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/routes/authenticatedRoutes.test.jsx`, change line 6 from:

```javascript
  expect(SHARED_AUTHENTICATED_ROUTES.map(route => route.path)).toEqual([TRACKER_HOME, '/allocation', '/transactions', '/import', '/dividends', '/analytics', '/search', '/stock/:ticker', '/watchlists', '/assistant', '/settings']);
```

to:

```javascript
  expect(SHARED_AUTHENTICATED_ROUTES.map(route => route.path)).toEqual([TRACKER_HOME, '/allocation', '/transactions', '/cash', '/import', '/dividends', '/analytics', '/search', '/stock/:ticker', '/watchlists', '/assistant', '/settings']);
```

In `frontend/src/components/layout/navigation.test.js`, change the `"portfolio group has Dashboard, Allocation, Transactions"` test (lines 21-28) to:

```javascript
  it("portfolio group has Dashboard, Allocation, Transactions, Cash", () => {
    const portfolio = NAV_GROUPS.find((group) => group.id === "portfolio");
    expect(portfolio.items.map((item) => item.to)).toEqual([
      TRACKER_HOME,
      "/allocation",
      "/transactions",
      "/cash",
    ]);
  });
```

In `frontend/src/App.routing.test.jsx`, replace the `"does not expose Cash in navigation or at /cash"` test (lines 184-191) with:

```javascript
  it("routes to Cash and exposes it in navigation", async () => {
    renderApp("/cash");

    expect(await screen.findByText("Cash page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cash" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- run src/routes/authenticatedRoutes.test.jsx src/components/layout/navigation.test.js src/App.routing.test.jsx`
Expected: FAIL — `/cash` is missing from `SHARED_AUTHENTICATED_ROUTES` and the portfolio nav group; `App.routing.test.jsx` redirects `/cash` to `TRACKER_HOME` instead of rendering "Cash page".

- [ ] **Step 3: Re-add the route**

In `frontend/src/routes/authenticatedRoutes.jsx`, change:

```javascript
const loadTransactions = () => import('../pages/Transactions');
const loadImport = () => import('../pages/Import');
```

to:

```javascript
const loadTransactions = () => import('../pages/Transactions');
const loadCash = () => import('../pages/Cash');
const loadImport = () => import('../pages/Import');
```

And change:

```javascript
export const SHARED_AUTHENTICATED_ROUTES = Object.freeze([
  [TRACKER_HOME, loadDashboard], ['/allocation', loadAllocation], ['/transactions', loadTransactions],
  ['/import', loadImport], ['/dividends', loadDividends], ['/analytics', loadAnalytics],
  ['/search', loadSearch], ['/stock/:ticker', loadStock], ['/watchlists', loadWatchlists],
  ['/assistant', loadAssistant], ['/settings', loadSettings],
].map(([path, preload]) => ({ path, preload, Component: path === '/import' ? LazyImport : lazy(preload) })));
```

to:

```javascript
export const SHARED_AUTHENTICATED_ROUTES = Object.freeze([
  [TRACKER_HOME, loadDashboard], ['/allocation', loadAllocation], ['/transactions', loadTransactions],
  ['/cash', loadCash], ['/import', loadImport], ['/dividends', loadDividends], ['/analytics', loadAnalytics],
  ['/search', loadSearch], ['/stock/:ticker', loadStock], ['/watchlists', loadWatchlists],
  ['/assistant', loadAssistant], ['/settings', loadSettings],
].map(([path, preload]) => ({ path, preload, Component: path === '/import' ? LazyImport : lazy(preload) })));
```

- [ ] **Step 4: Re-add the nav entry**

In `frontend/src/components/layout/navigation.js`, add `Wallet` to the `lucide-react` import:

```javascript
import {
  Activity,
  ArrowLeftRight,
  Bot,
  CalendarDays,
  LayoutDashboard,
  PieChart,
  Search,
  Settings as SettingsIcon,
  Star,
  Upload,
  Wallet,
} from "lucide-react";
```

And change the `"portfolio"` group's `items`:

```javascript
    items: [
      { to: TRACKER_HOME, label: "Dashboard", icon: LayoutDashboard },
      { to: "/allocation", label: "Allocation", icon: PieChart },
      { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
    ],
```

to:

```javascript
    items: [
      { to: TRACKER_HOME, label: "Dashboard", icon: LayoutDashboard },
      { to: "/allocation", label: "Allocation", icon: PieChart },
      { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
      { to: "/cash", label: "Cash", icon: Wallet },
    ],
```

- [ ] **Step 5: Update the operations doc**

In `docs/operations/2026-09-10-public-landing.md`, change:

```
`/dashboard`, `/overview`, `/allocation`, `/transactions`, `/import`,
`/dividends`, `/analytics`, `/search`, `/stock`, `/watchlists`, `/assistant`,
`/settings`, `/pricing`, `/login`, `/register`, `/verify-email`, `/forgot-password`.
```

to:

```
`/dashboard`, `/overview`, `/allocation`, `/transactions`, `/cash`, `/import`,
`/dividends`, `/analytics`, `/search`, `/stock`, `/watchlists`, `/assistant`,
`/settings`, `/pricing`, `/login`, `/register`, `/verify-email`, `/forgot-password`.

**Follow-up (2026-09-20):** `/cash` was re-added to the app's route table
(Cash is a first-class page again, see the 2026-09-20 cash-reconciliation
plan). The Cloudflare Access application's protected-path list is configured
in the Cloudflare dashboard, not in this repo — it must be updated by hand to
match this list before `/cash` will load in production.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npm test -- run src/routes/authenticatedRoutes.test.jsx src/components/layout/navigation.test.js src/App.routing.test.jsx`
Expected: PASS — all tests in all three files.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/authenticatedRoutes.jsx frontend/src/components/layout/navigation.js frontend/src/routes/authenticatedRoutes.test.jsx frontend/src/components/layout/navigation.test.js frontend/src/App.routing.test.jsx docs/operations/2026-09-10-public-landing.md
git commit -m "feat(cash): re-route /cash into navigation now that it shows reconciliation"
```

---

### Task 4: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Full backend fast suite**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/ --ignore=tests/postgres -q`
Expected: PASS, no fewer than 693 passed (689 baseline + 4 new reconciliation tests).

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS, all files green.

- [ ] **Step 3: Frontend build (local edition)**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors.

- [ ] **Step 4: Manual browser check**

Start `start.bat` (or the already-running dev servers), open `http://localhost:5173`, log in, and open `/cash` via the sidebar "Cash" link. Confirm:
- With no Trading 212 connection: an empty state with a "Connect Trading 212" link to Settings.
- After connecting + syncing a Trading 212 account (or by inserting a `BrokerBalance` row directly for a quick check): the broker amount, ledger amount, freshness timestamp, and a matched/different badge all render; a "different" state shows "Sync now" and "Import transactions", with no auto-fix control anywhere.
- The existing ledger CRUD (add/delete cash flow) and interest-rate settings sections still work unchanged.

- [ ] **Step 5: Report status**

Summarize which of Task 0–3's commits landed and the verification results back to the user; do not push.
