"""XTB xStation 5 Account History export (XLSX), cash-operations sheet.

The cash-operations sheet alone carries every money and position movement
for stocks/ETFs: buys/sells encode quantity and price in the comment. CFD
lines are counted and skipped; they are not ownership.

Built from the layout described in the research doc, not from a real export
(plan Task 0): the sheet name, the server time zone and GBX pricing of UK
listings are unverified until a real file confirms them.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.instruments import InstrumentRef, unresolved_errors

SOURCE = "xtb"
STREAM = "cash_operations"
_SERVER_TZ = ZoneInfo("Europe/Warsaw")  # unverified (plan Task 0)
_TRADE = re.compile(r"^(OPEN|CLOSE) BUY ([0-9.]+)(?:/[0-9.]+)? @ ([0-9.]+)$")
# XTB symbol suffix -> canonical venue key of importers.instruments.
XTB_SUFFIX_VENUES = {"US": "US", "DE": "XETRA", "UK": "LSE", "NL": "AMSTERDAM", "FR": "PARIS",
                     "IT": "MILAN", "CH": "SIX", "CZ": "PRAGUE", "PL": "WARSAW", "ES": "MADRID",
                     "BE": "BRUSSELS"}
_PRICE_CCY = {"US": "USD", "DE": "EUR", "NL": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
              "BE": "EUR", "UK": "GBX", "CH": "CHF", "CZ": "CZK", "PL": "PLN"}  # UK=GBX unverified
_CASH = {"deposit": "deposit", "withdrawal": "withdrawal", "free-funds interest": "interest",
         "free-funds interest tax": "fee", "sec fee": "fee", "commission": "fee"}
_CFD = {"close trade", "profit/loss", "swap", "rollover"}
_TRADES = {"stocks/etf purchase", "stocks/etf sale"}
_DIVIDENDS = {"divident", "dividend", "withholding tax"}


def _sheet(wb):
    return next((ws for ws in wb.worksheets if "CASH OPERATION" in ws.title.upper()), None)


def _detect(file: ImportFile) -> bool:
    if file.content[:2] != b"PK":
        return False
    try:
        wb = load_workbook(io.BytesIO(file.content), read_only=True, data_only=True)
    except Exception:
        return False  # a zip that is not a workbook (or a damaged one)
    try:
        return _sheet(wb) is not None
    finally:
        wb.close()


def _event_id(raw) -> str:
    # Excel stores whole numbers as floats; keep ids identical across exports.
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    return str(raw).strip()


def _ref_for(symbol: str) -> InstrumentRef:
    base, dot, suffix = symbol.rpartition(".")
    if not dot:
        return InstrumentRef(symbol=symbol, name=symbol)
    return InstrumentRef(symbol=base, venue=XTB_SUFFIX_VENUES.get(suffix.upper()), name=symbol)


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult("XTB (xStation)", rows=[], source_events=0)
    wb = load_workbook(io.BytesIO(file.content), read_only=True, data_only=True)
    try:
        values = [list(row) for row in _sheet(wb).iter_rows(values_only=True)]
    finally:
        wb.close()
    account_ccy = next((str(r[1]).strip().upper() for r in values
                        if r and r[0] == "Currency" and len(r) > 1 and r[1]), None)
    header_at = next((i for i, r in enumerate(values) if r and {"ID", "Type", "Amount"} <= set(r)), None)
    if not account_ccy or header_at is None:
        result.errors.append("XTB export: account currency or the cash-operations header is missing")
        return result
    col = {str(name).strip(): i for i, name in enumerate(values[header_at]) if name}
    missing = {"ID", "Type", "Time", "Comment", "Symbol", "Amount"} - set(col)
    if missing:
        result.errors.append(f"XTB export: missing columns {sorted(missing)}")
        return result
    rows = [r for r in values[header_at + 1:]
            if r and len(r) > col["ID"] and r[col["ID"]] not in (None, "")]
    result.source_events = len(rows)

    def kind_of(row) -> str:
        return str(row[col["Type"]] or "").strip().lower()

    # Only stock/ETF trades and dividends need a ticker; CFD symbols (US500)
    # must never be reported as unresolved.
    symbols = dict.fromkeys(str(r[col["Symbol"]]).strip() for r in rows
                            if r[col["Symbol"]] and kind_of(r) in _TRADES | _DIVIDENDS)
    refs = {symbol: _ref_for(symbol) for symbol in symbols}
    resolved = resolver.resolve_many(list(refs.values()))
    legs: list[DividendLeg] = []

    for row in rows:
        event_id = _event_id(row[col["ID"]])
        kind = str(row[col["Type"]] or "").strip()
        lowered = kind.lower()
        when = row[col["Time"]]
        if not isinstance(when, datetime):
            result.errors.append(f"XTB {event_id}: time is missing")
            continue
        executed_at = when.replace(tzinfo=_SERVER_TZ).astimezone(timezone.utc)
        amount = float(row[col["Amount"]] or 0.0)
        symbol = str(row[col["Symbol"]] or "").strip()
        comment = str(row[col["Comment"]] or "").strip()
        common = {"date": executed_at.date(), "executed_at": executed_at, "source": SOURCE,
                  "source_event_stream": STREAM, "source_event_id": event_id, "notes": comment}
        if lowered in _CFD:
            result.skip("CFD trade")
        elif lowered in _CASH:
            result.rows.append({**common, "type": _CASH[lowered], "ticker": None, "shares": 0.0,
                                "price": 0.0, "amount": abs(amount), "currency": account_ccy})
        elif lowered in _TRADES:
            match = _TRADE.match(comment)
            if not match:
                result.errors.append(f"XTB {event_id}: cannot read quantity/price from {comment!r}")
                continue
            ticker = resolved.get(refs.get(symbol))
            if ticker is None:
                continue  # reported once per symbol below
            suffix = symbol.rpartition(".")[2].upper()
            result.rows.append({**common, "type": "buy" if match.group(1) == "OPEN" else "sell",
                                "ticker": ticker, "name": symbol, "shares": float(match.group(2)),
                                "price": float(match.group(3)),
                                "currency": _PRICE_CCY.get(suffix, account_ccy),
                                "cash_amount": abs(amount), "cash_currency": account_ccy,
                                "source_instrument_id": symbol})
        elif lowered in _DIVIDENDS:
            ticker = resolved.get(refs.get(symbol))
            if ticker is None:
                continue
            # The dividend is paid in the account currency, so its price is
            # too; dividend analytics read cash_amount/cash_currency.
            legs.append(DividendLeg(group_key=f"{symbol}|{executed_at.date().isoformat()}",
                                    kind="tax" if lowered == "withholding tax" else "gross",
                                    ticker=ticker, name=symbol, pay_date=executed_at.date(),
                                    currency=account_ccy, amount=amount, executed_at=executed_at,
                                    instrument_id=symbol))
        else:
            result.errors.append(f"XTB {event_id}: unsupported operation type {kind!r}")

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors([r for r in refs.values() if r not in resolved], resolved))
    return result


FORMAT = ImportFormat("xtb", "XTB (xStation)", _detect, _parse)
