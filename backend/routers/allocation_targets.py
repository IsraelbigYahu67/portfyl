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
