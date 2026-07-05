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

    model_config = {"from_attributes": True}


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
        # shares/price are NOT NULL columns on Transaction (only ticker was relaxed
        # for cash rows); 0.0 is inert here since every consumer discriminates cash
        # vs trade rows by `type` membership (TRADE_TYPES/CASH_TYPES), never by
        # shares/price nullity.
        shares=0.0, price=0.0, amount=body.amount, currency=ccy,
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
