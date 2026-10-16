"""Locale-explicit number parsing for broker exports.

Every format states its decimal separator (or detects it once per file with
detect_decimal); a parser never guesses per cell, because "1.234" is a
thousand in a Czech Degiro export and one point two in a US one.
"""
from __future__ import annotations

from collections.abc import Iterable
import math
import re

_CURRENCY_TOKENS = ("Kč", "CZK", "USD", "EUR", "GBP", "$", "€", "£")
_EMPTY = {"", "-", "--"}
# Plain, non-breaking and narrow no-break spaces all appear as thousands
# separators in exports.
_SPACES = (" ", " ", " ")
_COMMA_DECIMAL = re.compile(r"^[-+(]?\d+(\.\d{3})*,\d+\)?$|^[-+(]?\d+,\d{1,2}\)?$")
_DOT_DECIMAL = re.compile(r"^[-+(]?\d+(,\d{3})*\.\d+\)?$")


def _strip_spaces(text: str) -> str:
    for space in _SPACES:
        text = text.replace(space, "")
    return text


def parse_number(raw, *, decimal: str) -> float | None:
    if decimal not in {".", ","}:
        raise ValueError(f"unsupported decimal separator {decimal!r}")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return None
        return float(raw)
    text = _strip_spaces(str(raw).strip())
    if text in _EMPTY:
        return None
    sign = 1.0
    if text.startswith("(") and text.endswith(")"):
        sign = -1.0
        text = text[1:-1]
    for token in _CURRENCY_TOKENS:
        text = text.replace(token, "")
    if text.startswith("-"):
        sign = -sign
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    thousands = "," if decimal == "." else "."
    text = text.replace(thousands, "")
    if decimal == ",":
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"not a number: {raw!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"not a finite number: {raw!r}")
    return sign * value


def detect_decimal(values: Iterable[str]) -> str:
    comma = dot = False
    for value in values:
        text = _strip_spaces(str(value).strip())
        if _COMMA_DECIMAL.match(text):
            comma = True
        elif _DOT_DECIMAL.match(text):
            dot = True
    if comma and dot:
        raise ValueError("file mixes comma and dot decimal separators")
    return "," if comma else "."
