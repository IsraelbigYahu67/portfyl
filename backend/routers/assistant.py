from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from collections import defaultdict
import httpx

from database import get_db
from models import Transaction, Portfolio
from routers.portfolios import require_portfolio
from app_settings import get_user_setting, set_user_setting
from tenancy import RequestContext, get_request_context

router = APIRouter(prefix="/assistant", tags=["assistant"])

# DeepSeek exposes an OpenAI-compatible chat completions endpoint.
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
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


def _system_prompt(context: str) -> str:
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


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(get_request_context),
):
    key = get_user_setting(db, request_context.user.id, KEY_SETTING)
    model = get_user_setting(db, request_context.user.id, MODEL_SETTING) or DEFAULT_MODEL
    return {
        "configured": bool(key),
        "model": model,
        "key_preview": _key_preview(key) if key else "",
    }


@router.put("/config")
def save_config(
    payload: ConfigPayload,
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(get_request_context),
):
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    model = (payload.model or DEFAULT_MODEL).strip()
    if model not in ALLOWED_MODELS:
        model = DEFAULT_MODEL

    set_user_setting(db, request_context.user.id, KEY_SETTING, api_key)
    set_user_setting(db, request_context.user.id, MODEL_SETTING, model)
    db.commit()

    return {"configured": True, "model": model, "key_preview": _key_preview(api_key)}


@router.delete("/config")
def delete_config(
    db: Session = Depends(get_db),
    request_context: RequestContext = Depends(get_request_context),
):
    set_user_setting(db, request_context.user.id, KEY_SETTING, None)
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


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    request_context: RequestContext = Depends(get_request_context),
):
    api_key = get_user_setting(db, request_context.user.id, KEY_SETTING)
    if not api_key:
        raise HTTPException(status_code=400, detail="DeepSeek API key not configured. Add it in the assistant settings.")
    model = get_user_setting(db, request_context.user.id, MODEL_SETTING) or DEFAULT_MODEL

    # Keep only valid user/assistant turns, most recent MAX_HISTORY.
    history = [
        {"role": m.role, "content": m.content}
        for m in payload.messages
        if m.role in ("user", "assistant") and m.content.strip()
    ][-MAX_HISTORY:]
    if not history or history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user.")

    portfolio_context = _build_portfolio_context(db, portfolio)
    messages = [{"role": "system", "content": _system_prompt(portfolio_context)}] + history

    content, usage = await _call_deepseek(api_key, model, messages)
    return {"reply": {"role": "assistant", "content": content}, "model": model, "usage": usage}
