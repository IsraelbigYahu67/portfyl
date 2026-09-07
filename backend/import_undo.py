"""Workspace-scoped, single-use recovery point for the latest CSV import."""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import zlib
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from models import BrokerConnection, Portfolio, TradeNote, Transaction, WorkspaceSetting


UNDO_WINDOW = timedelta(hours=24)
UNDO_KEY_PREFIX = "import_undo:"
UNDO_SCHEMA_VERSION = 1

_TRANSACTION_FIELDS = (
    "ticker",
    "name",
    "type",
    "shares",
    "price",
    "amount",
    "currency",
    "cash_amount",
    "cash_currency",
    "date",
    "notes",
    "source",
    "fx_to_czk",
    "created_at",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def undo_setting_key(portfolio: Portfolio) -> str:
    return f"{UNDO_KEY_PREFIX}{portfolio.public_id}"


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def capture_portfolio_state(db: Session, portfolio: Portfolio) -> dict[str, Any]:
    transactions = db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).order_by(Transaction.public_id).all()
    transaction_public_ids = {row.id: str(row.public_id) for row in transactions}
    notes = []
    if transaction_public_ids:
        note_rows = db.query(TradeNote).filter(
            TradeNote.workspace_id == portfolio.workspace_id,
            TradeNote.transaction_id.in_(list(transaction_public_ids)),
        ).order_by(TradeNote.public_id).all()
        notes = [
            {
                "public_id": str(note.public_id),
                "transaction_id": transaction_public_ids[note.transaction_id],
                "content": note.content,
                "tags": note.tags,
                "sentiment": note.sentiment,
                "updated_at": _json_value(note.updated_at),
            }
            for note in note_rows
        ]
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == portfolio.workspace_id,
        BrokerConnection.portfolio_id == portfolio.id,
    ).order_by(BrokerConnection.public_id).all()
    return {
        "portfolio": {
            "t212_csv_covered_through": _json_value(portfolio.t212_csv_covered_through),
        },
        "broker_connections": [
            {
                "public_id": str(connection.public_id),
                "t212_csv_covered_through": _json_value(connection.t212_csv_covered_through),
            }
            for connection in connections
        ],
        "transactions": [
            {
                "public_id": str(transaction.public_id),
                **{
                    field: _json_value(getattr(transaction, field))
                    for field in _TRANSACTION_FIELDS
                },
            }
            for transaction in transactions
        ],
        "notes": notes,
    }


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode("ascii")


def _decode(raw: str) -> dict:
    try:
        decoded = zlib.decompress(base64.urlsafe_b64decode(raw.encode("ascii")))
        payload = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error) as exc:
        raise ValueError("Invalid import undo snapshot") from exc
    if payload.get("schema_version") != UNDO_SCHEMA_VERSION:
        raise ValueError("Unsupported import undo snapshot")
    return payload


def _setting(db: Session, portfolio: Portfolio) -> WorkspaceSetting | None:
    return db.query(WorkspaceSetting).filter(
        WorkspaceSetting.workspace_id == portfolio.workspace_id,
        WorkspaceSetting.key == undo_setting_key(portfolio),
    ).first()


def save_undo_snapshot(
    db: Session,
    portfolio: Portfolio,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    mode: str,
    imported: int,
    format_name: str,
    now: datetime | None = None,
) -> dict:
    created_at = _as_utc(now or _utcnow())
    payload = {
        "schema_version": UNDO_SCHEMA_VERSION,
        "portfolio_id": str(portfolio.public_id),
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + UNDO_WINDOW).isoformat(),
        "mode": mode,
        "format": format_name,
        "imported": int(imported),
        "before": before,
        "after_fingerprint": snapshot_fingerprint(after),
    }
    row = _setting(db, portfolio)
    if row is None:
        row = WorkspaceSetting(
            workspace_id=portfolio.workspace_id,
            key=undo_setting_key(portfolio),
            value=_encode(payload),
        )
        db.add(row)
    else:
        row.value = _encode(payload)
    db.flush()
    return payload


def load_undo_snapshot(db: Session, portfolio: Portfolio) -> dict | None:
    row = _setting(db, portfolio)
    if row is None or not row.value:
        return None
    payload = _decode(row.value)
    if payload.get("portfolio_id") != str(portfolio.public_id):
        raise ValueError("Import undo snapshot belongs to another portfolio")
    return payload


def clear_undo_snapshot(db: Session, portfolio: Portfolio) -> bool:
    row = _setting(db, portfolio)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def undo_status(
    db: Session,
    portfolio: Portfolio,
    *,
    now: datetime | None = None,
) -> dict:
    try:
        payload = load_undo_snapshot(db, portfolio)
    except ValueError:
        return {"available": False, "reason": "snapshot_invalid"}
    if payload is None:
        return {"available": False, "reason": None}

    checked_at = _as_utc(now or _utcnow())
    expires_at = _as_utc(datetime.fromisoformat(payload["expires_at"]))
    base = {
        "mode": payload["mode"],
        "format": payload["format"],
        "imported": payload["imported"],
        "created_at": payload["created_at"],
        "expires_at": payload["expires_at"],
    }
    if checked_at >= expires_at:
        return {"available": False, "reason": "expired", **base}

    current = capture_portfolio_state(db, portfolio)
    if snapshot_fingerprint(current) != payload["after_fingerprint"]:
        return {"available": False, "reason": "portfolio_changed", **base}
    return {"available": True, "reason": None, **base}


def restore_snapshot(
    db: Session,
    portfolio: Portfolio,
    snapshot: dict[str, Any],
) -> int:
    current_ids = [
        row_id for (row_id,) in db.query(Transaction.id).filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
        ).all()
    ]
    if current_ids:
        db.query(TradeNote).filter(
            TradeNote.workspace_id == portfolio.workspace_id,
            TradeNote.transaction_id.in_(current_ids),
        ).delete(synchronize_session="fetch")
    db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).delete(synchronize_session="fetch")
    db.flush()

    restored_by_public_id: dict[str, Transaction] = {}
    for item in snapshot.get("transactions", []):
        values = {field: item.get(field) for field in _TRANSACTION_FIELDS}
        values["date"] = date.fromisoformat(values["date"])
        if values.get("created_at"):
            values["created_at"] = datetime.fromisoformat(values["created_at"])
        transaction = Transaction(
            public_id=UUID(item["public_id"]),
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            **values,
        )
        db.add(transaction)
        restored_by_public_id[item["public_id"]] = transaction
    db.flush()

    for item in snapshot.get("notes", []):
        transaction = restored_by_public_id.get(item["transaction_id"])
        if transaction is None:
            raise ValueError("Undo note refers to a missing transaction")
        db.add(TradeNote(
            public_id=UUID(item["public_id"]),
            workspace_id=portfolio.workspace_id,
            transaction_id=transaction.id,
            content=item.get("content") or "",
            tags=item.get("tags"),
            sentiment=item.get("sentiment"),
            updated_at=(
                datetime.fromisoformat(item["updated_at"])
                if item.get("updated_at") else None
            ),
        ))

    portfolio_coverage = snapshot.get("portfolio", {}).get("t212_csv_covered_through")
    portfolio.t212_csv_covered_through = (
        datetime.fromisoformat(portfolio_coverage) if portfolio_coverage else None
    )
    coverage_by_connection = {
        item["public_id"]: item.get("t212_csv_covered_through")
        for item in snapshot.get("broker_connections", [])
    }
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == portfolio.workspace_id,
        BrokerConnection.portfolio_id == portfolio.id,
    ).all()
    for connection in connections:
        coverage = coverage_by_connection.get(str(connection.public_id))
        connection.t212_csv_covered_through = (
            datetime.fromisoformat(coverage) if coverage else None
        )
    db.flush()
    return len(restored_by_public_id)
