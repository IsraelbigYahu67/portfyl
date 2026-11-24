"""Verified, immediate workspace (and, with its last workspace, account) deletion.

``delete_workspace_now`` is the only way to start a deletion: it checks the same
guards as before (owner, typed name, fresh re-authentication, sole member, and
either no live subscription or the owner's explicit consent to cancel it now)
and then erases the data in the same request. Within the withdrawal
window (``billing_config.WITHDRAWAL_DAYS`` after the order) that cancel is a
withdrawal: every payment of the subscription is refunded in full first, then
the subscription is cancelled, then the workspace is erased. There is
no grace period and no undo. The deferred state machine below
(``get_workspace_deletion``, ``cancel_workspace_deletion`` and
``purge_due_workspace_deletions``) remains only to finish requests that were
scheduled under the earlier 30-day rule; nothing creates new ones.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from audit import record_audit_event
from emails.catalog import SOURCE_LANGUAGE, EmailKind, normalize_language
from emails.notify import send_account_notice
from firebase_identity import VerifiedIdentity
from billing_config import WITHDRAWAL_DAYS, withdrawal_ends_at, withdrawal_open
from database import release_connection
from models import (
    Membership,
    Subscription,
    TermsAcceptance,
    User,
    Workspace,
    WorkspaceSetting,
)
from stripe_client import StripeClientProtocol, StripeError
from tenancy import RequestContext, RequestContextError


DELETION_SETTING_KEY = "privacy.workspace_deletion"
DELETION_STATE_VERSION = 1
MAX_REAUTH_AGE = timedelta(minutes=5)
MAX_REAUTH_FUTURE_SKEW = timedelta(minutes=1)

logger = logging.getLogger("portfyl.account_deletion")


@dataclass(frozen=True)
class WorkspaceDeletion:
    version: int
    requested_at: datetime
    execute_after: datetime
    requested_by_user_id: UUID
    # Language of the e-mails about this request (the backend stores no other
    # language). Last and defaulted so states stored before wave 2, which have
    # no such key, still parse (as English).
    lang: str = SOURCE_LANGUAGE


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse(raw: str) -> WorkspaceDeletion:
    try:
        data = json.loads(raw)
        state = WorkspaceDeletion(
            version=int(data["version"]),
            requested_at=_as_utc(datetime.fromisoformat(data["requested_at"])),
            execute_after=_as_utc(datetime.fromisoformat(data["execute_after"])),
            requested_by_user_id=UUID(data["requested_by_user_id"]),
            lang=normalize_language(data.get("lang")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Malformed workspace deletion state") from exc
    if state.version != DELETION_STATE_VERSION:
        raise RuntimeError("Unsupported workspace deletion state version")
    if state.execute_after <= state.requested_at:
        raise RuntimeError("Invalid workspace deletion deadline")
    return state


def get_workspace_deletion(
    db: Session,
    workspace_id: UUID,
) -> WorkspaceDeletion | None:
    row = db.scalar(
        select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == workspace_id,
            WorkspaceSetting.key == DELETION_SETTING_KEY,
        )
    )
    if row is None or not row.value:
        return None
    return _parse(row.value)


def _validate_reauthentication(
    context: RequestContext,
    identity: VerifiedIdentity,
    *,
    now: datetime,
) -> None:
    if not identity.email_verified:
        raise RequestContextError(403, "email_verification_required")
    if (
        not context.user.firebase_uid
        or identity.uid != context.user.firebase_uid
        or identity.email != context.user.email
    ):
        raise RequestContextError(403, "reauthentication_identity_mismatch")
    if identity.authenticated_at is None:
        raise RequestContextError(403, "recent_reauthentication_required")
    authenticated_at = _as_utc(identity.authenticated_at)
    age = now - authenticated_at
    if age > MAX_REAUTH_AGE or age < -MAX_REAUTH_FUTURE_SKEW:
        raise RequestContextError(403, "recent_reauthentication_required")


@dataclass(frozen=True)
class SubscriptionTeardown:
    """What must happen to the Stripe subscription before the erasure."""

    stripe_subscription_id: str
    refund: bool  # withdrawal window still open: refund every payment first


@dataclass(frozen=True)
class RefundOutcome:
    refunded: bool = False
    # ``None`` with ``refunded=True``: the amount is not known (the payment was
    # already refunded elsewhere, so Stripe told us nothing about the sum).
    amount_cents: int | None = None
    currency: str | None = None


# Refund statuses Stripe can answer a 200 with. ``succeeded`` and ``pending``
# mean the money is on its way back; the rest means it is NOT.
_REFUND_FAILED_STATUSES = frozenset({"failed", "canceled", "requires_action"})

# Idempotency keys only have to stop two *concurrent* requests from both
# creating a refund. Stripe stores the first response under a key for 24 h,
# errors included, so a permanent key would replay a 500 / lock timeout to every
# retry for a day. One key per minute bounds that replay to the same minute; a
# double refund is prevented anyway because the refund has no ``amount`` and a
# second attempt on a fully refunded payment is ``charge_already_refunded``.
_REFUND_KEY_BUCKET_SECONDS = 60

# The window the browser saw when the dialog opened may close a few minutes
# before the request arrives. For a request that says it EXPECTS a refund, the
# customer who opened the dialog in time is still refunded for this long after
# the window ended (see ``_validate_deletion_request``).
REFUND_EXPECTED_TOLERANCE = timedelta(minutes=15)

REFUND_TRACE_KEY = "privacy.withdrawal_refund"


def _validate_deletion_request(
    db: Session,
    context: RequestContext,
    identity: VerifiedIdentity,
    confirmation: str,
    *,
    now: datetime,
    cancel_subscription: bool = False,
    refund_expected: bool = False,
) -> SubscriptionTeardown | None:
    """Run every guard. Returns what the caller must do to the Stripe
    subscription before erasing, or ``None`` when Stripe stays untouched."""
    if context.membership.role != "owner":
        raise RequestContextError(403, "workspace_owner_required")
    if confirmation != context.workspace.name:
        raise RequestContextError(400, "workspace_confirmation_mismatch")
    _validate_reauthentication(context, identity, now=now)

    active_members = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.workspace_id == context.workspace.id,
            Membership.status == "active",
        )
    ) or 0
    if active_members != 1:
        raise RequestContextError(409, "workspace_has_other_members")

    # Deleting the workspace does not stop Stripe from charging the card, so a
    # live subscription must be ended first: either by the user in the Customer
    # Portal, or here when the user explicitly consented (``cancel_subscription
    # is True``). With consent EVERY live row is cancelled, whatever its status
    # (past_due keeps being retried, cancel_at_period_end still bills until the
    # period ends), and refunded when the withdrawal window is open.
    #
    # Without consent a renewing subscription is 409, and so is a paid one that
    # is cancel_at_period_end / past_due while the window is open: the customer
    # has a refund right the dialog must show. Outside the window those
    # proceed untouched.
    subscription = db.scalar(
        select(Subscription).where(
            Subscription.workspace_id == context.workspace.id,
            Subscription.ended_at.is_(None),
        )
    )
    if subscription is None:
        return None
    in_window = withdrawal_open(subscription.created_at, now)
    if cancel_subscription is True:
        refund = in_window
        if not refund and refund_expected:
            # Tolerance ONLY for a request that expects the refund: the
            # customer opened the dialog (which promised it) while the window
            # was open and took a few minutes to confirm.
            ends_at = withdrawal_ends_at(subscription.created_at)
            refund = ends_at is not None and now < ends_at + REFUND_EXPECTED_TOLERANCE
            if not refund:
                raise RequestContextError(409, "withdrawal_window_changed")
        return SubscriptionTeardown(subscription.stripe_subscription_id, refund=refund)
    renewing = (
        subscription.status in ("active", "trialing")
        and not subscription.cancel_at_period_end
    )
    if renewing or (
        in_window
        and subscription.status in ("active", "trialing", "past_due")
    ):
        raise RequestContextError(409, "active_subscription")
    return None


def _refund_subscription_payments(
    client: StripeClientProtocol,
    subscription_id: str,
    *,
    now: datetime,
) -> RefundOutcome:
    """Refund 100 % of every successful payment of the subscription.

    Retry-safe: Stripe's "already fully refunded" counts as done, and the
    idempotency key (subscription, payment, minute) only guards against
    concurrent duplicates, so a retry after a later step failed neither refunds
    twice nor replays a stored error for a day. Anything else aborts the
    deletion (nothing cancelled, nothing erased).
    """
    bucket = int(_as_utc(now).timestamp()) // _REFUND_KEY_BUCKET_SECONDS
    try:
        payments = client.list_paid_payments(subscription_id)
        total = 0
        amount_known = True
        currency: str | None = None
        for payment in payments:
            key = f"withdrawal-refund-{subscription_id}-{payment['id']}-{bucket}"
            if payment["kind"] == "charge":
                refs = {"charge": payment["id"]}
            else:
                refs = {"payment_intent": payment["id"]}
            try:
                refund = client.create_refund(idempotency_key=key, **refs)
            except StripeError as exc:
                if exc.code != "charge_already_refunded":
                    raise
                # Refunded before (an earlier attempt, or Link). How much is
                # not known from here, so no sum is claimed.
                logger.info("withdrawal refund already done in Stripe")
                amount_known = False
            else:
                status = refund.get("status")
                if status in _REFUND_FAILED_STATUSES:
                    raise StripeError(
                        "refund not completed", code=f"refund_{status}"
                    )
                total += int(refund.get("amount") or payment.get("amount_cents") or 0)
            currency = currency or payment.get("currency")
    except StripeError as exc:
        logger.warning(
            "withdrawal refund failed status=%s code=%s", exc.status, exc.code
        )
        raise RequestContextError(503, "subscription_refund_failed") from exc
    except Exception as exc:  # noqa: BLE001 - malformed Stripe answer
        logger.error("withdrawal refund impossible: %s", type(exc).__name__)
        raise RequestContextError(503, "subscription_refund_failed") from exc
    if not payments:
        logger.info("withdrawal: nothing paid, nothing to refund")
        return RefundOutcome()
    logger.info("withdrawal refund done payments=%d", len(payments))
    return RefundOutcome(
        refunded=True,
        amount_cents=total if amount_known else None,
        currency=currency,
    )


def _cancel_subscription_before_erasure(
    client: StripeClientProtocol,
    subscription_id: str,
    *,
    workspace_ref: str,
    refunded: bool,
) -> None:
    """Cancel the subscription in Stripe now (no proration credit, no final
    invoice). Anything but success aborts the deletion: never erase a
    workspace whose card may still be charged."""
    try:
        client.cancel_subscription(subscription_id)
    except StripeError as exc:
        if exc.status == 404 or exc.code == "resource_missing":
            # Stripe says the subscription is not there. Only believe it is
            # cancelled after looking: a 404 on the DELETE of a live
            # subscription would otherwise erase a workspace that is still
            # being billed.
            if _subscription_is_gone(client, subscription_id):
                logger.info("subscription already cancelled in Stripe before deletion")
                return
        _cancel_failed(
            "subscription cancel for deletion failed status=%s code=%s"
            % (exc.status, exc.code),
            workspace_ref=workspace_ref,
            refunded=refunded,
            exc=exc,
        )
    except Exception as exc:  # noqa: BLE001 - malformed Stripe answer
        _cancel_failed(
            "subscription cancel for deletion impossible: %s" % type(exc).__name__,
            workspace_ref=workspace_ref,
            refunded=refunded,
            exc=exc,
        )
    logger.info("subscription cancelled immediately because of workspace deletion")


def _subscription_is_gone(client: StripeClientProtocol, subscription_id: str) -> bool:
    try:
        remote = client.retrieve_subscription(subscription_id)
    except StripeError as exc:
        return exc.status == 404 or exc.code == "resource_missing"
    except Exception:  # noqa: BLE001 - cannot tell: not proven cancelled
        return False
    return isinstance(remote, dict) and remote.get("status") == "canceled"


def _cancel_failed(message: str, *, workspace_ref: str, refunded: bool, exc: Exception):
    if refunded:
        # Money went back to the customer but the subscription lives on: the
        # retry repairs it, support must know in case there is none.
        logger.error(
            "withdrawal refund done but subscription cancel failed workspace=%s",
            workspace_ref,
        )
    logger.warning(message)
    raise RequestContextError(503, "subscription_cancel_failed") from exc


def _read_refund_trace(
    db: Session, workspace_id: UUID, *, now: datetime
) -> RefundOutcome | None:
    row = db.scalar(
        select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == workspace_id,
            WorkspaceSetting.key == REFUND_TRACE_KEY,
        )
    )
    if row is None or not row.value:
        return None
    try:
        data = json.loads(row.value)
        at = _as_utc(datetime.fromisoformat(data["at"]))
        amount = data.get("amount_cents")
        outcome = RefundOutcome(
            refunded=True,
            amount_cents=None if amount is None else int(amount),
            currency=data.get("currency"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    # A trace only explains a retry of the SAME deletion: it is worthless once
    # the withdrawal period it belongs to is over.
    if now - at > timedelta(days=WITHDRAWAL_DAYS):
        return None
    return outcome


def _persist_refund_trace(
    db: Session, workspace_id: UUID, outcome: RefundOutcome, *, now: datetime
) -> None:
    """Commit a record of the refund BEFORE the erasure is attempted.

    If the erasure then fails (Firebase), the webhook for the cancel ends the
    subscription row, and the retry would find no subscription and could not
    tell the customer about the refund. The record lives in the workspace and
    goes with it when the erasure finally succeeds. Best effort: failing to
    write it must not stop the deletion.
    """
    value = json.dumps({
        "amount_cents": outcome.amount_cents,
        "currency": outcome.currency,
        "at": _as_utc(now).isoformat(),
    })
    try:
        row = db.scalar(
            select(WorkspaceSetting).where(
                WorkspaceSetting.workspace_id == workspace_id,
                WorkspaceSetting.key == REFUND_TRACE_KEY,
            )
        )
        if row is None:
            db.add(WorkspaceSetting(
                workspace_id=workspace_id, key=REFUND_TRACE_KEY, value=value,
            ))
        else:
            row.value = value
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.error("could not record the withdrawal refund trace")


def _teardown_subscription_before_erasure(
    db: Session,
    context: RequestContext,
    teardown: SubscriptionTeardown,
    stripe_client_factory: Callable[[], StripeClientProtocol] | None,
    *,
    now: datetime,
) -> RefundOutcome:
    """Refund (inside the withdrawal window), then cancel. In that order: a
    refund failure leaves the subscription alive and the workspace intact, and
    a cancel failure after a refund is repaired by the retry, which refunds
    idempotently and cancels. One Stripe client serves both calls and is closed
    afterwards."""
    workspace_id = context.workspace.id
    workspace_ref = str(context.workspace.public_id)
    failure_code = (
        "subscription_refund_failed" if teardown.refund else "subscription_cancel_failed"
    )
    # Slow outbound calls: hand the pooled connection back first. Nothing has
    # been written yet, so this is a plain end of the read transaction.
    release_connection(db)
    try:
        if stripe_client_factory is None:
            raise RuntimeError("Stripe client unavailable")
        client = stripe_client_factory()
    except Exception as exc:  # noqa: BLE001 - billing off / client not buildable
        logger.error("subscription teardown impossible: %s", type(exc).__name__)
        raise RequestContextError(503, failure_code) from exc
    try:
        outcome = RefundOutcome()
        if teardown.refund:
            outcome = _refund_subscription_payments(
                client, teardown.stripe_subscription_id, now=now
            )
            if outcome.refunded:
                prior = _read_refund_trace(db, workspace_id, now=now)
                if outcome.amount_cents is None and prior is not None:
                    outcome = replace(
                        outcome,
                        amount_cents=prior.amount_cents,
                        currency=outcome.currency or prior.currency,
                    )
                _persist_refund_trace(db, workspace_id, outcome, now=now)
        _cancel_subscription_before_erasure(
            client,
            teardown.stripe_subscription_id,
            workspace_ref=workspace_ref,
            refunded=outcome.refunded,
        )
        return outcome
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - closing must never mask the result
                pass


@dataclass(frozen=True)
class DeletionResult:
    """Outcome of an immediate deletion.

    ``farewell`` is ``(address, language)`` when the account itself went with
    its last workspace, else ``None``. It is read before the user row is
    deleted so the notice can be sent after the commit.
    """

    account_deleted: bool
    farewell: tuple[str, str] | None = None
    refund: RefundOutcome = RefundOutcome()


def _erase_workspace(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    identity_admin,
    now: datetime,
    lang: str,
) -> DeletionResult:
    """Delete the workspace and, if it was the user's last, the user and their
    Firebase identity. Flushes but never commits: the caller owns the
    transaction, so a Firebase failure rolls everything back.
    """
    other_memberships = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.workspace_id != workspace.id,
        )
    ) or 0

    farewell: tuple[str, str] | None = None
    db.delete(workspace)
    db.flush()
    if other_memberships == 0:
        if user.email:
            farewell = (user.email, lang)
        user.disabled_at = now
        db.flush()
        if user.firebase_uid:
            identity_admin.delete_user(user.firebase_uid)
        # Also cascades in PostgreSQL (ON DELETE CASCADE); explicit so the
        # sign-up acceptance never outlives the account on any backend.
        db.execute(delete(TermsAcceptance).where(TermsAcceptance.user_id == user.id))
        db.delete(user)
        db.flush()
    return DeletionResult(account_deleted=other_memberships == 0, farewell=farewell)


def delete_workspace_now(
    db: Session,
    context: RequestContext,
    *,
    identity: VerifiedIdentity,
    confirmation: str,
    identity_admin,
    now: datetime | None = None,
    lang: object = None,
    cancel_subscription: bool = False,
    refund_expected: bool = False,
    stripe_client_factory: Callable[[], StripeClientProtocol] | None = None,
) -> DeletionResult:
    """Validate and erase the caller's workspace immediately.

    ``cancel_subscription`` is the owner's consent to end a paid subscription:
    it is then cancelled in Stripe (through ``stripe_client_factory``, only
    called when there is one) after all other checks pass and before anything
    is erased. Inside the withdrawal window the payments are refunded in full
    first (``DeletionResult.refund``); after it the rest of the period is lost.

    ``refund_expected`` is what the dialog promised. When it is true and no
    refund would happen (window closed, or no live subscription and no trace of
    an earlier refund), the answer is 409 ``withdrawal_window_changed`` before
    any Stripe call or erasure, so the UI can reload and show the true text.

    Same guards as the old scheduled flow. The endpoint commits and then sends
    the ``account_deleted`` notice from the result; the only commit made here
    is the refund trace (see ``_persist_refund_trace``), written before the
    erasure so a failed erasure can be retried with the refund still known.
    There is no audit row to write, because audit rows are scoped to the
    workspace and the user being deleted and would be deleted with them.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    teardown = _validate_deletion_request(
        db, context, identity, confirmation, now=now,
        cancel_subscription=cancel_subscription,
        refund_expected=refund_expected,
    )
    refund = RefundOutcome()
    if teardown is not None:
        # The Stripe refund and cancel are external and cannot be rolled back.
        # If the erasure below fails afterwards (for instance Firebase
        # refuses), the subscription stays cancelled and refunded: the user can
        # simply retry the deletion and is never charged again.
        refund = _teardown_subscription_before_erasure(
            db, context, teardown, stripe_client_factory, now=now
        )
    else:
        # No live subscription to act on. A retry of a deletion whose erasure
        # failed after the refund finds the subscription already ended by the
        # webhook; the trace tells the customer the refund did happen.
        trace = _read_refund_trace(db, context.workspace.id, now=now)
        if trace is not None:
            refund = trace
        elif refund_expected:
            raise RequestContextError(409, "withdrawal_window_changed")
    # Same RLS context the cleanup job uses, so the deletes below pass the
    # policies on the workspace and the user.
    _set_cleanup_context(db, context.workspace.id, context.user.id)
    result = _erase_workspace(
        db,
        workspace=context.workspace,
        user=context.user,
        identity_admin=identity_admin,
        now=now,
        lang=normalize_language(lang),
    )
    result = replace(result, refund=refund)
    logger.info(
        "workspace deleted immediately account_deleted=%s refunded=%s",
        result.account_deleted, refund.refunded,
    )
    return result


def send_account_deleted_notice(*, to: str, lang: str, mailer: object) -> bool:
    try:
        return send_account_notice(
            EmailKind.ACCOUNT_DELETED,
            to=to,
            lang=lang,
            params={"email": to},
            mailer=mailer,
        )
    except Exception:  # noqa: BLE001 - a notice must never fail the purge
        logger.error("account_deletion notice kind=account_deleted failed")
        return False


def cancel_workspace_deletion(
    db: Session,
    context: RequestContext,
) -> bool:
    row = db.scalar(
        select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == context.workspace.id,
            WorkspaceSetting.key == DELETION_SETTING_KEY,
        )
    )
    if row is None:
        return False
    db.delete(row)
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="account.deletion.cancelled",
        target_type="workspace",
        target_id=str(context.workspace.public_id),
    )
    db.flush()
    return True


def deletion_status_payload(state: WorkspaceDeletion | None) -> dict:
    if state is None:
        return {"scheduled": False}
    return {
        "scheduled": True,
        "requested_at": state.requested_at.isoformat(),
        "execute_after": state.execute_after.isoformat(),
    }


def _rls_enforced(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _active_workspace_ids(db: Session) -> list[UUID]:
    """Enumerate active workspaces through the existing job-only RLS policy."""
    if not _rls_enforced(db):
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    db.execute(text("SELECT set_config('portfyl.job_context', 'true', true)"))
    try:
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    finally:
        db.execute(text("SELECT set_config('portfyl.job_context', '', true)"))


def _set_cleanup_context(
    db: Session,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> None:
    if not _rls_enforced(db):
        return
    db.execute(
        text("SELECT set_config('portfyl.workspace_id', :value, true)"),
        {"value": str(workspace_id)},
    )
    db.execute(
        text("SELECT set_config('portfyl.user_id', :value, true)"),
        {"value": "" if user_id is None else str(user_id)},
    )


def purge_due_workspace_deletions(
    db: Session,
    identity_admin,
    *,
    now: datetime | None = None,
    mailer: object = None,
) -> dict[str, int]:
    """Purge due explicit requests, committing each workspace independently.

    ``identity_admin`` is the narrow Firebase boundary and must expose
    ``delete_user(uid)``. No plan, trial, or subscription state is consulted.

    When the account itself goes (its last workspace), ``account_deleted`` is
    e-mailed in the language stored with the request. The address is read
    before the user row is deleted, but the notice is sent only after the
    commit: a purge that rolled back (for instance because Firebase failed) and
    is retried then never mails twice, and never claims a deletion that did
    not happen. Sending is best effort and cannot fail or undo the purge.
    ``mailer`` defaults to the process-wide one.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    summary = {
        "scanned": 0,
        "purged": 0,
        "not_due": 0,
        "shared": 0,
        "invalid": 0,
        "errors": 0,
    }
    workspace_ids = _active_workspace_ids(db)

    for workspace_id in workspace_ids:
        summary["scanned"] += 1
        try:
            _set_cleanup_context(db, workspace_id)
            try:
                state = get_workspace_deletion(db, workspace_id)
            except RuntimeError:
                summary["invalid"] += 1
                db.rollback()
                continue
            if state is None:
                db.commit()
                continue
            if state.execute_after > now:
                summary["not_due"] += 1
                db.commit()
                continue

            _set_cleanup_context(
                db,
                workspace_id,
                user_id=state.requested_by_user_id,
            )
            active_members = db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.workspace_id == workspace_id,
                    Membership.status == "active",
                )
            ) or 0
            if active_members != 1:
                summary["shared"] += 1
                db.commit()
                continue

            requesting_membership = db.scalar(
                select(Membership).where(
                    Membership.workspace_id == workspace_id,
                    Membership.user_id == state.requested_by_user_id,
                    Membership.status == "active",
                    Membership.role == "owner",
                )
            )
            user = db.scalar(
                select(User).where(User.id == state.requested_by_user_id)
            )
            workspace = db.scalar(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            if requesting_membership is None or user is None or workspace is None:
                summary["invalid"] += 1
                db.rollback()
                continue

            result = _erase_workspace(
                db,
                workspace=workspace,
                user=user,
                identity_admin=identity_admin,
                now=now,
                lang=state.lang,
            )
            farewell = result.farewell
            db.commit()
            summary["purged"] += 1
            if farewell is not None:
                send_account_deleted_notice(
                    to=farewell[0], lang=farewell[1], mailer=mailer
                )
        except Exception:
            db.rollback()
            summary["errors"] += 1
            logger.exception("Workspace deletion failed; transaction rolled back")

    return summary
