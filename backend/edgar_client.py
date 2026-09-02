"""Client for SEC EDGAR's public filing archive.

Shibui's `beneficial_ownership` table (see shibui_client.py) has no share
count / percent-of-class columns for SC 13D/13G filings -- that data only
lives in the filing's own cover-page table (Item 5's "Aggregate Amount
Beneficially Owned" / "Percent of Class"), which Shibui doesn't parse.
This module fetches the primary filing document straight from EDGAR's
archive (using the accession_number + filer_cik Shibui already gives us --
no separate lookup needed) and extracts those two cover-page fields.

EDGAR has no structured schema for 13D/13G content (unlike Form 4/5's
ownershipDocument XML) -- every filing is a free-form HTML/text document.
The cover-page table itself is SEC-mandated boilerplate (Rule 13d-101 for
13D, Rule 13d-102 for 13G) with identical label text across every filer,
just different row numbers between the two schedule types -- so
parse_ownership_summary() matches on label text, not row number, and
returns None for a field it can't confidently find rather than guessing.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

EDGAR_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

# SEC requires a descriptive User-Agent identifying the requester on every
# request or it will start blocking the IP -- see
# https://www.sec.gov/os/webmaster-faq#developers
USER_AGENT = "Portfyl (personal portfolio tracker) tom.zoubek@gmail.com"

# SEC's documented fair-access limit is 10 requests/second per IP. This is a
# single-user, single-process app, so a simple shared minimum-interval
# throttle keeps every caller comfortably under that without needing a real
# token bucket.
_MIN_INTERVAL = 0.15
_last_request_at = 0.0
_throttle_lock = threading.Lock()


class EdgarError(Exception):
    """Raised when a filing document can't be fetched from EDGAR."""


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        now = time.monotonic()
        wait = _last_request_at + _MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
            _last_request_at += _MIN_INTERVAL
        else:
            _last_request_at = now


def fetch_filing_document(cik: str, accession_number: str, primary_document: str) -> str:
    """Download a filing's primary document as raw HTML/text.

    `cik`, `accession_number`, and `primary_document` come straight from
    Shibui's beneficial_ownership/sec_filings tables -- no extra EDGAR
    lookup needed to locate the document. Raises EdgarError on any network
    failure or non-2xx response.
    """
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVE_BASE}/{cik_no_zeros}/{accession_no_dashes}/{primary_document}"
    _throttle()
    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise EdgarError(f"EDGAR fetch failed for {url}: {e}") from e
    return resp.text


# Cover-page label text is identical across 13D and 13G filers (SEC
# boilerplate) -- only the row number differs, which we deliberately don't
# match on.
_AGGREGATE_AMOUNT_LABEL = re.compile(r"aggregate\s+amount.{0,40}beneficially\s+owned", re.I)
_PERCENT_CLASS_LABEL = re.compile(r"percent(?:age)?\s+of\s+class", re.I)

# Requires >= 3 digits total (first digit + at least 2 more digit/comma
# chars) so a stray 1-2 digit number near the label -- a row-number
# cross-reference like "(9)", a footnote marker -- doesn't get mistaken for
# the real share count. A >5% beneficial-ownership stake is realistically
# always in the thousands or more.
_SHARES_RE = re.compile(r"\d[\d,]{2,}(?:\.\d+)?")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# How far past the matched label to look for the value -- covers both
# "label<br>value" and "label</td></tr><tr><td>value" renderings once
# flattened to text, without wandering into the next cover-page row.
_VALUE_WINDOW = 200


def _find_after_label(text: str, label_re: re.Pattern, value_re: re.Pattern) -> Optional[str]:
    label_match = label_re.search(text)
    if not label_match:
        return None
    window = text[label_match.end():label_match.end() + _VALUE_WINDOW]
    value_match = value_re.search(window)
    return value_match.group(0) if value_match else None


def parse_ownership_summary(html: str) -> dict[str, Optional[float]]:
    """Best-effort extraction of Item 5's two cover-page numbers from a
    13D/13G filing document.

    Returns {"shares_owned": float | None, "percent_of_class": float | None}
    -- either field is None when the document doesn't match the expected
    cover-page shape (very old plain-text filings, non-standard formatting).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)

    shares_raw = _find_after_label(text, _AGGREGATE_AMOUNT_LABEL, _SHARES_RE)
    shares_owned = float(shares_raw.replace(",", "")) if shares_raw else None

    percent_match = _PERCENT_CLASS_LABEL.search(text)
    percent_of_class = None
    if percent_match:
        window = text[percent_match.end():percent_match.end() + _VALUE_WINDOW]
        pct = _PERCENT_RE.search(window)
        if pct:
            percent_of_class = float(pct.group(1))

    return {"shares_owned": shares_owned, "percent_of_class": percent_of_class}
