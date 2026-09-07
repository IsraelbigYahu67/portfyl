"""Narrow Firebase Admin boundary used only during identity exchange."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth


class IdentityVerificationError(RuntimeError):
    """Raised when Firebase cannot provide a usable verified identity."""


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str
    email_verified: bool
    display_name: str | None
    authenticated_at: datetime | None = None


def _default_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app()


class FirebaseIdentityVerifier:
    def __init__(self, *, auth_client: Any = firebase_auth, app: Any = None):
        self._auth_client = auth_client
        self._app = app if app is not None else _default_firebase_app()

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        try:
            claims = self._auth_client.verify_id_token(
                token,
                app=self._app,
                check_revoked=True,
            )
        except Exception as exc:
            raise IdentityVerificationError(
                "Firebase ID token verification failed"
            ) from exc

        uid = str(claims.get("uid") or "").strip()
        email = str(claims.get("email") or "").strip().casefold()
        if not uid or not email:
            raise IdentityVerificationError(
                "Firebase identity must contain UID and e-mail"
            )
        name = claims.get("name")
        display_name = str(name).strip() if name is not None else None
        authenticated_at = None
        try:
            if claims.get("auth_time") is not None:
                authenticated_at = datetime.fromtimestamp(
                    float(claims["auth_time"]),
                    tz=timezone.utc,
                )
        except (TypeError, ValueError, OSError):
            authenticated_at = None
        return VerifiedIdentity(
            uid=uid,
            email=email,
            email_verified=bool(claims.get("email_verified")),
            display_name=display_name or None,
            authenticated_at=authenticated_at,
        )

    def revoke_refresh_tokens(self, uid: str) -> None:
        try:
            self._auth_client.revoke_refresh_tokens(uid, app=self._app)
        except Exception as exc:
            raise IdentityVerificationError(
                "Firebase refresh-token revocation failed"
            ) from exc

    def delete_user(self, uid: str) -> None:
        try:
            self._auth_client.delete_user(uid, app=self._app)
        except Exception as exc:
            raise IdentityVerificationError(
                "Firebase user deletion failed"
            ) from exc
