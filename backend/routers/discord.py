from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import httpx

from audit import record_audit_event
from database import get_db, release_connection
from entitlements import require_capability
from models import DiscordWebhook, Portfolio
from tenancy import RequestContext, require_csrf, require_portfolio

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


def _webhook_preview(url: str) -> str:
    """Identify the integration without exposing its webhook id or token."""
    if "discordapp.com/api/webhooks" in url:
        return "https://discordapp.com/api/webhooks/***/***"
    return "https://discord.com/api/webhooks/***/***"


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
        "webhook_url_preview": _webhook_preview(hook.webhook_url),
        "notify_trades": hook.notify_trades,
        "notify_dividends": hook.notify_dividends,
        "notify_milestones": hook.notify_milestones,
        "created_at": hook.created_at.isoformat() if hook.created_at else None,
    }


@router.post("/webhook", dependencies=[Depends(require_capability("notification_integrations"))])
def create_webhook(
    body: WebhookCreate,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
):
    if "discord.com/api/webhooks" not in body.webhook_url and "discordapp.com/api/webhooks" not in body.webhook_url:
        raise HTTPException(400, "Invalid Discord webhook URL")

    existing = _portfolio_webhook(db, portfolio)
    action = "discord.webhook.updated" if existing else "discord.webhook.created"
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
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=portfolio.workspace_id,
        action=action,
        target_type="discord_webhook",
        target_id=str(existing.public_id),
        metadata={"portfolio_id": str(portfolio.public_id)},
    )
    result = {"status": "ok", "id": str(existing.public_id),
              "portfolio_id": str(portfolio.public_id)}
    db.commit()
    return result


@router.patch("/webhook", dependencies=[Depends(require_capability("notification_integrations"))])
def update_webhook(
    body: WebhookUpdate,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
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
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=portfolio.workspace_id,
        action="discord.webhook.updated",
        target_type="discord_webhook",
        target_id=str(hook.public_id),
        metadata={"portfolio_id": str(portfolio.public_id)},
    )
    db.commit()
    return {"status": "ok"}


@router.delete("/webhook")
def delete_webhook(
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        raise HTTPException(404, "No webhook configured")
    target_id = str(hook.public_id)
    db.delete(hook)
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=portfolio.workspace_id,
        action="discord.webhook.deleted",
        target_type="discord_webhook",
        target_id=target_id,
        metadata={"portfolio_id": str(portfolio.public_id)},
    )
    db.commit()
    return {"status": "ok"}


@router.post("/webhook/test", dependencies=[Depends(require_capability("notification_integrations"))])
def test_webhook(
    body: WebhookTestMessage,
    portfolio: Portfolio = Depends(require_portfolio),
    db: Session = Depends(get_db),
):
    hook = _portfolio_webhook(db, portfolio)
    if not hook:
        raise HTTPException(404, "No webhook configured")
    webhook_url = hook.webhook_url
    # Don't hold a pooled connection while Discord answers.
    release_connection(db)

    message = body.message or "Test notification from Portfyl"
    payload = {
        "embeds": [{
            "title": "Portfyl Notification",
            "description": message,
            "color": 0x059669,
            "footer": {"text": "Portfyl Analytics"},
        }]
    }

    with httpx.Client() as client:
        resp = client.post(webhook_url, json=payload)
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
