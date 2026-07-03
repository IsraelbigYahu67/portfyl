from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from database import get_db
from models import Watchlist, WatchlistItem
from ticker_map import yf_symbol


router = APIRouter(prefix="/watchlists", tags=["watchlists"])


# -------- Schemas ----------------------------------------------------------

class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = None


class WatchlistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = None


class ItemCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=24)
    note: Optional[str] = None


# -------- Helpers ----------------------------------------------------------

def _quote(sym: str) -> dict:
    """Best-effort live quote so the watchlist row can show price + change."""
    try:
        info = yf.Ticker(yf_symbol(sym)).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        return {
            "symbol": sym,
            "name": info.get("longName") or info.get("shortName") or sym,
            "price": float(price) if price is not None else None,
            "change": float(info["regularMarketChange"]) if info.get("regularMarketChange") is not None else None,
            "change_percent": float(info["regularMarketChangePercent"]) if info.get("regularMarketChangePercent") is not None else None,
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "exchange": info.get("exchange"),
        }
    except Exception:
        return {"symbol": sym, "name": sym, "price": None, "change": None, "change_percent": None}


def _serialize_watchlist(w: Watchlist, items: list[WatchlistItem] | None = None, quotes: dict | None = None) -> dict:
    items = items or []
    return {
        "id": w.id,
        "name": w.name,
        "color": w.color,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "count": len(items),
        "items": [
            {
                "id": i.id,
                "ticker": i.ticker,
                "note": i.note,
                "quote": (quotes or {}).get(i.ticker, {"symbol": i.ticker}),
            }
            for i in items
        ],
    }


# -------- Endpoints --------------------------------------------------------

@router.get("")
def list_watchlists(db: Session = Depends(get_db)):
    """List all watchlists with their items + live quotes."""
    lists = db.query(Watchlist).order_by(Watchlist.created_at.asc()).all()
    items = db.query(WatchlistItem).all()
    by_list: dict[int, list[WatchlistItem]] = {}
    for it in items:
        by_list.setdefault(it.watchlist_id, []).append(it)

    # Fetch all distinct tickers' quotes in parallel — one network round-trip
    # per unique ticker rather than per item.
    tickers = sorted({it.ticker for it in items})
    quotes: dict[str, dict] = {}
    if tickers:
        with ThreadPoolExecutor(max_workers=min(10, len(tickers))) as ex:
            for q in ex.map(_quote, tickers):
                quotes[q["symbol"]] = q

    return [_serialize_watchlist(w, by_list.get(w.id, []), quotes) for w in lists]


@router.post("")
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Watchlist name is required")
    w = Watchlist(name=name, color=payload.color)
    db.add(w)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"A watchlist named '{name}' already exists")
    db.refresh(w)
    return _serialize_watchlist(w)


@router.patch("/{watchlist_id}")
def update_watchlist(watchlist_id: int, payload: WatchlistUpdate, db: Session = Depends(get_db)):
    w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    if payload.name is not None:
        w.name = payload.name.strip()
    if payload.color is not None:
        w.color = payload.color or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A watchlist with that name already exists")
    db.refresh(w)
    return _serialize_watchlist(w)


@router.delete("/{watchlist_id}")
def delete_watchlist(watchlist_id: int, db: Session = Depends(get_db)):
    w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist_id).delete(synchronize_session=False)
    db.delete(w)
    db.commit()
    return {"ok": True, "deleted_id": watchlist_id}


@router.post("/{watchlist_id}/items")
def add_item(watchlist_id: int, payload: ItemCreate, db: Session = Depends(get_db)):
    w = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    item = WatchlistItem(watchlist_id=watchlist_id, ticker=ticker, note=payload.note)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{ticker} is already in this watchlist")
    db.refresh(item)
    return {
        "id": item.id,
        "ticker": item.ticker,
        "note": item.note,
        "watchlist_id": watchlist_id,
        "quote": _quote(ticker),
    }


@router.delete("/{watchlist_id}/items/{item_id}")
def remove_item(watchlist_id: int, item_id: int, db: Session = Depends(get_db)):
    item = db.query(WatchlistItem).filter(
        WatchlistItem.id == item_id,
        WatchlistItem.watchlist_id == watchlist_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": item_id}
