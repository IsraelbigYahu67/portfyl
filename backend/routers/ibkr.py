from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict
from uuid import UUID
import asyncio
import json
import httpx
import xml.etree.ElementTree as ET

from database import get_db
from models import BrokerConnection, OptionsTrade, BrokerBalance, Portfolio
from tenancy import RequestContext, require_csrf, require_portfolio

router = APIRouter(prefix="/broker/ibkr", tags=["ibkr"])

FLEX_SEND_URL = (
    "https://gdcdyn.interactivebrokers.com/Universal/servlet/"
    "FlexStatementService.SendRequest?t={token}&q={queryId}&v=3"
)
FLEX_GET_URL = (
    "https://gdcdyn.interactivebrokers.com/Universal/servlet/"
    "FlexStatementService.GetStatement?q={referenceCode}&t={token}&v=3"
)


def _get_ibkr_connection(db: Session, portfolio: Portfolio) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == "ibkr",
            BrokerConnection.portfolio_id == portfolio.id,
        )
        .first()
    )


def _get_ibkr_balance(db: Session, portfolio: Portfolio) -> BrokerBalance | None:
    return (
        db.query(BrokerBalance)
        .filter(
            BrokerBalance.workspace_id == portfolio.workspace_id,
            BrokerBalance.broker == "ibkr",
            BrokerBalance.portfolio_id == portfolio.id,
        )
        .first()
    )


async def _send_flex_request(token: str, query_id: str) -> str:
    """Send a Flex request and return the reference code on success."""
    url = FLEX_SEND_URL.format(token=token, queryId=query_id)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    status = root.findtext("Status", "")
    if status == "Success":
        ref_code = root.findtext("ReferenceCode", "")
        if not ref_code:
            raise HTTPException(status_code=502, detail="IBKR returned Success but no ReferenceCode")
        return ref_code

    error_code = root.findtext("ErrorCode", "")
    error_msg = root.findtext("ErrorMessage", "Unknown error")
    raise HTTPException(
        status_code=502,
        detail=f"IBKR Flex request failed (code {error_code}): {error_msg}",
    )


async def _poll_flex_statement(token: str, reference_code: str) -> str:
    """Poll for the Flex statement with exponential backoff. Returns raw XML."""
    url = FLEX_GET_URL.format(referenceCode=reference_code, token=token)
    wait = 2.0
    elapsed = 0.0
    timeout = 60.0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < timeout:
            await asyncio.sleep(wait)
            elapsed += wait

            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

            # If the response is a status/warn XML (short), check for Warn status
            # A full report will be much larger and contain FlexQueryResponse
            if "<FlexQueryResponse" in text:
                return text

            # Try parsing as status XML
            try:
                root = ET.fromstring(text)
                status = root.findtext("Status", "")
                if status == "Success":
                    # Shouldn't happen without FlexQueryResponse, but handle it
                    return text
                if status == "Warn":
                    # Still generating, continue polling
                    pass
                elif status == "Fail":
                    error_msg = root.findtext("ErrorMessage", "Unknown error")
                    raise HTTPException(
                        status_code=502,
                        detail=f"IBKR statement generation failed: {error_msg}",
                    )
            except ET.ParseError:
                # Non-XML response, might be the raw report in unexpected format
                raise HTTPException(
                    status_code=502,
                    detail="Unexpected response format from IBKR",
                )

            # Exponential backoff, capped at 10s
            wait = min(wait * 1.5, 10.0)

    raise HTTPException(
        status_code=504,
        detail="Timed out waiting for IBKR Flex statement (60s)",
    )


def _parse_options_trades(xml_text: str) -> list[dict]:
    """Parse Flex XML and extract OPT trades as dicts."""
    root = ET.fromstring(xml_text)
    trades = []

    # Navigate: FlexQueryResponse/FlexStatements/FlexStatement/Trades/Trade
    for statement in root.iter("FlexStatement"):
        trades_elem = statement.find("Trades")
        if trades_elem is None:
            continue
        for trade_el in trades_elem.findall("Trade"):
            asset_category = trade_el.get("assetCategory", "")
            if asset_category != "OPT":
                continue

            trades.append({
                "underlying": trade_el.get("underlyingSymbol", ""),
                "strike": float(trade_el.get("strike", "0")),
                "expiry": trade_el.get("expiry", ""),
                "put_call": trade_el.get("putCall", ""),
                "quantity": int(float(trade_el.get("quantity", "0"))),
                "trade_price": float(trade_el.get("tradePrice", "0")),
                "trade_date": trade_el.get("tradeDate", ""),
                "open_close": trade_el.get("openCloseIndicator", ""),
                "buy_sell": trade_el.get("buySell", ""),
                "multiplier": int(float(trade_el.get("multiplier", "100"))),
                "currency": trade_el.get("currency", "USD"),
                "order_id": trade_el.get("ibOrderID", ""),
                "commission": float(trade_el.get("ibCommission", "0")),
            })

    return trades


def _pair_trades(trades: list[dict]) -> list[dict]:
    """Pair open and close trades using FIFO matching.

    Groups trades by (underlying, strike, expiry, putCall) and matches
    opens with closes chronologically.

    Returns list of paired trade dicts ready for DB insertion.
    """
    # Group by contract key
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: {"opens": [], "closes": []})

    for t in trades:
        key = (t["underlying"], t["strike"], t["expiry"], t["put_call"])
        if t["open_close"] == "O":
            groups[key]["opens"].append(t)
        elif t["open_close"] == "C":
            groups[key]["closes"].append(t)
        # Skip "?" (assignment/unknown) — they don't pair cleanly

    paired = []

    for key, bucket in groups.items():
        # Sort by trade_date for FIFO
        opens = sorted(bucket["opens"], key=lambda x: x["trade_date"])
        closes = sorted(bucket["closes"], key=lambda x: x["trade_date"])

        close_idx = 0
        for open_trade in opens:
            if close_idx >= len(closes):
                # No matching close — still open position, skip
                break

            close_trade = closes[close_idx]
            close_idx += 1

            # Determine if this was a short (sold to open) or long (bought to open)
            is_short = open_trade["buy_sell"] == "SELL"
            open_price = open_trade["trade_price"]
            close_price = close_trade["trade_price"]
            qty = abs(open_trade["quantity"])
            multiplier = open_trade["multiplier"]

            # Commission is negative in IBKR (cost), sum both legs
            commission = abs(open_trade["commission"]) + abs(close_trade["commission"])

            if is_short:
                pnl = (open_price - close_price) * qty * multiplier - commission
            else:
                pnl = (close_price - open_price) * qty * multiplier - commission

            # Parse dates
            try:
                open_date = date.fromisoformat(open_trade["trade_date"])
            except (ValueError, TypeError):
                continue
            try:
                close_date = date.fromisoformat(close_trade["trade_date"])
            except (ValueError, TypeError):
                continue
            try:
                expiry_date = date.fromisoformat(open_trade["expiry"])
            except (ValueError, TypeError):
                continue

            paired.append({
                "underlying": key[0],
                "strike": key[1],
                "expiry": expiry_date,
                "put_call": key[3],
                "quantity": qty,
                "open_price": open_price,
                "close_price": close_price,
                "open_date": open_date,
                "close_date": close_date,
                "status": "closed",
                "multiplier": multiplier,
                "currency": open_trade["currency"],
                "pnl": round(pnl, 2),
                "commission": round(commission, 2),
            })

    return paired


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_flex_date(v: str | None) -> date | None:
    if not v:
        return None
    v = v.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _parse_balance(xml_text: str) -> dict | None:
    """Extract the account balance from a Flex statement.

    Reads the Equity Summary (NAV in base) for the cash / stock / options / total
    breakdown and the Cash Report for the per-currency cash split. Returns None
    when the statement contains neither section — i.e. the user's Flex Query
    isn't configured to include "Net Asset Value (NAV) in Base" or "Cash Report".
    """
    root = ET.fromstring(xml_text)

    # AccountInformation.currency is the account's base currency, if that section
    # is enabled. EquitySummary/CashReport base figures are denominated in it.
    base_currency = None
    acct = root.find(".//AccountInformation")
    if acct is not None:
        base_currency = acct.get("currency") or None

    # NAV breakdown: the Flex statement carries one EquitySummaryByReportDateInBase
    # row per report date in the period; the latest row is the current balance.
    nav = None
    latest_date = ""
    for row in root.iter("EquitySummaryByReportDateInBase"):
        rd = row.get("reportDate", "")
        if rd >= latest_date:  # lexical compare is correct for YYYYMMDD / YYYY-MM-DD
            latest_date = rd
            nav = row

    cash = stock = options_value = net_liquidation = None
    as_of = None
    if nav is not None:
        cash = _to_float(nav.get("cash"))
        stock = _to_float(nav.get("stock"))
        options_value = _to_float(nav.get("options"))
        net_liquidation = _to_float(nav.get("total"))
        as_of = _parse_flex_date(nav.get("reportDate"))

    # Per-currency cash from the Cash Report. The "BASE_SUMMARY" row is the base-
    # currency total, not a real currency, so it's handled separately below.
    cash_by_currency: dict[str, float] = {}
    base_summary_cash = None
    for c in root.iter("CashReportCurrency"):
        cur = c.get("currency", "")
        val = _to_float(c.get("endingCash"))
        if cur == "BASE_SUMMARY":
            base_summary_cash = val
            continue
        if cur and val is not None:
            cash_by_currency[cur] = val

    # Neither section present → nothing to report.
    if nav is None and not cash_by_currency and base_summary_cash is None:
        return None

    # Fall back to the Cash Report base total if the Equity Summary was absent.
    if cash is None:
        cash = base_summary_cash

    return {
        "base_currency": base_currency,
        "cash": cash,
        "stock": stock,
        "options_value": options_value,
        "net_liquidation": net_liquidation,
        "cash_by_currency": cash_by_currency,
        "as_of": as_of,
    }


def _upsert_balance(db: Session, portfolio: Portfolio, bal: dict) -> None:
    """Store (or refresh) the latest IBKR balance snapshot for a portfolio."""
    row = _get_ibkr_balance(db, portfolio)
    if row is None:
        row = BrokerBalance(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="ibkr",
        )
        db.add(row)

    row.base_currency = bal.get("base_currency")
    row.cash = bal.get("cash")
    row.stock = bal.get("stock")
    row.options_value = bal.get("options_value")
    row.net_liquidation = bal.get("net_liquidation")
    row.cash_by_currency = json.dumps(bal.get("cash_by_currency") or {})
    row.as_of = bal.get("as_of")


@router.post("/connect")
async def connect(
    payload: dict,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    flex_token = payload.get("flex_token", "").strip()
    query_id = payload.get("query_id", "").strip()

    if not flex_token:
        raise HTTPException(status_code=400, detail="flex_token is required")
    if not query_id:
        raise HTTPException(status_code=400, detail="query_id is required")

    try:
        await _send_flex_request(flex_token, query_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not validate IBKR credentials: {e}")

    connection = _get_ibkr_connection(db, portfolio)
    if connection:
        connection.api_key = flex_token
        connection.api_secret = query_id
        connection.last_synced_at = None
    else:
        connection = BrokerConnection(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="ibkr",
            api_key=flex_token,
            api_secret=query_id,
            environment="live",
        )
        db.add(connection)
    db.flush()
    result = {
        "connected": True,
        "id": str(connection.public_id),
        "portfolio_id": str(portfolio.public_id),
        "message": "Connected to IBKR Flex Web Service",
    }
    db.commit()
    return result


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    conn = _get_ibkr_connection(db, portfolio)
    if not conn:
        return {"connected": False, "portfolio_id": str(portfolio.public_id)}

    token_preview = ""
    if conn.api_key and len(conn.api_key) > 8:
        token_preview = conn.api_key[:4] + "..." + conn.api_key[-4:]
    elif conn.api_key:
        token_preview = "***"

    return {
        "connected": True,
        "id": str(conn.public_id),
        "portfolio_id": str(portfolio.public_id),
        "auto_sync": conn.auto_sync,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "token_preview": token_preview,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
    }


@router.post("/auto-sync")
def set_auto_sync(
    payload: dict,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    """Toggle background auto-sync for this portfolio's IBKR connection."""
    conn = _get_ibkr_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="IBKR is not connected")
    conn.auto_sync = bool(payload.get("enabled"))
    db.commit()
    return {"ok": True, "auto_sync": conn.auto_sync}


@router.get("/balance")
def get_balance(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    """Return the latest stored IBKR balance snapshot for the active portfolio.

    Served from the DB (populated on sync), so it never hits IBKR — important
    because Flex requests are rate-limited. `balance` is null until the first
    sync that includes the NAV / Cash Report sections.
    """
    conn = _get_ibkr_connection(db, portfolio)
    if not conn:
        return {
            "connected": False,
            "portfolio_id": str(portfolio.public_id),
            "balance": None,
        }

    row = _get_ibkr_balance(db, portfolio)
    if row is None:
        return {
            "connected": True,
            "portfolio_id": str(portfolio.public_id),
            "balance": None,
        }

    try:
        cash_by_currency = json.loads(row.cash_by_currency) if row.cash_by_currency else {}
    except (ValueError, TypeError):
        cash_by_currency = {}

    return {
        "connected": True,
        "portfolio_id": str(portfolio.public_id),
        "balance": {
            "id": str(row.public_id),
            "portfolio_id": str(portfolio.public_id),
            "base_currency": row.base_currency,
            "cash": row.cash,
            "stock": row.stock,
            "options_value": row.options_value,
            "net_liquidation": row.net_liquidation,
            "cash_by_currency": cash_by_currency,
            "as_of": str(row.as_of) if row.as_of else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }


@router.delete("/connect")
def disconnect(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_ibkr_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="No IBKR connection found")
    db.delete(conn)
    db.query(BrokerBalance).filter(
        BrokerBalance.workspace_id == portfolio.workspace_id,
        BrokerBalance.broker == "ibkr",
        BrokerBalance.portfolio_id == portfolio.id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "message": "Disconnected from IBKR"}


async def _run_ibkr_sync(
    db: Session,
    workspace_id: UUID,
    portfolio_id: int,
) -> dict:
    """Core IBKR Flex sync for one explicitly scoped workspace portfolio."""
    portfolio = db.query(Portfolio).filter(
        Portfolio.workspace_id == workspace_id,
        Portfolio.id == portfolio_id,
    ).first()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    conn = _get_ibkr_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="IBKR is not connected")

    token = conn.api_key
    query_id = conn.api_secret or ""
    errors: list[str] = []

    # Phase 1: Send request
    try:
        reference_code = await _send_flex_request(token, query_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send Flex request: {e}")

    # Phase 2: Poll for statement
    try:
        xml_text = await _poll_flex_statement(token, reference_code)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve Flex statement: {e}")

    # Phase 3: Parse XML for OPT trades
    try:
        raw_trades = _parse_options_trades(xml_text)
    except ET.ParseError as e:
        raise HTTPException(status_code=502, detail=f"Failed to parse IBKR XML: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error parsing trades: {e}")

    # Phase 4: Pair trades (FIFO)
    paired = _pair_trades(raw_trades)

    # Phase 4b: Parse + store the account balance snapshot from the same XML.
    # Best-effort: a Flex Query without the NAV / Cash Report sections simply
    # yields no balance, and the sync still succeeds for trades.
    balance_found = False
    try:
        bal = _parse_balance(xml_text)
    except Exception:
        bal = None
    if bal is not None:
        _upsert_balance(db, portfolio, bal)
        balance_found = True

    # Phase 5: Load existing trades for dedup/update
    existing_rows = (
        db.query(OptionsTrade)
        .filter(
            OptionsTrade.workspace_id == workspace_id,
            OptionsTrade.portfolio_id == portfolio_id,
            OptionsTrade.source == "ibkr",
        )
        .all()
    )
    existing_map: dict[tuple, OptionsTrade] = {}
    for row in existing_rows:
        key = (
            row.underlying,
            row.strike,
            row.expiry,
            row.put_call,
            row.open_date,
            row.quantity,
            row.open_price,
        )
        existing_map[key] = row

    # Phase 6 & 7: Insert new trades or update existing with commission/pnl
    imported = 0
    updated = 0

    for trade in paired:
        dedup_key = (
            trade["underlying"],
            trade["strike"],
            trade["expiry"],
            trade["put_call"],
            trade["open_date"],
            trade["quantity"],
            trade["open_price"],
        )

        existing_row = existing_map.get(dedup_key)
        if existing_row:
            # Update commission and recalculated pnl on existing trades
            existing_row.commission = trade["commission"]
            existing_row.pnl = trade["pnl"]
            existing_row.close_price = trade["close_price"]
            existing_row.close_date = trade["close_date"]
            updated += 1
            continue

        try:
            db.add(OptionsTrade(
                workspace_id=workspace_id,
                portfolio_id=portfolio_id,
                underlying=trade["underlying"],
                strike=trade["strike"],
                expiry=trade["expiry"],
                put_call=trade["put_call"],
                quantity=trade["quantity"],
                open_price=trade["open_price"],
                close_price=trade["close_price"],
                open_date=trade["open_date"],
                close_date=trade["close_date"],
                status=trade["status"],
                multiplier=trade["multiplier"],
                currency=trade["currency"],
                pnl=trade["pnl"],
                commission=trade["commission"],
                source="ibkr",
            ))
            existing_map[dedup_key] = None
            imported += 1
        except Exception as e:
            errors.append(f"Failed to insert trade {trade['underlying']} {trade['strike']}: {e}")

    # Update last_synced_at
    conn.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "errors": errors,
        "balance_found": balance_found,
    }


@router.post("/sync")
async def sync_trades(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    """User-facing IBKR sync for the authorized portfolio."""
    return await _run_ibkr_sync(db, portfolio.workspace_id, portfolio.id)
