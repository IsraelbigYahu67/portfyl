"""Background job passes, driven by the periodic pollers in main.py.

Each pass is a self-contained coroutine that takes a DB session and returns a
summary list (empty when nothing happened) — the same shape the price-alert
`run_check` uses, so main.py can run them all through one generic loop and the
tests can drive them synchronously with `asyncio.run`.

Two passes live here:

* :func:`broker_autosync_pass` — syncs every broker connection whose
  ``auto_sync`` flag is on (Trading 212 and IBKR), and announces imports on the
  portfolio's Discord webhook when ``notify_trades`` is enabled. One failing
  connection never blocks the others.
* :func:`dividend_exdate_pass` — for every portfolio whose Discord webhook has
  ``notify_dividends`` on, looks up upcoming ex-dividend dates for open
  holdings and sends one digest per portfolio. A ``DividendNotification`` row
  per (portfolio, ticker, ex_date) guarantees each dividend is announced once,
  across ticks and restarts.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import BrokerConnection, DiscordWebhook, DividendNotification, Transaction
from routers.discord import send_discord_notification

log = logging.getLogger("portfyl.jobs")

DIVIDEND_COLOR = 0x8B5CF6  # violet — matches the TTM/dividend accents in the UI
SYNC_COLOR = 0x059669      # green — same as trade notifications


# -------- Broker auto-sync --------------------------------------------------

async def broker_autosync_pass(db: Session) -> list[dict]:
    """Sync every connection with auto_sync enabled. Returns one summary dict
    per attempted connection ({portfolio_id, broker, ok, imported | error})."""
    # Imported lazily: broker/ibkr import fx, market_data, httpx setup, etc.,
    # and jobs must stay importable in tests without that whole chain loading
    # at module import time.
    from routers.broker import sync_transactions
    from routers.ibkr import _run_ibkr_sync

    conns = db.query(BrokerConnection).filter(BrokerConnection.auto_sync == True).all()  # noqa: E712
    results: list[dict] = []
    for conn in conns:
        summary = {"portfolio_id": conn.portfolio_id, "broker": conn.broker, "ok": True}
        try:
            if conn.broker == "trading212":
                r = sync_transactions(db, conn.portfolio_id, conn.owner_id or "default")
                summary["imported"] = r.get("total_imported", 0)
                detail = (f"{r.get('imported_orders', 0)} order(s), "
                          f"{r.get('imported_dividends', 0)} dividend(s)")
            elif conn.broker == "ibkr":
                r = await _run_ibkr_sync(db, conn.portfolio_id, conn.owner_id or "default")
                summary["imported"] = r.get("imported", 0)
                detail = f"{r.get('imported', 0)} trade(s)"
            else:
                continue  # unknown broker — nothing to do
        except Exception as e:
            db.rollback()
            summary.update(ok=False, error=str(e))
            log.warning("auto-sync failed for portfolio %s (%s): %s",
                        conn.portfolio_id, conn.broker, e)
            results.append(summary)
            continue

        if summary.get("imported"):
            hook = (db.query(DiscordWebhook)
                      .filter(DiscordWebhook.portfolio_id == conn.portfolio_id)
                      .first())
            if hook and hook.notify_trades:
                await send_discord_notification(
                    db, conn.portfolio_id,
                    f"🔄 Auto-sync: {summary['imported']} new transaction(s)",
                    f"{conn.broker} auto-sync imported {detail}.",
                    color=SYNC_COLOR,
                )
        results.append(summary)
    return results


# -------- Dividend ex-date notifications ------------------------------------

def _upcoming_dividends(db: Session, pid: int, today: date, lead_days: int) -> list[dict]:
    """Open holdings of `pid` whose next ex-date falls within [today, today+lead]."""
    # Lazy imports for the same reason as above (portfolio pulls market_data).
    from routers.dividend_calendar import _next_dividend_info
    from routers.portfolio import _build_holdings

    txns = (db.query(Transaction)
              .filter(Transaction.portfolio_id == pid)
              .order_by(Transaction.date)
              .all())
    if not txns:
        return []
    holdings = _build_holdings(txns)

    horizon = today + timedelta(days=lead_days)
    upcoming: list[dict] = []
    for ticker in sorted(holdings.keys()):
        info = _next_dividend_info(ticker)
        ex_raw = info.get("ex_date")
        if not ex_raw:
            continue
        try:
            ex = date.fromisoformat(ex_raw)
        except (TypeError, ValueError):
            continue
        if not (today <= ex <= horizon):
            continue
        shares = holdings[ticker].get("shares") or 0
        amount = info.get("amount_per_share")
        upcoming.append({
            "ticker": ticker,
            "ex_date": ex,
            "amount_per_share": amount,
            "shares": shares,
            "est_payment": round(shares * amount, 2) if amount else None,
        })
    return upcoming


async def dividend_exdate_pass(db: Session, today: date | None = None,
                               lead_days: int = 3) -> list[dict]:
    """Announce upcoming ex-dividend dates on each portfolio's Discord webhook.
    Returns the items announced this pass (empty when everything was already
    announced or nothing is upcoming)."""
    today = today or date.today()
    hooks = db.query(DiscordWebhook).filter(DiscordWebhook.notify_dividends == True).all()  # noqa: E712

    announced: list[dict] = []
    for hook in hooks:
        pid = hook.portfolio_id
        try:
            upcoming = _upcoming_dividends(db, pid, today, lead_days)
        except Exception as e:
            log.warning("dividend check failed for portfolio %s: %s", pid, e)
            continue

        fresh = []
        for item in upcoming:
            dup = (db.query(DividendNotification)
                     .filter(DividendNotification.portfolio_id == pid,
                             DividendNotification.ticker == item["ticker"],
                             DividendNotification.ex_date == item["ex_date"])
                     .first())
            if not dup:
                fresh.append(item)
        if not fresh:
            continue

        lines = []
        for item in fresh:
            per_share = (f" — ${item['amount_per_share']:,.4g}/sh" if item["amount_per_share"] else "")
            est = (f" (≈ ${item['est_payment']:,.2f} on {item['shares']:g} sh)"
                   if item["est_payment"] else "")
            lines.append(f"**{item['ticker']}** ex-dividend **{item['ex_date'].isoformat()}**{per_share}{est}")

        await send_discord_notification(
            db, pid,
            f"📅 {len(fresh)} upcoming ex-dividend date(s)",
            "\n".join(lines),
            color=DIVIDEND_COLOR,
        )
        for item in fresh:
            db.add(DividendNotification(portfolio_id=pid, ticker=item["ticker"],
                                        ex_date=item["ex_date"]))
        db.commit()
        announced.extend({**i, "portfolio_id": pid, "ex_date": i["ex_date"].isoformat()} for i in fresh)
    return announced
