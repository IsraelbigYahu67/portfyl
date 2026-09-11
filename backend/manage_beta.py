"""Operator CLI for private-beta invitations.

Run this with an administrative DATABASE_URL, normally through a one-off Cloud
Run Job. It deliberately exposes no public HTTP administration endpoint.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from database import SessionLocal
from firebase_identity import FirebaseIdentityVerifier
from models import AuthSession, BetaInvite, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _email(value: str) -> str:
    normalized = value.strip().casefold()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise argparse.ArgumentTypeError("enter a valid e-mail address")
    return normalized


def invite(email: str, expires_days: int) -> None:
    now = _utcnow()
    with SessionLocal() as db:
        row = db.scalar(select(BetaInvite).where(BetaInvite.email == email))
        if row is None:
            row = BetaInvite(email=email)
            db.add(row)
        if row.status != "accepted":
            row.status = "invited"
            row.accepted_at = None
            row.expires_at = now + timedelta(days=expires_days)
        row.revoked_at = None
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            user.disabled_at = None
        db.commit()
    print(f"invited {email}")


def revoke(email: str) -> None:
    now = _utcnow()
    firebase_uid: str | None = None
    with SessionLocal() as db:
        row = db.scalar(select(BetaInvite).where(BetaInvite.email == email))
        if row is None:
            raise SystemExit(f"no beta invitation exists for {email}")
        row.status = "revoked"
        row.revoked_at = now
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            user.disabled_at = now
            firebase_uid = user.firebase_uid
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
        db.commit()
    if firebase_uid:
        FirebaseIdentityVerifier().revoke_refresh_tokens(firebase_uid)
    print(f"revoked {email}")


def list_invites() -> None:
    with SessionLocal() as db:
        rows = db.scalars(select(BetaInvite).order_by(BetaInvite.email)).all()
        for row in rows:
            expiry = row.expires_at.isoformat() if row.expires_at else "-"
            print(f"{row.email}\t{row.status}\t{expiry}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Portfyl private-beta testers")
    commands = parser.add_subparsers(dest="command", required=True)

    invite_parser = commands.add_parser("invite", help="allow a tester to create a Portfyl account")
    invite_parser.add_argument("email", type=_email)
    invite_parser.add_argument("--expires-days", type=int, default=30)

    revoke_parser = commands.add_parser("revoke", help="remove access and revoke Portfyl sessions")
    revoke_parser.add_argument("email", type=_email)

    commands.add_parser("list", help="list private-beta invitations")
    args = parser.parse_args()

    if args.command == "invite":
        if args.expires_days < 1:
            parser.error("--expires-days must be at least 1")
        invite(args.email, args.expires_days)
    elif args.command == "revoke":
        revoke(args.email)
    else:
        list_invites()


if __name__ == "__main__":
    main()
