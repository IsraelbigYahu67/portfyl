"""eToro positions/history JSON -> ledger rows.

Real (unleveraged, long) positions only: CFDs, shorts and copy trading are
counted, never imported. Supported for now: US-listed stocks/ETFs and crypto,
both priced in the USD account currency. Other venues fail closed until a
real response (plan Task 0) shows the currency of openRate there.
"""
from __future__ import annotations

from datetime import datetime, timezone

from etoro_client import field
from importers.base import ParseResult
from importers.instruments import yahoo_symbol

SOURCE = "etoro"
FORMAT_NAME = "eToro"
# The documented cash endpoint is eToro Money (card/bank), not the trading
# account; dividends and deposits have no confirmed endpoint yet. Until they
# do, any cash input is an error and the router must not fetch it.
CASH_MAPPED = False
# eToro exchange description keywords of US venues.
US_EXCHANGE_KEYWORDS = ("nasdaq", "nyse", "new york", "amex", "cboe", "bats")


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)


def _ticker(info: dict | None, result: ParseResult, instrument_id) -> str | None:
    if not info or not info.get("symbol"):
        result.errors.append(f"eToro instrument {instrument_id} has no market ticker")
        return None
    kind = (info.get("type") or "").lower()
    symbol = info["symbol"].strip().upper()
    if "crypto" in kind:
        return f"{symbol.removesuffix('USD').removesuffix('-')}-USD"
    if "stock" not in kind and "etf" not in kind:
        result.skip(f"unsupported asset: {info.get('type') or '?'}")
        return None
    exchange = (info.get("exchange") or "").lower()
    if any(word in exchange for word in US_EXCHANGE_KEYWORDS):
        return yahoo_symbol(symbol, "US")
    result.errors.append(
        f"eToro instrument {symbol} on {info.get('exchange') or 'an unknown exchange'} "
        "is not supported yet (only US-listed stocks/ETFs and crypto)"
    )
    return None


def _position_key(item: dict) -> str:
    return str(field(item, "positionId", "positionID"))


def map_account(history: list[dict], positions: list[dict], cash: list[dict],
                instruments: dict[int, dict]) -> ParseResult:
    result = ParseResult(FORMAT_NAME, rows=[], source_events=len(history) + len(positions) + len(cash))
    open_by_id = {_position_key(item): item for item in positions}
    closed_by_id = {_position_key(item): item for item in history}
    for pid in set(open_by_id) & set(closed_by_id):
        units_open = float(field(open_by_id[pid], "units", default=0))
        units_closed = float(field(closed_by_id[pid], "units", default=0))
        if abs(units_open - units_closed) > 1e-9:
            # Keep mapping the rest so the preview lists every problem at once.
            result.errors.append(f"eToro position {pid} is partially closed; it needs manual review")
            closed_by_id.pop(pid)
        open_by_id.pop(pid)  # the closed record is final

    for pid, item in sorted({**open_by_id, **closed_by_id}.items()):
        if field(item, "mirrorId", "mirrorID") or field(item, "socialTradeId", "socialTradeID"):
            result.skip("copy trading")
            continue
        if (field(item, "leverage", default=1) or 1) > 1 or field(item, "isBuy") is False:
            result.skip("CFD / leveraged position")
            continue
        instrument_id = field(item, "instrumentId", "instrumentID")
        info = instruments.get(int(instrument_id)) if instrument_id is not None else None
        ticker = _ticker(info, result, instrument_id)
        if ticker is None:
            continue
        units = float(item["units"])
        opened = _dt(field(item, "openTimestamp", "openDateTime"))
        open_rate = float(item["openRate"])
        common = {"ticker": ticker, "name": (info or {}).get("name"),
                  "shares": units, "currency": "USD", "cash_currency": "USD", "source": SOURCE,
                  "source_event_stream": "positions", "source_instrument_id": str(instrument_id),
                  "notes": "eToro"}
        result.rows.append({**common, "type": "buy", "date": opened.date(), "executed_at": opened,
                            "price": open_rate, "cash_amount": units * open_rate,
                            "source_event_id": f"{pid}:open"})
        if pid in closed_by_id:
            closed = _dt(item["closeTimestamp"])
            close_rate = float(item["closeRate"])
            result.rows.append({**common, "type": "sell", "date": closed.date(), "executed_at": closed,
                                "price": close_rate, "cash_amount": units * close_rate,
                                "source_event_id": f"{pid}:close"})
            fees = float(field(item, "fees", default=0) or 0)
            if fees > 0:
                result.rows.append({"type": "fee", "date": closed.date(), "executed_at": closed,
                                    "ticker": None, "shares": 0.0, "price": 0.0, "amount": fees,
                                    "currency": "USD", "source": SOURCE,
                                    "source_event_stream": "positions",
                                    "source_event_id": f"{pid}:fees", "notes": f"eToro fees {ticker}"})
    if cash and not CASH_MAPPED:
        result.errors.append("eToro cash transactions are not mapped yet (plan Task 0 question 1)")
    return result
