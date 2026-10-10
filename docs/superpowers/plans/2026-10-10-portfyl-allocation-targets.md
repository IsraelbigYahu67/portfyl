# Target Allocation (Cílová alokace) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status (2026-10-10):** Implemented on `feat/allocation-targets`. Gates: fast backend 1147, PostgreSQL/RLS 371, frontend local 720 (+1 skipped) / cloud 721, both builds, one Alembic head `0023_allocation_targets` (local dev DB upgraded, `assert_alembic_head()` OK). Final review fixed two defects: the save response was read after commit and failed under `portfyl_runtime` (RLS context is transaction-local), and an open draft survived a portfolio switch. Deviation: `tests/test_plan_schema.py` pins the head and was updated too. Logged-in browser check (Task 7 Step 2) done on 2026-10-10 at 1440x900 and 390x844: save from current weights, edits, a not-held ticker, both validation errors and currency conversion behave as planned; it found the editor unreadable on phones (squeezed inputs, page overflow from the sr-only header), fixed in `bd8341a` and re-verified. Test targets were removed from the local database afterwards.

**Goal:** Let a user save a target weight (and optional group) for each ticker in a portfolio, and show on the Allocation page how far each holding has drifted from its target.

**Architecture:** One new tenant table `allocation_targets` (per portfolio and ticker, forced RLS). A pure module `backend/allocation_targets.py` validates a target set and computes drift from the existing `/portfolio/holdings` rows. A thin router `backend/routers/allocation_targets.py` exposes `GET`/`PUT /api/allocation-targets` (stored targets, replace-all) and `GET /api/allocation-targets/drift` (targets joined with current holdings). The frontend adds a pure editor helper `frontend/src/lib/allocationTargets.js` and one component `AllocationTargets.jsx` with a view mode and an inline edit mode, mounted on the Allocation page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL forced RLS, pytest (fast SQLite suite + `tests/postgres/`), React 18, TanStack Query 5, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-roadmap-design.md` §4.2 (targets part), §5 (P1), §6 (cross-cutting acceptance), §7 (non-goals).

**Out of scope (separate plans):** rebalancing recommendations (§4.3, depends on this plan), holdings column presets and CSV export (§4.2 first paragraph), goals (§4.4), production deploy.

## Global Constraints

- Every persisted row is workspace- and portfolio-scoped: composite FK `(workspace_id, portfolio_id)` → `portfolios` with `ON DELETE CASCADE`, forced RLS policy on `portfyl.workspace_id`, grants to `portfyl_runtime`.
- `EXPECTED_ALEMBIC_HEAD` in `backend/database.py` must equal the new single head `0023_allocation_targets` in the same commit as the migration.
- Public API identifiers stay UUID `public_id`; this API is keyed by ticker and never serializes an integer id.
- Missing targets are explicit (`target_pct: null`), never silently treated as zero. An explicit `0` is a valid target.
- A target set may be saved while its sum is below 100%; it is **complete** when the sum equals 100% within **0.01 percentage points**; a sum above **100.01%** is rejected.
- Target percentages have at most two decimal places, range 0–100 inclusive. At most 200 targets per portfolio. Group names at most 40 characters.
- New API responses carrying derived financial data include `source`, `as_of` and `warnings` (spec §6).
- Current weight denominator = market value of the portfolio's active (not closed) holdings in the display currency, exactly as `/portfolio/holdings` computes `weight`. Cash is not part of the denominator.
- Historical analytics are untouched. Targets never create transactions, orders or trades (spec §7).
- The feature is shared (local and cloud) and available on every plan tier. Run `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`.
- Fast suite from `backend/`: `.venv/Scripts/python -m pytest tests/ --ignore=tests/postgres -q`. PostgreSQL suite: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait` (repo root), then from `backend/` `.venv/Scripts/python -m pytest tests/postgres/ -q`. RED before GREEN for every behavior change.
- Mutating routes take `Depends(require_csrf)`.
- UI copy is English (the app is English), neutral wording: no "buy"/"sell" advice; the column is "Value to target".
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `feat/allocation-targets`.

## Review Focus

1. **A holding without a current price** (`price_status == "missing"`, valued at 0) makes its weight and drift wrong → the drift response lists it in `missing_price_tickers`, adds the `missing_prices` warning, and the UI says drift may be off. Tests: Task 1 `test_missing_price_is_flagged`, Task 6 `shows a missing-price notice`.
2. **Ticker typed in lower case or with spaces** (`" msft "`), or the same ticker twice in different case → normalized to `MSFT`; duplicates after normalization are rejected with a readable message on both client and server. Tests: Task 1 `test_ticker_is_trimmed_and_upper_cased`, `test_duplicate_ticker_rejected`; Task 3 `test_replace_saves_normalized_targets_in_order`, `test_invalid_set_is_rejected_without_changing_saved_targets`; Task 5 `flags duplicates case-insensitively`.
3. **A target for a ticker the user does not hold yet, or has sold** → shown as not held, current 0%, drift −target, value to target positive; a sold (closed) position is never an "unassigned holding". Tests: Task 1 `test_drift_for_held_and_unheld_targets`, `test_closed_positions_count_as_not_held`; Task 6 `adds a ticker that is not held yet`.
4. **Empty portfolio or all prices missing** (total value 0) → no division by zero; current 0%, `value_to_target` null. Test: Task 1 `test_empty_portfolio_has_no_division_by_zero`.
5. **"Use current weights" with many holdings**, whose rounded weights sum to 99.99% or 100.03% → the residual goes to the largest row so the draft totals exactly 100.00% and can be saved. Test: Task 5 `fillFromCurrentWeights totals exactly 100`.

---

### Task 1: Pure validation and drift module

**Files:**
- Create: `backend/allocation_targets.py`
- Test: `backend/tests/test_allocation_targets.py`

**Interfaces:**
- Produces:
  - `class TargetSetError(ValueError)` — message is user-facing.
  - `@dataclass(frozen=True) class TargetSpec: ticker: str; target_pct: Decimal; group: str | None = None`
  - `normalize_ticker(raw: str) -> str`, `normalize_group(raw: str | None) -> str | None`
  - `target_total(targets) -> Decimal`, `is_complete(total: Decimal) -> bool`
  - `validate_target_set(targets: list[TargetSpec]) -> Decimal` (returns the total)
  - `compute_drift(holdings: list[dict], targets: list[TargetSpec]) -> dict` with keys `total_value, target_total_pct, is_complete, unassigned_pct, rows, groups, missing_price_tickers, warnings`
  - constants `MAX_TARGETS = 200`, `MAX_GROUP_LENGTH = 40`, `TARGET_SUM_TOLERANCE = Decimal("0.01")`

- [ ] **Step 1: Write the failing tests**

```python
"""Target allocation: pure validation and drift (plan 2026-10-10, Task 1)."""

from decimal import Decimal

import pytest

from allocation_targets import (
    TargetSetError,
    TargetSpec,
    compute_drift,
    is_complete,
    normalize_group,
    normalize_ticker,
    validate_target_set,
)


def spec(ticker, pct, group=None):
    return TargetSpec(ticker, Decimal(pct), group)


def holding(ticker, value, *, closed=False, price_status="live", name=None):
    return {
        "ticker": ticker,
        "name": name or ticker.title(),
        "market_value": value,
        "closed": closed,
        "price_status": price_status,
    }


class TestNormalize:
    def test_ticker_is_trimmed_and_upper_cased(self):
        assert normalize_ticker("  vwce.de ") == "VWCE.DE"
        assert normalize_ticker("brk-b") == "BRK-B"

    @pytest.mark.parametrize("raw", ["", "   ", "AA PL", "A" * 33, "AAPL;DROP"])
    def test_invalid_ticker_is_rejected(self, raw):
        with pytest.raises(TargetSetError):
            normalize_ticker(raw)

    def test_blank_group_is_none(self):
        assert normalize_group("   ") is None
        assert normalize_group(None) is None

    def test_group_is_trimmed(self):
        assert normalize_group("  Core ") == "Core"

    def test_long_group_is_rejected(self):
        with pytest.raises(TargetSetError, match="at most 40"):
            normalize_group("x" * 41)


class TestValidateTargetSet:
    def test_total_is_returned(self):
        assert validate_target_set([spec("AAPL", "60"), spec("MSFT", "40")]) == Decimal("100")

    def test_partial_and_empty_sets_are_allowed(self):
        assert validate_target_set([spec("AAPL", "50")]) == Decimal("50")
        assert validate_target_set([]) == Decimal("0")

    def test_zero_target_is_a_valid_explicit_target(self):
        assert validate_target_set([spec("AAPL", "0")]) == Decimal("0")

    def test_duplicate_ticker_rejected(self):
        with pytest.raises(TargetSetError, match="AAPL has more than one target"):
            validate_target_set([spec("AAPL", "10"), spec("AAPL", "20")])

    def test_more_than_two_decimals_rejected(self):
        with pytest.raises(TargetSetError, match="two decimal places"):
            validate_target_set([spec("AAPL", "33.333")])

    @pytest.mark.parametrize("pct", ["-1", "100.01"])
    def test_out_of_range_rejected(self, pct):
        with pytest.raises(TargetSetError, match="between 0 and 100"):
            validate_target_set([spec("AAPL", pct)])

    def test_sum_over_tolerance_rejected(self):
        with pytest.raises(TargetSetError, match="more than 100%"):
            validate_target_set([spec("A", "60"), spec("B", "40.02")])

    def test_sum_within_tolerance_allowed(self):
        assert validate_target_set([spec("A", "60"), spec("B", "40.01")]) == Decimal("100.01")

    def test_too_many_targets_rejected(self):
        with pytest.raises(TargetSetError, match="at most 200"):
            validate_target_set([spec(f"T{i}", "0") for i in range(201)])

    def test_is_complete_uses_the_tolerance(self):
        assert is_complete(Decimal("99.99")) is True
        assert is_complete(Decimal("100.01")) is True
        assert is_complete(Decimal("99.98")) is False


class TestComputeDrift:
    def test_drift_for_held_and_unheld_targets(self):
        result = compute_drift(
            [holding("AAPL", 700.0, name="Apple"), holding("TSLA", 300.0, name="Tesla")],
            [spec("AAPL", "60", "Core"), spec("MSFT", "30", "Core")],
        )

        assert result["total_value"] == 1000.0
        assert result["target_total_pct"] == 90.0
        assert result["is_complete"] is False
        assert result["unassigned_pct"] == 30.0
        assert result["warnings"] == ["targets_incomplete"]
        assert result["rows"] == [
            {"ticker": "AAPL", "name": "Apple", "group": "Core", "held": True,
             "target_pct": 60.0, "current_pct": 70.0, "drift_pct": 10.0,
             "market_value": 700.0, "value_to_target": -100.0},
            {"ticker": "MSFT", "name": None, "group": "Core", "held": False,
             "target_pct": 30.0, "current_pct": 0.0, "drift_pct": -30.0,
             "market_value": 0.0, "value_to_target": 300.0},
            {"ticker": "TSLA", "name": "Tesla", "group": None, "held": True,
             "target_pct": None, "current_pct": 30.0, "drift_pct": None,
             "market_value": 300.0, "value_to_target": None},
        ]
        assert result["groups"] == [
            {"group": "Core", "target_pct": 90.0, "current_pct": 70.0, "drift_pct": -20.0},
        ]

    def test_ticker_matching_ignores_case(self):
        result = compute_drift([holding("vwce.de", 500.0)], [spec("VWCE.DE", "100")])
        assert result["rows"][0]["held"] is True
        assert result["rows"][0]["current_pct"] == 100.0
        assert result["unassigned_pct"] == 0.0

    def test_closed_positions_count_as_not_held(self):
        result = compute_drift(
            [holding("AAPL", 0.0, closed=True), holding("MSFT", 1000.0)],
            [spec("AAPL", "50")],
        )
        aapl = result["rows"][0]
        assert aapl["held"] is False and aapl["current_pct"] == 0.0
        assert [r["ticker"] for r in result["rows"]] == ["AAPL", "MSFT"]

    def test_empty_portfolio_has_no_division_by_zero(self):
        result = compute_drift([], [spec("AAPL", "100")])
        row = result["rows"][0]
        assert result["total_value"] == 0.0
        assert row["current_pct"] == 0.0 and row["drift_pct"] == -100.0
        assert row["value_to_target"] is None
        assert result["is_complete"] is True
        assert result["warnings"] == []

    def test_missing_price_is_flagged(self):
        result = compute_drift(
            [holding("AAPL", 0.0, price_status="missing"), holding("MSFT", 1000.0)],
            [spec("AAPL", "50"), spec("MSFT", "50")],
        )
        assert result["missing_price_tickers"] == ["AAPL"]
        assert result["warnings"] == ["missing_prices"]

    def test_unassigned_holdings_are_sorted_by_value(self):
        result = compute_drift([holding("A", 100.0), holding("B", 300.0)], [])
        assert [r["ticker"] for r in result["rows"]] == ["B", "A"]
        assert result["unassigned_pct"] == 100.0

    def test_groups_keep_first_seen_order_and_skip_ungrouped_targets(self):
        result = compute_drift(
            [holding("A", 500.0), holding("B", 500.0)],
            [spec("A", "40", "Growth"), spec("C", "10"), spec("B", "50", "Income")],
        )
        assert [g["group"] for g in result["groups"]] == ["Growth", "Income"]
```

- [ ] **Step 2: Run to verify failure**

Run (from `backend/`): `.venv/Scripts/python -m pytest tests/test_allocation_targets.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'allocation_targets'`.

- [ ] **Step 3: Implement**

```python
"""Per-portfolio target allocation: validation and drift.

Snowball-gap spec 2026-09-20 §4.2; plan 2026-10-10. Pure functions -- no
database, no network. Drift is computed from `/portfolio/holdings` rows, so the
current-weight denominator is the market value of active holdings in the
display currency (cash excluded), exactly like that endpoint's `weight`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

TARGET_SUM_TOLERANCE = Decimal("0.01")
HUNDRED = Decimal("100")
MAX_TARGETS = 200
MAX_GROUP_LENGTH = 40
_CENT = Decimal("0.01")
_TICKER_RE = re.compile(r"[A-Z0-9^][A-Z0-9.\-=_^]{0,31}")


class TargetSetError(ValueError):
    """A target set that must not be saved. The message is shown to the user."""


@dataclass(frozen=True)
class TargetSpec:
    ticker: str
    target_pct: Decimal
    group: str | None = None


def normalize_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise TargetSetError(f"'{(raw or '').strip()}' is not a valid ticker.")
    return ticker


def normalize_group(raw: str | None) -> str | None:
    group = (raw or "").strip()
    if not group:
        return None
    if len(group) > MAX_GROUP_LENGTH:
        raise TargetSetError(f"Group names can be at most {MAX_GROUP_LENGTH} characters.")
    return group


def target_total(targets: Iterable[TargetSpec]) -> Decimal:
    return sum((t.target_pct for t in targets), Decimal("0"))


def is_complete(total: Decimal) -> bool:
    return abs(total - HUNDRED) <= TARGET_SUM_TOLERANCE


def validate_target_set(targets: list[TargetSpec]) -> Decimal:
    """Reject a set that must not be stored; return its total otherwise.

    A partial set (total below 100%) is allowed -- the user may save while
    still deciding. Only a total above 100% (plus tolerance) is an error.
    """
    if len(targets) > MAX_TARGETS:
        raise TargetSetError(f"A portfolio can have at most {MAX_TARGETS} targets.")
    seen: set[str] = set()
    for target in targets:
        if target.ticker in seen:
            raise TargetSetError(f"{target.ticker} has more than one target.")
        seen.add(target.ticker)
        if target.target_pct < 0 or target.target_pct > HUNDRED:
            raise TargetSetError(f"The target for {target.ticker} must be between 0 and 100%.")
        if target.target_pct != target.target_pct.quantize(_CENT):
            raise TargetSetError(
                f"The target for {target.ticker} can have at most two decimal places."
            )
    total = target_total(targets)
    if total > HUNDRED + TARGET_SUM_TOLERANCE:
        raise TargetSetError(f"Targets add up to {total}%, more than 100%.")
    return total


def compute_drift(holdings: list[dict], targets: list[TargetSpec]) -> dict:
    active = [h for h in holdings if not h.get("closed")]
    by_ticker = {str(h["ticker"]).strip().upper(): h for h in active}
    total_value = sum(float(h.get("market_value") or 0) for h in active)

    def weight(value: float) -> float:
        return value / total_value * 100 if total_value > 0 else 0.0

    rows: list[dict] = []
    group_totals: dict[str, list[float]] = {}
    targeted: set[str] = set()
    for target in targets:
        held = by_ticker.get(target.ticker)
        value = float(held.get("market_value") or 0) if held else 0.0
        target_pct = float(target.target_pct)
        current = weight(value)
        rows.append({
            "ticker": target.ticker,
            "name": held.get("name") if held else None,
            "group": target.group,
            "held": held is not None,
            "target_pct": target_pct,
            "current_pct": round(current, 2),
            "drift_pct": round(current - target_pct, 2),
            "market_value": round(value, 2),
            "value_to_target": (
                round(total_value * target_pct / 100 - value, 2) if total_value > 0 else None
            ),
        })
        targeted.add(target.ticker)
        if target.group is not None:
            sums = group_totals.setdefault(target.group, [0.0, 0.0])
            sums[0] += target_pct
            sums[1] += current

    unassigned = sorted(
        (h for ticker, h in by_ticker.items() if ticker not in targeted),
        key=lambda h: -float(h.get("market_value") or 0),
    )
    unassigned_pct = 0.0
    for held in unassigned:
        value = float(held.get("market_value") or 0)
        unassigned_pct += weight(value)
        rows.append({
            "ticker": str(held["ticker"]).strip().upper(),
            "name": held.get("name"),
            "group": None,
            "held": True,
            "target_pct": None,
            "current_pct": round(weight(value), 2),
            "drift_pct": None,
            "market_value": round(value, 2),
            "value_to_target": None,
        })

    total = target_total(targets)
    complete = is_complete(total)
    missing = sorted(t for t, h in by_ticker.items() if h.get("price_status") == "missing")
    warnings = []
    if not complete:
        warnings.append("targets_incomplete")
    if missing:
        warnings.append("missing_prices")
    return {
        "total_value": round(total_value, 2),
        "target_total_pct": float(total),
        "is_complete": complete,
        "unassigned_pct": round(unassigned_pct, 2),
        "rows": rows,
        "groups": [
            {
                "group": name,
                "target_pct": round(target_sum, 2),
                "current_pct": round(current_sum, 2),
                "drift_pct": round(current_sum - target_sum, 2),
            }
            for name, (target_sum, current_sum) in group_totals.items()
        ],
        "missing_price_tickers": missing,
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_allocation_targets.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/allocation_targets.py backend/tests/test_allocation_targets.py
git commit -m "feat(allocation): pure target validation and drift calculation"
```

---

### Task 2: Persistence — model, migration 0023, export

**Files:**
- Modify: `backend/models.py` (add `AllocationTarget` after `CashInterestRate`)
- Create: `backend/alembic/versions/0023_allocation_targets.py`
- Modify: `backend/database.py:56` (`EXPECTED_ALEMBIC_HEAD`)
- Modify: `backend/workspace_export.py` (query + `"allocation_targets"` section, `EXPORT_SCHEMA_VERSION = 5`)
- Modify: `backend/tests/test_account_export.py` (schema version asserts at lines ~153 and ~460, new test)

**Interfaces:**
- Produces: `models.AllocationTarget` with columns `id, public_id, workspace_id, portfolio_id, ticker (String(32)), group_name (String(40), nullable), target_pct (Numeric(5,2)), display_order (Integer), created_at`. Export key `allocation_targets` with items `{id, portfolio_id, ticker, group, target_pct, display_order, created_at}`.

- [ ] **Step 1: Write the failing test** — in `tests/test_account_export.py`, add `AllocationTarget` to the `from models import (...)` list, change both `assert payload["schema_version"] == 4` to `== 5`, and append:

```python
def test_export_includes_allocation_targets_for_own_portfolios(db_session, request_context):
    from decimal import Decimal

    portfolio = Portfolio(workspace_id=request_context.workspace.id, name="Targets")
    db_session.add(portfolio)
    db_session.flush()
    db_session.add(AllocationTarget(
        workspace_id=request_context.workspace.id, portfolio_id=portfolio.id,
        ticker="VWCE.DE", group_name="Core", target_pct=Decimal("62.50"), display_order=0,
    ))
    db_session.commit()

    payload = build_workspace_export(db_session, request_context, exported_at=EXPORTED_AT)

    assert payload["schema_version"] == 5
    [row] = payload["allocation_targets"]
    assert row["portfolio_id"] == str(portfolio.public_id)
    assert row["ticker"] == "VWCE.DE"
    assert row["group"] == "Core"
    assert row["target_pct"] == 62.5
    assert row["display_order"] == 0
    assert "workspace_id" not in row
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_account_export.py -q`
Expected: FAIL with `ImportError: cannot import name 'AllocationTarget'`.

- [ ] **Step 3: Implement**

`backend/models.py`, directly after the `CashInterestRate` class:

```python
class AllocationTarget(Base):
    """User-chosen target weight for one ticker in one portfolio (plan
    2026-10-10). A missing row means "no target"; a row with 0 is an explicit
    zero target. Replaced as a whole set by PUT /api/allocation-targets."""

    __tablename__ = "allocation_targets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "portfolio_id", "ticker", name="uq_allocation_target_ticker"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_allocation_target_workspace_portfolio",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "target_pct >= 0 AND target_pct <= 100",
            name="ck_allocation_target_pct_range",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String(32), nullable=False)
    group_name = Column(String(40), nullable=True)
    target_pct = Column(Numeric(5, 2), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

`backend/alembic/versions/0023_allocation_targets.py` (table/index/RLS shape copied from `0014_broker_positions.py` and `0020_broker_corporate_actions.py`):

```python
"""Add allocation_targets (target allocation, plan 2026-10-10 Task 2).

Revision ID: 0023_allocation_targets
Revises: 0022_t212_cash_stream
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_allocation_targets"
down_revision: Union[str, Sequence[str], None] = "0022_t212_cash_stream"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_TABLE = "allocation_targets"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=40), nullable=True),
        sa.Column("target_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "target_pct >= 0 AND target_pct <= 100",
            name="ck_allocation_target_pct_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_allocation_target_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "portfolio_id", "ticker", name="uq_allocation_target_ticker",
        ),
    )
    op.create_index("ix_allocation_targets_public_id", _TABLE, ["public_id"], unique=True)
    op.create_index("ix_allocation_targets_workspace_id", _TABLE, ["workspace_id"])
    op.create_index("ix_allocation_targets_portfolio_id", _TABLE, ["portfolio_id"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} TO portfyl_runtime")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {_TABLE}_id_seq TO portfyl_runtime")
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY {_TABLE}_tenant_policy ON {_TABLE}
        USING (workspace_id = {_WORKSPACE_SETTING})
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
    """)


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant_policy ON {_TABLE}")
    op.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')
    op.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {_TABLE}_id_seq FROM portfyl_runtime")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} FROM portfyl_runtime")
    for name in (
        "ix_allocation_targets_portfolio_id",
        "ix_allocation_targets_workspace_id",
        "ix_allocation_targets_public_id",
    ):
        op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
```

`backend/database.py:56`:

```python
EXPECTED_ALEMBIC_HEAD = "0023_allocation_targets"
```

`backend/workspace_export.py`: add `AllocationTarget` to the `from models import (...)` list; set `EXPORT_SCHEMA_VERSION = 5`; after the `cash_interest_rates = db.scalars(...)` query add

```python
    allocation_targets = db.scalars(
        select(AllocationTarget)
        .where(AllocationTarget.workspace_id == workspace_id)
        .order_by(
            AllocationTarget.portfolio_id,
            AllocationTarget.display_order,
            AllocationTarget.id,
        )
    ).all()
```

and after the `"cash_interest_rates": [...]` entry of the returned dict add

```python
        "allocation_targets": [
            {
                "id": str(target.public_id),
                "portfolio_id": portfolio_public_ids[target.portfolio_id],
                "ticker": target.ticker,
                "group": target.group_name,
                "target_pct": float(target.target_pct),
                "display_order": target.display_order,
                "created_at": _iso(target.created_at),
            }
            for target in allocation_targets
            if target.portfolio_id in portfolio_public_ids
        ],
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_account_export.py tests/test_database.py -q`
Expected: PASS. Then from `backend/`: `.venv/Scripts/alembic heads` → exactly one head, `0023_allocation_targets (head)`.

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/alembic/versions/0023_allocation_targets.py backend/database.py backend/workspace_export.py backend/tests/test_account_export.py
git commit -m "feat(allocation): allocation_targets table with RLS, migration 0023, export v5"
```

---

### Task 3: API router

**Files:**
- Create: `backend/routers/allocation_targets.py`
- Modify: `backend/main.py` (import + `app.include_router(allocation_targets.router, prefix="/api")` directly below `cash.router`)
- Test: `backend/tests/test_allocation_targets_api.py`

**Interfaces:**
- Consumes: Task 1 (`TargetSpec`, `TargetSetError`, `normalize_ticker`, `normalize_group`, `validate_target_set`, `compute_drift`, `is_complete`, `target_total`, `MAX_TARGETS`), Task 2 (`AllocationTarget`), `routers.portfolio.get_holdings`, `tenancy.require_portfolio`, `tenancy.require_csrf`.
- Produces:
  - `GET /api/allocation-targets` → `{"targets": [{"ticker", "group", "target_pct"}], "target_total_pct": float, "is_complete": bool}`
  - `PUT /api/allocation-targets` body `{"targets": [{"ticker": str, "target_pct": str|number, "group": str|null}]}` → same shape as GET; `422` with a string `detail` on an invalid set.
  - `GET /api/allocation-targets/drift?currency=CZK` → `compute_drift` keys plus `currency`, `as_of` (ISO UTC, `Z`), `source`.
  - Python names: `TargetItem`, `TargetsPayload`, `list_targets`, `replace_targets`, `target_drift`, `_current_holdings(db, portfolio, currency)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Target allocation API (plan 2026-10-10, Task 3). Router functions are called
directly, as elsewhere in the fast suite; the HTTP surface and tenant isolation
are covered by tests/postgres (Task 4)."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from models import AllocationTarget, Portfolio
from routers.allocation_targets import (
    TargetItem,
    TargetsPayload,
    _current_holdings,
    list_targets,
    replace_targets,
    target_drift,
)


def payload(*items):
    return TargetsPayload(targets=[TargetItem(**item) for item in items])


def save(db, portfolio, context, *items):
    return replace_targets(payload(*items), db=db, portfolio=portfolio, context=context)


def test_list_is_empty_by_default(db_session, default_portfolio):
    assert list_targets(db=db_session, portfolio=default_portfolio) == {
        "targets": [], "target_total_pct": 0.0, "is_complete": False,
    }


def test_replace_saves_normalized_targets_in_order(db_session, default_portfolio, request_context):
    result = save(
        db_session, default_portfolio, request_context,
        {"ticker": " msft ", "target_pct": "40", "group": " Core "},
        {"ticker": "AAPL", "target_pct": "60"},
    )

    assert result == {
        "targets": [
            {"ticker": "MSFT", "group": "Core", "target_pct": 40.0},
            {"ticker": "AAPL", "group": None, "target_pct": 60.0},
        ],
        "target_total_pct": 100.0,
        "is_complete": True,
    }


def test_replace_overwrites_the_previous_set(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context,
         {"ticker": "AAPL", "target_pct": "60"}, {"ticker": "MSFT", "target_pct": "40"})
    save(db_session, default_portfolio, request_context, {"ticker": "NVDA", "target_pct": "10"})

    result = list_targets(db=db_session, portfolio=default_portfolio)
    assert [t["ticker"] for t in result["targets"]] == ["NVDA"]
    assert db_session.query(AllocationTarget).count() == 1


def test_empty_payload_clears_all_targets(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "60"})
    assert save(db_session, default_portfolio, request_context)["targets"] == []


def test_invalid_set_is_rejected_without_changing_saved_targets(
    db_session, default_portfolio, request_context,
):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "50"})

    with pytest.raises(HTTPException) as exc:
        save(db_session, default_portfolio, request_context,
             {"ticker": "aapl", "target_pct": "10"}, {"ticker": "AAPL", "target_pct": "20"})

    assert exc.value.status_code == 422
    assert exc.value.detail == "AAPL has more than one target."
    assert list_targets(db=db_session, portfolio=default_portfolio)["targets"] == [
        {"ticker": "AAPL", "group": None, "target_pct": 50.0},
    ]


def test_targets_are_scoped_to_their_portfolio(db_session, default_portfolio, request_context):
    other = Portfolio(workspace_id=default_portfolio.workspace_id, name="Other")
    db_session.add(other)
    db_session.commit()

    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "100"})

    assert list_targets(db=db_session, portfolio=other)["targets"] == []


def test_drift_joins_targets_with_current_holdings(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "60"})
    holdings = [
        {"ticker": "AAPL", "name": "Apple", "market_value": 600.0, "closed": False, "price_status": "live"},
        {"ticker": "TSLA", "name": "Tesla", "market_value": 400.0, "closed": False, "price_status": "live"},
    ]

    with patch("routers.allocation_targets._current_holdings", return_value=holdings) as fake:
        result = target_drift(currency="czk", db=db_session, portfolio=default_portfolio)

    fake.assert_called_once_with(db_session, default_portfolio, "CZK")
    assert result["currency"] == "CZK"
    assert result["source"]
    assert result["as_of"].endswith("Z")
    assert result["rows"][0]["drift_pct"] == 0.0
    assert result["unassigned_pct"] == 40.0


def test_current_holdings_reads_active_holdings_only(db_session, default_portfolio):
    with patch("routers.allocation_targets.get_holdings", return_value=[]) as fake:
        assert _current_holdings(db_session, default_portfolio, "USD") == []

    fake.assert_called_once_with(
        include_closed=False, currency="USD", db=db_session, portfolio=default_portfolio,
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_allocation_targets_api.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'routers.allocation_targets'`.

- [ ] **Step 3: Implement**

`backend/routers/allocation_targets.py`:

```python
"""Target allocation per portfolio (plan 2026-10-10).

Targets are stored and replaced as one set; drift joins them with the same
holdings rows `/portfolio/holdings` returns. Nothing here creates transactions
or orders.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from allocation_targets import (
    MAX_TARGETS,
    TargetSetError,
    TargetSpec,
    compute_drift,
    is_complete,
    normalize_group,
    normalize_ticker,
    target_total,
    validate_target_set,
)
from database import get_db
from models import AllocationTarget, Portfolio
from routers.portfolio import get_holdings
from tenancy import RequestContext, require_csrf, require_portfolio

router = APIRouter(prefix="/allocation-targets", tags=["allocation-targets"])

DRIFT_SOURCE = "Imported transactions valued at the latest available quotes"


class TargetItem(BaseModel):
    ticker: str = Field(max_length=64)
    # Range and precision are checked by validate_target_set so the user gets
    # one readable message instead of a Pydantic error list.
    target_pct: Decimal
    group: Optional[str] = Field(default=None, max_length=200)


class TargetsPayload(BaseModel):
    targets: list[TargetItem] = Field(default_factory=list, max_length=MAX_TARGETS)


def _load_specs(db: Session, portfolio: Portfolio) -> list[TargetSpec]:
    rows = db.query(AllocationTarget).filter(
        AllocationTarget.portfolio_id == portfolio.id,
        AllocationTarget.workspace_id == portfolio.workspace_id,
    ).order_by(AllocationTarget.display_order, AllocationTarget.id).all()
    return [TargetSpec(r.ticker, Decimal(r.target_pct), r.group_name) for r in rows]


def _targets_response(specs: list[TargetSpec]) -> dict:
    total = target_total(specs)
    return {
        "targets": [
            {"ticker": s.ticker, "group": s.group, "target_pct": float(s.target_pct)}
            for s in specs
        ],
        "target_total_pct": float(total),
        "is_complete": is_complete(total),
    }


def _current_holdings(db: Session, portfolio: Portfolio, currency: str) -> list[dict]:
    return get_holdings(include_closed=False, currency=currency, db=db, portfolio=portfolio)


@router.get("")
def list_targets(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    return _targets_response(_load_specs(db, portfolio))


@router.put("")
def replace_targets(
    body: TargetsPayload,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    context: RequestContext = Depends(require_csrf),
):
    try:
        specs = [
            TargetSpec(normalize_ticker(item.ticker), item.target_pct, normalize_group(item.group))
            for item in body.targets
        ]
        validate_target_set(specs)
    except TargetSetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Serialize concurrent saves of the same portfolio (a no-op on SQLite).
    db.query(Portfolio).filter(Portfolio.id == portfolio.id).with_for_update().one()
    db.query(AllocationTarget).filter(
        AllocationTarget.portfolio_id == portfolio.id,
        AllocationTarget.workspace_id == portfolio.workspace_id,
    ).delete(synchronize_session=False)
    db.add_all([
        AllocationTarget(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            ticker=spec.ticker,
            group_name=spec.group,
            target_pct=spec.target_pct,
            display_order=order,
        )
        for order, spec in enumerate(specs)
    ])
    db.commit()
    return _targets_response(_load_specs(db, portfolio))


@router.get("/drift")
def target_drift(
    currency: str = "USD",
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    display_ccy = currency.upper()
    specs = _load_specs(db, portfolio)
    holdings = _current_holdings(db, portfolio, display_ccy)
    return {
        "currency": display_ccy,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": DRIFT_SOURCE,
        **compute_drift(holdings, specs),
    }
```

`backend/main.py`: add `allocation_targets` to the existing `from routers import ...` statement and, directly below `app.include_router(cash.router, prefix="/api")`:

```python
app.include_router(allocation_targets.router, prefix="/api")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_allocation_targets_api.py tests/test_allocation_targets.py -q`
Expected: PASS. Then the whole fast suite: `.venv/Scripts/python -m pytest tests/ --ignore=tests/postgres -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/allocation_targets.py backend/main.py backend/tests/test_allocation_targets_api.py
git commit -m "feat(allocation): target allocation API with drift"
```

---

### Task 4: PostgreSQL gate — RLS, runtime role, Alice/Bob matrix, constraints

**Files:**
- Modify: `backend/tests/postgres/test_rls.py` (`RLS_TABLES` += `"allocation_targets"`)
- Modify: `backend/tests/postgres/test_runtime_role.py` (`WORKSPACE_SCOPED_TABLES` += `"allocation_targets"`)
- Modify: `backend/tests/postgres/conftest.py` (`_seed_tenant` seeds one `AllocationTarget` per tenant; `_matrix_app` mounts `allocation_targets`)
- Modify: `backend/tests/postgres/matrix_cases.py` (reads, mutations, own mutation, CSRF)
- Modify: `backend/tests/postgres/test_alice_bob_matrix.py` (`_hermetic` patches `_current_holdings`)
- Create: `backend/tests/postgres/test_allocation_target_constraints.py`
- Modify: `docs/security/tenant-isolation-matrix.md` (new rows)

**Interfaces:**
- Consumes: Tasks 2–3.

- [ ] **Step 1: Write the tests**

`tests/postgres/conftest.py` — in `_seed_tenant`, add `AllocationTarget` to the local `from models import (...)` list and append to the large `db.add_all([...])` list (the one containing `TradeNote(...)`):

```python
        AllocationTarget(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            ticker="AAPL", group_name="Core", target_pct=60, display_order=0,
        ),
```

In `_matrix_app`, add `allocation_targets` to the `from routers import (...)` list and to the `for module in (...)` tuple.

`test_rls.py` `RLS_TABLES` and `test_runtime_role.py` `WORKSPACE_SCOPED_TABLES`: add `"allocation_targets"`.

`matrix_cases.py`:

```python
# PORTFOLIO_SCOPED_READS, append:
    ("allocation-targets", "/api/allocation-targets"),
    ("allocation-target-drift", "/api/allocation-targets/drift"),

# PORTFOLIO_SCOPED_MUTATIONS, append:
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}),

# OWN_MUTATIONS, append:
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}, 200),

# CSRF_GATED, append:
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}),
```

`test_alice_bob_matrix.py` `_hermetic()` tuple, append:

```python
        patch("routers.allocation_targets._current_holdings", return_value=[]),
```

`tests/postgres/test_allocation_target_constraints.py`:

```python
"""Database-level guarantees for allocation_targets (plan 2026-10-10, Task 4).

Runs as the real NOBYPASSRLS `portfyl_runtime` role. `matrix_tenants` must be
listed before `runtime_session` (see test_runtime_role.py's fixture-order note).
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from database import set_rls_context
from models import AllocationTarget, Portfolio


def _as(session: Session, tenant) -> None:
    set_rls_context(session, tenant.user_id, tenant.workspace_id)


def _portfolio_id(postgres_engine, tenant) -> int:
    with Session(postgres_engine) as owner:
        return owner.scalars(
            select(Portfolio.id).where(Portfolio.workspace_id == tenant.workspace_id)
        ).first()


def test_alice_sees_only_her_targets(matrix_tenants, runtime_session):
    _as(runtime_session, matrix_tenants.alice)
    rows = runtime_session.scalars(select(AllocationTarget)).all()
    assert len(rows) == 1
    assert rows[0].workspace_id == matrix_tenants.alice.workspace_id


def test_target_above_100_is_rejected_by_the_database(
    matrix_tenants, postgres_engine, runtime_session,
):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(AllocationTarget(
        workspace_id=matrix_tenants.alice.workspace_id, portfolio_id=portfolio_id,
        ticker="MSFT", target_pct=101, display_order=1,
    ))
    with pytest.raises(IntegrityError):
        runtime_session.flush()


def test_duplicate_ticker_is_rejected_by_the_database(
    matrix_tenants, postgres_engine, runtime_session,
):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(AllocationTarget(
        workspace_id=matrix_tenants.alice.workspace_id, portfolio_id=portfolio_id,
        ticker="AAPL", target_pct=10, display_order=1,
    ))
    with pytest.raises(IntegrityError):
        runtime_session.flush()


def test_alice_cannot_insert_into_bobs_workspace(
    matrix_tenants, postgres_engine, runtime_session,
):
    bob_portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.bob)
    _as(runtime_session, matrix_tenants.alice)
    with pytest.raises(DBAPIError):
        runtime_session.execute(
            AllocationTarget.__table__.insert().values(
                public_id="00000000-0000-4000-8000-0000000a110c",
                workspace_id=matrix_tenants.bob.workspace_id,
                portfolio_id=bob_portfolio_id,
                ticker="X", target_pct=5, display_order=0,
            )
        )


def test_deleting_a_portfolio_deletes_its_targets(matrix_tenants, postgres_engine):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    with Session(postgres_engine) as owner:
        owner.execute(delete(Portfolio).where(Portfolio.id == portfolio_id))
        owner.commit()
        remaining = owner.scalars(
            select(AllocationTarget).where(AllocationTarget.portfolio_id == portfolio_id)
        ).all()
    assert remaining == []
```

`docs/security/tenant-isolation-matrix.md`: below the `cash-interest-rates` row, add an `allocation-targets` row (`GET/PUT /api/allocation-targets`, read 200, write 200, foreign 404, tests `test_own_mutation_succeeds[allocation-targets]`, `test_foreign_portfolio_read_…[allocation-targets]`, `test_foreign_portfolio_mutation_…[allocation-targets]`, `…reads_only_her_own_workspace_rows[allocation_targets]`) and an `allocation-target-drift` row (`GET /api/allocation-targets/drift`, read 200, foreign 404, `test_foreign_portfolio_read_…[allocation-target-drift]`), keeping that table's column order.

- [ ] **Step 2: Run the new cases**

Run (repo root): `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`; then from `backend/`: `.venv/Scripts/python -m pytest tests/postgres/ -q -k "allocation"`
Expected: all collected cases PASS. If one fails, fix the cause in the Task 2–3 code (for example a missing grant or an index the schema comparison expects), never by weakening the test.

- [ ] **Step 3: Run the full PostgreSQL suite**

Run: `.venv/Scripts/python -m pytest tests/postgres/ -q`
Expected: all PASS (356 before this plan plus the new cases). The fixture's `downgrade base` exercises the 0023 downgrade.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/postgres docs/security/tenant-isolation-matrix.md
git commit -m "test(allocation): prove allocation_targets isolation under forced RLS"
```

---

### Task 5: Frontend data layer

**Files:**
- Modify: `frontend/src/api.js` (two functions after `fetchAllHoldings`)
- Create: `frontend/src/lib/allocationTargets.js`
- Test: `frontend/src/lib/allocationTargets.test.js`

**Interfaces:**
- Produces:
  - `fetchAllocationTargetDrift(currency) -> Promise<DriftResponse>`, `saveAllocationTargets(targets) -> Promise<TargetsResponse>`
  - `parseTarget(text) -> number | null | NaN` (null = empty, NaN = invalid)
  - `draftFromDrift(drift) -> DraftRow[]` where `DraftRow = { key: string, ticker: string, name: string|null, group: string, target: string, currentPct: number, isNew: boolean }`
  - `newDraftRow(index) -> DraftRow`, `draftTotal(rows) -> number`, `draftErrors(rows) -> string[]`, `toPayload(rows) -> {ticker, target_pct: string, group: string|null}[]`, `fillFromCurrentWeights(rows) -> DraftRow[]`

- [ ] **Step 1: Write the failing tests**

```js
import { describe, it, expect } from "vitest";
import {
  draftErrors,
  draftFromDrift,
  draftTotal,
  fillFromCurrentWeights,
  parseTarget,
  toPayload,
} from "./allocationTargets";

const row = (ticker, target, extra = {}) => ({
  key: ticker, ticker, name: null, group: "", target, currentPct: 0, isNew: false, ...extra,
});

describe("allocation target drafts", () => {
  it("parses targets strictly", () => {
    expect(parseTarget("")).toBeNull();
    expect(parseTarget(" 12,5 ")).toBe(12.5);
    expect(parseTarget("100")).toBe(100);
    expect(parseTarget("33.333")).toBeNaN();
    expect(parseTarget("100.5")).toBeNaN();
    expect(parseTarget("-1")).toBeNaN();
    expect(parseTarget("abc")).toBeNaN();
  });

  it("builds rows from drift, keeping no-target rows empty", () => {
    const rows = draftFromDrift({
      rows: [
        { ticker: "AAPL", name: "Apple", group: "Core", target_pct: 60, current_pct: 70 },
        { ticker: "TSLA", name: "Tesla", group: null, target_pct: null, current_pct: 30 },
      ],
    });
    expect(rows).toEqual([
      { key: "AAPL", ticker: "AAPL", name: "Apple", group: "Core", target: "60", currentPct: 70, isNew: false },
      { key: "TSLA", ticker: "TSLA", name: "Tesla", group: "", target: "", currentPct: 30, isNew: false },
    ]);
  });

  it("totals in hundredths so 0.1 + 0.2 is exactly 0.3", () => {
    expect(draftTotal([row("A", "0.1"), row("B", "0.2"), row("C", "")])).toBe(0.3);
  });

  it("flags duplicates case-insensitively and over-100 totals", () => {
    expect(draftErrors([row("AAPL", "10"), row("aapl", "20", { key: "new-1", isNew: true })]))
      .toContain("AAPL has more than one target.");
    expect(draftErrors([row("A", "60"), row("B", "40.02")]))
      .toContain("Targets add up to 100.02%, more than 100%.");
    expect(draftErrors([row("A", "60"), row("B", "40.01")])).toEqual([]);
  });

  it("flags an invalid number and a target without a ticker", () => {
    expect(draftErrors([row("A", "33.333")]))
      .toContain("The target for A must be a number from 0 to 100 with at most two decimals.");
    expect(draftErrors([row("", "10", { key: "new-1", isNew: true })]))
      .toContain("Every target needs a ticker.");
  });

  it("ignores empty rows and normalizes the payload", () => {
    expect(toPayload([
      row(" msft ", "12,5", { group: " Core " }),
      row("TSLA", ""),
      row("", "", { key: "new-1", isNew: true }),
    ])).toEqual([{ ticker: "MSFT", target_pct: "12.5", group: "Core" }]);
  });

  it("fillFromCurrentWeights totals exactly 100", () => {
    const rows = fillFromCurrentWeights([
      row("A", "", { currentPct: 33.33 }),
      row("B", "", { currentPct: 33.33 }),
      row("C", "", { currentPct: 33.33 }),
      row("D", "50", { currentPct: 0 }),
    ]);
    expect(rows.map((r) => r.target)).toEqual(["33.34", "33.33", "33.33", ""]);
    expect(draftTotal(rows)).toBe(100);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `frontend/`): `npx vitest run src/lib/allocationTargets.test.js`
Expected: FAIL, cannot resolve `./allocationTargets`.

- [ ] **Step 3: Implement**

`frontend/src/api.js`, after `fetchAllHoldings`:

```js
export const fetchAllocationTargetDrift = (currency = "USD") =>
  api.get("/allocation-targets/drift", { params: { currency } }).then((r) => r.data);
export const saveAllocationTargets = (targets) =>
  api.put("/allocation-targets", { targets }).then((r) => r.data);
```

`frontend/src/lib/allocationTargets.js`:

```js
// Editor model for per-portfolio target weights. Mirrors the rules in
// backend/allocation_targets.py so problems show before saving; the server
// re-validates everything. Targets stay text while editing and are sent as
// strings, so no float rounding happens on the way to the Decimal column.

export const TARGET_SUM_TOLERANCE = 0.01;
const MAX_GROUP_LENGTH = 40;
const PCT_RE = /^\d{1,3}(\.\d{1,2})?$/;

export function parseTarget(text) {
  const value = String(text ?? "").trim().replace(",", ".");
  if (value === "") return null;
  if (!PCT_RE.test(value)) return NaN;
  const n = Number(value);
  return n > 100 ? NaN : n;
}

const toCents = (n) => Math.round(n * 100);

export function draftFromDrift(drift) {
  return (drift?.rows || []).map((r) => ({
    key: r.ticker,
    ticker: r.ticker,
    name: r.name ?? null,
    group: r.group ?? "",
    target: r.target_pct == null ? "" : String(r.target_pct),
    currentPct: r.current_pct ?? 0,
    isNew: false,
  }));
}

export function newDraftRow(index) {
  return { key: `new-${index}`, ticker: "", name: null, group: "", target: "", currentPct: 0, isNew: true };
}

export function draftTotal(rows) {
  const cents = rows.reduce((sum, r) => {
    const v = parseTarget(r.target);
    return Number.isFinite(v) ? sum + toCents(v) : sum;
  }, 0);
  return cents / 100;
}

export function draftErrors(rows) {
  const errors = [];
  const seen = new Set();
  for (const r of rows) {
    if (String(r.target).trim() === "") continue;
    const ticker = r.ticker.trim().toUpperCase();
    if (!ticker) {
      errors.push("Every target needs a ticker.");
      continue;
    }
    if (seen.has(ticker)) errors.push(`${ticker} has more than one target.`);
    seen.add(ticker);
    if (Number.isNaN(parseTarget(r.target))) {
      errors.push(`The target for ${ticker} must be a number from 0 to 100 with at most two decimals.`);
    }
    if (r.group.trim().length > MAX_GROUP_LENGTH) {
      errors.push(`The group for ${ticker} can be at most ${MAX_GROUP_LENGTH} characters.`);
    }
  }
  const total = draftTotal(rows);
  if (total > 100 + TARGET_SUM_TOLERANCE) {
    errors.push(`Targets add up to ${total.toFixed(2)}%, more than 100%.`);
  }
  return [...new Set(errors)];
}

export function toPayload(rows) {
  return rows
    .filter((r) => String(r.target).trim() !== "" && r.ticker.trim() !== "")
    .map((r) => ({
      ticker: r.ticker.trim().toUpperCase(),
      target_pct: String(r.target).trim().replace(",", "."),
      group: r.group.trim() || null,
    }));
}

// Pre-fill targets with today's weights so the user edits from the status quo.
// Rounded weights rarely sum to exactly 100.00, so the residual goes to the
// largest row; rows not currently held are cleared.
export function fillFromCurrentWeights(rows) {
  const held = rows.filter((r) => r.currentPct > 0);
  if (!held.length) return rows;
  const residual = 10000 - held.reduce((sum, r) => sum + toCents(r.currentPct), 0);
  const largest = held.reduce((a, b) => (b.currentPct > a.currentPct ? b : a));
  return rows.map((r) => {
    if (r.currentPct <= 0) return { ...r, target: "" };
    const cents = toCents(r.currentPct) + (r === largest ? residual : 0);
    return { ...r, target: (cents / 100).toFixed(2) };
  });
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/allocationTargets.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/lib/allocationTargets.js frontend/src/lib/allocationTargets.test.js
git commit -m "feat(allocation): target editor model and API client"
```

---

### Task 6: Target allocation UI on the Allocation page

**Files:**
- Create: `frontend/src/components/AllocationTargets.jsx`
- Test: `frontend/src/components/AllocationTargets.test.jsx`
- Modify: `frontend/src/pages/Allocation.jsx` (render `<AllocationTargets currency={currency} />` directly before the `<div>` containing the "All Holdings" `<h2>`)
- Modify: `frontend/src/pages/Allocation.decisions.test.jsx` (stub the component, assert it renders)

**Interfaces:**
- Consumes: Task 5 (`fetchAllocationTargetDrift`, `saveAllocationTargets`, `draftFromDrift`, `draftErrors`, `draftTotal`, `fillFromCurrentWeights`, `newDraftRow`, `toPayload`), `formatMoney`, `formatPercent` (`lib/format.js`), `getApiErrorMessage` (`lib/apiError.js`), `AsyncSection`, `EmptyState` (`components/ui`), CSS classes `card`, `input`, `btn-primary`, `btn-ghost` (`index.css`).
- Produces: default export `AllocationTargets({ currency })` rendering `<section aria-label="Target allocation">`. Query key `["allocation-target-drift", currency]`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/AllocationTargets.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AllocationTargets from "./AllocationTargets";

const api = vi.hoisted(() => ({
  fetchAllocationTargetDrift: vi.fn(),
  saveAllocationTargets: vi.fn(),
}));
vi.mock("../api", () => api);

const DRIFT = {
  currency: "USD",
  total_value: 1000,
  target_total_pct: 90,
  is_complete: false,
  unassigned_pct: 30,
  rows: [
    { ticker: "AAPL", name: "Apple", group: "Core", held: true, target_pct: 60, current_pct: 70, drift_pct: 10, market_value: 700, value_to_target: -100 },
    { ticker: "MSFT", name: null, group: "Core", held: false, target_pct: 30, current_pct: 0, drift_pct: -30, market_value: 0, value_to_target: 300 },
    { ticker: "TSLA", name: "Tesla", group: null, held: true, target_pct: null, current_pct: 30, drift_pct: null, market_value: 300, value_to_target: null },
  ],
  groups: [{ group: "Core", target_pct: 90, current_pct: 70, drift_pct: -20 }],
  missing_price_tickers: [],
  warnings: ["targets_incomplete"],
};

function renderTargets() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AllocationTargets currency="USD" />
    </QueryClientProvider>
  );
}

describe("AllocationTargets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchAllocationTargetDrift.mockResolvedValue(DRIFT);
    api.saveAllocationTargets.mockResolvedValue({});
  });

  it("shows target, current weight and drift per holding", async () => {
    renderTargets();
    const aapl = await screen.findByRole("row", { name: /AAPL/ });
    expect(within(aapl).getByText("60.00%")).toBeInTheDocument();
    expect(within(aapl).getByText("70.00%")).toBeInTheDocument();
    expect(within(aapl).getByText("+10.00%")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /MSFT/ })).getByText(/not held/i)).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /TSLA/ })).getByText(/no target/i)).toBeInTheDocument();
    expect(screen.getByText(/90.00% of 100% assigned/i)).toBeInTheDocument();
    expect(screen.getByText(/10.00% not assigned/i)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /target groups/i })).toHaveTextContent("Core");
  });

  it("shows an empty state when no targets are set", async () => {
    api.fetchAllocationTargetDrift.mockResolvedValue({
      ...DRIFT, target_total_pct: 0, groups: [], rows: [DRIFT.rows[2]],
    });
    renderTargets();
    expect(await screen.findByText(/no target allocation yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /set targets/i }));
    expect(screen.getByLabelText("Target for TSLA")).toBeInTheDocument();
  });

  it("shows a missing-price notice", async () => {
    api.fetchAllocationTargetDrift.mockResolvedValue({
      ...DRIFT, missing_price_tickers: ["AAPL"], warnings: ["targets_incomplete", "missing_prices"],
    });
    renderTargets();
    expect(await screen.findByText(/no current price for AAPL/i)).toBeInTheDocument();
  });

  it("edits and saves targets", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.change(screen.getByLabelText("Target for AAPL"), { target: { value: "70" } });
    expect(screen.getByText(/total 100.00% of 100%/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));

    await waitFor(() => expect(api.saveAllocationTargets).toHaveBeenCalledWith([
      { ticker: "AAPL", target_pct: "70", group: "Core" },
      { ticker: "MSFT", target_pct: "30", group: "Core" },
    ]));
    await waitFor(() => expect(screen.queryByLabelText("Target for AAPL")).not.toBeInTheDocument());
  });

  it("blocks saving a total above 100%", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.change(screen.getByLabelText("Target for AAPL"), { target: { value: "80" } });
    expect(screen.getByRole("alert")).toHaveTextContent("more than 100%");
    expect(screen.getByRole("button", { name: /save targets/i })).toBeDisabled();
  });

  it("adds a ticker that is not held yet", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /add ticker/i }));
    fireEvent.change(screen.getByLabelText("Ticker for new row 1"), { target: { value: "nvda" } });
    fireEvent.change(screen.getByLabelText("Target for new row 1"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));
    await waitFor(() => expect(api.saveAllocationTargets).toHaveBeenCalledWith(
      expect.arrayContaining([{ ticker: "NVDA", target_pct: "10", group: null }]),
    ));
  });

  it("keeps the editor open and shows the server message when saving fails", async () => {
    api.saveAllocationTargets.mockRejectedValue({ response: { data: { detail: "MSFT has more than one target." } } });
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));
    expect(await screen.findByText("MSFT has more than one target.")).toBeInTheDocument();
    expect(screen.getByLabelText("Target for AAPL")).toBeInTheDocument();
  });

  it("pre-fills targets from current weights", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /use current weights/i }));
    expect(screen.getByLabelText("Target for AAPL")).toHaveValue("70.00");
    expect(screen.getByLabelText("Target for TSLA")).toHaveValue("30.00");
    expect(screen.getByLabelText("Target for MSFT")).toHaveValue("");
  });
});
```

In `Allocation.decisions.test.jsx`, add next to the other `vi.mock` calls:

```jsx
vi.mock("../components/AllocationTargets", () => ({
  default: ({ currency }) => <section aria-label="Target allocation">targets in {currency}</section>,
}));
```

and inside the `describe` block:

```jsx
  it("shows the target allocation section", async () => {
    renderPage();
    expect(await screen.findByRole("region", { name: "Target allocation" })).toHaveTextContent("USD");
  });
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/components/AllocationTargets.test.jsx src/pages/Allocation.decisions.test.jsx`
Expected: FAIL — `./AllocationTargets` cannot be resolved; the page test cannot find the region.

- [ ] **Step 3: Implement**

`frontend/src/components/AllocationTargets.jsx`:

```jsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target, Trash2 } from "lucide-react";
import { fetchAllocationTargetDrift, saveAllocationTargets } from "../api";
import { formatMoney, formatPercent } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiError";
import {
  draftErrors,
  draftFromDrift,
  draftTotal,
  fillFromCurrentWeights,
  newDraftRow,
  toPayload,
} from "../lib/allocationTargets";
import { AsyncSection, EmptyState } from "./ui";

const pct = (n) => formatPercent(n, { sign: false });
const TH = "text-left px-3 py-2 text-xs font-medium text-muted uppercase tracking-wider";
const TD = "px-3 py-2 text-sm";
const INPUT = "input w-full min-w-0 text-sm py-1";

// Highlights large drift only; direction is in the sign. Neutral on purpose:
// a target is the user's plan, not advice (spec 2026-09-20 §4.2, §7).
function driftClass(drift) {
  if (drift == null) return "text-muted";
  return Math.abs(drift) >= 5 ? "text-amber-500 font-medium" : "text-ink";
}

export default function AllocationTargets({ currency }) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState(null); // null = view mode
  const [newCount, setNewCount] = useState(0);
  const query = useQuery({
    queryKey: ["allocation-target-drift", currency],
    queryFn: () => fetchAllocationTargetDrift(currency),
  });
  const save = useMutation({
    mutationFn: (targets) => saveAllocationTargets(targets),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["allocation-target-drift"] });
      setRows(null);
    },
  });

  const drift = query.data;
  const targeted = (drift?.rows || []).filter((r) => r.target_pct != null);
  const startEditing = () => {
    save.reset();
    setRows(draftFromDrift(drift));
  };
  const update = (key, field, value) =>
    setRows((current) => current.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
  const addRow = () => {
    const next = newCount + 1;
    setNewCount(next);
    setRows((current) => [...current, newDraftRow(next)]);
  };
  const removeRow = (key) =>
    setRows((current) =>
      current.flatMap((r) => (r.key !== key ? [r] : r.isNew ? [] : [{ ...r, target: "", group: "" }]))
    );

  return (
    <section aria-label="Target allocation" className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wider">Target allocation</h2>
        {rows == null && targeted.length > 0 && (
          <button type="button" className="btn-ghost text-sm" onClick={startEditing}>
            Edit targets
          </button>
        )}
      </div>

      <AsyncSection
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => query.refetch()}
        loading={<div className="animate-pulse h-24 text-muted text-sm">Loading targets...</div>}
      >
        {rows != null ? (
          <TargetEditor
            rows={rows}
            onChange={update}
            onAdd={addRow}
            onRemove={removeRow}
            onFill={() => setRows((current) => fillFromCurrentWeights(current))}
            onCancel={() => setRows(null)}
            onSave={() => save.mutate(toPayload(rows))}
            saving={save.isPending}
            saveError={save.error ? getApiErrorMessage(save.error, "We couldn't save your targets.") : null}
          />
        ) : targeted.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No target allocation yet"
            hint="Set a target weight for each holding to see how far the portfolio has drifted from your plan."
            action={(
              <button type="button" className="btn-primary text-sm" onClick={startEditing}>
                Set targets
              </button>
            )}
          />
        ) : (
          <TargetView drift={drift} currency={currency} />
        )}
      </AsyncSection>
    </section>
  );
}

function TargetView({ drift, currency }) {
  const remaining = Math.max(0, 100 - drift.target_total_pct);
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">
        {pct(drift.target_total_pct)} of 100% assigned
        {drift.is_complete ? (
          " · complete"
        ) : (
          <span className="text-amber-500"> · {pct(remaining)} not assigned</span>
        )}
        {" · "}Weights use imported transactions at the latest quotes; cash is not included.
      </p>
      {drift.missing_price_tickers.length > 0 && (
        <p className="text-xs text-amber-500">
          No current price for {drift.missing_price_tickers.join(", ")}. These holdings are valued at 0,
          so their drift may be off.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-surface-border">
            <tr>
              <th className={TH}>Ticker</th>
              <th className={TH}>Group</th>
              <th className={`${TH} text-right`}>Target</th>
              <th className={`${TH} text-right`}>Current</th>
              <th className={`${TH} text-right`} title="Current weight minus target weight">Drift</th>
              <th className={`${TH} text-right`} title="Value change that would bring this holding to its target">
                Value to target
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {drift.rows.map((r) => (
              <tr key={r.ticker}>
                <td className={`${TD} font-mono font-bold`}>
                  {r.ticker}
                  {!r.held && <span className="ml-1.5 financial-meta font-normal text-muted">not held</span>}
                </td>
                <td className={`${TD} text-muted`}>{r.group ?? "—"}</td>
                <td className={`${TD} text-right tabular-nums`}>
                  {r.target_pct == null ? <span className="text-xs text-muted">No target</span> : pct(r.target_pct)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>{pct(r.current_pct)}</td>
                <td className={`${TD} text-right tabular-nums ${driftClass(r.drift_pct)}`}>
                  {r.drift_pct == null ? "—" : formatPercent(r.drift_pct)}
                </td>
                <td className={`${TD} text-right tabular-nums`}>
                  {r.value_to_target == null ? "—" : formatMoney(r.value_to_target, currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {drift.groups.length > 0 && (
        <ul aria-label="Target groups" className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
          {drift.groups.map((g) => (
            <li key={g.group}>
              <span className="text-ink font-medium">{g.group}</span>: target {pct(g.target_pct)} · current{" "}
              {pct(g.current_pct)} · drift {formatPercent(g.drift_pct)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TargetEditor({ rows, onChange, onAdd, onRemove, onFill, onCancel, onSave, saving, saveError }) {
  const errors = draftErrors(rows);
  const total = draftTotal(rows);
  let newIndex = 0;
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-surface-border">
            <tr>
              <th className={TH}>Ticker</th>
              <th className={TH}>Group</th>
              <th className={`${TH} text-right`}>Target %</th>
              <th className={`${TH} text-right`}>Current</th>
              <th className={TH}><span className="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {rows.map((r) => {
              const label = r.isNew ? `new row ${++newIndex}` : r.ticker;
              return (
                <tr key={r.key}>
                  <td className={`${TD} font-mono font-bold`}>
                    {r.isNew ? (
                      <input
                        className={INPUT}
                        aria-label={`Ticker for ${label}`}
                        value={r.ticker}
                        maxLength={32}
                        onChange={(e) => onChange(r.key, "ticker", e.target.value)}
                      />
                    ) : (
                      r.ticker
                    )}
                  </td>
                  <td className={TD}>
                    <input
                      className={INPUT}
                      aria-label={`Group for ${label}`}
                      value={r.group}
                      maxLength={40}
                      placeholder="Optional"
                      onChange={(e) => onChange(r.key, "group", e.target.value)}
                    />
                  </td>
                  <td className={`${TD} text-right`}>
                    <input
                      className={`${INPUT} text-right w-24`}
                      aria-label={`Target for ${label}`}
                      inputMode="decimal"
                      value={r.target}
                      placeholder="—"
                      onChange={(e) => onChange(r.key, "target", e.target.value)}
                    />
                  </td>
                  <td className={`${TD} text-right tabular-nums text-muted`}>{pct(r.currentPct)}</td>
                  <td className={TD}>
                    <button
                      type="button"
                      className="btn-ghost p-1"
                      aria-label={`Remove target for ${label}`}
                      onClick={() => onRemove(r.key)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-ghost text-sm flex items-center gap-1" onClick={onAdd}>
          <Plus size={14} /> Add ticker
        </button>
        <button type="button" className="btn-ghost text-sm" onClick={onFill}>
          Use current weights
        </button>
      </div>

      <p className="text-xs text-muted">
        Total {pct(total)} of 100%. Leave a target empty for “no target”. You can save before reaching 100%.
      </p>
      {errors.length > 0 && (
        <ul role="alert" className="text-xs text-loss space-y-1">
          {errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}
      {saveError && <p role="alert" className="text-xs text-loss">{saveError}</p>}

      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost text-sm" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        <button
          type="button"
          className="btn-primary text-sm"
          onClick={onSave}
          disabled={saving || errors.length > 0}
        >
          {saving ? "Saving..." : "Save targets"}
        </button>
      </div>
    </div>
  );
}
```

`frontend/src/pages/Allocation.jsx`: add `import AllocationTargets from "../components/AllocationTargets";` with the other component imports and, directly before the `<div>` whose `<h2>` reads "All Holdings", insert:

```jsx
      <AllocationTargets currency={currency} />
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/components/AllocationTargets.test.jsx src/pages/Allocation.decisions.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AllocationTargets.jsx frontend/src/components/AllocationTargets.test.jsx frontend/src/pages/Allocation.jsx frontend/src/pages/Allocation.decisions.test.jsx
git commit -m "feat(allocation): show and edit target allocation on the Allocation page"
```

---

### Task 7: Gates, browser check, records

**Files:**
- Modify: `docs/superpowers/plans/2026-10-10-portfyl-allocation-targets.md` (status line)
- Modify: `docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-roadmap-design.md` (one status note under §5: targets shipped, rebalancing next)

- [ ] **Step 1: Run every gate**

From `backend/`:
- `.venv/Scripts/python -m pytest tests/ --ignore=tests/postgres -q` → all pass
- `.venv/Scripts/python -m pytest tests/postgres/ -q` → all pass
- `.venv/Scripts/alembic heads` → one head `0023_allocation_targets`; `.venv/Scripts/python -c "import database; print(database.EXPECTED_ALEMBIC_HEAD)"` prints the same
- `.venv/Scripts/alembic upgrade head` against the local dev `DATABASE_URL` with the migration-owner credential; start the backend and confirm `/health` is OK (startup runs `assert_alembic_head()`)

From `frontend/`: `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud` → all pass.

- [ ] **Step 2: Browser check**

With `start.bat` running, log in at http://localhost:5173 and open Allocation:
1. Empty state → "Set targets" → "Use current weights" → total 100.00% → Save → the view shows drift ≈ 0 everywhere.
2. Edit: raise one holding by 5 pp, add a not-held ticker with 5%, lower another → Save → drift and "Value to target" update; the new row says "not held".
3. Type `33.333` → error, Save disabled; push the total to 110% → error.
4. Switch the display currency → "Value to target" changes currency, percentages stay.
5. Repeat steps 1–2 at 390×844 and 1440×900: no horizontal page scroll (the table scrolls inside its card).
Screenshots go to `artifacts/allocation-targets/` (not committed).

- [ ] **Step 3: Update records and commit**

Set this plan's status line to `**Status (YYYY-MM-DD):** Implemented. Gates: fast <n>, PostgreSQL/RLS <n>, frontend local <n> / cloud <n>, both builds, one Alembic head 0023_allocation_targets.` and add the spec note.

```bash
git add docs/superpowers/plans/2026-10-10-portfyl-allocation-targets.md docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-roadmap-design.md
git commit -m "docs(allocation): record target allocation gates"
```

- [ ] **Step 4: Integrate**

Use superpowers:finishing-a-development-branch to merge `feat/allocation-targets` into `main`. Production rollout (the Cloud Run migration Job `deploy/run-migrations.ps1` first, then the service) is a separate step the owner triggers.
