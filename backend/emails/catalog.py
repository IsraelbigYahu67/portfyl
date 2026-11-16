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
from datetime import date, datetime, timezone
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
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_DELETION_SCHEDULED = "account_deletion_scheduled"
    ACCOUNT_DELETED = "account_deleted"


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
    # Date formatting (see ``format_date``). ``date_pattern`` uses {day},
    # {month} (a name from ``months``) and {year}; ``datetime_pattern`` uses
    # {date} and {time}. The defaults are English.
    months: tuple[str, ...] = (
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    )
    date_pattern: str = "{day} {month} {year}"
    datetime_pattern: str = "{date}, {time} UTC"


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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Your Portfyl password was changed",
            preheader="If that was you, there's nothing more to do.",
            heading="Your password was changed",
            paragraphs=(
                "The password for **{email}** was just changed. "
                "If that was you, there's nothing more to do.",
            ),
            facts=(("When", "{datetime}"),),
            button="That wasn't me",
            note="The button lets you reset the password right away. "
            "If it doesn't work, write to support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Your Portfyl account will be deleted on {date}",
            preheader="You can change your mind until then.",
            heading="Account deletion is scheduled",
            paragraphs=(
                "You asked us to delete your Portfyl account and all its data. "
                "You can change your mind until the date below.",
            ),
            facts=(("Account", "{email}"), ("We delete it on", "{date}")),
            button="Keep my account",
            note="If you didn't ask for this, cancel it with the button "
            "and change your password.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Your Portfyl account has been deleted",
            preheader="The last e-mail about this account.",
            heading="Your account is deleted",
            paragraphs=(
                "We deleted the account **{email}** and its data, as you asked. "
                "This is the last e-mail we send about it.",
                "You're welcome to come back and start a new one any time.",
            ),
            note="Questions about this? Write to support@portfyl.com.",
            footer_reason="account",
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


def _utc(value: date | datetime) -> date | datetime:
    if isinstance(value, datetime):
        # A naive datetime is taken as UTC (every Portfyl timestamp is).
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def format_date(value: date | datetime, lang: str) -> str:
    """``16 November 2026`` in the language's own pattern; a datetime is
    shown as its UTC calendar date."""
    locale = locale_for(lang)
    value = _utc(value)
    return locale.date_pattern.format(
        day=value.day, month=locale.months[value.month - 1], year=value.year
    )


def format_datetime(value: datetime, lang: str) -> str:
    """``16 November 2026, 14:05 UTC`` in the language's own pattern."""
    locale = locale_for(lang)
    value = _utc(value)
    return locale.datetime_pattern.format(
        date=format_date(value, lang), time=f"{value.hour:02d}:{value.minute:02d}"
    )
