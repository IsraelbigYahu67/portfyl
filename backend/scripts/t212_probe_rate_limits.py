"""Read-only probe of Trading 212's rate-limit response headers.

Answers the two questions plan 2026-10-06-t212-sync-speed.md Task 5 step 3 left
open, because the sync's own `ratelimit remaining=... reset_at=...` log lines are
not persisted and show the clamped value rather than the raw header:

  (a) does `x-ratelimit-remaining` fall by one per request on an endpoint?
  (b) is `x-ratelimit-reset` a Unix timestamp that lands within about a minute
      of the server's own `Date` header?

It sends a few GET requests (limit=1, so the payloads are tiny) to each history
endpoint, well under the documented 20 requests per minute per endpoint. The
credentials come ONLY from the environment of the process that runs it and are
never printed or written. Only rate-limit headers, status codes and the server
`Date` are printed -- no response bodies.

    T212_API_KEY=... [T212_API_SECRET=...] [T212_ENV=live|demo] \
        python -m scripts.t212_probe_rate_limits [--requests 4]
"""

from __future__ import annotations

import argparse
import base64
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

T212_BASES = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}
_API_VERSION_PREFIX = "/api/v0"
ENDPOINTS = (
    "/equity/history/orders",
    "/equity/history/dividends",
    "/equity/history/transactions",
)
_HEADER_NAMES = (
    "x-ratelimit-limit",
    "x-ratelimit-period",
    "x-ratelimit-remaining",
    "x-ratelimit-used",
    "x-ratelimit-reset",
    "retry-after",
)


def t212_headers(api_key: str, api_secret: str = "") -> dict:
    if api_secret:
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {"Authorization": api_key}


def read_credentials(env) -> tuple[str, str, str]:
    key = env.get("T212_API_KEY")
    if not key:
        raise SystemExit("Set T212_API_KEY (and T212_API_SECRET if required) in the environment.")
    environment = env.get("T212_ENV", "live")
    if environment not in T212_BASES:
        raise SystemExit("T212_ENV must be 'live' or 'demo'.")
    return key, env.get("T212_API_SECRET", ""), environment


def follow_path(endpoint: str, next_path: str | None) -> str | None:
    """Relative continuation of `endpoint` from a nextPagePath, or None. Same
    rule as t212_sync.validate_next_page_path: no scheme/host, exactly this
    endpoint, so the Authorization header never goes to a forged URL."""
    if not next_path:
        return None
    parsed = urlsplit(next_path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    path = parsed.path
    if path.startswith(_API_VERSION_PREFIX + "/"):
        path = path[len(_API_VERSION_PREFIX):]
    if path != endpoint:
        return None
    return f"{path}?{parsed.query}" if parsed.query else path


def describe_reset(raw: str | None, server_date: datetime | None) -> str:
    if raw is None:
        return "reset header missing"
    try:
        value = float(raw)
    except ValueError:
        return f"reset={raw!r} (not numeric)"
    if value >= 100_000_000_000:
        kind, seconds = "Unix milliseconds", value / 1000
    elif value >= 1_000_000_000:
        kind, seconds = "Unix seconds", value
    else:
        return f"reset={raw} (small value, looks like relative seconds)"
    when = datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = f"reset={raw} ({kind}) = {when:%H:%M:%S}Z"
    if server_date is not None:
        text += f", {(when - server_date).total_seconds():+.1f}s after the server Date"
    return text


def probe_endpoint(client: httpx.Client, base: str, headers: dict, endpoint: str, count: int) -> None:
    print(f"\n{endpoint}")
    target = f"{endpoint}?limit=1"
    for i in range(1, count + 1):
        resp = client.get(base + target, headers=headers)
        server_date = None
        if resp.headers.get("date"):
            try:
                server_date = parsedate_to_datetime(resp.headers["date"])
            except (TypeError, ValueError):
                server_date = None
        shown = {n: resp.headers.get(n) for n in _HEADER_NAMES if resp.headers.get(n) is not None}
        print(f"  #{i} status={resp.status_code} {shown}")
        print(f"      {describe_reset(resp.headers.get('x-ratelimit-reset'), server_date)}")
        if resp.status_code != 200:
            print("      stopping this endpoint (non-200)")
            return
        try:
            next_path = resp.json().get("nextPagePath")
        except ValueError:
            next_path = None
        followed = follow_path(endpoint, next_path)
        if followed is None:
            print("      no further page; repeating the first request")
            followed = f"{endpoint}?limit=1"
        target = followed


def main(argv=None, env=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--requests", type=int, default=4, help="requests per endpoint (1-8)")
    args = parser.parse_args(argv)
    count = max(1, min(8, args.requests))
    key, secret, environment = read_credentials(env if env is not None else os.environ)
    base = T212_BASES[environment]
    headers = t212_headers(key, secret)
    print(f"Trading 212 {environment}: {count} request(s) per history endpoint")
    with httpx.Client(timeout=15.0) as client:
        for endpoint in ENDPOINTS:
            probe_endpoint(client, base, headers, endpoint, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
