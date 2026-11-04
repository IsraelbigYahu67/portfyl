"""Degiro Account statement CSV: dividends, withholding, deposits, fees, FX.

Rows carrying an Order Id are the cash side of trades already imported from
Transactions.csv (whose Total includes fees and AutoFX), so they are counted
and skipped here.
"""
from __future__ import annotations

from collections import defaultdict

from currency_codes import normalize_currency
from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.formats._degiro_common import (
    DATE, ISIN, classify_description, numeric_cells, parse_degiro_date, read_degiro_csv,
)
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import detect_decimal, parse_number

SOURCE = "degiro"
FORMAT_NAME = "Degiro (Account statement)"
TRADE_SETTLEMENT = "trade settlement (imported from Transactions.csv)"
# Cash kind -> sign the amount must have.
_CASH_SIGNS = {"deposit": 1, "withdrawal": -1, "interest": 1, "fee": -1}


def _detect(file: ImportFile) -> bool:
    rows = read_degiro_csv(file, head_only=True)
    if len(rows) < 2 or not 11 <= len(rows[0]) <= 12:
        return False
    data = rows[1]
    return (len(data) >= 11 and bool(DATE.match(data[2].strip()))
            and (not data[4].strip() or bool(ISIN.match(data[4].strip()))))


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult(FORMAT_NAME, rows=[], source_events=0)
    rows = read_degiro_csv(file)[1:]
    result.source_events = len(rows)
    short = [index + 2 for index, row in enumerate(rows) if len(row) < 11]
    if short:
        result.errors.append(f"Rows {short[:10]} have fewer columns than the header")
        return result
    try:
        decimal = detect_decimal(numeric_cells(rows, (8, 10)))
    except ValueError as exc:
        result.errors.append(str(exc))
        return result
    ids = occurrence_ids([(r[0], r[1], r[5], r[7], r[8]) for r in rows])
    dividend_refs = {
        r[4].strip(): InstrumentRef(isin=r[4].strip(), name=r[3].strip())
        for r in rows if r[4].strip() and classify_description(r[5]) in {"gross", "tax"}
    }
    resolved = resolver.resolve_many(list(dividend_refs.values()))
    legs: list[DividendLeg] = []
    fx_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for index, row in enumerate(rows):
        label = f"Row {index + 2}"
        description = row[5].strip()
        order_id = row[11].strip() if len(row) > 11 else ""
        if order_id:
            result.skip(TRADE_SETTLEMENT)
            continue
        try:
            amount = parse_number(row[8], decimal=decimal)
            value_date = parse_degiro_date(row[2] or row[0])
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        if not amount:
            result.skip("informational row")
            continue
        kind = classify_description(description)
        currency = normalize_currency(row[7], default="")
        if not currency:
            result.errors.append(f"{label}: currency is missing for {description!r}")
            continue
        base = {"date": value_date, "currency": currency, "source": SOURCE,
                "source_event_stream": "account", "source_event_id": ids[index],
                "ticker": None, "shares": 0.0, "price": 0.0, "notes": description}
        if kind in {"gross", "tax"}:
            if not row[4].strip():
                result.errors.append(f"{label}: dividend entry {description!r} has no ISIN")
                continue
            ticker = resolved.get(dividend_refs[row[4].strip()])
            if ticker is None:
                continue  # reported once via unresolved_errors
            legs.append(DividendLeg(
                group_key=f"{row[4].strip()}|{value_date.isoformat()}", kind=kind,
                ticker=ticker, name=row[3].strip(), pay_date=value_date,
                currency=currency, amount=amount, instrument_id=row[4].strip(),
            ))
        elif kind in {"fx_in", "fx_out"}:
            if (amount > 0) != (kind == "fx_in"):
                result.errors.append(f"{label}: sign contradicts description {description!r}")
                continue
            fx_groups[(row[0].strip(), row[1].strip())].append({**base, "type": kind, "amount": abs(amount)})
        elif kind in _CASH_SIGNS:
            if amount * _CASH_SIGNS[kind] < 0:
                result.errors.append(f"{label}: sign contradicts description {description!r}")
                continue
            result.rows.append({**base, "type": kind, "amount": abs(amount)})
        else:
            result.errors.append(f"{label}: unsupported Degiro account entry {description!r}")

    for (day, time), legs_fx in fx_groups.items():
        if sorted(leg["type"] for leg in legs_fx) != ["fx_in", "fx_out"]:
            result.errors.append(f"unpaired currency conversion on {day} {time}")
            continue
        result.rows.extend(legs_fx)

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors(list(dividend_refs.values()), resolved))
    return result


FORMAT = ImportFormat("degiro_account", FORMAT_NAME, _detect, _parse)
