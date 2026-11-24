"""Workspace data portability and verified deletion endpoints."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from account_deletion import (
    cancel_workspace_deletion,
    delete_workspace_now,
    deletion_status_payload,
    get_workspace_deletion,
    send_account_deleted_notice,
)
from auth import clear_session_cookie
from billing_sync import make_stripe_client
from database import get_db, release_connection
from firebase_identity import FirebaseIdentityVerifier, IdentityVerificationError
from routers.auth import get_identity_verifier
from routers.auth_email import Mailer, get_mailer
from tenancy import (
    RequestContext,
    RequestContextError,
    get_request_context,
    require_csrf,
)
from workspace_export import build_workspace_export


logger = logging.getLogger("portfyl.account")

router = APIRouter(prefix="/account", tags=["account"])


class DeletionRequestPayload(BaseModel):
    reauth_id_token: str = Field(min_length=1)
    confirmation: str = Field(min_length=1)
    # The app language, for the confirmation e-mail. Accepts anything: a
    # garbage value gives English, never a 422.
    lang: Any = None
    # The owner's explicit consent to end a paid subscription immediately:
    # within 14 days of the order it is a withdrawal (full refund), later the
    # rest of the paid period is lost. Without it a renewing subscription
    # still answers 409 active_subscription (also a paid cancel_at_period_end
    # or past_due one while the withdrawal window is open).
    cancel_subscription: bool = False
    # What the dialog promised: a full refund (true) or none. When true and the
    # server finds that no refund would happen any more, it answers 409
    # ``withdrawal_window_changed`` before touching Stripe or the data, so the
    # UI can reload and show the truth. Absent/false: behaviour unchanged.
    refund_expected: bool = False


def get_stripe_client_factory(request: Request) -> Callable[[], Any]:
    """A lazy Stripe client builder: only called when a subscription must be
    cancelled, so a workspace without one never needs Stripe configured."""
    config = request.app.state.billing_config

    def factory():
        return make_stripe_client(config)  # raises when billing is not enabled

    return factory


@router.get("/export", response_class=Response)
def export_workspace_data(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
) -> Response:
    exported_at = datetime.now(timezone.utc)
    payload = build_workspace_export(db, context, exported_at=exported_at)
    filename = (
        f"portfyl-workspace-{context.workspace.public_id}-"
        f"{exported_at:%Y%m%d}.json"
    )
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/deletion")
def get_deletion_status(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
) -> dict:
    return deletion_status_payload(
        get_workspace_deletion(db, context.workspace.id)
    )


@router.post("/deletion")
def delete_workspace(
    payload: DeletionRequestPayload,
    response: Response,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
    verifier: FirebaseIdentityVerifier = Depends(get_identity_verifier),
    mailer: Mailer | None = Depends(get_mailer),
    stripe_client_factory: Callable[[], Any] | None = Depends(get_stripe_client_factory),
) -> dict:
    """Erase the caller's workspace now. No grace period, no undo.

    When it was the user's last workspace the account goes with it (and its
    Firebase identity), so the session cookie is cleared as well.
    """
    try:
        identity = verifier.verify_id_token(payload.reauth_id_token)
    except IdentityVerificationError as exc:
        raise RequestContextError(
            401,
            "recent_reauthentication_required",
        ) from exc
    try:
        result = delete_workspace_now(
            db,
            context,
            identity=identity,
            confirmation=payload.confirmation,
            identity_admin=verifier,
            lang=payload.lang,
            cancel_subscription=payload.cancel_subscription,
            refund_expected=payload.refund_expected,
            stripe_client_factory=stripe_client_factory,
        )
        db.commit()
    except RequestContextError:
        raise
    except Exception as exc:
        # Most likely the identity provider refused the delete. Nothing was
        # committed, so the data is intact and the user can simply retry.
        db.rollback()
        logger.exception("Immediate workspace deletion failed; rolled back")
        raise RequestContextError(503, "account_deletion_unavailable") from exc
    if result.account_deleted:
        clear_session_cookie(response)
    if result.farewell is not None:
        # After the commit, best effort, and the connection goes back to the
        # pool before the outbound call.
        release_connection(db)
        send_account_deleted_notice(
            to=result.farewell[0], lang=result.farewell[1], mailer=mailer
        )
    refund = result.refund
    return {
        "deleted": True,
        "account_deleted": result.account_deleted,
        # Withdrawal inside the first 14 days: everything paid was refunded.
        "refunded": refund.refunded,
        "refunded_amount_cents": refund.amount_cents if refund.refunded else None,
        "currency": refund.currency if refund.refunded else None,
    }


@router.delete("/deletion", status_code=204)
def cancel_deletion(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
) -> Response:
    cancel_workspace_deletion(db, context)
    db.commit()
    return Response(status_code=204)
