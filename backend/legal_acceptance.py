"""Server-side record that a person accepted the Terms at sign-up.

Portfyl must be able to prove what was accepted and when (GDPR art. 5(2) for
the privacy information having been provided; burden of proof for a consumer
contract; Directive 2011/83/EU art. 8(7) confirmation). The browser only sends
"yes, I ticked the box"; the versions and the time are decided here.

The Privacy Policy is information (GDPR art. 13), never consent: the record
says which privacy-notice text was shown, nothing more. Bump the two version
constants whenever the published Terms or Privacy Policy change, together with
the "last updated" date in docs/legal/.

Two ways a record is written:

* first Google sign-in: the exchange request carries `terms_accepted: true` and
  the row is created with the new user;
* e-mail/password: the address is verified later (possibly on another device),
  so the register page posts the flag to `/auth/signup-acceptance` right after
  creating the Firebase user. That writes a *pending* row keyed by the Firebase
  uid, which the first `/auth/session` exchange links to the new Portfyl user.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import TermsAcceptance


# Same naming style as billing_config.CHECKOUT_CONSENT_VERSION.
LEGAL_TERMS_VERSION = "2026-11-24"
LEGAL_PRIVACY_VERSION = "2026-11-24"

# A pending acceptance (e-mail sign-up, no Portfyl user yet) that is never
# linked is removed after this many days; the Privacy Policy says "30 days".
PENDING_ACCEPTANCE_MAX_AGE_DAYS = 30

SOURCE_EMAIL = "email_signup"
SOURCE_GOOGLE = "google_signup"


def source_for_provider(sign_in_provider: str | None) -> str:
    return SOURCE_GOOGLE if sign_in_provider == "google.com" else SOURCE_EMAIL


def _new_row(*, source: str, now: datetime, **subject) -> TermsAcceptance:
    return TermsAcceptance(
        terms_version=LEGAL_TERMS_VERSION,
        privacy_notice_version=LEGAL_PRIVACY_VERSION,
        age_confirmed=True,
        accepted_at=now,
        source=source,
        **subject,
    )


def has_pending(db: Session, firebase_uid: str) -> bool:
    return db.scalar(
        select(TermsAcceptance.id).where(
            TermsAcceptance.firebase_uid == firebase_uid,
            TermsAcceptance.user_id.is_(None),
        )
    ) is not None


def record_pending(
    db: Session,
    *,
    firebase_uid: str,
    now: datetime | None = None,
    source: str = SOURCE_EMAIL,
) -> bool:
    """Store the acceptance for a Firebase identity that has no Portfyl user
    yet. Idempotent: the first acceptance is kept (the evidence is the moment
    the person actually accepted). True when a row was written. The caller
    commits."""
    existing = db.scalar(
        select(TermsAcceptance.id).where(TermsAcceptance.firebase_uid == firebase_uid)
    )
    if existing is not None:
        return False
    row = _new_row(
        source=source,
        now=now or datetime.now(timezone.utc),
        firebase_uid=firebase_uid,
    )
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:
        # A concurrent request wrote the same uid first; that row stands.
        return False
    return True


def attach_to_new_user(
    db: Session,
    *,
    user_id: UUID,
    firebase_uid: str,
    accepted_now: bool,
    source: str,
    now: datetime | None = None,
) -> TermsAcceptance | None:
    """Give a just-created user their acceptance record: the pending row from
    registration if there is one, else a new row when this very request carries
    the acceptance. None when neither exists (local edition, where acceptance
    is not enforced). The caller commits."""
    pending = db.scalar(
        select(TermsAcceptance).where(
            TermsAcceptance.firebase_uid == firebase_uid,
            TermsAcceptance.user_id.is_(None),
        )
    )
    if pending is not None:
        pending.user_id = user_id
        db.flush()
        return pending
    if not accepted_now:
        return None
    row = _new_row(
        source=source,
        now=now or datetime.now(timezone.utc),
        user_id=user_id,
        firebase_uid=firebase_uid,
    )
    db.add(row)
    db.flush()
    return row


def purge_stale_pending(db: Session, now: datetime | None = None) -> int:
    """Delete pending acceptances (`user_id` IS NULL) older than
    `PENDING_ACCEPTANCE_MAX_AGE_DAYS`: a registration that was never finished.
    Linked rows (the proof of acceptance of a real account) are never touched.
    Returns how many rows went; idempotent. The caller commits. Run by the
    daily `account_deletion_cleanup` job."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(
        days=PENDING_ACCEPTANCE_MAX_AGE_DAYS
    )
    result = db.execute(
        delete(TermsAcceptance).where(
            TermsAcceptance.user_id.is_(None),
            TermsAcceptance.accepted_at < cutoff,
        )
    )
    return result.rowcount or 0


def get_for_user(db: Session, user_id: UUID) -> TermsAcceptance | None:
    return db.scalar(
        select(TermsAcceptance).where(TermsAcceptance.user_id == user_id)
    )
