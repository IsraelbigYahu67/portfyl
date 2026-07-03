from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db
from models import TradeNote, Transaction
from routers.portfolios import require_portfolio

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteUpsert(BaseModel):
    content: str
    tags: Optional[str] = None
    sentiment: Optional[str] = None


@router.get("/transaction/{transaction_id}")
def get_note(transaction_id: int, portfolio_id: int = Depends(require_portfolio), db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.portfolio_id == portfolio_id,
    ).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")

    note = db.query(TradeNote).filter(TradeNote.transaction_id == transaction_id).first()
    if not note:
        return {"transaction_id": transaction_id, "content": "", "tags": None, "sentiment": None}
    return {
        "transaction_id": transaction_id,
        "content": note.content,
        "tags": note.tags,
        "sentiment": note.sentiment,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.put("/transaction/{transaction_id}")
def upsert_note(transaction_id: int, body: NoteUpsert, portfolio_id: int = Depends(require_portfolio), db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.portfolio_id == portfolio_id,
    ).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")

    if body.sentiment and body.sentiment not in ("bullish", "bearish", "neutral"):
        raise HTTPException(400, "Sentiment must be bullish, bearish, or neutral")

    note = db.query(TradeNote).filter(TradeNote.transaction_id == transaction_id).first()
    if note:
        note.content = body.content
        note.tags = body.tags
        note.sentiment = body.sentiment
    else:
        note = TradeNote(
            transaction_id=transaction_id,
            content=body.content,
            tags=body.tags,
            sentiment=body.sentiment,
        )
        db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "transaction_id": transaction_id,
        "content": note.content,
        "tags": note.tags,
        "sentiment": note.sentiment,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.delete("/transaction/{transaction_id}")
def delete_note(transaction_id: int, portfolio_id: int = Depends(require_portfolio), db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.portfolio_id == portfolio_id,
    ).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")

    note = db.query(TradeNote).filter(TradeNote.transaction_id == transaction_id).first()
    if note:
        db.delete(note)
        db.commit()
    return {"status": "ok"}


@router.get("/all")
def get_all_notes(portfolio_id: int = Depends(require_portfolio), db: Session = Depends(get_db)):
    txn_ids = [t.id for t in db.query(Transaction.id).filter(Transaction.portfolio_id == portfolio_id).all()]
    if not txn_ids:
        return []
    notes = db.query(TradeNote).filter(TradeNote.transaction_id.in_(txn_ids)).all()
    return [
        {
            "transaction_id": n.transaction_id,
            "content": n.content,
            "tags": n.tags,
            "sentiment": n.sentiment,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }
        for n in notes
    ]
