from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import httpx

from database import get_db
from models import DiscordWebhook, Portfolio
from tenancy import require_portfolio

router = APIRouter(prefix="/discord", tags=["discord"])


class WebhookCreate(BaseModel):
    webhook_url: str
    notify_trades: bool = True
    notify_dividends: bool = True
    notify_milestones: bool = True


class WebhookUpdate(BaseModel):
    webhook_url: Optional[str] = None
    notify_trades: Optional[bool] = None
    notify_dividends: Optional[bool] = None
    notify_milestones: Optional[bool] = None


class WebhookTestMessage(BaseModel):
    message: Optional[str] = None


def _portfolio_webhook(db: Session, portfolio: Portfolio) -> DiscordWebhook | None:
    return db.query(DiscordWebhook).filter(
        DiscordWebhook.workspace_id == portfolio.workspace_id,
        DiscordWebhook.portfolio_id == portfolio.id,
    ).first()


@router.get("/webhook")
def get_webhook(
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        return {"connected": False, "portfolio_id": str(portfolio.public_id)}
    return {
        "connected": True,
        "id": str(hook.public_id),
        "portfolio_id": str(portfolio.public_id),
        "webhook_url_preview": hook.webhook_url[:40] + "..." if len(hook.webhook_url) > 40 else hook.webhook_url,
        "notify_trades": hook.notify_trades,
        "notify_dividends": hook.notify_dividends,
        "notify_milestones": hook.notify_milestones,
        "created_at": hook.created_at.isoformat() if hook.created_at else None,
    }


@router.post("/webhook")
def create_webhook(
    body: WebhookCreate,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    if "discord.com/api/webhooks" not in body.webhook_url and "discordapp.com/api/webhooks" not in body.webhook_url:
        raise HTTPException(400, "Invalid Discord webhook URL")

    existing = _portfolio_webhook(db, portfolio)
    if existing:
        existing.webhook_url = body.webhook_url
        existing.notify_trades = body.notify_trades
        existing.notify_dividends = body.notify_dividends
        existing.notify_milestones = body.notify_milestones
    else:
        existing = DiscordWebhook(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            webhook_url=body.webhook_url,
            notify_trades=body.notify_trades,
            notify_dividends=body.notify_dividends,
            notify_milestones=body.notify_milestones,
        )
        db.add(existing)
    db.flush()
    result = {"status": "ok", "id": str(existing.public_id),
              "portfolio_id": str(portfolio.public_id)}
    db.commit()
    return result


@router.patch("/webhook")
def update_webhook(
    body: WebhookUpdate,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        raise HTTPException(404, "No webhook configured")
    if body.webhook_url is not None:
        hook.webhook_url = body.webhook_url
    if body.notify_trades is not None:
        hook.notify_trades = body.notify_trades
    if body.notify_dividends is not None:
        hook.notify_dividends = body.notify_dividends
    if body.notify_milestones is not None:
        hook.notify_milestones = body.notify_milestones
    db.commit()
    return {"status": "ok"}


@router.delete("/webhook")
def delete_webhook(
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        raise HTTPException(404, "No webhook configured")
    db.delete(hook)
    db.commit()
    return {"status": "ok"}


@router.post("/webhook/test")
async def test_webhook(
    body: WebhookTestMessage,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        raise HTTPException(404, "No webhook configured")

    message = body.message or "Test notification from Portfyl"
    payload = {
        "embeds": [{
            "title": "Portfyl Notification",
            "description": message,
            "color": 0x059669,
            "footer": {"text": "Portfyl Analytics"},
        }]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(hook.webhook_url, json=payload)
        if resp.status_code not in (200, 204):
            raise HTTPException(502, f"Discord returned {resp.status_code}: {resp.text[:200]}")

    return {"status": "sent"}


async def send_discord_notification(db: Session, workspace_id: UUID, portfolio_id: int,
                                    title: str, description: str,
                                    color: int = 0x059669) -> bool | None:
    """Post an embed to the portfolio's webhook, reporting delivery: True when
    Discord accepted it, False when the post failed (callers gating one-shot
    state — alert trigger flags, dividend dedup rows — must not persist it on
    False so a later pass retries), None when no webhook is configured.

    `workspace_id` is mandatory and applied as an application-level predicate:
    background callers reach this helper with an internal integer portfolio ID,
    and every tenant query must carry its own workspace filter rather than
    relying on RLS or on integer PKs happening to be globally unique."""
    hook = db.query(DiscordWebhook).filter(
        DiscordWebhook.workspace_id == workspace_id,
        DiscordWebhook.portfolio_id == portfolio_id,
    ).first()
    if not hook:
        return None

    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": "Portfyl Analytics"},
        }]
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(hook.webhook_url, json=payload, timeout=5.0)
    except Exception:
        return False
    return resp.status_code in (200, 204)
