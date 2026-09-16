from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Literal
from collections import defaultdict
import httpx
import os
from datetime import datetime, timezone
from typing import Annotated

from audit import record_audit_event
from plans import PlanTier
from database import get_db
from models import Transaction, Portfolio
from routers.portfolios import require_portfolio
from app_settings import get_user_secret, get_user_setting, set_user_secret, set_user_setting
from tenancy import RequestContext, get_request_context, require_csrf
from rate_limit import rate_limit
from entitlements import (
    EffectiveEntitlements,
    EntitlementDenied,
    finalize_usage,
    release_usage,
    require_capability,
    reserve_usage,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# DeepSeek exposes an OpenAI-compatible chat completions endpoint.
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
PROVIDER = "deepseek"
ALLOWED_MODELS = {"deepseek-chat", "deepseek-reasoner"}

KEY_SETTING = "deepseek_api_key"
MODEL_SETTING = "deepseek_model"

# Cap how much chat history we forward to keep payloads + cost bounded.
MAX_HISTORY = 20


# ---------------------------------------------------------------------------
# App-setting helpers
# ---------------------------------------------------------------------------

def _key_preview(key: str) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "..." + key[-4:]
    return "***"


# ---------------------------------------------------------------------------
# Portfolio context
# ---------------------------------------------------------------------------

def _build_portfolio_context(db: Session, portfolio: Portfolio) -> str:
    """Compact, DB-only snapshot of the active portfolio for the system prompt.

    Derived from transactions (cost basis, positions, recent activity) — no live
    market calls, so it stays fast. Mixed transaction currencies are shown as-is
    rather than converted.
    """
    name = portfolio.name

    txns = (
        db.query(Transaction)
        .filter(Transaction.workspace_id == portfolio.workspace_id,
                Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.date.asc())
        .all()
    )
    if not txns:
        return f"Active portfolio: {name}. It currently has no recorded transactions."

    positions: dict[str, dict] = {}
    dividend_income: dict[str, float] = defaultdict(float)

    for t in txns:
        p = positions.setdefault(
            t.ticker,
            {
                "name": t.name or t.ticker,
                "net_shares": 0.0,
                "buy_shares": 0.0,
                "buy_cost": 0.0,
                "currency": t.currency or "USD",
            },
        )
        typ = (t.type or "").lower()
        if typ == "buy":
            p["net_shares"] += t.shares
            p["buy_shares"] += t.shares
            p["buy_cost"] += t.shares * t.price
        elif typ == "sell":
            p["net_shares"] -= t.shares
        elif typ == "dividend":
            dividend_income[t.currency or "USD"] += t.shares * t.price

    open_positions = []
    for ticker, p in positions.items():
        if p["net_shares"] > 1e-9:
            avg = p["buy_cost"] / p["buy_shares"] if p["buy_shares"] else 0.0
            invested = p["net_shares"] * avg
            open_positions.append((invested, ticker, p, avg))
    open_positions.sort(reverse=True, key=lambda x: x[0])

    base_ccy = open_positions[0][2]["currency"] if open_positions else "USD"
    total_invested = sum(x[0] for x in open_positions)

    lines = [
        f"Active portfolio: {name}.",
        f"Open positions: {len(open_positions)}; approx total cost basis "
        f"{total_invested:,.0f} {base_ccy} (currencies may be mixed).",
        "Holdings (largest cost basis first):",
    ]
    for invested, ticker, p, avg in open_positions[:25]:
        lines.append(
            f"- {ticker} ({p['name']}): {p['net_shares']:g} shares, "
            f"avg cost {avg:,.2f} {p['currency']}, ~{invested:,.0f} {p['currency']} invested"
        )
    if len(open_positions) > 25:
        lines.append(f"- (+{len(open_positions) - 25} more smaller positions)")

    if dividend_income:
        divs = ", ".join(f"{v:,.0f} {c}" for c, v in dividend_income.items())
        lines.append(f"Recorded dividend income (approx): {divs}.")

    lines.append("Recent transactions (newest first):")
    for t in reversed(txns[-15:]):
        lines.append(
            f"- {t.date} {(t.type or '').upper()} {t.shares:g} {t.ticker} "
            f"@ {t.price:,.2f} {t.currency or 'USD'}"
        )

    lines.append(f"Total recorded transactions: {len(txns)}.")
    lines.append(
        "Note: figures are cost-basis / transaction-derived. Live market prices and "
        "current valuation/P&L are NOT in this snapshot."
    )
    return "\n".join(lines)


def _system_prompt(context: str | None) -> str:
    if context is None:
        return (
            "You are Portfyl's assistant, powered by DeepSeek. Explain general investing "
            "concepts clearly and concisely. Use only information supplied in this conversation. "
            "If information is missing, say so rather than inventing numbers. Market data "
            "may be delayed. Avoid definitive buy/sell directives or guarantees."
        )
    return (
        "You are Portfyl's built-in portfolio assistant, powered by DeepSeek. You help "
        "the user understand and analyze their investment portfolio. Be concise, "
        "accurate, and practical. Use the portfolio snapshot below to answer questions "
        "about holdings, allocation, cost basis, and trading activity. If the snapshot "
        "lacks data needed to answer (e.g. live prices or current P&L), say so rather "
        "than guessing or inventing numbers. You may explain general investing concepts, "
        "but make clear you are not a licensed financial advisor and avoid definitive "
        "buy/sell directives.\n\n"
        "=== PORTFOLIO SNAPSHOT ===\n"
        f"{context}\n"
        "=== END SNAPSHOT ==="
    )


# ---------------------------------------------------------------------------
# DeepSeek call
# ---------------------------------------------------------------------------

async def _call_deepseek(api_key: str, model: str, messages: list[dict]) -> tuple[str, dict | None]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": False, "temperature": 0.3}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(DEEPSEEK_URL, headers=headers, json=body)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="DeepSeek timed out. Try again or use deepseek-chat.")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach DeepSeek: {e}")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="DeepSeek rejected the API key. Check it in the assistant settings.")
    if resp.status_code == 402:
        raise HTTPException(status_code=402, detail="DeepSeek reports insufficient balance on this API key.")
    if resp.status_code >= 400:
        detail = resp.text
        try:
            err = resp.json().get("error")
            if isinstance(err, dict):
                detail = err.get("message", detail)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"DeepSeek API error ({resp.status_code}): {detail}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"].get("content", "")
    except (ValueError, KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Unexpected response from DeepSeek")

    return content, data.get("usage")


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

class ConfigPayload(BaseModel):
    api_key: str = Field(min_length=8)
    model: Optional[str] = None


@router.get("/config", dependencies=[Depends(require_capability("assistant_byok"))])
def get_config(
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(get_request_context),
):
    key = get_user_secret(db, request_context.user.id, KEY_SETTING)
    model = get_user_setting(db, request_context.user.id, MODEL_SETTING) or DEFAULT_MODEL
    return {
        "configured": bool(key),
        "model": model,
        "key_preview": _key_preview(key) if key else "",
    }


@router.put("/config", dependencies=[Depends(require_capability("assistant_byok"))])
def save_config(
    payload: ConfigPayload,
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(require_csrf),
):
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    model = (payload.model or DEFAULT_MODEL).strip()
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL

    set_user_secret(db, request_context.user.id, KEY_SETTING, api_key)
    set_user_setting(db, request_context.user.id, MODEL_SETTING, model)
    record_audit_event(
        db,
        actor_user_id=request_context.user.id,
        action="assistant.api_key.set",
        target_type="user_setting",
        target_id=KEY_SETTING,
        metadata={"model": model},
    )
    db.commit()

    return {"configured": True, "model": model, "key_preview": _key_preview(api_key)}


@router.delete("/config")
def delete_config(
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(require_csrf),
):
    set_user_secret(db, request_context.user.id, KEY_SETTING, None)
    record_audit_event(
        db,
        actor_user_id=request_context.user.id,
        action="assistant.api_key.cleared",
        target_type="user_setting",
        target_id=KEY_SETTING,
    )
    db.commit()
    return {"configured": False}


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context_mode: Literal["none", "portfolio_summary"] = "none"


@router.post("/chat", dependencies=[Depends(require_capability("assistant_byok")), Depends(rate_limit("assistant_chat", by="workspace"))])
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    request_context: RequestContext = Depends(require_csrf),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    _entitlements: EffectiveEntitlements = Depends(require_capability("assistant_byok")),
):
    # Validate and assemble all local request state before reserving variable-
    # cost hosted usage. A malformed conversation or context-building failure
    # must never consume quota.
    history = [
        {"role": message.role, "content": message.content}
        for message in payload.messages
        if message.role in ("user", "assistant") and message.content.strip()
    ][-MAX_HISTORY:]
    if not history or history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user.")
    model = get_user_setting(db, request_context.user.id, MODEL_SETTING) or DEFAULT_MODEL
    portfolio_context = None
    context_as_of = None
    if payload.context_mode == "portfolio_summary":
        portfolio_context = _build_portfolio_context(db, portfolio)
        context_as_of = datetime.now(timezone.utc).isoformat()
    messages = [{"role": "system", "content": _system_prompt(portfolio_context)}] + history

    api_key = get_user_secret(db, request_context.user.id, KEY_SETTING)
    usage_reservation = None
    if not api_key:
        if not isinstance(_entitlements, EffectiveEntitlements) or _entitlements.source == "local":
            raise HTTPException(status_code=400, detail="DeepSeek API key not configured. Add it in the assistant settings.")
        if "assistant_hosted" not in _entitlements.capabilities:
            raise EntitlementDenied(
                "plan_upgrade_required",
                capability="assistant_hosted",
                plan=_entitlements.plan,
                required_plan=PlanTier.PRO,
            )
        api_key = os.environ.get("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(status_code=503, detail={"code": "hosted_ai_unavailable"})
        key = (idempotency_key or "").strip()
        if not key or len(key) > 255:
            raise HTTPException(status_code=400, detail={"code": "idempotency_key_required"})
        now = datetime.now(timezone.utc)
        metric = "hosted_ai_monthly"
        limit = _entitlements.limits.hosted_ai_monthly
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)
        usage_reservation = reserve_usage(
            db,
            workspace_id=request_context.workspace.id,
            metric=metric,
            idempotency_key=key,
            limit=limit,
            period_start=period_start,
            period_end=period_end,
        )
        if getattr(usage_reservation, "_portfyl_reused", False):
            raise HTTPException(
                status_code=409,
                detail={"code": "idempotency_key_already_used"},
            )
        db.commit()
    try:
        content, usage = await _call_deepseek(api_key, model, messages)
    except Exception:
        if usage_reservation is not None:
            usage_reservation = db.merge(usage_reservation)
            release_usage(db, usage_reservation)
            db.commit()
        raise
    if usage_reservation is not None:
        usage_reservation = db.merge(usage_reservation)
        finalize_usage(db, usage_reservation)
        db.commit()
    return {
        "reply": {"role": "assistant", "content": content}, "model": model, "usage": usage,
        "provider": PROVIDER, "context_mode": payload.context_mode, "context_as_of": context_as_of,
    }
