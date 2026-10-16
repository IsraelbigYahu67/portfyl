"""Minimal sync OpenFIGI v3 /mapping client.

Sync on purpose: it runs inside plain-def import endpoints (threadpool) and
inside the IBKR sync's private loop thread, never on the main event loop.
Without an API key OpenFIGI allows 10 jobs per request and ~25 requests per
minute; with OPENFIGI_API_KEY 100 jobs per request.
"""
from __future__ import annotations

import os

import httpx

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


class OpenFigiUnavailable(RuntimeError):
    pass


class OpenFigiClient:
    def __init__(self, api_key: str | None, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 10.0):
        self.api_key = api_key
        self.jobs_per_request = 100 if api_key else 10
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-OPENFIGI-APIKEY"] = api_key
        self._client = httpx.Client(headers=headers, timeout=timeout, transport=transport)

    @classmethod
    def from_env(cls) -> "OpenFigiClient":
        return cls(os.environ.get("OPENFIGI_API_KEY") or None)

    def map_isins(self, jobs: list[tuple[str, str | None]]) -> list[list[dict]]:
        """jobs = [(isin, bloomberg_exch_code | None)] -> per-job list of matches."""
        results: list[list[dict]] = []
        for start in range(0, len(jobs), self.jobs_per_request):
            chunk = jobs[start:start + self.jobs_per_request]
            payload = [
                {"idType": "ID_ISIN", "idValue": isin, **({"exchCode": exch} if exch else {})}
                for isin, exch in chunk
            ]
            try:
                response = self._client.post(OPENFIGI_URL, json=payload)
            except httpx.HTTPError as exc:
                raise OpenFigiUnavailable(f"Instrument lookup failed: {exc}") from exc
            if response.status_code == 429:
                raise OpenFigiUnavailable(
                    "Instrument lookup is rate-limited; try the import again in a minute"
                )
            if response.status_code >= 400:
                raise OpenFigiUnavailable(f"Instrument lookup returned HTTP {response.status_code}")
            try:
                items = response.json()
            except ValueError as exc:
                raise OpenFigiUnavailable("Instrument lookup returned an unreadable response") from exc
            if not isinstance(items, list) or len(items) != len(chunk):
                raise OpenFigiUnavailable("Instrument lookup returned an unexpected response")
            for item in items:
                results.append(list((item or {}).get("data") or []))
        return results
