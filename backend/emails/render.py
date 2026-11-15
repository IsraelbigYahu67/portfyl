"""Layout: e-mail content + params -> subject, HTML and plain text.

The layout is written once here. Copy comes from ``emails.catalog``.

Colours are the DESIGN.md tokens written as literals, because e-mail clients
do not support CSS variables. This module is the only place they may be
hardcoded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Mapping

from emails.catalog import (
    ENGLISH,
    PLACEHOLDERS,
    EmailContent,
    EmailKind,
    Locale,
    locale_for,
    normalize_language,
)

# --- DESIGN.md tokens as literals (e-mail has one, light look) -------------
BG = "#F3E8DA"  # --bg: page background
CARD = "#FDF9F3"  # --surface-card-elevated (rgb), solid: the card
WELL = "#ECE0CF"  # --bg-subtle: facts well
INK = "#3A352C"  # --ink: heading and body text
MUTED = "#6B6353"  # --muted: note and footer text
BRAND = "#6D7048"  # --brand: button
BUTTON_TEXT = "#FFFFFF"  # text on --brand

LOGO_URL = "https://portfyl.com/portfyl-mark.png"
SUPPORT_ADDRESS = "support@portfyl.com"
FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")


class TemplateError(ValueError):
    """Unknown or missing placeholder, or a button without ``action_url``."""


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


# --- placeholder filling ----------------------------------------------------


def _fill(template: str, params: Mapping[str, str]) -> str:
    """Replace ``{name}`` with the (unescaped) param; raise on bad names."""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in PLACEHOLDERS:
            raise TemplateError(f"unknown placeholder {{{name}}}")
        if name not in params:
            raise TemplateError(f"missing value for placeholder {{{name}}}")
        return str(params[name])

    return _PLACEHOLDER_RE.sub(sub, template)


def _check_braces(template: str) -> None:
    leftover = _PLACEHOLDER_RE.sub("", template)
    if "{" in leftover or "}" in leftover:
        raise TemplateError("unbalanced brace in template")


def _segments(template: str) -> list[tuple[str, bool]]:
    """Split on ``**`` into (text, is_bold) segments."""
    parts = template.split("**")
    if len(parts) % 2 == 0:
        raise TemplateError("unbalanced ** in template")
    return [(part, index % 2 == 1) for index, part in enumerate(parts) if part]


def _plain(template: str, params: Mapping[str, str]) -> str:
    """Template -> plain text (placeholders filled, ``**`` dropped)."""
    _check_braces(template)
    return "".join(_fill(text, params) for text, _bold in _segments(template))


def _rich(template: str, params: Mapping[str, str]) -> str:
    """Template -> HTML-safe text with ``<b>``; every value is escaped."""
    _check_braces(template)
    out: list[str] = []
    for text, bold in _segments(template):
        # Split first, fill after: a value containing ``**`` cannot make bold.
        piece = escape(_fill(text, params), quote=True)
        out.append(f"<b>{piece}</b>" if bold else piece)
    return "".join(out)


# --- HTML -------------------------------------------------------------------


def _html(
    content: EmailContent,
    locale: Locale,
    lang: str,
    params: Mapping[str, str],
    action_url: str | None,
) -> str:
    font = f"font-family:{FONT_STACK};"
    preheader = escape(_plain(content.preheader, params), quote=True)
    # Padding keeps the first body text out of the inbox preview line.
    padding = "&#847;&zwnj;&nbsp;" * 60

    blocks: list[str] = [
        f'<h1 style="margin:0 0 16px;{font}font-size:22px;line-height:1.3;'
        f'font-weight:700;color:{INK};">{_rich(content.heading, params)}</h1>'
    ]
    for paragraph in content.paragraphs:
        blocks.append(
            f'<p style="margin:0 0 16px;{font}font-size:15px;line-height:1.6;'
            f'color:{INK};">{_rich(paragraph, params)}</p>'
        )
    if content.bullets:
        items = "".join(
            f'<li style="margin:0 0 6px;">{_rich(bullet, params)}</li>'
            for bullet in content.bullets
        )
        blocks.append(
            f'<ul style="margin:0 0 16px;padding-left:20px;{font}font-size:15px;'
            f'line-height:1.6;color:{INK};">{items}</ul>'
        )
    if content.facts:
        rows = "".join(
            "<tr>"
            f'<td style="padding:6px 0;{font}font-size:14px;color:{MUTED};">'
            f"{_rich(label, params)}</td>"
            f'<td align="right" style="padding:6px 0;{font}font-size:14px;'
            f'font-weight:600;color:{INK};">{_rich(value, params)}</td>'
            "</tr>"
            for label, value in content.facts
        )
        blocks.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'border="0" style="margin:0 0 16px;"><tr>'
            f'<td bgcolor="{WELL}" style="background:{WELL};border-radius:12px;'
            'padding:10px 16px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0">{rows}</table></td></tr></table>'
        )
    if content.button:
        href = escape(action_url or "", quote=True)
        blocks.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:8px 0 20px;"><tr>'
            f'<td bgcolor="{BRAND}" style="background:{BRAND};border-radius:999px;">'
            f'<a href="{href}" style="display:inline-block;padding:13px 28px;{font}'
            f"font-size:15px;line-height:1.2;font-weight:600;color:{BUTTON_TEXT};"
            f'text-decoration:none;">{_rich(content.button, params)}</a>'
            "</td></tr></table>"
        )
    if content.note:
        blocks.append(
            f'<p style="margin:0;{font}font-size:13px;line-height:1.5;color:{MUTED};">'
            f"{_rich(content.note, params)}</p>"
        )

    reason = escape(locale.footer_reasons[content.footer_reason], quote=True)
    help_line = escape(locale.footer_help, quote=True).replace(
        SUPPORT_ADDRESS,
        f'<a href="mailto:{SUPPORT_ADDRESS}" style="color:{MUTED};">{SUPPORT_ADDRESS}</a>',
    )
    footer_style = f"margin:0 0 6px;{font}font-size:12px;line-height:1.5;color:{MUTED};"
    body = "".join(blocks)

    return (
        "<!DOCTYPE html>"
        f'<html lang="{escape(lang, quote=True)}" xmlns="http://www.w3.org/1999/xhtml">'
        "<head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        '<meta name="supported-color-schemes" content="light">'
        f"<title>{escape(_plain(content.subject, params), quote=True)}</title>"
        "</head>"
        f'<body style="margin:0;padding:0;background:{BG};" bgcolor="{BG}">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;'
        'mso-hide:all;font-size:1px;line-height:1px;">'
        f"{preheader}{padding}</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" bgcolor="{BG}" style="background:{BG};"><tr>'
        '<td align="center" style="padding:32px 16px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="max-width:480px;">'
        '<tr><td align="center" style="padding-bottom:20px;">'
        f'<img src="{LOGO_URL}" width="44" height="44" alt="Portfyl" '
        'style="display:block;border:0;outline:none;text-decoration:none;">'
        "</td></tr>"
        f'<tr><td bgcolor="{CARD}" style="background:{CARD};border-radius:20px;'
        f'padding:32px 28px;">{body}</td></tr>'
        '<tr><td align="center" style="padding:20px 12px 0;">'
        f'<p style="{footer_style}">{reason}</p>'
        f'<p style="{footer_style}">{help_line}</p>'
        f'<p style="{footer_style}">Portfyl &middot; portfyl.com</p>'
        "</td></tr></table></td></tr></table></body></html>"
    )


# --- plain text -------------------------------------------------------------


def _text(
    content: EmailContent,
    locale: Locale,
    params: Mapping[str, str],
    action_url: str | None,
) -> str:
    blocks: list[str] = [_plain(content.heading, params)]
    blocks.extend(_plain(paragraph, params) for paragraph in content.paragraphs)
    if content.bullets:
        blocks.append("\n".join(f"- {_plain(bullet, params)}" for bullet in content.bullets))
    if content.facts:
        blocks.append(
            "\n".join(
                f"{_plain(label, params)}: {_plain(value, params)}"
                for label, value in content.facts
            )
        )
    if content.button:
        blocks.append(f"{_plain(content.button, params)}\n{action_url}")
    if content.note:
        blocks.append(_plain(content.note, params))
    blocks.append(
        "\n".join(
            (
                locale.footer_reasons[content.footer_reason],
                locale.footer_help,
                "Portfyl · portfyl.com",
            )
        )
    )
    return "\n\n".join(blocks) + "\n"


# --- public entry point -----------------------------------------------------


def render(
    kind: EmailKind,
    lang: str,
    *,
    params: Mapping[str, str],
    action_url: str | None = None,
) -> RenderedEmail:
    """Render one e-mail kind in ``lang`` (any input; unknown -> English)."""
    code = normalize_language(lang)
    locale = locale_for(code)
    content = locale.messages.get(kind)
    if content is None:
        # A language that does not define this kind yet reads English
        # throughout, so the page language and the copy never disagree.
        locale, content = ENGLISH, ENGLISH.messages[kind]
    used_lang = code if locale is not ENGLISH else "en"

    if content.button:
        if not action_url:
            raise TemplateError("this e-mail has a button but no action_url was given")
        if not action_url.lower().startswith(("https://", "http://")):
            raise TemplateError("action_url must be an http(s) URL")

    return RenderedEmail(
        subject=_plain(content.subject, params),
        html=_html(content, locale, used_lang, params, action_url),
        text=_text(content, locale, params, action_url),
    )
