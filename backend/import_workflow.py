"""Pure CSV import comparison primitives.

Parsing remains broker-format-specific, while this module owns the stable
business identity used for preview, duplicate detection, reconciliation and
preview/commit drift detection.  Functions accept either dictionaries or ORM
objects so the same rules compare uploaded rows with persisted transactions.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


IDENTITY_FIELDS = (
    "date",
    "type",
    "ticker",
    "shares",
    "price",
    "amount",
    "currency",
    "cash_amount",
    "cash_currency",
    "notes",
)

_IMPORTED_FIELDS = (
    "date",
    "type",
    "ticker",
    "name",
    "shares",
    "price",
    "amount",
    "currency",
    "cash_amount",
    "cash_currency",
    "notes",
    "source",
    "fx_to_czk",
)


def _get(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _number(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip()
    if not number.is_finite():
        return str(value).strip().lower()
    normalized = number.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _text(value: Any, *, upper: bool = False, lower: bool = False) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    if upper:
        return rendered.upper()
    if lower:
        return rendered.lower()
    return rendered


def _date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    rendered = str(value).strip()
    try:
        return date.fromisoformat(rendered[:10]).isoformat()
    except ValueError:
        return rendered


def canonical_transaction(row: Any) -> tuple[str | None, ...]:
    """Return the source/id/name/FX-independent identity of one ledger row."""
    return (
        _date(_get(row, "date")),
        _text(_get(row, "type"), lower=True),
        _text(_get(row, "ticker"), upper=True),
        _number(_get(row, "shares")),
        _number(_get(row, "price")),
        _number(_get(row, "amount")),
        _text(_get(row, "currency"), upper=True),
        _number(_get(row, "cash_amount")),
        _text(_get(row, "cash_currency"), upper=True),
        _text(_get(row, "notes")),
    )


def deduplicate_rows(rows: Sequence[Any]) -> tuple[list[Any], int]:
    """Keep the first exact business event and count later occurrences."""
    seen: set[tuple[str | None, ...]] = set()
    unique: list[Any] = []
    repeated = 0
    for row in rows:
        identity = canonical_transaction(row)
        if identity in seen:
            repeated += 1
            continue
        seen.add(identity)
        unique.append(row)
    return unique, repeated


def state_fingerprint(rows: Sequence[Any]) -> str:
    """Order-independent fingerprint that preserves duplicate multiplicity."""
    identities = sorted(
        (canonical_transaction(row) for row in rows),
        key=lambda identity: json.dumps(identity, separators=(",", ":")),
    )
    encoded = json.dumps(identities, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _imported_row(row: Any) -> dict[str, str | None]:
    return {
        "date": _date(_get(row, "date")),
        "type": _text(_get(row, "type"), lower=True),
        "ticker": _text(_get(row, "ticker"), upper=True),
        "name": _text(_get(row, "name")),
        "shares": _number(_get(row, "shares")),
        "price": _number(_get(row, "price")),
        "amount": _number(_get(row, "amount")),
        "currency": _text(_get(row, "currency"), upper=True),
        "cash_amount": _number(_get(row, "cash_amount")),
        "cash_currency": _text(_get(row, "cash_currency"), upper=True),
        "notes": _text(_get(row, "notes")),
        "source": _text(_get(row, "source"), lower=True),
        "fx_to_czk": _number(_get(row, "fx_to_czk")),
    }


def _preview_fingerprint(
    *,
    current_rows: Sequence[Any],
    incoming_rows: Sequence[Any],
    portfolio_public_id: str,
    mode: str,
    current_state_fingerprint: str | None,
) -> str:
    payload = {
        "version": 1,
        "portfolio_id": str(portfolio_public_id),
        "mode": mode,
        "current": current_state_fingerprint or state_fingerprint(current_rows),
        # Preserve source-file multiplicity here even though duplicate rows are
        # collapsed for insertion. A changed upload requires a fresh preview.
        "incoming": [_imported_row(row) for row in incoming_rows],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_preview(
    *,
    current_rows: Sequence[Any],
    incoming_rows: Sequence[Any],
    requested_replace: bool,
    mandatory_replace: bool,
    portfolio_public_id: str,
    source_events: int,
    skipped: int,
    format_name: str,
    current_state_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Compare one normalized upload to the persisted portfolio state."""
    replace = bool(requested_replace or mandatory_replace)
    mode = "replace" if replace else "append"
    unique_rows, duplicates_in_file = deduplicate_rows(incoming_rows)
    current_counts = Counter(canonical_transaction(row) for row in current_rows)
    incoming_identities = [canonical_transaction(row) for row in unique_rows]
    incoming_set = set(incoming_identities)
    duplicates_existing = sum(identity in current_counts for identity in incoming_identities)

    if replace:
        unchanged = sum(min(current_counts[identity], 1) for identity in incoming_set)
        removed = len(current_rows) - unchanged
        added = len(unique_rows) - unchanged
        projected = len(unique_rows)
        rows_to_insert = unique_rows
    else:
        unchanged = len(current_rows)
        removed = 0
        rows_to_insert = [
            row for row, identity in zip(unique_rows, incoming_identities)
            if identity not in current_counts
        ]
        added = len(rows_to_insert)
        projected = len(current_rows) + added

    return {
        "preview_id": _preview_fingerprint(
            current_rows=current_rows,
            incoming_rows=incoming_rows,
            portfolio_public_id=portfolio_public_id,
            mode=mode,
            current_state_fingerprint=current_state_fingerprint,
        ),
        "format": format_name,
        "mode": mode,
        "mandatory_replace": bool(mandatory_replace),
        "counts": {
            "source_events": int(source_events),
            "recognized_rows": len(incoming_rows),
            "unique_rows": len(unique_rows),
            "duplicates_in_file": duplicates_in_file,
            "duplicates_existing": duplicates_existing,
            "current": len(current_rows),
            "added": added,
            "removed": removed,
            "unchanged": unchanged,
            "projected": projected,
            "skipped": int(skipped),
        },
        # Internal commit input. Routers must serialize only a bounded sample,
        # never an unbounded second copy of an uploaded portfolio.
        "rows_to_insert": rows_to_insert,
    }
