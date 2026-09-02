from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db
from models import Portfolio, TradeNote, Transaction
from routers.portfolios import require_portfolio

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteUpsert(BaseModel):
    content: str
    tags: Optional[str] = None
    sentiment: Optional[str] = None


def _find_transaction(db: Session, portfolio: Portfolio, transaction_id: UUID) -> Transaction:
    txn = db.query(Transaction).filter(
        Transaction.public_id == transaction_id,
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
    ).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


def _find_note(db: Session, portfolio: Portfolio, txn: Transaction) -> TradeNote | None:
    return db.query(TradeNote).filter(
        TradeNote.transaction_id == txn.id,
        TradeNote.workspace_id == portfolio.workspace_id,
    ).first()


@router.get("/transaction/{transaction_id}")
def get_note(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    txn = _find_transaction(db, portfolio, transaction_id)

    note = _find_note(db, portfolio, txn)
    if not note:
        return {"transaction_id": str(txn.public_id), "content": "", "tags": None, "sentiment": None}
    return {
        "transaction_id": str(txn.public_id),
        "content": note.content,
        "tags": note.tags,
        "sentiment": note.sentiment,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.put("/transaction/{transaction_id}")
def upsert_note(
    transaction_id: UUID,
    body: NoteUpsert,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    txn = _find_transaction(db, portfolio, transaction_id)

    if body.sentiment and body.sentiment not in ("bullish", "bearish", "neutral"):
        raise HTTPException(400, "Sentiment must be bullish, bearish, or neutral")

    note = _find_note(db, portfolio, txn)
    if note:
        note.content = body.content
        note.tags = body.tags
        note.sentiment = body.sentiment
    else:
        note = TradeNote(
            workspace_id=portfolio.workspace_id,
            transaction_id=txn.id,
            content=body.content,
            tags=body.tags,
            sentiment=body.sentiment,
        )
        db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "transaction_id": str(txn.public_id),
        "content": note.content,
        "tags": note.tags,
        "sentiment": note.sentiment,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.delete("/transaction/{transaction_id}")
def delete_note(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    txn = _find_transaction(db, portfolio, transaction_id)

    note = _find_note(db, portfolio, txn)
    if note:
        db.delete(note)
        db.commit()
    return {"status": "ok"}


@router.get("/all")
def get_all_notes(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    txns = db.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id,
        Transaction.workspace_id == portfolio.workspace_id,
    ).all()
    if not txns:
        return []
    public_id_by_internal_id = {t.id: t.public_id for t in txns}
    notes = db.query(TradeNote).filter(
        TradeNote.transaction_id.in_(list(public_id_by_internal_id.keys())),
        TradeNote.workspace_id == portfolio.workspace_id,
    ).all()
    return [
        {
            "transaction_id": str(public_id_by_internal_id[n.transaction_id]),
            "content": n.content,
            "tags": n.tags,
            "sentiment": n.sentiment,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }
        for n in notes
    ]
