"""Portfyl action links built from Firebase one-time codes (spec 5.2).

Firebase Admin returns a link on the project's single action URL. We only
need its ``oobCode``; the link we e-mail points at Portfyl's own ``/auth/action``
page on the configured app URL instead, with its parameters in the URL
fragment (``/auth/action#mode=…&oobCode=…``).

Nothing here puts an e-mail address, a link or a one-time code into an
exception message: callers log these exceptions, and the original exception
is deliberately not chained for the same reason (Firebase's own messages can
contain the address).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions

from firebase_identity import _default_firebase_app


class ActionLinkError(RuntimeError):
    """The action link could not be produced."""


class AccountNotFound(ActionLinkError):
    """Firebase has no account for the address."""


class ActionLinkBuilder:
    def __init__(
        self,
        *,
        app_url: str,
        auth_client: Any = firebase_auth,
        app: Any = None,
    ):
        self._app_url = app_url.rstrip("/")
        self._auth_client = auth_client
        # With no explicit app the default Firebase app is resolved on first
        # use, so constructing the builder never touches Firebase.
        self._app = app

    def verification_url(self, email: str, lang: str) -> str:
        link = self._generate(
            self._auth_client.generate_email_verification_link, email
        )
        return self._action_url(
            link,
            mode="verifyEmail",
            lang=lang,
            continue_url=self._continue_url(),
        )

    def password_reset_url(self, email: str, lang: str) -> str:
        link = self._generate(
            self._auth_client.generate_password_reset_link, email
        )
        return self._action_url(link, mode="resetPassword", lang=lang)

    def _continue_url(self) -> str:
        return f"{self._app_url}/login?verified=1"

    def _generate(self, generate: Any, email: str) -> Any:
        try:
            if self._app is None:
                self._app = _default_firebase_app()
            return generate(
                email,
                action_code_settings=firebase_auth.ActionCodeSettings(
                    url=self._continue_url()
                ),
                app=self._app,
            )
        except firebase_exceptions.NotFoundError:
            raise AccountNotFound("Firebase has no account for this address") from None
        except Exception as exc:
            raise ActionLinkError(
                f"Firebase action link generation failed ({type(exc).__name__})"
            ) from None

    def _action_url(
        self,
        firebase_link: Any,
        *,
        mode: str,
        lang: str,
        continue_url: str | None = None,
    ) -> str:
        oob_code = _oob_code(firebase_link)
        if not oob_code:
            raise ActionLinkError("Firebase action link carries no one-time code")
        params = {"mode": mode, "oobCode": oob_code, "lang": lang}
        if continue_url is not None:
            params["continueUrl"] = continue_url
        # In the fragment, not the query: a browser never sends the fragment to
        # a server, so the one-time code stays out of request logs. The page
        # reads the fragment first and the query second.
        return f"{self._app_url}/auth/action#{urlencode(params)}"


def _oob_code(firebase_link: Any) -> str | None:
    if not isinstance(firebase_link, str):
        return None
    try:
        values = parse_qs(urlparse(firebase_link).query).get("oobCode")
    except ValueError:
        return None
    return values[0] if values else None
