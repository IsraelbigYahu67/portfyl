"""Charles Schwab History -> Transactions CSV export."""
from __future__ import annotations

import csv
from datetime import datetime
import io

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import parse_number

SOURCE = "schwab"
FORMAT_NAME = "Charles Schwab"
_HEADER = {"Date", "Action", "Symbol", "Amount", "Fees & Comm"}
_BUY = {"Buy", "Reinvest Shares"}
_SELL = {"Sell"}
_GROSS = {"Cash Dividend", "Qualified Dividend", "Non-Qualified Div", "Reinvest Dividend",
          "Special Dividend", "Pr Yr Cash Div"}
_TAX = {"NRA Tax Adj", "Foreign Tax Paid", "NRA Withholding"}
_INTEREST = {"Bank Interest", "Credit Interest"}
_TRANSFER = {"MoneyLink Transfer", "Wire Funds", "Wire Received", "Funds Received", "Journal"}
_FEE = {"ADR Mgmt Fee", "Service Fee", "Margin Interest"}
# Option legs are not modelled by the ledger; count them instead of failing.
_OPTIONS = {"Buy to Open", "Sell to Close", "Sell to Open", "Buy to Close", "Expired"}


def _header_index(lines: list[list[str]]) -> int | None:
    return next((i for i, row in enumerate(lines) if _HEADER.issubset({c.strip() for c in row})), None)


def _table(text: str) -> list[dict]:
    lines = list(csv.reader(io.StringIO(text)))
    start = _header_index(lines)
    if start is None:
        return []
    header = [c.strip() for c in lines[start]]
    rows = []
    for row in lines[start + 1:]:
        if not row or not any(c.strip() for c in row):
            continue
        if row[0].strip().startswith("Transactions Total"):
            break
        rows.append(dict(zip(header, (c.strip() for c in row))))
    return rows


def _detect(file: ImportFile) -> bool:
    return _header_index(list(csv.reader(io.StringIO(file.head())))) is not None


def _parse(file: ImportFile, resolver) -> ParseResult:
    rows = _table(file.text())
    result = ParseResult(FORMAT_NAME, rows=[], source_events=len(rows))
    refs = {r["Symbol"]: InstrumentRef(symbol=r["Symbol"], venue="US", name=r.get("Description"))
            for r in rows if r.get("Symbol") and r.get("Action") not in _OPTIONS}
    resolved = resolver.resolve_many(list(refs.values()))
    ids = occurrence_ids([(r.get("Date"), r.get("Action"), r.get("Symbol"), r.get("Quantity"),
                           r.get("Price"), r.get("Amount")) for r in rows])
    legs: list[DividendLeg] = []
    for index, row in enumerate(rows):
        action = row.get("Action") or ""
        label = f"Schwab {row.get('Date')} {action}"
        if action in _OPTIONS:
            result.skip("options (not imported)")
            continue
        try:
            day = datetime.strptime((row.get("Date") or "").split(" as of ")[0].strip(), "%m/%d/%Y").date()
            amount = parse_number(row.get("Amount"), decimal=".") or 0.0
            quantity = parse_number(row.get("Quantity"), decimal=".")
            price = parse_number(row.get("Price"), decimal=".")
            fees = parse_number(row.get("Fees & Comm"), decimal=".") or 0.0
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        symbol = row.get("Symbol") or ""
        ticker = resolved.get(refs[symbol]) if symbol in refs else None
        common = {"date": day, "currency": "USD", "source": SOURCE,
                  "source_event_stream": "transactions", "source_event_id": ids[index],
                  "notes": row.get("Description") or action}
        if action in _BUY | _SELL:
            if not quantity or ticker is None:
                result.errors.append(f"{label}: quantity or symbol missing")
                continue
            if price is None:
                price = (abs(amount) - abs(fees)) / abs(quantity)
            result.rows.append({**common, "type": "buy" if action in _BUY else "sell", "ticker": ticker,
                                "name": row.get("Description"), "shares": abs(quantity), "price": price,
                                "cash_amount": abs(amount), "cash_currency": "USD"})
        elif action in _GROSS | _TAX:
            if ticker is None:
                result.errors.append(f"{label}: dividend without symbol")
                continue
            legs.append(DividendLeg(group_key=f"{ticker}|{day.isoformat()}",
                                    kind="tax" if action in _TAX else "gross", ticker=ticker,
                                    name=row.get("Description"), pay_date=day, currency="USD",
                                    amount=amount))
        elif action in _INTEREST | _TRANSFER | _FEE:
            if action in _INTEREST:
                kind, sign_ok = "interest", amount > 0
            elif action in _FEE:
                kind, sign_ok = "fee", amount < 0
            else:
                kind, sign_ok = ("deposit" if amount > 0 else "withdrawal"), amount != 0
            if not sign_ok:
                result.errors.append(f"{label}: amount {amount} does not fit the action")
                continue
            result.rows.append({**common, "type": kind, "ticker": None, "shares": 0.0,
                                "price": 0.0, "amount": abs(amount)})
        elif action == "Stock Split" and ticker and quantity and quantity > 0:
            result.rows.append({**common, "type": "split_open", "ticker": ticker, "shares": quantity,
                                "price": 0.0})
        else:
            result.errors.append(f"{label}: unsupported Schwab action {action!r}")
    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors(list(refs.values()), resolved))
    return result


FORMAT = ImportFormat("schwab", FORMAT_NAME, _detect, _parse)
