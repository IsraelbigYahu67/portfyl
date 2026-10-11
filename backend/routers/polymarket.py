from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import re
import os

from database import get_db, release_connection
from entitlements import require_broker_capacity, require_capability, require_writable_broker
from rate_limit import rate_limit
from models import BrokerConnection, PolymarketPosition, Portfolio
from tenancy import RequestContext, require_csrf, require_portfolio

router = APIRouter(tags=["polymarket"])

DATA_API_BASE = "https://data-api.polymarket.com"

WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _get_poly_connection(db: Session, portfolio: Portfolio) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == "polymarket",
            BrokerConnection.portfolio_id == portfolio.id,
        )
        .first()
    )


def _portfolio_positions(db: Session, portfolio: Portfolio):
    return db.query(PolymarketPosition).filter(
        PolymarketPosition.workspace_id == portfolio.workspace_id,
        PolymarketPosition.portfolio_id == portfolio.id,
    )


# ---------------------------------------------------------------------------
# POST /broker/polymarket/connect
# ---------------------------------------------------------------------------
@router.post(
    "/broker/polymarket/connect",
    dependencies=[Depends(require_capability("polymarket")), Depends(require_broker_capacity("polymarket"))],
)
def connect(
    payload: dict,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    address = (payload.get("address") or "").strip().lower()

    if not address:
        raise HTTPException(status_code=400, detail="Wallet address is required")
    if not WALLET_RE.match(address):
        raise HTTPException(status_code=400, detail="Invalid wallet address format (expected 0x + 40 hex chars)")

    # Validate by test-fetching positions from the public Data API
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{DATA_API_BASE}/positions", params={"user": address})
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Polymarket Data API returned {resp.status_code}",
                )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Polymarket API: {e}")

    connection = _get_poly_connection(db, portfolio)
    if connection:
        connection.api_key = address
        connection.api_secret = None
        connection.last_synced_at = None
    else:
        connection = BrokerConnection(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="polymarket",
            api_key=address,
            api_secret=None,
            environment="live",
        )
        db.add(connection)
    db.flush()
    result = {
        "connected": True,
        "id": str(connection.public_id),
        "portfolio_id": str(portfolio.public_id),
        "message": "Connected to Polymarket",
    }
    db.commit()
    return result


# ---------------------------------------------------------------------------
# GET /broker/polymarket/status
# ---------------------------------------------------------------------------
@router.get("/broker/polymarket/status")
def get_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    conn = _get_poly_connection(db, portfolio)
    if not conn:
        return {"connected": False, "portfolio_id": str(portfolio.public_id)}

    address = conn.api_key or ""
    address_preview = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address

    return {
        "connected": True,
        "id": str(conn.public_id),
        "portfolio_id": str(portfolio.public_id),
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "address_preview": address_preview,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
    }


# ---------------------------------------------------------------------------
# DELETE /broker/polymarket/connect
# ---------------------------------------------------------------------------
@router.delete("/broker/polymarket/connect")
def disconnect(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_poly_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="No Polymarket connection found")
    db.delete(conn)
    db.commit()
    return {"ok": True, "message": "Disconnected from Polymarket"}


# ---------------------------------------------------------------------------
# POST /broker/polymarket/sync
# ---------------------------------------------------------------------------
@router.post("/broker/polymarket/sync", dependencies=[Depends(require_capability("polymarket")), Depends(require_writable_broker("polymarket")), Depends(rate_limit("broker_sync", by="workspace"))])
def sync_positions(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_poly_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="Polymarket is not connected")

    address = conn.api_key
    # Don't hold a pooled connection while the Data API pages through trades.
    release_connection(db)

    # Fetch all trades (the only source of truth for actual buy/sell prices)
    all_trades = []
    offset = 0
    limit = 100
    try:
        with httpx.Client(timeout=30) as client:
            while True:
                resp = client.get(
                    f"{DATA_API_BASE}/trades",
                    params={"user": address, "limit": limit, "offset": offset},
                )
                resp.raise_for_status()
                batch = resp.json()
                if not isinstance(batch, list) or not batch:
                    break
                all_trades.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit

            # Fetch current market prices for open positions
            pos_resp = client.get(f"{DATA_API_BASE}/positions", params={"user": address})
            pos_resp.raise_for_status()
            live_positions = pos_resp.json() if pos_resp.status_code == 200 else []
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Polymarket API error: {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Polymarket API: {e}")

    # Build lookup of current prices by (conditionId, outcome)
    live_prices: dict[tuple, float] = {}
    if isinstance(live_positions, list):
        for lp in live_positions:
            cid = lp.get("conditionId") or lp.get("condition_id") or ""
            out = lp.get("outcome") or ""
            cur = lp.get("curPrice") or lp.get("current_price")
            if cur is not None:
                live_prices[(cid, out)] = float(cur)

    # Group trades by (conditionId, outcome) and compute real avg buy/sell prices
    groups: dict[tuple, dict] = {}
    for t in all_trades:
        condition_id = t.get("conditionId", "")
        outcome = t.get("outcome", "")
        key = (condition_id, outcome)

        if key not in groups:
            groups[key] = {
                "condition_id": condition_id,
                "asset_id": t.get("asset", ""),
                "outcome": outcome,
                "market_slug": t.get("slug", ""),
                "question": t.get("title", ""),
                "buys": [],
                "sells": [],
            }

        side = t.get("side", "").upper()
        size = float(t.get("size") or 0)
        price = float(t.get("price") or 0)

        if side == "BUY":
            groups[key]["buys"].append((size, price))
        elif side == "SELL":
            groups[key]["sells"].append((size, price))

    imported = 0
    updated = 0

    # Clear old positions for this portfolio and rebuild from trades
    _portfolio_positions(db, portfolio).delete(synchronize_session=False)

    for agg in groups.values():
        buys = agg["buys"]
        sells = agg["sells"]

        buy_size = sum(s for s, _ in buys)
        sell_size = sum(s for s, _ in sells)
        buy_cost = sum(s * p for s, p in buys)
        sell_revenue = sum(s * p for s, p in sells)

        avg_buy = round(buy_cost / buy_size, 6) if buy_size > 0 else 0
        avg_sell = round(sell_revenue / sell_size, 6) if sell_size > 0 else None

        # Position is closed if all bought shares were sold (within rounding)
        remaining = buy_size - sell_size
        is_closed = remaining < 0.01

        key = (agg["condition_id"], agg["outcome"])

        if is_closed:
            status = "closed"
            current_price = avg_sell
            resolved_price = avg_sell
            pnl = round(sell_revenue - buy_cost, 4)
        else:
            # Open position: current_price = live market price (what you'd sell at now).
            # If the position no longer appears in the live feed, there is no sell price
            # to show because the market has almost certainly resolved against us and the
            # shares are worth $0 — treat a missing price as 0 rather than unknown.
            live_price = live_prices.get(key)
            current_price = live_price if live_price is not None else 0.0

            if current_price == 0:
                # Worthless shares mean a -100% return — the market has resolved against
                # us, so record the position as closed/resolved rather than open. Total
                # realized P&L is sell revenue minus cost (the remainder is worth $0).
                status = "closed"
                resolved_price = 0.0
                pnl = round(sell_revenue - buy_cost, 4)
            else:
                status = "open"
                resolved_price = None
                # Unrealized P&L: (current_price - avg_buy) * remaining_size
                pnl = round((current_price - avg_buy) * remaining, 4)

        db.add(PolymarketPosition(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            condition_id=agg["condition_id"],
            asset_id=agg["asset_id"],
            market_slug=agg["market_slug"],
            question=agg["question"],
            outcome=agg["outcome"],
            size=round(buy_size, 4),
            avg_price=avg_buy,
            current_price=current_price,
            resolved_price=resolved_price,
            status=status,
            pnl=pnl,
            source="polymarket",
        ))
        imported += 1

    conn.last_synced_at = datetime.utcnow()
    db.commit()

    return {"imported": imported, "updated": updated}


# ---------------------------------------------------------------------------
# GET /polymarket/positions
# ---------------------------------------------------------------------------
@router.get("/polymarket/positions")
def get_positions(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    open_positions = (
        _portfolio_positions(db, portfolio)
        .filter(PolymarketPosition.status == "open")
        .order_by(PolymarketPosition.pnl.desc())
        .all()
    )
    resolved_positions = (
        _portfolio_positions(db, portfolio)
        .filter(PolymarketPosition.status != "open")
        .order_by(PolymarketPosition.updated_at.desc())
        .all()
    )

    def serialize(p: PolymarketPosition) -> dict:
        return {
            "id": str(p.public_id),
            "portfolio_id": str(portfolio.public_id),
            "condition_id": p.condition_id,
            "asset_id": p.asset_id,
            "market_slug": p.market_slug,
            "question": p.question,
            "outcome": p.outcome,
            "size": p.size,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "resolved_price": p.resolved_price,
            "status": p.status,
            "pnl": p.pnl,
            "source": p.source,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

    all_positions = [serialize(p) for p in open_positions] + [serialize(p) for p in resolved_positions]
    return {"positions": all_positions}


# ---------------------------------------------------------------------------
# GET /polymarket/summary
# ---------------------------------------------------------------------------
@router.get("/polymarket/summary")
def get_summary(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    positions = _portfolio_positions(db, portfolio).all()

    total_pnl = 0.0
    unrealized_pnl = 0.0
    realized_pnl = 0.0
    open_count = 0
    resolved_count = 0
    positions_value = 0.0
    wins = 0
    resolved_or_closed = 0

    for p in positions:
        pnl = p.pnl or 0.0
        total_pnl += pnl

        if p.status == "open":
            open_count += 1
            unrealized_pnl += pnl
            if p.current_price is not None:
                positions_value += p.current_price * p.size
        else:
            resolved_count += 1
            realized_pnl += pnl
            resolved_or_closed += 1
            if pnl > 0:
                wins += 1

    win_rate = round(wins / resolved_or_closed, 4) if resolved_or_closed > 0 else None

    return {
        "total_pnl": round(total_pnl, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "realized_pnl": round(realized_pnl, 4),
        "open_positions": open_count,
        "resolved_positions": resolved_count,
        "total_value": round(positions_value, 4),
        "win_rate": win_rate,
    }
