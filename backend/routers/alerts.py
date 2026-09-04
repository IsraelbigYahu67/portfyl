"""Price alerts: user-armed thresholds that fire a Discord notification when a
ticker's live price crosses them.

The check logic (`run_check`) is shared between the manual `POST /alerts/check`
endpoint and the background poller started in main.py — both call the same
coroutine so behaviour is identical whether a human or the scheduler triggers it.
An alert flips to `triggered` when it fires and won't re-fire until reset, so a
price that sits past the threshold doesn't spam the channel.

`run_check` always requires an explicit `workspace_id`: it is a pure function
of that one workspace's alerts and never scans across tenants on its own. The
background poller's cross-tenant sweep is an explicit workspace-by-workspace
iteration owned by jobs.alert_check_all_workspaces, not by this function.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import market_data
from database import get_db
from entitlements import EffectiveEntitlements, require_capability, require_capacity, require_writable_resource
from models import Portfolio, PriceAlert
from routers.portfolios import require_portfolio
from routers.discord import send_discord_notification

router = APIRouter(prefix="/alerts", tags=["alerts"])

ALERT_COLOR = 0xF59E0B  # amber — distinct from the trade (green) notifications


# -------- Schemas ----------------------------------------------------------

class AlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=24)
    direction: str = Field(pattern="^(above|below)$")
    target_price: float = Field(gt=0)
    note: Optional[str] = None


class AlertUpdate(BaseModel):
    direction: Optional[str] = Field(default=None, pattern="^(above|below)$")
    target_price: Optional[float] = Field(default=None, gt=0)
    note: Optional[str] = None
    enabled: Optional[bool] = None
    # Only "active" (re-arm) is accepted: "triggered" is set exclusively by the
    # checker, so a PATCH can't fake a trigger or silently disarm monitoring.
    status: Optional[str] = Field(default=None, pattern="^active$")


# -------- Serialization ----------------------------------------------------

def _serialize(a: PriceAlert, price: float | None = None) -> dict:
    return {
        "id": str(a.public_id),
        "ticker": a.ticker,
        "direction": a.direction,
        "target_price": a.target_price,
        "note": a.note,
        "enabled": a.enabled,
        "status": a.status,
        "current_price": price,
        "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
        "triggered_price": a.triggered_price,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _crossed(direction: str, price: float, target: float) -> bool:
    return price >= target if direction == "above" else price <= target


def _find_alert(db: Session, portfolio: Portfolio, alert_id: UUID) -> PriceAlert:
    a = db.scalar(
        select(PriceAlert).where(
            PriceAlert.workspace_id == portfolio.workspace_id,
            PriceAlert.portfolio_id == portfolio.id,
            PriceAlert.public_id == alert_id,
        )
    )
    if not a:
        raise HTTPException(404, "Alert not found")
    return a


# -------- Shared check logic ------------------------------------------------

async def run_check(
    db: Session,
    workspace_id: UUID,
    portfolio_id: int | None = None,
    *,
    max_alerts: int | None = None,
    allow_external_notifications: bool = True,
) -> list[dict]:
    """Evaluate every armed (`enabled` + `active`) alert in `workspace_id`
    against the live price. Fires a Discord notification per crossing and
    marks the alert `triggered`. When `portfolio_id` is None, checks every
    portfolio in that one workspace (never other workspaces — see the module
    docstring). Returns a summary of the alerts that fired this run."""
    allowed_ids = None
    if max_alerts is not None:
        allowed_ids = [row.id for row in db.query(PriceAlert).filter(
            PriceAlert.workspace_id == workspace_id,
        ).order_by(PriceAlert.created_at, PriceAlert.id).limit(max_alerts).all()]
    q = db.query(PriceAlert).filter(
        PriceAlert.workspace_id == workspace_id,
        PriceAlert.enabled == True, PriceAlert.status == "active",  # noqa: E712
    )
    if allowed_ids is not None:
        q = q.filter(PriceAlert.id.in_(allowed_ids))
    if portfolio_id is not None:
        q = q.filter(PriceAlert.portfolio_id == portfolio_id)
    alerts = q.all()
    if not alerts:
        return []

    tickers = sorted({a.ticker for a in alerts})
    # get_infos is blocking (threaded yfinance); keep the event loop free.
    infos = await asyncio.to_thread(market_data.get_infos, tickers)

    fired: list[dict] = []
    for a in alerts:
        price, _, _ = market_data.quote(infos.get(a.ticker, {}), a.ticker)
        if not price or price <= 0:
            continue  # no live data this pass; try again next time
        if not _crossed(a.direction, price, a.target_price):
            continue

        arrow = "▲" if a.direction == "above" else "▼"
        title = f"🔔 {a.ticker} {arrow} {a.target_price:g}"
        desc = (f"**{a.ticker}** is now **{price:,.2f}**, "
                f"{'at or above' if a.direction == 'above' else 'at or below'} "
                f"your target of {a.target_price:g}.")
        if a.note:
            desc += f"\n\n_{a.note}_"
        delivered = None
        if allow_external_notifications:
            delivered = await send_discord_notification(
                db, workspace_id, a.portfolio_id, title, desc, color=ALERT_COLOR
            )
        if delivered is False:
            # Webhook down or misconfigured: leave the alert armed so the next
            # pass retries — flipping it now would eat the notification forever
            # (triggered is one-shot). No webhook at all (None) still triggers:
            # the alert badge in the UI works without Discord.
            continue
        a.status = "triggered"
        a.last_triggered_at = datetime.utcnow()
        a.triggered_price = round(price, 4)
        fired.append(_serialize(a, price))

    db.commit()
    return fired


# -------- Endpoints --------------------------------------------------------

@router.get("")
def list_alerts(db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    """All alerts for the active portfolio, annotated with the live price."""
    alerts = (db.query(PriceAlert)
                .filter(PriceAlert.workspace_id == portfolio.workspace_id,
                        PriceAlert.portfolio_id == portfolio.id)
                .order_by(PriceAlert.created_at.desc())
                .all())
    prices: dict[str, float] = {}
    tickers = sorted({a.ticker for a in alerts})
    if tickers:
        infos = market_data.get_infos(tickers)
        for tk in tickers:
            prices[tk] = market_data.quote(infos.get(tk, {}), tk)[0] or None
    return [_serialize(a, prices.get(a.ticker)) for a in alerts]


@router.post("", dependencies=[Depends(require_capacity("alerts", PriceAlert))])
def create_alert(body: AlertCreate, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    a = PriceAlert(
        workspace_id=portfolio.workspace_id,
        portfolio_id=portfolio.id,
        ticker=body.ticker.strip().upper(),
        direction=body.direction,
        target_price=body.target_price,
        note=body.note,
        enabled=True,
        status="active",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.patch("/{alert_id}", dependencies=[Depends(require_writable_resource("alerts", PriceAlert, "alert_id"))])
def update_alert(alert_id: UUID, body: AlertUpdate, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    a = _find_alert(db, portfolio, alert_id)
    if body.direction is not None:
        a.direction = body.direction
    if body.target_price is not None:
        a.target_price = body.target_price
    if body.note is not None:
        a.note = body.note
    if body.enabled is not None:
        a.enabled = body.enabled
    if body.status is not None:
        # Re-arming clears the previous trigger record so the UI reads clean.
        a.status = body.status
        if body.status == "active":
            a.last_triggered_at = None
            a.triggered_price = None
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/{alert_id}")
def delete_alert(alert_id: UUID, db: Session = Depends(get_db), portfolio: Portfolio = Depends(require_portfolio)):
    a = _find_alert(db, portfolio, alert_id)
    db.delete(a)
    db.commit()
    return {"ok": True, "deleted_id": str(alert_id)}


@router.post("/check")
async def check_now(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    entitlements: EffectiveEntitlements = Depends(require_capability("alerts")),
):
    """Manually evaluate this portfolio's alerts right now (same logic as the
    background poller). Returns the alerts that fired."""
    fired = await run_check(
        db,
        portfolio.workspace_id,
        portfolio.id,
        max_alerts=entitlements.limits.alerts,
        allow_external_notifications="notification_integrations" in entitlements.capabilities,
    )
    return {"checked": True, "fired": fired}
