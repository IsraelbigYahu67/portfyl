from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, case

from database import get_db
from models import OptionsTrade, Portfolio
from tenancy import require_portfolio

router = APIRouter(prefix="/options", tags=["options"])


def serialize_trade(trade: OptionsTrade, portfolio: Portfolio) -> dict:
    return {
        "id": str(trade.public_id),
        "portfolio_id": str(portfolio.public_id),
        "underlying": trade.underlying,
        "strike": trade.strike,
        "expiry": str(trade.expiry) if trade.expiry else None,
        "put_call": trade.put_call,
        "quantity": trade.quantity,
        "open_price": trade.open_price,
        "close_price": trade.close_price,
        "open_date": str(trade.open_date) if trade.open_date else None,
        "close_date": str(trade.close_date) if trade.close_date else None,
        "status": trade.status,
        "multiplier": trade.multiplier,
        "currency": trade.currency,
        "pnl": trade.pnl,
        "commission": trade.commission,
        "source": trade.source,
        "fx_to_czk": trade.fx_to_czk,
        "notes": trade.notes,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
    }


def _portfolio_trades(db: Session, portfolio: Portfolio):
    return db.query(OptionsTrade).filter(
        OptionsTrade.workspace_id == portfolio.workspace_id,
        OptionsTrade.portfolio_id == portfolio.id,
    )


@router.get("/trades")
def get_trades(
    source: str = None,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    query = _portfolio_trades(db, portfolio)

    if source:
        query = query.filter(OptionsTrade.source == source)

    # Order by close_date DESC nulls last, then open_date DESC
    query = query.order_by(
        case((OptionsTrade.close_date.is_(None), 1), else_=0),
        desc(OptionsTrade.close_date),
        desc(OptionsTrade.open_date),
    )

    trades = query.all()
    return [serialize_trade(t, portfolio) for t in trades]


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    trades = _portfolio_trades(db, portfolio).all()

    total_trades = len(trades)
    trades_with_pnl = [t for t in trades if t.pnl is not None]
    winning_trades = [t for t in trades_with_pnl if t.pnl > 0]
    losing_trades = [t for t in trades_with_pnl if t.pnl <= 0]

    total_pnl = sum(t.pnl for t in trades_with_pnl) if trades_with_pnl else 0.0
    total_commission = sum(t.commission or 0.0 for t in trades)
    win_rate = (len(winning_trades) / len(trades_with_pnl) * 100) if trades_with_pnl else 0.0
    avg_win = (sum(t.pnl for t in winning_trades) / len(winning_trades)) if winning_trades else 0.0
    avg_loss = (sum(t.pnl for t in losing_trades) / len(losing_trades)) if losing_trades else 0.0
    best_trade = max(t.pnl for t in trades_with_pnl) if trades_with_pnl else 0.0
    worst_trade = min(t.pnl for t in trades_with_pnl) if trades_with_pnl else 0.0

    return {
        "total_pnl": total_pnl,
        "total_commission": total_commission,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "total_trades": total_trades,
    }


@router.get("/by-underlying")
def get_by_underlying(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    trades = _portfolio_trades(db, portfolio).all()

    # Group by underlying
    groups: dict[str, list[OptionsTrade]] = {}
    for trade in trades:
        groups.setdefault(trade.underlying, []).append(trade)

    result = []
    for underlying, group_trades in groups.items():
        trades_with_pnl = [t for t in group_trades if t.pnl is not None]
        total_pnl = sum(t.pnl for t in trades_with_pnl) if trades_with_pnl else 0.0
        total_commission = sum(t.commission or 0.0 for t in group_trades)
        winning = [t for t in trades_with_pnl if t.pnl > 0]
        win_rate = (len(winning) / len(trades_with_pnl) * 100) if trades_with_pnl else 0.0

        result.append({
            "underlying": underlying,
            "total_pnl": total_pnl,
            "total_commission": total_commission,
            "win_rate": win_rate,
            "trade_count": len(group_trades),
            "trades": [serialize_trade(t, portfolio) for t in group_trades],
        })

    # Sort by total_pnl descending
    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return result


@router.get("/calendar")
def get_calendar(
    period: str = None,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    query = _portfolio_trades(db, portfolio).filter(
        OptionsTrade.close_date.isnot(None)
    )

    # Apply period filter
    if period and period != "all":
        today = date.today()
        period_map = {
            "1m": timedelta(days=30),
            "3m": timedelta(days=90),
            "6m": timedelta(days=180),
            "1y": timedelta(days=365),
        }
        delta = period_map.get(period)
        if delta:
            start_date = today - delta
            query = query.filter(OptionsTrade.close_date >= start_date)

    trades = query.all()

    # Aggregate by close_date
    daily: dict[date, dict] = {}
    for trade in trades:
        d = trade.close_date
        if d not in daily:
            daily[d] = {"date": str(d), "pnl": 0.0, "trades_count": 0}
        daily[d]["pnl"] += trade.pnl if trade.pnl else 0.0
        daily[d]["trades_count"] += 1

    # Sort by date ascending
    result = sorted(daily.values(), key=lambda x: x["date"])
    return result
