"""Workspace-scoped, single-use recovery point for the latest CSV import."""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import zlib
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from models import (
    BrokerConnection,
    BrokerCorporateAction,
    BrokerCorporateActionApplication,
    Portfolio,
    TradeNote,
    Transaction,
    WorkspaceSetting,
)


UNDO_WINDOW = timedelta(hours=24)
UNDO_KEY_PREFIX = "import_undo:"
UNDO_SCHEMA_VERSION = 3
_SUPPORTED_UNDO_SCHEMA_VERSIONS = {1, 2, UNDO_SCHEMA_VERSION}

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
    "source_event_id",
    "source_event_stream",
    "source_account_fingerprint",
    "source_credential_generation",
    "source_instrument_id",
    "source_fill_type",
    "executed_at",
    "source_payload_hash",
    "source_mapper_version",
    "fx_to_czk",
    "created_at",
)

_ACTION_FIELDS = (
    "public_id",
    "broker",
    "account_fingerprint",
    "provider_instrument_id",
    "ticker",
    "action_type",
    "effective_at",
    "provider_event_key",
    "ratio_numerator",
    "ratio_denominator",
    "representation",
    "run_id",
    "created_at",
)
# Identifies an action inside one portfolio; used instead of the integer id,
# which changes on restore.
_ACTION_IDENTITY_FIELDS = (
    "account_fingerprint",
    "provider_instrument_id",
    "action_type",
    "effective_at",
    "provider_event_key",
)
_APPLICATION_FIELDS = (
    "shares_before",
    "price_before",
    "shares_after",
    "price_after",
    "applied_by_run_id",
    "applied_at",
)
# Snapshot keys that only exist from schema v3 on.
_V3_ONLY_KEYS = ("corporate_actions", "corporate_action_applications")

_V1_TRANSACTION_FIELDS = tuple(
    field
    for field in _TRANSACTION_FIELDS
    if field not in {
        "source_event_id",
        "source_event_stream",
        "source_account_fingerprint",
        "source_credential_generation",
        "source_instrument_id",
        "source_fill_type",
        "executed_at",
        "source_payload_hash",
        "source_mapper_version",
    }
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
    if isinstance(value, Decimal):
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
    actions = db.query(BrokerCorporateAction).filter(
        BrokerCorporateAction.workspace_id == portfolio.workspace_id,
        BrokerCorporateAction.portfolio_id == portfolio.id,
    ).order_by(BrokerCorporateAction.public_id).all()
    action_by_id = {action.id: action for action in actions}
    transaction_index = {row.id: index for index, row in enumerate(transactions)}
    applications = []
    if action_by_id and transaction_index:
        applications = db.query(BrokerCorporateActionApplication).filter(
            BrokerCorporateActionApplication.workspace_id == portfolio.workspace_id,
            BrokerCorporateActionApplication.action_id.in_(list(action_by_id)),
        ).order_by(BrokerCorporateActionApplication.id).all()
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
        "corporate_actions": [
            {field: _json_value(getattr(action, field)) for field in _ACTION_FIELDS}
            for action in actions
        ],
        "corporate_action_applications": [
            {
                "transaction_index": transaction_index[application.transaction_id],
                "action": {
                    field: _json_value(getattr(action_by_id[application.action_id], field))
                    for field in _ACTION_IDENTITY_FIELDS
                },
                **{field: _json_value(getattr(application, field)) for field in _APPLICATION_FIELDS},
            }
            for application in applications
            if application.transaction_id in transaction_index
        ],
    }


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_v2_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project current state to the shape used by still-live v2 undo points,
    which were taken before corporate-action records existed."""
    return {key: value for key, value in snapshot.items() if key not in _V3_ONLY_KEYS}


def _as_v1_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project current state to the shape used by still-live v1 undo points."""
    return {
        **_as_v2_snapshot(snapshot),
        "transactions": [
            {
                "public_id": item["public_id"],
                **{field: item.get(field) for field in _V1_TRANSACTION_FIELDS},
            }
            for item in snapshot.get("transactions", [])
        ],
    }


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode("ascii")


def _decode(raw: str) -> dict:
    try:
        decoded = zlib.decompress(base64.urlsafe_b64decode(raw.encode("ascii")))
        payload = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error) as exc:
        raise ValueError("Invalid import undo snapshot") from exc
    if payload.get("schema_version") not in _SUPPORTED_UNDO_SCHEMA_VERSIONS:
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
    if payload["schema_version"] == 1:
        current = _as_v1_snapshot(current)
    elif payload["schema_version"] == 2:
        current = _as_v2_snapshot(current)
    if snapshot_fingerprint(current) != payload["after_fingerprint"]:
        return {"available": False, "reason": "portfolio_changed", **base}
    return {"available": True, "reason": None, **base}


def _action_key(item: dict[str, Any]) -> tuple:
    return tuple(str(item.get(field)) for field in _ACTION_IDENTITY_FIELDS)


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
    # Corporate-action records describe this ledger, so they are replaced with
    # it. Applications go first: they reference both actions and transactions.
    action_ids = [
        action_id for (action_id,) in db.query(BrokerCorporateAction.id).filter(
            BrokerCorporateAction.workspace_id == portfolio.workspace_id,
            BrokerCorporateAction.portfolio_id == portfolio.id,
        ).all()
    ]
    if action_ids:
        db.query(BrokerCorporateActionApplication).filter(
            BrokerCorporateActionApplication.workspace_id == portfolio.workspace_id,
            BrokerCorporateActionApplication.action_id.in_(action_ids),
        ).delete(synchronize_session="fetch")
        db.query(BrokerCorporateAction).filter(
            BrokerCorporateAction.workspace_id == portfolio.workspace_id,
            BrokerCorporateAction.id.in_(action_ids),
        ).delete(synchronize_session="fetch")
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
    restored_in_order: list[Transaction] = []
    for item in snapshot.get("transactions", []):
        values = {field: item.get(field) for field in _TRANSACTION_FIELDS}
        values["date"] = date.fromisoformat(values["date"])
        if values.get("executed_at"):
            values["executed_at"] = datetime.fromisoformat(values["executed_at"])
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
        restored_in_order.append(transaction)
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

    # v1/v2 points carry no action data, which is correct: they predate any action.
    restored_actions: dict[tuple, BrokerCorporateAction] = {}
    for item in snapshot.get("corporate_actions", []):
        values = {field: item.get(field) for field in _ACTION_FIELDS}
        values["public_id"] = UUID(values["public_id"])
        values["ratio_numerator"] = Decimal(values["ratio_numerator"])
        values["ratio_denominator"] = Decimal(values["ratio_denominator"])
        values["effective_at"] = datetime.fromisoformat(values["effective_at"])
        if values.get("created_at"):
            values["created_at"] = datetime.fromisoformat(values["created_at"])
        action = BrokerCorporateAction(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id, **values,
        )
        db.add(action)
        restored_actions[_action_key(item)] = action
    db.flush()
    for item in snapshot.get("corporate_action_applications", []):
        action = restored_actions.get(_action_key(item["action"]))
        index = item["transaction_index"]
        if action is None or not 0 <= index < len(restored_in_order):
            raise ValueError("Undo application refers to a missing action or transaction")
        values = {field: item.get(field) for field in _APPLICATION_FIELDS}
        if values.get("applied_at"):
            values["applied_at"] = datetime.fromisoformat(values["applied_at"])
        db.add(BrokerCorporateActionApplication(
            workspace_id=portfolio.workspace_id, action_id=action.id,
            transaction_id=restored_in_order[index].id, **values,
        ))
    db.flush()

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
