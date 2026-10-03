"""Dependency-free payload redaction shared by the Trading 212 capture CLIs.

Kept free of `models`/`database` imports so a capture CLI can run on a shell
that only has the provider credentials set (no DATABASE_URL).
"""

from __future__ import annotations

_ID_KEYS = {"id", "reference", "parentOrder", "orderId", "fillId"}
_DROP_KEYS = {"accountId", "accountNumber", "clientId"}


def redact_payload(payload, id_map: dict[str, str]):
    if isinstance(payload, list):
        return [redact_payload(item, id_map) for item in payload]
    if not isinstance(payload, dict):
        return payload
    out = {}
    for key, value in payload.items():
        if key in _DROP_KEYS:
            continue
        if key in _ID_KEYS and value is not None and not isinstance(value, (dict, list)):
            raw = str(value)
            if raw not in id_map:
                id_map[raw] = f"id-{len(id_map) + 1:04d}"
            out[key] = id_map[raw]
        else:
            out[key] = redact_payload(value, id_map)
    return out
