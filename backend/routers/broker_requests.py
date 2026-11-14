"""'Notify me when my broker is supported' (onboarding-flow plan, Task 3).

A user whose broker has no importer can leave its name. The name is free text,
so it is whitespace-collapsed, length-limited and only ever stored and
returned as plain text (never interpreted as markup here or by the UI).
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import BrokerRequest
from tenancy import RequestContext, require_csrf

router = APIRouter(prefix="/broker-requests", tags=["broker-requests"])

MAX_NAME_LENGTH = 60
MAX_PER_WORKSPACE = 20
# Anything longer than this cannot become a valid name; skip normalizing it.
_MAX_RAW_LENGTH = 2000


class BrokerRequestPayload(BaseModel):
    broker_name: str


def normalize_broker_name(raw: str) -> str | None:
    """Trimmed, inner whitespace collapsed; None when empty or too long."""
    if len(raw) > _MAX_RAW_LENGTH or "\x00" in raw:
        return None
    name = " ".join(raw.split())
    if not name or len(name) > MAX_NAME_LENGTH:
        return None
    return name


def _find_existing(db: Session, workspace_id, name: str) -> BrokerRequest | None:
    return db.query(BrokerRequest).filter(
        BrokerRequest.workspace_id == workspace_id,
        func.lower(BrokerRequest.broker_name) == func.lower(name),
    ).first()


@router.post("")
def create_broker_request(
    body: BrokerRequestPayload,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
):
    name = normalize_broker_name(body.broker_name)
    if name is None:
        return JSONResponse({"code": "invalid_broker_name"}, status_code=422)

    # Read once: the commit below expires the context's ORM objects.
    workspace_id = context.workspace.id
    user_id = context.user.id

    existing = _find_existing(db, workspace_id, name)
    if existing is not None:
        return JSONResponse({"broker_name": existing.broker_name, "created": False})

    # Count-then-insert is not atomic: two truly concurrent requests can overshoot
    # the cap by a row or two. Accepted; it only limits abuse.
    count = db.query(func.count(BrokerRequest.id)).filter(
        BrokerRequest.workspace_id == workspace_id,
    ).scalar()
    if count >= MAX_PER_WORKSPACE:
        return JSONResponse({"code": "broker_request_limit"}, status_code=429)

    db.add(BrokerRequest(workspace_id=workspace_id, user_id=user_id, broker_name=name))
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request stored the same name between our check and insert.
        db.rollback()
        existing = _find_existing(db, workspace_id, name)
        if existing is None:
            raise
        return JSONResponse({"broker_name": existing.broker_name, "created": False})
    return JSONResponse({"broker_name": name, "created": True}, status_code=201)
