from __future__ import annotations

from collections import defaultdict
from datetime import date
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from edition import edition_from_env
from entitlements import (
    enforce_capacity_locked,
    ensure_count_limit,
    ensure_final_count_limit,
    require_capacity,
    require_writable_resource,
    resolve_entitlements,
)
from ledger_mutation import acquire_workspace_ledger_lock
from models import BrokerConnection, Portfolio, Transaction, Workspace
from portfolio_activation import clear_pending_portfolio, pending_portfolio, set_pending_portfolio
from audit import record_audit_event
from broker_sources import portfolio_brokers
from tenancy import (
    RequestContext,
    RequestContextError,
    get_request_context,
    require_csrf,
    require_portfolio,
)


router = APIRouter(prefix="/portfolios", tags=["portfolios"])


_DEMO_TRANSACTIONS = (
    {
        "ticker": None, "name": None, "type": "deposit", "shares": 0.0,
        "price": 0.0, "amount": 200_000.0, "currency": "CZK",
        "date": date(2025, 1, 2), "fx_to_czk": 1.0,
        "notes": "Sample opening balance",
    },
    {
        "ticker": "AAPL", "name": "Apple (sample)", "type": "buy", "shares": 3.0,
        "price": 180.0, "currency": "USD", "date": date(2025, 1, 6),
        "fx_to_czk": 23.0, "cash_amount": 12_420.0, "cash_currency": "CZK",
        "notes": "Sample transaction",
    },
    {
        "ticker": "MSFT", "name": "Microsoft (sample)", "type": "buy", "shares": 2.0,
        "price": 410.0, "currency": "USD", "date": date(2025, 1, 8),
        "fx_to_czk": 23.0, "cash_amount": 18_860.0, "cash_currency": "CZK",
        "notes": "Sample transaction",
    },
    {
        "ticker": "VWCE.DE", "name": "Vanguard FTSE All-World (sample)",
        "type": "buy", "shares": 4.0, "price": 120.0, "currency": "EUR",
        "date": date(2025, 1, 10), "fx_to_czk": 25.0,
        "cash_amount": 12_000.0, "cash_currency": "CZK",
        "notes": "Sample transaction",
    },
    {
        "ticker": "MSFT", "name": "Microsoft (sample)", "type": "dividend",
        "shares": 2.0, "price": 0.75, "currency": "USD",
        "date": date(2025, 3, 15), "fx_to_czk": 23.0,
        "cash_amount": 34.5, "cash_currency": "CZK",
        "notes": "Sample dividend",
    },
    {
        "ticker": "AAPL", "name": "Apple (sample)", "type": "sell", "shares": 1.0,
        "price": 210.0, "currency": "USD", "date": date(2025, 4, 2),
        "fx_to_czk": 23.0, "cash_amount": 4_830.0, "cash_currency": "CZK",
        "notes": "Sample transaction",
    },
)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = None


def _serialize(
    p: Portfolio,
    counts: dict[int, int] | None = None,
    *,
    activation_state: str = "active",
    brokers: dict[int, list[str]] | None = None,
) -> dict:
    return {
        "id": str(p.public_id),
        "name": p.name,
        "color": p.color,
        "is_default": bool(p.is_default),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "transaction_count": counts.get(p.id, 0) if counts is not None else None,
        "activation_state": activation_state,
        # Where its data comes from (broker_sources); the frontend opens a new
        # portfolio rather than mixing a second broker into this one.
        "brokers": (brokers or {}).get(p.id, []),
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
    brokers = portfolio_brokers(db, context.workspace.id)
    pending = pending_portfolio(db, context.workspace.id)
    pending_id = pending.id if pending is not None else None
    return [
        _serialize(
            portfolio,
            counts,
            activation_state="pending_import" if portfolio.id == pending_id else "active",
            brokers=brokers,
        )
        for portfolio in rows
    ]


@router.post("", dependencies=[Depends(require_capacity("portfolios", Portfolio))])
def create_portfolio(
    payload: PortfolioCreate,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Portfolio name is required")
    enforce_capacity_locked(db, context.workspace.id, None, "portfolios", Portfolio)
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


def _next_portfolio_name(db: Session, workspace_id: UUID, base: str = "My portfolio") -> str:
    names = set(db.scalars(
        select(Portfolio.name).where(Portfolio.workspace_id == workspace_id)
    ).all())
    if base not in names:
        return base
    suffix = 2
    while f"{base} {suffix}" in names:
        suffix += 1
    return f"{base} {suffix}"


@router.post("/pending-import")
def create_pending_import_portfolio(
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            select(Workspace.id)
            .where(Workspace.id == context.workspace.id)
            .with_for_update()
        ).one()
    existing = pending_portfolio(db, context.workspace.id, clean_stale=True)
    if existing is not None:
        result = _serialize(existing, {existing.id: 0}, activation_state="pending_import")
        db.commit()
        return result

    used = db.scalar(
        select(func.count()).select_from(Portfolio).where(
            Portfolio.workspace_id == context.workspace.id
        )
    ) or 0
    entitlements = resolve_entitlements(
        db,
        edition=edition_from_env(os.environ),
        workspace_id=context.workspace.id,
        env=os.environ,
    )
    ensure_count_limit(entitlements, "portfolios", used=used, increase=1)
    portfolio = Portfolio(
        workspace_id=context.workspace.id,
        name=_next_portfolio_name(db, context.workspace.id),
        is_default=used == 0,
    )
    try:
        db.add(portfolio)
        db.flush()
        set_pending_portfolio(db, portfolio)
        result = _serialize(portfolio, {portfolio.id: 0}, activation_state="pending_import")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


@router.post("/{portfolio_id}/activate")
def activate_pending_import_portfolio(
    portfolio_id: UUID,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    portfolio = _workspace_portfolio(db, context, portfolio_id)
    marked = pending_portfolio(
        db,
        context.workspace.id,
        clean_stale=True,
        require_empty=False,
    )
    if marked is None or marked.id != portfolio.id:
        db.rollback()
        raise RequestContextError(404, "resource_not_found")
    transaction_count = db.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.workspace_id == context.workspace.id,
            Transaction.portfolio_id == portfolio.id,
        )
    ) or 0
    if transaction_count:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only an empty pending portfolio can be activated")
    try:
        clear_pending_portfolio(db, portfolio)
        record_audit_event(
            db,
            actor_user_id=context.user.id,
            workspace_id=context.workspace.id,
            action="onboarding.portfolio.activated",
            target_type="portfolio",
            target_id=str(portfolio.public_id),
            metadata={"kind": "blank"},
        )
        result = _serialize(portfolio, {portfolio.id: 0}, activation_state="active")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


@router.post("/demo")
def create_demo_portfolio(
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    """Create one deterministic, removable sample portfolio for onboarding."""
    acquire_workspace_ledger_lock(db, context.workspace.id)
    existing_portfolios = db.scalar(
        select(func.count()).select_from(Portfolio).where(
            Portfolio.workspace_id == context.workspace.id
        )
    ) or 0
    if existing_portfolios:
        raise HTTPException(
            status_code=409,
            detail="A demo can only be created in an empty workspace",
        )

    entitlements = resolve_entitlements(
        db,
        edition=edition_from_env(os.environ),
        workspace_id=context.workspace.id,
        env=os.environ,
    )
    ensure_count_limit(entitlements, "portfolios", used=0, increase=1)
    workspace_transactions = db.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.workspace_id == context.workspace.id
        )
    ) or 0
    ensure_count_limit(
        entitlements,
        "transactions",
        used=workspace_transactions,
        increase=len(_DEMO_TRANSACTIONS),
    )
    ensure_final_count_limit(
        entitlements,
        "active_positions",
        current=0,
        final=3,
    )

    portfolio = Portfolio(
        workspace_id=context.workspace.id,
        name="Portfyl demo",
        color="#6D7048",
        is_default=True,
    )
    try:
        db.add(portfolio)
        db.flush()
        db.add_all([
            Transaction(
                **values,
                source="demo",
                workspace_id=context.workspace.id,
                portfolio_id=portfolio.id,
            )
            for values in _DEMO_TRANSACTIONS
        ])
        record_audit_event(
            db,
            actor_user_id=context.user.id,
            workspace_id=context.workspace.id,
            action="onboarding.demo.created",
            target_type="portfolio",
            target_id=str(portfolio.public_id),
            metadata={"transactions": len(_DEMO_TRANSACTIONS)},
        )
        db.flush()
        db.refresh(portfolio)
        result = {**_serialize(portfolio, {portfolio.id: len(_DEMO_TRANSACTIONS)}), "demo": True}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


@router.patch("/{portfolio_id}", dependencies=[Depends(require_writable_resource("portfolios", Portfolio, "portfolio_id"))])
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
    acquire_workspace_ledger_lock(db, context.workspace.id)
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
        # Task 6 moved routers.portfolio.get_summary / routers.analytics
        # ._allocation_totals to take the authorized Portfolio object rather
        # than a bare (tenant-unsafe) integer id -- these two calls are the
        # only cross-router consumers of that interface change.
        summary = get_summary(currency=currency, db=db, portfolio=portfolio)
        total_nw += summary.get("net_worth") or 0.0
        total_dc += summary.get("day_change") or 0.0

        raw = _allocation_totals(db, portfolio, display_ccy)
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
