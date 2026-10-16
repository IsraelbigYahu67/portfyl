"""Stable event ids for exports that carry no broker transaction id.

The id is a digest of the row's business content plus its occurrence number
among identical rows *in the same file*. Two genuinely identical fills on one
day stay two rows, and an overlapping later export (Q1, then the full year)
reproduces the same ids, so the existing source_event_id dedup applies.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import hashlib
import json


def occurrence_ids(keys: Iterable[tuple]) -> list[str]:
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for key in keys:
        encoded = json.dumps(key, default=str, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
        seen[digest] += 1
        ids.append(f"{digest}#{seen[digest]}")
    return ids
