"""IBKR Activity Flex Query XML -> ledger rows (stocks/ETFs, cash, splits).

Options stay with routers/ibkr.py's OptionsTrade sync and are only counted
here. The same parser serves the user's XML upload (history older than the
Flex Web Service's 365-day window) and the Flex Web Service sync
(ibkr_ledger.apply_flex_ledger), so both write identical event ids.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from currency_codes import normalize_currency
from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.instruments import InstrumentRef, InstrumentResolver, unresolved_errors

SOURCE = "ibkr"
FORMAT_NAME = "Interactive Brokers (Flex XML)"
OPTIONS_SKIP = "options (synced to Options)"
_ET = ZoneInfo("America/New_York")
_STOCK_CATEGORIES = {"STK", "ETF", "FUND"}
_PER_SHARE = re.compile(r"([A-Z]{3})\s+([0-9.]+)\s+PER SHARE")

# IBKR listingExchange -> canonical venue (importers.instruments.VENUE_SUFFIX).
IBKR_VENUES = {
    "NASDAQ": "US", "NYSE": "US", "ARCA": "US", "AMEX": "US", "BATS": "US",
    "ISLAND": "US", "IEX": "US", "PINK": "US", "NYSENAT": "US",
    "IBIS": "XETRA", "IBIS2": "XETRA", "FWB": "FRANKFURT", "FWB2": "FRANKFURT",
    "LSE": "LSE", "LSEETF": "LSE", "AEB": "AMSTERDAM", "SBF": "PARIS",
    "BVME": "MILAN", "BVME.ETF": "MILAN", "EBS": "SIX", "SWX": "SIX",
    "PRA": "PRAGUE", "TSE": "TORONTO", "SEHK": "HONGKONG", "ENEXT.BE": "BRUSSELS",
    "BM": "MADRID", "VSE": "VIENNA", "WSE": "WARSAW",
}

_DIVIDEND_TYPES = {"Dividends", "Payment In Lieu Of Dividends"}
_WITHHOLDING = "Withholding Tax"
_FEE_TYPES = {"Broker Interest Paid", "Other Fees", "Commission Adjustments"}
_INTEREST_TYPES = {"Broker Interest Received", "Bond Interest Received"}


def _detect(file: ImportFile) -> bool:
    head = file.head()
    return "<FlexQueryResponse" in head or "<FlexStatements" in head


def _parse(file: ImportFile, resolver: InstrumentResolver) -> ParseResult:
    return parse_flex_statement(file.text(), resolver)


FORMAT = ImportFormat("ibkr_flex", FORMAT_NAME, _detect, _parse)


def _num(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _when(raw: str | None) -> tuple[date | None, datetime | None]:
    """Flex `dateTime` is New York local time; the ledger stores UTC."""
    if not raw:
        return None, None
    text = re.sub(r"[-:\s]", "", raw.strip().replace(",", ";"))
    day_part, _, time_part = text.partition(";")
    if not time_part and len(day_part) > 8:
        day_part, time_part = day_part[:8], day_part[8:]
    day = datetime.strptime(day_part[:8], "%Y%m%d").date()
    if not time_part:
        return day, None
    local = datetime.strptime(day_part[:8] + time_part[:6], "%Y%m%d%H%M%S").replace(tzinfo=_ET)
    return day, local.astimezone(timezone.utc)


def _detail(el: ET.Element, allowed: str) -> bool:
    return el.get("levelOfDetail") in (None, "", allowed)


def _category(el: ET.Element) -> str:
    return (el.get("assetCategory") or "STK").upper()


def has_ledger_sections(xml_text: str) -> bool:
    return any(tag in xml_text for tag in ("<Trades", "<CashTransactions"))


def _ref(el: ET.Element) -> InstrumentRef:
    return InstrumentRef(
        isin=el.get("isin") or None,
        symbol=el.get("symbol") or None,
        venue=IBKR_VENUES.get((el.get("listingExchange") or "").upper()),
        currency=el.get("currency") or None,
        name=el.get("description") or el.get("symbol"),
    )


def parse_flex_statement(xml_text: str, resolver: InstrumentResolver) -> ParseResult:
    result = ParseResult(FORMAT_NAME, rows=[], source_events=0)
    upper = xml_text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        result.errors.append("Flex XML must not contain a DOCTYPE or entity declarations")
        return result
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.errors.append(f"Could not parse IBKR XML: {exc}")
        return result

    for statement in root.iter("FlexStatement"):
        info = statement.find("AccountInformation")
        base = ((info.get("currency") if info is not None else None)
                or statement.get("currency") or "").upper()
        _parse_one(statement, base, resolver, result)
    return result


def _fx(el: ET.Element, base: str) -> float | None:
    return _num(el.get("fxRateToBase")) if base == "CZK" else None


def _needs_ticker(el: ET.Element) -> bool:
    if el.tag == "CashTransaction":
        kind = el.get("type")
        return kind in _DIVIDEND_TYPES or (kind == _WITHHOLDING and bool(el.get("symbol")))
    return bool(el.get("symbol")) and _category(el) in _STOCK_CATEGORIES


def _missing_detail_level(elements: list[ET.Element], allowed: str, section: str) -> str | None:
    """A query set to Orders/Summary only would otherwise import nothing
    for that section without saying so."""
    if elements and not any(_detail(el, allowed) for el in elements):
        return (f"The Flex Query reports {section} without the {allowed.title()} level; "
                f"enable {section} → {allowed.title()} in the query and sync again")
    return None


def _parse_one(statement: ET.Element, base: str, resolver: InstrumentResolver, result: ParseResult) -> None:
    stock_trades = [t for t in statement.iter("Trade") if _category(t) in _STOCK_CATEGORIES | {"CASH"}]
    for problem in (
        _missing_detail_level(stock_trades, "EXECUTION", "Trades"),
        _missing_detail_level(list(statement.iter("CashTransaction")), "DETAIL", "Cash Transactions"),
    ):
        if problem:
            result.errors.append(problem)
    trades = [t for t in statement.iter("Trade") if _detail(t, "EXECUTION")]
    cash = [c for c in statement.iter("CashTransaction") if _detail(c, "DETAIL")]
    actions = [a for a in statement.iter("CorporateAction") if _detail(a, "DETAIL")]
    transfers = list(statement.iter("Transfer"))
    result.source_events += len(trades) + len(cash) + len(actions) + len(transfers)

    refs = [_ref(el) for el in [*trades, *cash, *actions, *transfers] if _needs_ticker(el)]
    resolved = resolver.resolve_many(refs)

    def ticker(el: ET.Element) -> str | None:
        return resolved.get(_ref(el))

    legs: list[DividendLeg] = []
    for trade in trades:
        _trade(trade, base, ticker, result)
    for row in cash:
        _cash(row, base, ticker, legs, result)
    for action in actions:
        _corporate_action(action, ticker, result)
    for transfer in transfers:
        _transfer(transfer, base, ticker, result)

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors(refs, resolved))


def _event_id(el: ET.Element) -> str | None:
    return el.get("transactionID") or el.get("tradeID") or None


def _cash_row(common: dict, kind: str, amount: float, currency: str, event_id: str, notes=None) -> dict:
    return {**common, "type": kind, "ticker": None, "shares": 0.0, "price": 0.0,
            "amount": amount, "currency": currency, "notes": notes,
            "source_event_id": event_id, "fx_to_czk": None}


def _skip_non_stock(el: ET.Element, result: ParseResult) -> bool:
    category = _category(el)
    if category in _STOCK_CATEGORIES:
        return False
    result.skip(OPTIONS_SKIP if category == "OPT" else f"unsupported asset: {category}")
    return True


def _trade(el, base, ticker, result):
    category = (el.get("assetCategory") or "").upper()
    if category == "OPT":
        result.skip(OPTIONS_SKIP)
        return
    if category not in _STOCK_CATEGORIES | {"CASH"}:
        result.skip(f"unsupported asset: {category or '?'}")
        return
    event_id = _event_id(el)
    day, executed_at = _when(el.get("dateTime") or el.get("tradeDate"))
    if event_id is None or day is None:
        result.errors.append(f"IBKR trade {el.get('symbol')}: missing transactionID or date")
        return
    currency = normalize_currency(el.get("currency"), default="")
    quantity = _num(el.get("quantity")) or 0.0
    price = _num(el.get("tradePrice")) or 0.0
    commission = abs(_num(el.get("ibCommission")) or 0.0)
    commission_ccy = normalize_currency(el.get("ibCommissionCurrency") or currency, default="")
    common = {"date": day, "executed_at": executed_at, "source": SOURCE,
              "source_event_stream": "trades", "fx_to_czk": _fx(el, base)}

    if category == "CASH":
        # fxRateToBase is the quoted currency's rate, not both legs': leave
        # fx_to_czk empty and let the import fill it per currency.
        bought, _, quoted = (el.get("symbol") or "").upper().partition(".")
        if not bought or not quoted or quantity == 0:
            result.errors.append(f"IBKR FX trade {el.get('symbol')} on {day}: cannot read the currency pair")
            return
        legs = [(bought, abs(quantity)), (quoted, abs(quantity * price))]
        incoming, outgoing = legs if quantity > 0 else legs[::-1]
        result.rows.append(_cash_row(common, "fx_in", incoming[1], incoming[0], f"{event_id}:in"))
        result.rows.append(_cash_row(common, "fx_out", outgoing[1], outgoing[0], f"{event_id}:out"))
        if commission:
            result.rows.append(_cash_row(common, "fee", commission, commission_ccy,
                                         f"{event_id}:commission", "IBKR FX commission"))
        return
    symbol = ticker(el)
    if symbol is None:
        return  # reported once via unresolved_errors
    net_cash = abs(_num(el.get("netCash")) or quantity * price)
    result.rows.append({
        **common, "type": "buy" if quantity > 0 else "sell", "ticker": symbol,
        "name": el.get("description"), "shares": abs(quantity), "price": price,
        "currency": currency, "cash_amount": net_cash, "cash_currency": currency,
        "source_event_id": event_id, "source_instrument_id": el.get("isin") or el.get("conid"),
        "notes": "IBKR",
    })
    if commission and commission_ccy != currency:
        result.rows.append(_cash_row(common, "fee", commission, commission_ccy,
                                     f"{event_id}:commission", f"IBKR commission {symbol}"))


def _cash(el, base, ticker, legs, result):
    kind = el.get("type") or ""
    day, executed_at = _when(el.get("dateTime") or el.get("settleDate"))
    amount = _num(el.get("amount"))
    event_id = _event_id(el)
    currency = normalize_currency(el.get("currency"), default="")
    if day is None or amount is None or not currency:
        result.errors.append(f"IBKR cash transaction {kind}: missing date, amount or currency")
        return
    if kind in _DIVIDEND_TYPES or (kind == _WITHHOLDING and el.get("symbol")):
        symbol = ticker(el)
        if symbol is None:
            return
        group = el.get("actionID") or f"{el.get('conid')}:{day.isoformat()}"
        per_share = _PER_SHARE.search(el.get("description") or "")
        shares = None
        if kind in _DIVIDEND_TYPES and per_share and float(per_share.group(2)) > 0:
            shares = abs(amount) / float(per_share.group(2))
        legs.append(DividendLeg(
            group_key=group, kind="tax" if kind == _WITHHOLDING else "gross",
            ticker=symbol, name=el.get("description"), pay_date=day, currency=currency,
            amount=amount, shares=shares, executed_at=executed_at, fx_to_czk=_fx(el, base),
            instrument_id=el.get("isin") or el.get("conid"),
        ))
        return
    if event_id is None:
        result.errors.append(f"IBKR cash transaction {kind} {day}: missing transactionID")
        return
    if kind == "Deposits/Withdrawals" and amount != 0:
        ledger_type = "deposit" if amount > 0 else "withdrawal"
    elif kind in _INTEREST_TYPES and amount > 0:
        ledger_type = "interest"
    elif (kind in _FEE_TYPES or kind == _WITHHOLDING) and amount < 0:
        # A withholding tax without a symbol is tax on credit interest.
        ledger_type = "fee"
    else:
        result.errors.append(
            f"IBKR cash transaction {kind!r} ({amount} {currency} on {day}) is not supported yet"
        )
        return
    result.rows.append({
        "date": day, "type": ledger_type, "ticker": None, "shares": 0.0, "price": 0.0,
        "amount": abs(amount), "currency": currency, "notes": el.get("description"),
        "source": SOURCE, "source_event_stream": "cash", "source_event_id": event_id,
        "executed_at": executed_at, "fx_to_czk": _fx(el, base),
    })


def _corporate_action(el, ticker, result):
    if _skip_non_stock(el, result):
        return
    kind = el.get("type") or ""
    quantity = _num(el.get("quantity")) or 0.0
    day, executed_at = _when(el.get("dateTime") or el.get("reportDate"))
    event_id = _event_id(el)
    if kind not in {"FS", "RS"} or day is None or event_id is None:
        result.errors.append(
            f"IBKR corporate action {kind} on {el.get('symbol')} needs manual review; nothing was imported"
        )
        return
    symbol = ticker(el)
    if symbol is None or quantity == 0:
        return
    result.rows.append({
        "date": day, "type": "split_open" if quantity > 0 else "split_close",
        "ticker": symbol, "name": el.get("description"), "shares": abs(quantity), "price": 0.0,
        "currency": normalize_currency(el.get("currency")), "notes": el.get("description"),
        "source": SOURCE, "source_event_stream": "corporate_actions", "source_event_id": event_id,
        "executed_at": executed_at, "source_instrument_id": el.get("isin") or el.get("conid"),
    })


def _transfer(el, base, ticker, result):
    if _skip_non_stock(el, result):
        return
    direction = (el.get("direction") or "").upper()
    quantity = abs(_num(el.get("quantity")) or 0.0)
    price = _num(el.get("transferPrice")) or 0.0
    day, executed_at = _when(el.get("dateTime") or el.get("date"))
    event_id = _event_id(el)
    if direction not in {"IN", "OUT"} or price <= 0 or quantity <= 0 or day is None or event_id is None:
        result.errors.append(
            f"IBKR transfer of {el.get('symbol')} has no cost basis (transferPrice); "
            "add it manually after importing the rest"
        )
        return
    symbol = ticker(el)
    if symbol is None:
        return
    currency = normalize_currency(el.get("currency"))
    value = quantity * price
    trade_type, cash_type = ("buy", "deposit") if direction == "IN" else ("sell", "withdrawal")
    common = {"date": day, "currency": currency, "source": SOURCE, "source_event_stream": "transfers",
              "executed_at": executed_at, "fx_to_czk": _fx(el, base),
              "notes": f"IBKR transfer {direction} {el.get('type') or ''}".strip()}
    cash_row = {**common, "type": cash_type, "ticker": None, "shares": 0.0, "price": 0.0,
                "amount": value, "source_event_id": f"{event_id}:cash"}
    trade_row = {**common, "type": trade_type, "ticker": symbol, "name": el.get("description"),
                 "shares": quantity, "price": price, "cash_amount": value, "cash_currency": currency,
                 "source_event_id": f"{event_id}:position",
                 "source_instrument_id": el.get("isin") or el.get("conid")}
    result.rows.extend([cash_row, trade_row] if direction == "IN" else [trade_row, cash_row])
