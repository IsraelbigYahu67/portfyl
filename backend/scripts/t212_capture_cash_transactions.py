"""Read-only capture of Trading 212 cash-movement payloads.

Unblocks the `/equity/history/transactions` stream (plan 2026-09-20 §5.5 items
7-8): the sign convention of DEPOSIT / WITHDRAW / FEE / interest and the meaning
of TRANSFER are not proven by the provider docs, so a human must inspect real
payloads before any mapper is written (same gate as G1 for splits).

Unlike the corporate-action capture this stream is not staged in the database,
so the tool calls Trading 212 directly. The credentials come ONLY from the
environment of the process that runs it, never from arguments, and are never
printed or written:

    T212_API_KEY=... [T212_API_SECRET=...] [T212_ENV=live|demo] \
        python -m scripts.t212_capture_cash_transactions [--max-pages 5]

Output lands in tests/fixtures/t212_cash_transactions/_captured/ (git-ignored),
identifiers replaced by stable placeholders. Review every file before copying
anything into a committed fixture directory.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from scripts._redact import redact_payload

# Deliberately duplicated from t212_sync (importing it pulls in models/database,
# which need DATABASE_URL); tests assert the two stay identical.
T212_BASES = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}


def t212_headers(api_key: str, api_secret: str = "") -> dict:
    if api_secret:
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {"Authorization": api_key}


CASH_ENDPOINT = "/equity/history/transactions"
_API_VERSION_PREFIX = "/api/v0"
_ALLOWED_QUERY_KEYS = {"cursor", "limit", "time"}
# Types the plan already names; everything else (TRANSFER included) is kept in
# full so the human reviewer sees every unresolved shape.
KNOWN_TYPES = frozenset(
    {"DEPOSIT", "WITHDRAW", "FEE", "INTEREST_ON_FREE_CASH", "LENDING_INTEREST"}
)
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "t212_cash_transactions"
    / "_captured"
)


def read_credentials(env) -> tuple[str, str, str]:
    key = env.get("T212_API_KEY")
    if not key:
        raise SystemExit("Set T212_API_KEY (and T212_API_SECRET if required) in the environment.")
    environment = env.get("T212_ENV", "live")
    if environment not in T212_BASES:
        raise SystemExit("T212_ENV must be 'live' or 'demo'.")
    return key, env.get("T212_API_SECRET", ""), environment


def validate_cash_next_path(path: str | None) -> str | None:
    """Same rule as t212_sync.validate_next_page_path: same-origin relative path
    on exactly this endpoint, known query keys only, so the Authorization header
    is never attached to a forged URL."""
    if not path:
        return None
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    relative = parsed.path
    if relative.startswith(_API_VERSION_PREFIX + "/"):
        relative = relative[len(_API_VERSION_PREFIX):]
    if relative != CASH_ENDPOINT:
        return None
    if not set(parse_qs(parsed.query)) <= _ALLOWED_QUERY_KEYS:
        return None
    return relative + (f"?{parsed.query}" if parsed.query else "")


def collect_pages(fetch, *, max_pages: int) -> tuple[list[dict], bool]:
    """Walk up to `max_pages` pages. `fetch(path_or_None) -> (items, next_path)`.
    Returns (items, exhausted) where exhausted means no further page remained."""
    items: list[dict] = []
    path: str | None = None
    for _ in range(max_pages):
        page, path = fetch(path)
        items.extend(page)
        if not path:
            return items, True
    return items, False


def summarize(items: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for item in items:
        row = out.setdefault(str(item.get("type")), {"count": 0, "positive": 0, "negative": 0})
        row["count"] += 1
        amount = item.get("amount")
        if isinstance(amount, (int, float)):
            if amount > 0:
                row["positive"] += 1
            elif amount < 0:
                row["negative"] += 1
    return out


def select_examples(items: list[dict], *, per_type: int = 3) -> list[dict]:
    seen: dict[str, int] = {}
    picked: list[dict] = []
    for item in items:
        kind = str(item.get("type"))
        if kind in KNOWN_TYPES:
            if seen.get(kind, 0) >= per_type:
                continue
            seen[kind] = seen.get(kind, 0) + 1
        picked.append(item)
    return picked


def _make_fetch(base: str, headers: dict):
    def fetch(path: str | None):
        if path:
            resp = httpx.get(f"{base}{path}", headers=headers, timeout=15)
        else:
            resp = httpx.get(f"{base}{CASH_ENDPOINT}", headers=headers, params={"limit": 50}, timeout=15)
        if resp.status_code == 429:
            raise SystemExit("Rate limited by Trading 212; wait for the reset and retry.")
        if resp.status_code == 401:
            raise SystemExit("Trading 212 rejected the API key.")
        resp.raise_for_status()
        data = resp.json()
        return data.get("items") or [], validate_cash_next_path(data.get("nextPagePath"))

    return fetch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()
    key, secret, environment = read_credentials(os.environ)
    fetch = _make_fetch(T212_BASES[environment], t212_headers(key, secret))
    items, exhausted = collect_pages(fetch, max_pages=args.max_pages)
    capture = {
        "source": "t212 /equity/history/transactions (redacted)",
        "exhausted": exhausted,
        "summary": summarize(items),
        "events": redact_payload(select_examples(items), {}),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"cash_{environment}.json"
    path.write_text(json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Read {len(items)} transactions ({'all' if exhausted else 'first pages only'}).")
    print(f"Wrote {len(capture['events'])} examples to {path}. Review before committing.")
    print(json.dumps(capture["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
