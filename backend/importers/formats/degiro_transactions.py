"""Degiro Inbox -> Transactions CSV (trades only; cash events are in Account.csv)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

from currency_codes import normalize_currency
from importers.base import ImportFile, ImportFormat, ParseResult
from importers.formats._degiro_common import (
    DATE, DEGIRO_VENUES, ISIN, numeric_cells, parse_degiro_date, read_degiro_csv,
)
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import detect_decimal, parse_number

SOURCE = "degiro"
FORMAT_NAME = "Degiro (Transactions)"
_AMS = ZoneInfo("Europe/Amsterdam")
# Public samples show two layouts. Compact: "Value EUR" / "Total EUR" carry the
# currency in the header and have no currency column after them (16-17 columns
# before Order ID). Wide: a currency column follows Value, fees and Total
# (19-20 columns). Not yet confirmed against a real export (plan Task 0).
_MIN_COLUMNS = 16
_CURRENCY = re.compile(r"^[A-Za-z]{3}$")


def _layout(header: list[str], rows: list[list[str]]) -> tuple[int, int | None]:
    """Return (index of Total, index of its currency column or None if compact)."""
    wide = any(len(row) > 12 and _CURRENCY.match(row[12].strip()) for row in rows)
    width = len(header)
    while width and not header[width - 1].strip():
        width -= 1  # a trailing empty header cell is not a column
    if wide:
        # Older wide exports have no "AutoFX Fee" column: everything from 14 on moves left.
        shift = 0 if width >= 20 else -1
        return 17 + shift, 18 + shift
    return (15 if width >= 17 else 14), None


def _total_currency(header: list[str], total: int) -> str:
    """Compact layouts name the currency in the header ("Total EUR")."""
    last = header[total].split()[-1] if total < len(header) and header[total].split() else ""
    return last.upper() if _CURRENCY.match(last) else "EUR"


def _detect(file: ImportFile) -> bool:
    rows = read_degiro_csv(file, head_only=True)
    if len(rows) < 2 or len(rows[0]) < _MIN_COLUMNS:
        return False
    data = rows[1]
    return (len(data) >= _MIN_COLUMNS - 1 and bool(DATE.match(data[0].strip()))
            and bool(ISIN.match(data[3].strip())))


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult(FORMAT_NAME, rows=[], source_events=0)
    table = read_degiro_csv(file)
    header, rows = table[0], table[1:]
    total, total_ccy = _layout(header, rows)
    last_needed = total if total_ccy is None else total_ccy
    result.source_events = len(rows)
    short = [index + 2 for index, row in enumerate(rows) if len(row) <= last_needed]
    if short:
        result.errors.append(f"Rows {short[:10]} have fewer columns than the header")
        return result
    try:
        decimal = detect_decimal(numeric_cells(rows, (6, 7, 9, 11, total)))
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    refs = [InstrumentRef(isin=r[3].strip(), venue=DEGIRO_VENUES.get(r[4].strip()),
                          name=r[2].strip(), currency=r[8].strip()) for r in rows]
    resolved = resolver.resolve_many(refs)
    fallback_ids = occurrence_ids([(r[0], r[1], r[3], r[6], r[7]) for r in rows])
    fills: Counter[str] = Counter()

    for index, (row, ref) in enumerate(zip(rows, refs)):
        label = f"Row {index + 2}"
        try:
            day = parse_degiro_date(row[0])
            quantity = parse_number(row[6], decimal=decimal)
            price = parse_number(row[7], decimal=decimal)
            total_value = parse_number(row[total], decimal=decimal)
            executed_at = None
            if row[1].strip():
                local = datetime.strptime(f"{row[0].strip()} {row[1].strip()}", "%d-%m-%Y %H:%M")
                executed_at = local.replace(tzinfo=_AMS).astimezone(timezone.utc)
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        if not quantity or price is None or total_value is None:
            result.errors.append(f"{label}: quantity, price or total is missing")
            continue
        ticker = resolved.get(ref)
        if ticker is None:
            continue  # reported once via unresolved_errors
        # Some exports leave "Order ID" empty and put the id in a trailing column.
        order_id = next((cell.strip() for cell in row[last_needed + 1:] if cell.strip()), "")
        if order_id:
            # One order can fill in several rows; their order in the file is stable.
            fills[order_id] += 1
            event_id = f"{order_id}:{fills[order_id]}"
        else:
            event_id = fallback_ids[index]
        result.rows.append({
            "date": day, "type": "buy" if quantity > 0 else "sell", "ticker": ticker,
            "name": row[2].strip(), "shares": abs(quantity), "price": price,
            "currency": normalize_currency(row[8]), "cash_amount": abs(total_value),
            "cash_currency": (normalize_currency(row[total_ccy]) if total_ccy is not None
                              else _total_currency(header, total)), "notes": "Degiro",
            "source": SOURCE, "source_event_stream": "trades", "source_event_id": event_id,
            "source_instrument_id": ref.isin, "executed_at": executed_at,
        })
    result.errors.extend(unresolved_errors(refs, resolved))
    return result


FORMAT = ImportFormat("degiro_transactions", FORMAT_NAME, _detect, _parse)
