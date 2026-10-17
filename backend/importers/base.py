"""Contract between broker format modules and the CSV import endpoints."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from cash_ledger import CASH_TYPES, POSITION_TYPES
from import_workflow import _IMPORTED_FIELDS

if TYPE_CHECKING:
    from importers.instruments import InstrumentResolver

ALLOWED_ROW_KEYS = frozenset(_IMPORTED_FIELDS)
LEDGER_TYPES = POSITION_TYPES | CASH_TYPES
MAX_REPORTED_ERRORS = 100


@dataclass(frozen=True)
class ImportFile:
    filename: str
    content: bytes

    def text(self, encoding: str = "utf-8-sig") -> str:
        return self.content.decode(encoding)

    def head(self, size: int = 4096) -> str:
        return self.content[:size].decode("utf-8-sig", errors="replace")


@dataclass
class ParseResult:
    format_name: str
    rows: list[dict]
    source_events: int
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return sum(self.skipped_reasons.values())

    def skip(self, reason: str) -> None:
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


@dataclass(frozen=True)
class ImportFormat:
    key: str
    format_name: str
    detect: Callable[[ImportFile], bool]
    parse: Callable[[ImportFile, "InstrumentResolver"], ParseResult]


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def validate_rows(rows: list[dict]) -> list[str]:
    """Shape check every parser's output against the ledger before preview."""
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        label = f"Row {index} ({row.get('type')} {row.get('ticker') or ''})".replace(" )", ")")
        extra = set(row) - ALLOWED_ROW_KEYS
        if extra:
            errors.append(f"{label}: unsupported fields {sorted(extra)}")
        kind = row.get("type")
        if kind not in LEDGER_TYPES:
            errors.append(f"{label}: unsupported type {kind!r}")
            continue
        if not isinstance(row.get("date"), date):
            errors.append(f"{label}: date is missing")
        if not row.get("currency"):
            errors.append(f"{label}: currency is missing")
        if not row.get("source") or not row.get("source_event_stream") or not row.get("source_event_id"):
            errors.append(f"{label}: source event identity is missing")
        if kind in CASH_TYPES:
            if not _positive(row.get("amount")):
                errors.append(f"{label}: amount must be greater than 0")
        else:
            if not row.get("ticker"):
                errors.append(f"{label}: ticker is missing")
            if not _positive(row.get("shares")):
                errors.append(f"{label}: shares must be greater than 0")
            if not isinstance(row.get("price"), (int, float)) or row["price"] < 0:
                errors.append(f"{label}: price must be 0 or more")
    return errors[:MAX_REPORTED_ERRORS]
