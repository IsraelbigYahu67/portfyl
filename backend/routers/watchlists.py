from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

import market_data

from database import get_db
from entitlements import require_capacity, require_writable_resource
from models import Watchlist, WatchlistItem
from tenancy import RequestContext, get_request_context
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
        info = market_data.ticker(yf_symbol(sym)).info or {}
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
        "id": str(w.public_id),
        "name": w.name,
        "color": w.color,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "count": len(items),
        "items": [
            {
                "id": str(i.public_id),
                "ticker": i.ticker,
                "note": i.note,
                "quote": (quotes or {}).get(i.ticker, {"symbol": i.ticker}),
            }
            for i in items
        ],
    }


def _find_watchlist(db: Session, context: RequestContext, watchlist_id: UUID) -> Watchlist:
    w = db.scalar(
        select(Watchlist).where(
            Watchlist.workspace_id == context.workspace.id,
            Watchlist.public_id == watchlist_id,
        )
    )
    if w is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return w


# -------- Endpoints --------------------------------------------------------

@router.get("")
def list_watchlists(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    """List this workspace's watchlists with their items + live quotes."""
    lists = db.scalars(
        select(Watchlist)
        .where(Watchlist.workspace_id == context.workspace.id)
        .order_by(Watchlist.created_at.asc())
    ).all()
    items = db.scalars(
        select(WatchlistItem).where(WatchlistItem.workspace_id == context.workspace.id)
    ).all()
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


@router.post("", dependencies=[Depends(require_capacity("watchlists", Watchlist))])
def create_watchlist(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Watchlist name is required")
    w = Watchlist(workspace_id=context.workspace.id, name=name, color=payload.color)
    db.add(w)
    try:
        db.flush()
        db.refresh(w)
        result = _serialize_watchlist(w)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"A watchlist named '{name}' already exists")
    return result


@router.patch("/{watchlist_id}", dependencies=[Depends(require_writable_resource("watchlists", Watchlist, "watchlist_id"))])
def update_watchlist(
    watchlist_id: UUID,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    w = _find_watchlist(db, context, watchlist_id)
    if payload.name is not None:
        w.name = payload.name.strip()
    if payload.color is not None:
        w.color = payload.color or None
    try:
        db.flush()
        db.refresh(w)
        result = _serialize_watchlist(w)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A watchlist with that name already exists")
    return result


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    w = _find_watchlist(db, context, watchlist_id)
    db.query(WatchlistItem).filter(
        WatchlistItem.workspace_id == context.workspace.id,
        WatchlistItem.watchlist_id == w.id,
    ).delete(synchronize_session=False)
    deleted_id = str(w.public_id)
    db.delete(w)
    db.commit()
    return {"ok": True, "deleted_id": deleted_id}


@router.post(
    "/{watchlist_id}/items",
    dependencies=[
        Depends(require_writable_resource("watchlists", Watchlist, "watchlist_id")),
        Depends(require_capacity("watchlist_symbols", WatchlistItem)),
    ],
)
def add_item(
    watchlist_id: UUID,
    payload: ItemCreate,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    w = _find_watchlist(db, context, watchlist_id)
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    item = WatchlistItem(workspace_id=context.workspace.id, watchlist_id=w.id, ticker=ticker, note=payload.note)
    db.add(item)
    try:
        db.flush()
        db.refresh(item)
        result = {
            "id": str(item.public_id),
            "ticker": item.ticker,
            "note": item.note,
            "watchlist_id": str(w.public_id),
            "quote": _quote(ticker),
        }
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{ticker} is already in this watchlist")
    return result


@router.delete("/{watchlist_id}/items/{item_id}")
def remove_item(
    watchlist_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    w = _find_watchlist(db, context, watchlist_id)
    item = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.workspace_id == context.workspace.id,
            WatchlistItem.watchlist_id == w.id,
            WatchlistItem.public_id == item_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    deleted_id = str(item.public_id)
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": deleted_id}
