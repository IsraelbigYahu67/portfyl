"""E-mail copy model: kinds, content shape, languages, English source copy.

An e-mail definition is only text; layout lives in ``render.py``. English is
the source and the fallback. Other languages are modules
``emails.locales.<code>`` exposing a ``LOCALE`` attribute (added separately).

Placeholders are ``{name}``; the only markup is ``**bold**``. Both are handled
(and every value escaped) by ``render.py``.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Mapping

LANGUAGES: tuple[str, ...] = ("cs", "en", "de", "fr", "es", "it", "pt", "pl", "nl")
SOURCE_LANGUAGE = "en"

# Placeholder names a template may use.
PLACEHOLDERS: frozenset[str] = frozenset(
    {"email", "date", "plan", "price", "broker", "datetime"}
)


class EmailKind(str, Enum):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True)
class EmailContent:
    """One e-mail in one language."""

    subject: str
    preheader: str  # inbox preview line, hidden in the body
    heading: str
    paragraphs: tuple[str, ...]  # 1-2
    bullets: tuple[str, ...] = ()
    facts: tuple[tuple[str, str], ...] = ()  # (label, value)
    button: str | None = None  # label; the URL comes from the caller
    note: str = ""  # grey line under the button
    footer_reason: Literal["account", "address"] = "account"


@dataclass(frozen=True)
class Locale:
    """All copy of one language."""

    messages: Mapping[EmailKind, EmailContent]
    footer_reasons: Mapping[str, str]  # keys "account" and "address"
    footer_help: str


ENGLISH = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Confirm your e-mail for Portfyl",
            preheader="One click and your account is ready.",
            heading="Confirm your e-mail",
            paragraphs=(
                "Welcome to Portfyl! Confirm **{email}** to finish setting up your account.",
            ),
            button="Confirm e-mail",
            note="If you didn't create a Portfyl account, you can ignore this e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Reset your Portfyl password",
            preheader="Choose a new password. The link works for 1 hour.",
            heading="Reset your password",
            paragraphs=(
                "We got a request to reset the password for **{email}**. "
                "Choose a new one with the button below. The link works for 1 hour.",
            ),
            button="Choose a new password",
            note="If you didn't ask for this, you can ignore this e-mail. "
            "Your password stays the same.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "You got this e-mail because it is about your Portfyl account.",
        "address": "You got this e-mail because someone entered this address at Portfyl.",
    },
    footer_help="Need help? support@portfyl.com",
)


def normalize_language(code: object) -> str:
    """Map any input to a supported language code; never raises.

    ``"CS"`` and ``"cs-CZ"`` give ``"cs"``; anything unknown gives ``"en"``.
    """
    if not isinstance(code, str):
        return SOURCE_LANGUAGE
    base = code.strip().lower().split("-", 1)[0]
    return base if base in LANGUAGES else SOURCE_LANGUAGE


def locale_for(lang: str) -> Locale:
    """The copy of ``lang``; English when it is English or not available yet."""
    code = normalize_language(lang)
    if code == SOURCE_LANGUAGE:
        return ENGLISH
    module_name = f"emails.locales.{code}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Only a missing locale (or the locales package itself) falls back; a
        # broken import inside an existing locale module must stay visible.
        if exc.name in (module_name, "emails.locales"):
            return ENGLISH
        raise
    return module.LOCALE
