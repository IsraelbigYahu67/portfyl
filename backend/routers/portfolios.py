from __future__ import annotations

from collections import defaultdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import BrokerConnection, Portfolio, Transaction
from tenancy import (
    RequestContext,
    RequestContextError,
    get_request_context,
    require_csrf,
    require_portfolio,
)


router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = None


def _serialize(p: Portfolio, counts: dict[int, int] | None = None) -> dict:
    return {
        "id": str(p.public_id),
        "name": p.name,
        "color": p.color,
        "is_default": bool(p.is_default),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "transaction_count": counts.get(p.id, 0) if counts is not None else None,
    }


def _counts_by_portfolio(db: Session, workspace_id: UUID) -> dict[int, int]:
    rows = db.execute(
        select(Transaction.portfolio_id, func.count(Transaction.id))
        .where(Transaction.workspace_id == workspace_id)
        .group_by(Transaction.portfolio_id)
    ).all()
    return {portfolio_id: count for portfolio_id, count in rows}


def _workspace_portfolio(
    db: Session,
    context: RequestContext,
    portfolio_id: UUID,
) -> Portfolio:
    portfolio = db.scalar(
        select(Portfolio).where(
            Portfolio.workspace_id == context.workspace.id,
            Portfolio.public_id == portfolio_id,
        )
    )
    if portfolio is None:
        raise RequestContextError(404, "resource_not_found")
    return portfolio


@router.get("")
def list_portfolios(
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Portfolio)
        .where(Portfolio.workspace_id == context.workspace.id)
        .order_by(
            Portfolio.is_default.desc(),
            Portfolio.created_at,
            Portfolio.id,
        )
    ).all()
    counts = _counts_by_portfolio(db, context.workspace.id)
    return [_serialize(portfolio, counts) for portfolio in rows]


@router.post("")
def create_portfolio(
    payload: PortfolioCreate,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Portfolio name is required")
    portfolio = Portfolio(
        workspace_id=context.workspace.id,
        name=name,
        color=payload.color,
        is_default=False,
    )
    db.add(portfolio)
    try:
        db.flush()
        db.refresh(portfolio)
        result = _serialize(portfolio, {})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A portfolio named '{name}' already exists",
        )
    return result


@router.patch("/{portfolio_id}")
def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    portfolio = _workspace_portfolio(db, context, portfolio_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Portfolio name is required")
        portfolio.name = name
    if payload.color is not None:
        portfolio.color = payload.color or None
    try:
        db.flush()
        db.refresh(portfolio)
        result = _serialize(portfolio)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A portfolio with that name already exists",
        )
    return result


@router.delete("/{portfolio_id}")
def delete_portfolio(
    portfolio_id: UUID,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    portfolio = _workspace_portfolio(db, context, portfolio_id)
    total = db.scalar(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.workspace_id == context.workspace.id)
    )
    if (total or 0) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last remaining portfolio",
        )

    db.query(Transaction).filter(
        Transaction.workspace_id == context.workspace.id,
        Transaction.portfolio_id == portfolio.id,
    ).delete(synchronize_session=False)
    db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == context.workspace.id,
        BrokerConnection.portfolio_id == portfolio.id,
    ).delete(synchronize_session=False)

    was_default = bool(portfolio.is_default)
    deleted_id = str(portfolio.public_id)
    db.delete(portfolio)
    db.flush()
    if was_default:
        new_default = db.scalar(
            select(Portfolio)
            .where(Portfolio.workspace_id == context.workspace.id)
            .order_by(Portfolio.created_at, Portfolio.id)
        )
        if new_default is not None:
            new_default.is_default = True
    db.commit()
    return {"ok": True, "deleted_id": deleted_id}


@router.get("/overview")
def portfolios_overview(
    currency: str = "USD",
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Aggregate only portfolios inside the authenticated workspace."""
    from routers.analytics import _allocation_totals, _weighted
    from routers.portfolio import get_summary

    display_ccy = "CZK" if currency.upper() == "CZK" else "USD"
    rows = db.scalars(
        select(Portfolio).where(Portfolio.workspace_id == context.workspace.id)
    ).all()

    total_nw = 0.0
    total_dc = 0.0
    sectors: dict[str, float] = defaultdict(float)
    countries: dict[str, float] = defaultdict(float)
    asset_types: dict[str, float] = defaultdict(float)

    for portfolio in rows:
        summary = get_summary(currency=currency, db=db, pid=portfolio.id)
        total_nw += summary.get("net_worth") or 0.0
        total_dc += summary.get("day_change") or 0.0

        raw = _allocation_totals(db, portfolio.id, display_ccy)
        for name, value in raw["sectors"].items():
            sectors[name] += value
        for name, value in raw["countries"].items():
            countries[name] += value
        for name, value in raw["asset_types"].items():
            asset_types[name] += value

    base = total_nw - total_dc
    day_change_percent = round(total_dc / base * 100, 2) if base > 0 else None
    return {
        "currency": display_ccy,
        "total_net_worth": round(total_nw, 2),
        "total_day_change": round(total_dc, 2),
        "total_day_change_percent": day_change_percent,
        "portfolio_count": len(rows),
        "sectors": _weighted(sectors),
        "countries": _weighted(countries),
        "asset_types": _weighted(asset_types),
    }
