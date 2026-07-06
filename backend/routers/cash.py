from datetime import date as date_type
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Transaction, CashInterestRate
from routers.portfolios import require_portfolio
from fx import fetch_fx_to_czk, convert_amount
from cash_ledger import CASH_TYPES, cash_balance_by_currency, accrued_interest

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


# ---------------------------------------------------------------------------
# Interest-rate settings + per-currency balance (Task 7)
# ---------------------------------------------------------------------------


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
