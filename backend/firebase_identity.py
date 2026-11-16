"""Narrow Firebase Admin boundary used only during identity exchange."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class IdentityVerificationError(RuntimeError):
    """Raised when Firebase cannot provide a usable verified identity."""


# Firebase `firebase.sign_in_provider` values Portfyl enables. Anything else is
# reported as None rather than echoed, so audit metadata never carries an
# arbitrary claim string.
KNOWN_SIGN_IN_PROVIDERS = frozenset({"password", "google.com"})


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str
    email_verified: bool
    display_name: str | None
    authenticated_at: datetime | None = None
    sign_in_provider: str | None = None


def _sign_in_provider(claims: dict) -> str | None:
    firebase_claims = claims.get("firebase")
    if not isinstance(firebase_claims, dict):
        return None
    provider = firebase_claims.get("sign_in_provider")
    return provider if provider in KNOWN_SIGN_IN_PROVIDERS else None


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
            sign_in_provider=_sign_in_provider(claims),
        )

    def password_updated_at(self, uid: str) -> datetime | None:
        """When the user's password last changed, or None if they have none.

        Firebase does not put this in the ID token, so it is read with an
        Admin `get_user` lookup (REST `accounts:lookup`). `UserRecord` has no
        public property for the lookup field `passwordUpdatedAt` (milliseconds
        since the epoch), so it is read from the record's raw data; a shape
        change then reads as "unknown" (None) and detection quietly stops
        rather than raising. An account that has a password provider but no
        `passwordUpdatedAt` (older accounts that never changed it) falls back
        to its creation time, so its first change still moves the value
        forward. Accounts without a password provider (Google only) are None.
        """
        try:
            record = self._auth_client.get_user(uid, app=self._app)
        except Exception as exc:
            raise IdentityVerificationError(
                "Firebase user lookup failed"
            ) from exc
        providers = getattr(record, "provider_data", None) or []
        if not any(
            getattr(provider, "provider_id", None) == "password"
            for provider in providers
        ):
            return None
        raw = getattr(record, "_data", None)
        millis = raw.get("passwordUpdatedAt") if isinstance(raw, dict) else None
        if millis is None:
            metadata = getattr(record, "user_metadata", None)
            millis = getattr(metadata, "creation_timestamp", None)
        try:
            return _EPOCH + timedelta(milliseconds=int(millis))
        except (TypeError, ValueError, OverflowError):
            return None

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
        except firebase_auth.UserNotFoundError:
            # A prior attempt can delete Firebase successfully and then lose
            # its database commit. Treat an already-absent identity as the
            # desired state so the retry can finish the Portfyl transaction.
            return
        except Exception as exc:
            raise IdentityVerificationError(
                "Firebase user deletion failed"
            ) from exc
