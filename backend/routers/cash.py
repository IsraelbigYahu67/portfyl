from datetime import date as date_type
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Portfolio, Transaction, CashInterestRate
from routers.portfolios import require_portfolio
from fx import fetch_fx_to_czk, cash_amount_to_display
from cash_ledger import CASH_TYPES, cash_balance_by_currency, accrued_interest, signed_cash

router = APIRouter(prefix="/cash", tags=["cash"])


class CashCreate(BaseModel):
    # Manual entry uses the first four; the rest exist so imported rows
    # (card debits, cashback, FX legs) can be edited without a 422.
    type: str = Field(pattern="^(deposit|withdrawal|fee|interest|card_debit|cashback|fx_in|fx_out)$")
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    date: date_type
    note: Optional[str] = None


class CashRow(BaseModel):
    # Public API identifier: the row's internal integer PK is never
    # serialized -- this reads the ORM Transaction's `public_id` column.
    id: UUID
    type: str
    amount: float
    currency: str
    date: date_type
    note: Optional[str] = None
    fx_to_czk: Optional[float] = None

    model_config = {"from_attributes": True}


def _to_row(t: Transaction) -> CashRow:
    return CashRow(id=t.public_id, type=t.type, amount=t.amount, currency=t.currency,
                   date=t.date, note=t.notes, fx_to_czk=t.fx_to_czk)


def _portfolio_cash_rows(db: Session, portfolio: Portfolio):
    return db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.type.in_(list(CASH_TYPES)),
    )


@router.get("", response_model=List[CashRow])
def list_cash(db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    rows = _portfolio_cash_rows(db, portfolio).order_by(
        Transaction.date.desc(), Transaction.id.desc()
    ).all()
    return [_to_row(t) for t in rows]


@router.post("", response_model=CashRow)
def create_cash(body: CashCreate, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    ccy = body.currency.upper()
    row = Transaction(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id, ticker=None, name=None, type=body.type,
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


@router.put("/{cash_id:uuid}", response_model=CashRow)
def update_cash(cash_id: UUID, body: CashCreate, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    row = _portfolio_cash_rows(db, portfolio).filter(Transaction.public_id == cash_id).first()
    if not row:
        raise HTTPException(404, "Cash entry not found")
    ccy = body.currency.upper()
    row.type, row.amount, row.currency, row.date, row.notes = body.type, body.amount, ccy, body.date, body.note
    row.fx_to_czk = fetch_fx_to_czk(ccy, body.date)
    db.commit(); db.refresh(row)
    return _to_row(row)


@router.delete("/{cash_id:uuid}")
def delete_cash(cash_id: UUID, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    row = _portfolio_cash_rows(db, portfolio).filter(Transaction.public_id == cash_id).first()
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
def get_rates(db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    rows = db.query(CashInterestRate).filter(
        CashInterestRate.portfolio_id == portfolio.id,
        CashInterestRate.workspace_id == portfolio.workspace_id,
    ).all()
    return [RateItem(currency=r.currency, annual_rate=r.annual_rate, enabled=r.enabled,
                     start_date=r.start_date) for r in rows]


@router.put("/interest-rates", response_model=List[RateItem])
def put_rates(body: RatesPayload, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    for item in body.rates:
        ccy = item.currency.upper()
        row = (db.query(CashInterestRate)
                 .filter(CashInterestRate.portfolio_id == portfolio.id,
                         CashInterestRate.workspace_id == portfolio.workspace_id,
                         CashInterestRate.currency == ccy)
                 .first())
        if not row:
            row = CashInterestRate(workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id, currency=ccy)
            db.add(row)
        row.annual_rate, row.enabled, row.start_date = item.annual_rate, item.enabled, item.start_date
    db.commit()
    return get_rates(db, portfolio)


@router.get("/history")
def get_history(currency: str = "USD", db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    """Dated running cash-balance series in the display currency, one point per
    event date. Every cash/trade event moves the balance (buys pull cash out,
    sells/dividends/deposits push in), so the final point equals /balance's
    blended `total` minus lazy accrued interest (which has no dated event).
    Cross-currency events are converted on the same live CZK-pivot basis as
    /balance so the two endpoints reconcile."""
    disp = currency.upper()
    txns = db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
    ).all()
    events = []
    for t in txns:
        ccy, amt = signed_cash(t)
        if not amt:
            continue
        events.append((t.date, cash_amount_to_display(amt, ccy, disp)))
    events.sort(key=lambda e: e[0])

    series: List[dict] = []
    running = 0.0
    for d, amt in events:
        running += amt
        iso = d.isoformat()
        if series and series[-1]["date"] == iso:
            series[-1]["balance"] = round(running, 2)
        else:
            series.append({"date": iso, "balance": round(running, 2)})
    return {"currency": disp, "series": series}


@router.get("/balance")
def get_balance(currency: str = "USD", db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    txns = db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
    ).all()
    rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
             for r in db.query(CashInterestRate).filter(
                 CashInterestRate.portfolio_id == portfolio.id,
                 CashInterestRate.workspace_id == portfolio.workspace_id,
             ).all()}
    balances = cash_balance_by_currency(txns)
    accrued = accrued_interest(txns, rates)
    disp = currency.upper()
    by_currency, total, total_accrued = {}, 0.0, 0.0
    for ccy in set(balances) | set(accrued):
        bal, acc = balances.get(ccy, 0.0), accrued.get(ccy, 0.0)
        by_currency[ccy] = {"balance": round(bal, 2), "accrued": round(acc, 2)}
        # Blended totals convert into the display currency; by_currency stays native.
        total += cash_amount_to_display(bal, ccy, disp)
        total_accrued += cash_amount_to_display(acc, ccy, disp)
    return {"by_currency": by_currency, "total": round(total, 2),
            "total_accrued": round(total_accrued, 2), "currency": disp}
