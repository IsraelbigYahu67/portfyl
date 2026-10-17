"""eToro Public API client (read-only, personal keys).

Sync httpx: called from the eToro router's plain-def sync and from the
autosync job, never on the event loop. Trading endpoints share a quota of 60
requests per 60 s (market data: 120), so the client spaces calls and surfaces
429 as EtoroRateLimited instead of sleeping on the caller's thread.

Paths and field names follow api-portal.etoro.com (read 2026-10-17); the docs'
example responses disagree with their schemas on ID casing (positionId vs
positionID), so readers accept both. Verify against a real response (plan
Task 0) before relying on anything marked "unverified" below.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
import time
import uuid

import httpx

BASE_URL = "https://public-api.etoro.com"
ENDPOINTS = {
    # Top-level JSON array; `page`/`pageSize`; lookback per request < 1 year.
    "trade_history": "/api/v1/trading/info/trade/history",
    # {"clientPortfolio": {"positions": [...], "mirrors": [...]}}
    "positions": "/api/v1/trading/info/real/pnl",
    # eToro Money cash account (card/bank movements), not the trading account.
    "cash_transactions": "/api/v1/money/accounts/cash/{account_id}/transactions",
    "instruments": "/api/v1/market-data/instruments",
    "exchanges": "/api/v1/market-data/exchanges",
    "instrument_types": "/api/v1/market-data/instrument-types",
}
WINDOW_DAYS = 360
PAGE_SIZE = 100
MIN_INTERVAL = 1.05  # seconds between calls -> stays under 60 per 60 s


class EtoroAuthError(RuntimeError):
    pass


class EtoroRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"eToro rate limit, retry after {retry_after:g}s")
        self.retry_after = retry_after


def field(item: dict, *names, default=None):
    """First present key among casing variants (positionId / positionID)."""
    for name in names:
        if item.get(name) is not None:
            return item[name]
    return default


class EtoroClient:
    def __init__(self, app_key: str, user_key: str, *, transport=None, base_url: str = BASE_URL):
        self._client = httpx.Client(
            base_url=base_url, timeout=20.0, transport=transport,
            headers={"x-api-key": app_key, "x-user-key": user_key, "accept": "application/json"},
        )
        self._throttle = transport is None
        self._last_call = 0.0
        self._lookups: dict[str, dict[int, str]] = {}

    def _get(self, path: str, **params):
        if self._throttle:
            wait = MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
        self._last_call = time.monotonic()
        response = self._client.get(
            path,
            params={k: v for k, v in params.items() if v is not None},
            headers={"x-request-id": str(uuid.uuid4())},
        )
        if response.status_code in (401, 403):
            raise EtoroAuthError("eToro rejected the keys (check Read permission and the Real environment)")
        if response.status_code == 429:
            raise EtoroRateLimited(float(response.headers.get("Retry-After", "60")))
        response.raise_for_status()
        return response.json()

    def trade_history(self, min_date: date) -> list[dict]:
        """Closed positions since `min_date`, walked in < 1-year windows and
        pages. Unverified: whether a window returns only its year or
        everything since minDate; positions are de-duplicated either way."""
        by_id: dict[str, dict] = {}
        start = min_date
        today = datetime.now(timezone.utc).date()
        while start <= today:
            page = 1
            while True:
                batch = self._get(ENDPOINTS["trade_history"], minDate=start.isoformat(),
                                  page=page, pageSize=PAGE_SIZE) or []
                for item in batch:
                    by_id[str(field(item, "positionId", "positionID"))] = item
                if len(batch) < PAGE_SIZE:
                    break
                page += 1
            start += timedelta(days=WINDOW_DAYS)
        return list(by_id.values())

    def positions(self) -> list[dict]:
        data = self._get(ENDPOINTS["positions"]) or {}
        return list((data.get("clientPortfolio") or {}).get("positions") or [])

    def cash_transactions(self, account_id: str) -> list[dict]:
        """eToro Money transactions (cursor pages). Not yet mapped to the
        ledger: see etoro_mapper.CASH_MAPPED."""
        items: list[dict] = []
        token = None
        while True:
            data = self._get(ENDPOINTS["cash_transactions"].format(account_id=account_id),
                             pageSize=500, pageToken=token) or {}
            items.extend(data.get("results") or [])
            token = (data.get("pagination") or {}).get("nextPageToken")
            if not token:
                return items

    def _lookup(self, kind: str) -> dict[int, str]:
        if kind not in self._lookups:
            if kind == "exchanges":
                rows = (self._get(ENDPOINTS["exchanges"]) or {}).get("exchangeInfo") or []
                self._lookups[kind] = {int(r["exchangeID"]): r.get("exchangeDescription") or "" for r in rows}
            else:
                rows = (self._get(ENDPOINTS["instrument_types"]) or {}).get("instrumentTypes") or []
                self._lookups[kind] = {int(r["instrumentTypeID"]): r.get("instrumentTypeDescription") or ""
                                       for r in rows}
        return self._lookups[kind]

    def instruments(self, ids: Iterable[int]) -> dict[int, dict]:
        """instrumentId -> {"symbol", "exchange", "type", "name"} with the
        exchange and type resolved to eToro's own descriptions."""
        wanted = sorted({int(i) for i in ids})
        if not wanted:
            return {}
        data = self._get(ENDPOINTS["instruments"], instrumentIds=",".join(map(str, wanted))) or {}
        exchanges = self._lookup("exchanges")
        types = self._lookup("instrument_types")
        out: dict[int, dict] = {}
        for item in data.get("instrumentDisplayDatas") or []:
            instrument_id = int(field(item, "instrumentID", "instrumentId"))
            out[instrument_id] = {
                "symbol": item.get("symbolFull") or "",
                "exchange": exchanges.get(field(item, "exchangeID", "exchangeId", default=-1), ""),
                "type": types.get(field(item, "instrumentTypeID", "instrumentTypeId", default=-1), ""),
                "name": item.get("instrumentDisplayName"),
            }
        return out
