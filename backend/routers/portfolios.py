from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from typing import Optional

from database import get_db
from models import Portfolio, Transaction, BrokerConnection
from auth import get_current_user

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = None


def _serialize(p: Portfolio, counts: dict | None = None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "color": p.color,
        "is_default": bool(p.is_default),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "transaction_count": counts.get(p.id, 0) if counts else None,
    }


def _counts_by_portfolio(db: Session) -> dict:
    rows = (
        db.query(Transaction.portfolio_id, Transaction.id)
        .all()
    )
    out: dict[int, int] = {}
    for pid, _ in rows:
        out[pid] = out.get(pid, 0) + 1
    return out


@router.get("")
def list_portfolios(db: Session = Depends(get_db)):
    portfolios = db.query(Portfolio).order_by(Portfolio.is_default.desc(), Portfolio.created_at.asc()).all()
    counts = _counts_by_portfolio(db)
    return [_serialize(p, counts) for p in portfolios]


@router.post("")
def create_portfolio(payload: PortfolioCreate, db: Session = Depends(get_db), owner: str = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Portfolio name is required")
    p = Portfolio(name=name, color=payload.color, is_default=False, owner_id=owner)
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"A portfolio named '{name}' already exists")
    db.refresh(p)
    return _serialize(p, {})


@router.patch("/{portfolio_id}")
def update_portfolio(portfolio_id: int, payload: PortfolioUpdate, db: Session = Depends(get_db)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.color is not None:
        p.color = payload.color or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A portfolio with that name already exists")
    db.refresh(p)
    return _serialize(p)


@router.delete("/{portfolio_id}")
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if p.is_default:
        # We allow deleting any portfolio EXCEPT the last remaining one. The default
        # flag itself is migratable.
        pass
    total = db.query(Portfolio).count()
    if total <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last remaining portfolio")

    # Explicitly drop dependent rows so we don't rely on SQLite enforcing FK CASCADE
    # (it's off by default on most installs).
    db.query(Transaction).filter(Transaction.portfolio_id == portfolio_id).delete(synchronize_session=False)
    db.query(BrokerConnection).filter(BrokerConnection.portfolio_id == portfolio_id).delete(synchronize_session=False)

    was_default = p.is_default
    db.delete(p)
    db.commit()

    if was_default:
        new_default = db.query(Portfolio).order_by(Portfolio.created_at.asc()).first()
        if new_default is not None:
            new_default.is_default = True
            db.commit()

    return {"ok": True, "deleted_id": portfolio_id}


# ----------------------------------------------------------------------------
# Shared dependency: every other router uses this to resolve the active portfolio.
# ----------------------------------------------------------------------------

def require_portfolio(
    portfolio_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> int:
    """Resolve and validate the active portfolio id from the request.

    If `portfolio_id` is omitted, falls back to the default portfolio. Raises 404
    if the requested id doesn't exist. The returned id is guaranteed to belong to
    a real Portfolio row, so downstream queries can safely filter by it.
    """
    if portfolio_id is not None:
        p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")
        return p.id

    default = db.query(Portfolio).filter(Portfolio.is_default.is_(True)).first()
    if default is None:
        default = db.query(Portfolio).order_by(Portfolio.created_at.asc()).first()
    if default is None:
        # Should never happen — startup migration always creates one.
        raise HTTPException(status_code=500, detail="No portfolio exists")
    return default.id
