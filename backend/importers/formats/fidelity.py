"""Fidelity Accounts -> Activity & Orders -> Download (CSV).

The column layout is from public examples, not yet from a real export: verify
it against a sample (plan Task 0) before relying on it. Action is free text,
classified by prefix. Money-market core positions are the account's cash:
their buys, sells and reinvestments are sweeps and their dividends interest.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import re

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import parse_number

SOURCE = "fidelity"
FORMAT_NAME = "Fidelity"
_HEADER = {"Run Date", "Action", "Symbol", "Amount ($)"}
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MONEY_MARKET = {"SPAXX", "FDRXX", "FZFXX", "SPRXX"}
# Prefix -> kind, checked in order.
_PREFIXES = (
    ("YOU BOUGHT", "buy"),
    ("REINVESTMENT", "buy"),
    ("YOU SOLD", "sell"),
    ("DIVIDEND RECEIVED", "gross"),
    ("FOREIGN TAX PAID", "tax"),
    ("NON-RESIDENT TAX", "tax"),
    ("INTEREST EARNED", "interest"),
    ("ELECTRONIC FUNDS TRANSFER", "transfer"),
    ("DIRECT DEPOSIT", "transfer"),
    ("TRANSFERRED FROM", "transfer"),
    ("TRANSFERRED TO", "transfer"),
    ("CASH CONTRIBUTION", "transfer"),
    ("FEE CHARGED", "fee"),
)


def _classify(action: str) -> str | None:
    upper = action.strip().upper()
    return next((kind for prefix, kind in _PREFIXES if upper.startswith(prefix)), None)


def _header_index(lines: list[list[str]]) -> int | None:
    return next((i for i, row in enumerate(lines) if _HEADER.issubset({c.strip() for c in row})), None)


def _table(text: str) -> list[dict]:
    lines = list(csv.reader(io.StringIO(text)))
    start = _header_index(lines)
    if start is None:
        return []
    header = [c.strip() for c in lines[start]]
    # Blank lines and the trailing disclaimer do not start with a date.
    return [dict(zip(header, (c.strip() for c in row))) for row in lines[start + 1:]
            if row and _DATE.match(row[0].strip())]


def _detect(file: ImportFile) -> bool:
    return _header_index(list(csv.reader(io.StringIO(file.head())))) is not None


def _symbol(raw: str | None) -> str:
    return (raw or "").strip().rstrip("*").strip().upper()


def _is_money_market(raw: str | None) -> bool:
    text = (raw or "").strip()
    return text.endswith("**") or _symbol(text) in _MONEY_MARKET


def _parse(file: ImportFile, resolver) -> ParseResult:
    rows = _table(file.text())
    result = ParseResult(FORMAT_NAME, rows=[], source_events=len(rows))
    refs = {_symbol(r.get("Symbol")): InstrumentRef(symbol=_symbol(r.get("Symbol")), venue="US",
                                                     name=r.get("Description"))
            for r in rows if _symbol(r.get("Symbol")) and not _is_money_market(r.get("Symbol"))}
    resolved = resolver.resolve_many(list(refs.values()))
    ids = occurrence_ids([(r.get("Run Date"), r.get("Action"), r.get("Symbol"), r.get("Quantity"),
                           r.get("Price ($)"), r.get("Amount ($)")) for r in rows])
    legs: list[DividendLeg] = []
    for index, row in enumerate(rows):
        action = row.get("Action") or ""
        label = f"Fidelity {row.get('Run Date')} {action}"
        kind = _classify(action)
        try:
            day = datetime.strptime(row["Run Date"], "%m/%d/%Y").date()
            amount = parse_number(row.get("Amount ($)"), decimal=".") or 0.0
            quantity = parse_number(row.get("Quantity"), decimal=".")
            price = parse_number(row.get("Price ($)"), decimal=".")
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        money_market = _is_money_market(row.get("Symbol"))
        if money_market and kind in {"buy", "sell"}:
            result.skip("money market sweep")
            continue
        if money_market and kind == "gross":
            kind = "interest"
        symbol = _symbol(row.get("Symbol"))
        ticker = resolved.get(refs[symbol]) if symbol in refs else None
        common = {"date": day, "currency": "USD", "source": SOURCE,
                  "source_event_stream": "activity", "source_event_id": ids[index],
                  "notes": action}
        if kind in {"buy", "sell"}:
            if not quantity or ticker is None:
                result.errors.append(f"{label}: quantity or symbol missing")
                continue
            if price is None:
                price = abs(amount) / abs(quantity)
            result.rows.append({**common, "type": kind, "ticker": ticker, "name": row.get("Description"),
                                "shares": abs(quantity), "price": price,
                                "cash_amount": abs(amount), "cash_currency": "USD"})
        elif kind in {"gross", "tax"}:
            if ticker is None:
                result.errors.append(f"{label}: dividend without symbol")
                continue
            legs.append(DividendLeg(group_key=f"{ticker}|{day.isoformat()}", kind=kind, ticker=ticker,
                                    name=row.get("Description"), pay_date=day, currency="USD",
                                    amount=amount))
        elif kind in {"interest", "fee", "transfer"}:
            if kind == "interest":
                sign_ok = amount > 0
            elif kind == "fee":
                sign_ok = amount < 0
            else:
                kind, sign_ok = ("deposit" if amount > 0 else "withdrawal"), amount != 0
            if not sign_ok:
                result.errors.append(f"{label}: amount {amount} does not fit the action")
                continue
            result.rows.append({**common, "type": kind, "ticker": None, "shares": 0.0,
                                "price": 0.0, "amount": abs(amount)})
        else:
            result.errors.append(f"{label}: unsupported Fidelity action {action!r}")
    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors(list(refs.values()), resolved))
    return result


FORMAT = ImportFormat("fidelity", FORMAT_NAME, _detect, _parse)
