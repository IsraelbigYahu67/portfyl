# Portfyl API Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the cloud-only, PostgreSQL-backed fixed-window API rate
limiter described in the spec below: a trusted-edge origin-auth contract, a
global per-IP HTTP gate, four targeted per-route limits, an hourly cleanup
job, and the full fast + PostgreSQL test coverage the spec requires.

**Architecture:** A new `backend/rate_limit.py` owns the core primitives
(rule config, HMAC bucket keys, the race-free upsert, the dependency
factory); `backend/edge_trust.py` owns the `PORTFYL_EDGE_TOKEN` contract;
`backend/cloud_gate.py` combines both into one `BaseHTTPMiddleware` that
`main.py` registers **before** (i.e. more inner than) `CORSMiddleware` so
CORS headers still land on its direct 400/403/429/503 responses. A new
Alembic migration adds the global, non-tenant `rate_limit_buckets` table
(deliberately outside RLS, like `job_runs`). Four existing routes gain a
`rate_limit(...)` dependency; a new `rate_limit_cleanup` recurring job follows
the existing `internal_jobs.py`/Cloud Scheduler pattern exactly.

**Tech Stack:** FastAPI + Starlette (`BaseHTTPMiddleware`, `run_in_threadpool`),
SQLAlchemy 2.0 raw `text()` upsert (`INSERT ... ON CONFLICT ... RETURNING`,
portable to both PostgreSQL and the SQLite fast-test fixture), Alembic,
stdlib `hmac`/`hashlib`/`ipaddress`. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md`
— read it alongside this plan; this plan argues from it but does not repeat
every rationale paragraph verbatim.

## Global Constraints

- Cloud edition only. Local never registers the gate middleware, never
  applies targeted dependencies (they no-op there), never runs the cleanup
  job, and never reads the four rule-config env vars or either secret.
- The rate limiter's DB session is **always its own new `SessionLocal()`**,
  never a route's `Depends(get_db)` session, and it commits before any
  `RateLimitExceeded`/`RateLimitUnavailable` is raised.
- All eight rule env vars (`RATE_LIMIT_{GLOBAL,AUTH_SESSION,BROKER_SYNC,ASSISTANT_CHAT}_{LIMIT,WINDOW_SECONDS}`)
  and both secrets (`PORTFYL_EDGE_TOKEN`, `RATE_LIMIT_KEY_SECRET`) are
  **required, non-defaulted** in cloud — blank, zero, negative, or
  non-integer is a startup `RuntimeError`. The spec's "Default" values are
  what operators should actually set (see the deploy runbook task), not a
  code fallback.
- Never log a raw IP, workspace id, HMAC bucket key, edge token, or key
  secret. Log only rule names, retry-after seconds, and exception type names.
- `rate_limit_buckets` is global infrastructure state: no `workspace_id`
  column, no RLS policy, and it must stay out of `RLS_TABLES`
  (`tests/postgres/test_rls.py`) and `WORKSPACE_SCOPED_TABLES`
  (`tests/postgres/test_runtime_role.py`).
- Every new module-level "cloud secret/config" global (`rate_limit.RATE_LIMIT_RULES`,
  `rate_limit.KEY_SECRET`, `edge_trust.EDGE_TOKEN`) must be read by
  **other** modules via a qualified attribute lookup at call time
  (`rate_limit.RATE_LIMIT_RULES[...]`), never via `from rate_limit import
  RATE_LIMIT_RULES` — the latter freezes a stale reference at import time
  and breaks `monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", ...)` in
  tests (see Task 6).

---

## Task 1: `rate_limit_buckets` table and model

**Files:**
- Modify: `backend/models.py` (add `RateLimitBucket`)
- Modify: `backend/database.py:56` (`EXPECTED_ALEMBIC_HEAD`)
- Create: `backend/alembic/versions/0012_rate_limit_buckets.py`
- Modify: `docs/security/tenant-isolation-matrix.md` (document the non-RLS exception)
- Modify: `deploy/validate-restore.py:72-76` (`ALL_TABLES`)

**Interfaces:**
- Produces: `models.RateLimitBucket` (`key: str` primary key, `count: int`,
  `expires_at: datetime`), used by Task 3's `consume_rate_limit` (raw SQL,
  not the ORM class directly) and Task 8's `rate_limit_cleanup_pass`.

- [ ] **Step 1: Add the model**

In `backend/models.py`, add after the `UsageCounter` class (after line 235):

```python
class RateLimitBucket(Base):
    """Global, non-tenant fixed-window rate-limit state -- one row per
    (rule, identity, window). Deliberately outside RLS: see job_runs above
    and docs/security/tenant-isolation-matrix.md's "Non-tenant
    infrastructure tables" section. `key` is an opaque HMAC-SHA256 digest
    (rate_limit.py) -- never a raw IP or workspace id."""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint("count >= 0", name="ck_rate_limit_bucket_nonnegative"),
    )

    key = Column(String(64), primary_key=True)
    count = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
```

- [ ] **Step 2: Bump the expected Alembic head**

In `backend/database.py:56`, change:

```python
EXPECTED_ALEMBIC_HEAD = "0011_remove_payment_runtime"
```

to:

```python
EXPECTED_ALEMBIC_HEAD = "0012_rate_limit_buckets"
```

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0012_rate_limit_buckets.py`:

```python
"""Add rate_limit_buckets: global, non-tenant fixed-window rate-limit state.

Revision ID: 0012_rate_limit_buckets
Revises: 0011_remove_payment_runtime
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_rate_limit_buckets"
down_revision: Union[str, Sequence[str], None] = "0011_remove_payment_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_bucket_nonnegative"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rate_limit_buckets TO portfyl_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE rate_limit_buckets FROM portfyl_runtime")
    op.drop_index("ix_rate_limit_buckets_expires_at", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
```

- [ ] **Step 4: Document the non-RLS exception**

In `docs/security/tenant-isolation-matrix.md`, insert a new subsection
immediately after the "Database-role invariants" table (after the line
ending `...postgres_engine fixture deliberately grants...` paragraph, i.e.
after line 136) and before `## Adding a resource`:

```markdown
### Non-tenant infrastructure tables

Not every table is workspace-scoped, and not every non-tenant table needs
RLS. `job_runs` (recurring-job heartbeats) and `rate_limit_buckets`
(fixed-window rate-limit counters,
`docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md`) are
process-wide infrastructure state, never keyed by workspace, and are
deliberately excluded from `RLS_TABLES` (`tests/postgres/test_rls.py`) and
`WORKSPACE_SCOPED_TABLES` (`tests/postgres/test_runtime_role.py`). Each
grants `portfyl_runtime` exactly the privileges its access pattern needs:
`job_runs` never deletes rows, so it has no DELETE grant; `rate_limit_buckets`
is upserted by every request and deleted by its hourly cleanup job, so it
has all four (`SELECT, INSERT, UPDATE, DELETE`).

| Table | Grants | Test |
| --- | --- | --- |
| `job_runs` | `SELECT, INSERT, UPDATE` | absent from `RLS_TABLES`/`WORKSPACE_SCOPED_TABLES` by design (no dedicated grants test) |
| `rate_limit_buckets` | `SELECT, INSERT, UPDATE, DELETE` | `test_runtime_role_has_exact_grants_on_rate_limit_buckets` (`tests/postgres/test_runtime_role.py`); absent from `RLS_TABLES`/`WORKSPACE_SCOPED_TABLES` by design |
```

- [ ] **Step 5: Add the table to the restore-validation inventory**

The spec's cleanup section requires updating "restore validation's expected
table inventory" — that is `ALL_TABLES` in `deploy/validate-restore.py`. In
`deploy/validate-restore.py:72-76`, change:

```python
ALL_TABLES: tuple[str, ...] = (
    "users",
    "auth_sessions",
    "job_runs",
) + TENANT_RLS_TABLES
```

to:

```python
ALL_TABLES: tuple[str, ...] = (
    "users",
    "auth_sessions",
    "job_runs",
    "rate_limit_buckets",
) + TENANT_RLS_TABLES
```

`backend/tests/test_restore_validation.py` derives its assertions from this
same `ALL_TABLES` list, so no test file needs editing — run it to confirm:

Run: `cd backend && python -m pytest tests/test_restore_validation.py -v`
Expected: passes unchanged.

- [ ] **Step 6: Verify the fast suite still collects (no Postgres needed yet)**

Run: `cd backend && python -m pytest tests/ -k "test_health" -v`
Expected: passes unchanged (proves `models.py` still imports cleanly and
`Base.metadata` now includes `rate_limit_buckets` without breaking anything
that already exists).

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/database.py backend/alembic/versions/0012_rate_limit_buckets.py docs/security/tenant-isolation-matrix.md deploy/validate-restore.py
git commit -m "feat: add rate_limit_buckets table and model"
```

---

## Task 2: `backend/rate_limit.py` — rule config and secrets

**Files:**
- Create: `backend/rate_limit.py`
- Test: `backend/tests/test_rate_limit_config.py`

**Interfaces:**
- Consumes: `edition.Edition`, `edition.edition_from_env` (`edition.py`).
- Produces: `RateLimitRule` (frozen dataclass: `name: str, limit: int,
  window_seconds: int`, validates positivity in `__post_init__`);
  `load_rate_limit_rules(env: Mapping[str, str]) -> dict[str, RateLimitRule]`;
  `load_key_secret(env: Mapping[str, str]) -> bytes`; module globals
  `RATE_LIMIT_RULES: dict[str, RateLimitRule]` and `KEY_SECRET: bytes |
  None`, both computed once at import time, empty/`None` outside cloud.
  Task 3 appends `client_ip`/`consume_rate_limit` to this same file; Task 4
  appends `rate_limit(...)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rate_limit_config.py`:

```python
"""backend/rate_limit.py: rule config parsing and the two cloud-only
module-level globals it feeds (RATE_LIMIT_RULES, KEY_SECRET)."""
from __future__ import annotations

import pytest

import rate_limit
from rate_limit import RateLimitRule, load_key_secret, load_rate_limit_rules

VALID_CLOUD_ENV = {
    "PORTFYL_EDITION": "cloud",
    "RATE_LIMIT_GLOBAL_LIMIT": "120",
    "RATE_LIMIT_GLOBAL_WINDOW_SECONDS": "60",
    "RATE_LIMIT_AUTH_SESSION_LIMIT": "10",
    "RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS": "60",
    "RATE_LIMIT_BROKER_SYNC_LIMIT": "5",
    "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS": "60",
    "RATE_LIMIT_ASSISTANT_CHAT_LIMIT": "20",
    "RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS": "60",
}


def test_load_rate_limit_rules_returns_all_four_rules_when_valid():
    rules = load_rate_limit_rules(VALID_CLOUD_ENV)
    assert set(rules) == {"global", "auth_session", "broker_sync", "assistant_chat"}
    assert rules["global"] == RateLimitRule(name="global", limit=120, window_seconds=60)
    assert rules["broker_sync"] == RateLimitRule(name="broker_sync", limit=5, window_seconds=60)


@pytest.mark.parametrize("bad_value", ["", "0", "-1", "not-a-number", "  "])
def test_load_rate_limit_rules_rejects_bad_limit(bad_value):
    env = {**VALID_CLOUD_ENV, "RATE_LIMIT_GLOBAL_LIMIT": bad_value}
    with pytest.raises(RuntimeError, match="RATE_LIMIT_GLOBAL_LIMIT"):
        load_rate_limit_rules(env)


@pytest.mark.parametrize("bad_value", ["", "0", "-5", "soon"])
def test_load_rate_limit_rules_rejects_bad_window(bad_value):
    env = {**VALID_CLOUD_ENV, "RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS": bad_value}
    with pytest.raises(RuntimeError, match="RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS"):
        load_rate_limit_rules(env)


def test_load_key_secret_rejects_blank():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SECRET"):
        load_key_secret({"RATE_LIMIT_KEY_SECRET": "  "})


def test_load_key_secret_rejects_missing():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SECRET"):
        load_key_secret({})


def test_load_key_secret_returns_bytes_when_set():
    assert load_key_secret({"RATE_LIMIT_KEY_SECRET": "abc123"}) == b"abc123"


def test_rate_limit_rule_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        RateLimitRule(name="x", limit=0, window_seconds=60)


def test_rate_limit_rule_rejects_non_positive_window():
    with pytest.raises(ValueError):
        RateLimitRule(name="x", limit=1, window_seconds=0)


def test_local_edition_module_level_globals_are_empty():
    # The whole fast suite boots under PORTFYL_EDITION=local (tests/conftest.py);
    # rate_limit.py must never have parsed cloud-only config as a result.
    assert rate_limit.RATE_LIMIT_RULES == {}
    assert rate_limit.KEY_SECRET is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_rate_limit_config.py -v`
Expected: `ModuleNotFoundError: No module named 'rate_limit'`

- [ ] **Step 3: Implement `backend/rate_limit.py`**

```python
"""Cloud-only fixed-window API rate limiting. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md.

Other modules must read RATE_LIMIT_RULES/KEY_SECRET via a qualified
attribute lookup (`rate_limit.RATE_LIMIT_RULES[...]`) at call time, never
via `from rate_limit import RATE_LIMIT_RULES` -- the latter freezes a stale
reference at import time and breaks test monkeypatching of these globals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from edition import Edition, edition_from_env

_RULE_ENV_VARS: dict[str, tuple[str, str]] = {
    "global": ("RATE_LIMIT_GLOBAL_LIMIT", "RATE_LIMIT_GLOBAL_WINDOW_SECONDS"),
    "auth_session": ("RATE_LIMIT_AUTH_SESSION_LIMIT", "RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS"),
    "broker_sync": ("RATE_LIMIT_BROKER_SYNC_LIMIT", "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS"),
    "assistant_chat": ("RATE_LIMIT_ASSISTANT_CHAT_LIMIT", "RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS"),
}


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError(f"RateLimitRule {self.name!r} limit must be positive, got {self.limit}")
        if self.window_seconds <= 0:
            raise ValueError(
                f"RateLimitRule {self.name!r} window_seconds must be positive, got {self.window_seconds}"
            )


def _require_positive_int(env: Mapping[str, str], var_name: str) -> int:
    raw = env.get(var_name, "").strip()
    if not raw:
        raise RuntimeError(f"{var_name} is required in the cloud edition and must be a positive integer")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{var_name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{var_name} must be a positive integer, got {raw!r}")
    return value


def load_rate_limit_rules(env: Mapping[str, str]) -> dict[str, RateLimitRule]:
    """Parse and validate all four rules. Cloud requires every one of the
    eight env vars to be an explicit positive integer -- there is no
    zero-means-disabled behavior and no silent fallback for a blank value."""
    return {
        name: RateLimitRule(
            name=name,
            limit=_require_positive_int(env, limit_var),
            window_seconds=_require_positive_int(env, window_var),
        )
        for name, (limit_var, window_var) in _RULE_ENV_VARS.items()
    }


def load_key_secret(env: Mapping[str, str]) -> bytes:
    raw = env.get("RATE_LIMIT_KEY_SECRET", "").strip()
    if not raw:
        raise RuntimeError("RATE_LIMIT_KEY_SECRET is required in the cloud edition and must not be blank")
    return raw.encode("utf-8")


RATE_LIMIT_RULES: dict[str, RateLimitRule] = (
    load_rate_limit_rules(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else {}
)

KEY_SECRET: bytes | None = (
    load_key_secret(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else None
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_rate_limit_config.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rate_limit.py backend/tests/test_rate_limit_config.py
git commit -m "feat: add rate limit rule config parsing"
```

---

## Task 3: `client_ip()` and `consume_rate_limit()`

**Files:**
- Modify: `backend/rate_limit.py` (append)
- Test: `backend/tests/test_rate_limit_consume.py`

**Interfaces:**
- Consumes: `RateLimitRule`, `KEY_SECRET` (Task 2); `database.SessionLocal`;
  `db_session` fixture (`tests/conftest.py`).
- Produces: `client_ip(request: Request) -> str`; `InvalidClientIp(Exception)`;
  `RateLimitExceeded(Exception)` (`.rule_name: str`, `.retry_after_seconds:
  int`); `RateLimitUnavailable(Exception)` (`.rule_name: str`,
  `.original_exception_type: str`); `consume_rate_limit(*, rule:
  RateLimitRule, identity: str, now: datetime | None = None) -> None`. Task 4
  consumes all of these; Task 6 (`cloud_gate.py`) consumes `client_ip`,
  `InvalidClientIp`, `consume_rate_limit`, `RateLimitExceeded`,
  `RateLimitUnavailable`, and `RATE_LIMIT_RULES["global"]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rate_limit_consume.py`:

```python
"""backend/rate_limit.py: client_ip() validation and consume_rate_limit()'s
race-free upsert, transaction boundary, and fixed-window arithmetic."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import rate_limit
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    client_ip,
    consume_rate_limit,
)


def _request(headers: dict[str, str] | list[tuple[str, str]]):
    if isinstance(headers, dict):
        headers = list(headers.items())
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }
    return Request(scope)


class TestClientIp:
    def test_accepts_canonical_ipv4(self):
        assert client_ip(_request({"CF-Connecting-IP": "203.0.113.9"})) == "203.0.113.9"

    def test_canonicalizes_ipv6(self):
        expanded = _request({"CF-Connecting-IP": "2001:0db8:0000:0000:0000:0000:0000:0001"})
        compressed = _request({"CF-Connecting-IP": "2001:db8::1"})
        assert client_ip(expanded) == client_ip(compressed)

    def test_rejects_missing_header(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({}))

    def test_rejects_duplicated_header(self):
        req = _request([("CF-Connecting-IP", "203.0.113.9"), ("CF-Connecting-IP", "198.51.100.4")])
        with pytest.raises(InvalidClientIp):
            client_ip(req)

    def test_rejects_comma_separated_value(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "203.0.113.9, 198.51.100.4"}))

    def test_rejects_overlong_value(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "2001:db8::1" + "0" * 60}))

    def test_rejects_garbage(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "not-an-ip"}))


@pytest.fixture(autouse=True)
def _consume_env(monkeypatch, db_session):
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")


class TestConsumeRateLimit:
    RULE = RateLimitRule(name="test_rule", limit=2, window_seconds=60)
    NOW = datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)

    def test_nth_succeeds_and_n_plus_1_is_exceeded_with_retry_after(self):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        with pytest.raises(RateLimitExceeded) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        assert exc_info.value.rule_name == "test_rule"
        assert exc_info.value.retry_after_seconds >= 1

    def test_repeated_denied_requests_remain_denied(self):
        for _ in range(2):
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        for _ in range(3):
            with pytest.raises(RateLimitExceeded):
                consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)

    def test_distinct_identities_use_distinct_buckets(self):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="bob", now=self.NOW)  # bob's own bucket, not exceeded

    def test_bucket_persists_across_a_later_rollback_on_the_same_session(self, db_session):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)  # commits internally
        db_session.rollback()  # simulates the route's own later rollback
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        with pytest.raises(RateLimitExceeded):
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)

    def test_minimum_retry_after_is_one_second(self):
        # now sits 59.9s into a 60s window -- expires_at - now < 1s, must clamp up.
        just_before_boundary = datetime(2026, 1, 1, 0, 0, 59, 900000, tzinfo=timezone.utc)
        consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        with pytest.raises(RateLimitExceeded) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        assert exc_info.value.retry_after_seconds == 1

    def test_new_window_resets_the_count(self):
        rule = RateLimitRule(name="test_window", limit=1, window_seconds=60)
        first_window = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        second_window = datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
        consume_rate_limit(rule=rule, identity="dave", now=first_window)
        with pytest.raises(RateLimitExceeded):
            consume_rate_limit(rule=rule, identity="dave", now=first_window)
        consume_rate_limit(rule=rule, identity="dave", now=second_window)  # new window, not exceeded

    def test_db_error_raises_rate_limiter_unavailable(self, monkeypatch):
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise SQLAlchemyError("boom")

            def rollback(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BrokenSession())
        with pytest.raises(RateLimitUnavailable) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="erin", now=self.NOW)
        assert exc_info.value.rule_name == "test_rule"
        assert exc_info.value.original_exception_type == "SQLAlchemyError"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_rate_limit_consume.py -v`
Expected: `ImportError: cannot import name 'client_ip' from 'rate_limit'`

- [ ] **Step 3: Append to `backend/rate_limit.py`**

Add these imports at the top (merge into the existing `from __future__
import annotations` / stdlib block):

```python
import hashlib
import hmac
import ipaddress
import math
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
```

Then append to the end of the file:

```python
_MAX_IP_TEXT_LENGTH = 45  # longest valid IPv6 textual form, e.g. an IPv4-mapped address
_CF_CONNECTING_IP_HEADER = "CF-Connecting-IP"


class InvalidClientIp(Exception):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, rule_name: str, retry_after_seconds: int):
        super().__init__(f"{rule_name}: retry after {retry_after_seconds}s")
        self.rule_name = rule_name
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailable(Exception):
    def __init__(self, rule_name: str, original_exception_type: str):
        super().__init__(f"{rule_name}: {original_exception_type}")
        self.rule_name = rule_name
        self.original_exception_type = original_exception_type


def client_ip(request: Request) -> str:
    """Validate and canonicalize the trusted CF-Connecting-IP value. Callers
    must only trust this after edge_trust.verify_edge_token has already
    succeeded for this request."""
    values = request.headers.getlist(_CF_CONNECTING_IP_HEADER)
    if len(values) != 1:
        raise InvalidClientIp()
    raw = values[0].strip()
    if not raw or len(raw) > _MAX_IP_TEXT_LENGTH:
        raise InvalidClientIp()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        raise InvalidClientIp() from exc


_BUCKET_KEY_VERSION = "1"


def _encode_field(value: str) -> bytes:
    data = value.encode("utf-8")
    return len(data).to_bytes(4, "big") + data


def _bucket_key(*, rule_name: str, identity: str, window_index: int) -> str:
    message = b"".join(
        _encode_field(field)
        for field in (_BUCKET_KEY_VERSION, rule_name, identity, str(window_index))
    )
    return hmac.new(KEY_SECRET, message, hashlib.sha256).hexdigest()


_UPSERT_SQL = text(
    """
    INSERT INTO rate_limit_buckets (key, count, expires_at)
    VALUES (:key, 1, :expires_at)
    ON CONFLICT (key) DO UPDATE
      SET count = CASE
        WHEN rate_limit_buckets.count < :limit_plus_one
          THEN rate_limit_buckets.count + 1
        ELSE rate_limit_buckets.count
      END
    RETURNING count
    """
)


def consume_rate_limit(*, rule: RateLimitRule, identity: str, now: datetime | None = None) -> None:
    """Hash the bucket identity, perform and commit one isolated upsert on a
    brand-new SessionLocal(), then raise if the committed count exceeds the
    rule's limit. Never touches a route's own DB session."""
    captured_now = now or datetime.now(timezone.utc)
    window_index = int(captured_now.timestamp() // rule.window_seconds)
    expires_at = datetime.fromtimestamp((window_index + 1) * rule.window_seconds, tz=timezone.utc)
    key = _bucket_key(rule_name=rule.name, identity=identity, window_index=window_index)

    session = SessionLocal()
    try:
        try:
            count = session.execute(
                _UPSERT_SQL,
                {"key": key, "expires_at": expires_at, "limit_plus_one": rule.limit + 1},
            ).scalar_one()
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise RateLimitUnavailable(rule.name, type(exc).__name__) from exc
    finally:
        session.close()

    if count > rule.limit:
        retry_after = max(1, math.ceil((expires_at - captured_now).total_seconds()))
        raise RateLimitExceeded(rule.name, retry_after)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_rate_limit_consume.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rate_limit.py backend/tests/test_rate_limit_consume.py
git commit -m "feat: add client_ip validation and the rate limit upsert"
```

---

## Task 4: `rate_limit()` dependency factory and response builders

**Files:**
- Modify: `backend/rate_limit.py` (append)
- Test: `backend/tests/test_rate_limit_dependency.py`

**Interfaces:**
- Consumes: `RATE_LIMIT_RULES`, `client_ip`, `consume_rate_limit`,
  `RateLimitExceeded`, `RateLimitUnavailable`, `InvalidClientIp` (Tasks 2-3);
  `tenancy.RequestContext`, `tenancy.get_request_context`; `edition.Edition`.
- Produces: `rate_limit(rule_name: str, *, by: Literal["ip", "workspace"])
  -> Callable`; `rate_limit_exceeded_response(exc) -> JSONResponse`,
  `rate_limit_exceeded_handler(request, exc) -> JSONResponse`; same pair for
  `rate_limit_unavailable_*` and `invalid_client_ip_*`. Task 6 uses the three
  `*_response` builders directly (no request); Task 7 registers the three
  `*_handler` functions with `app.add_exception_handler`; Tasks 8-10 use
  `rate_limit(...)` as a route dependency.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rate_limit_dependency.py`:

```python
"""backend/rate_limit.py: the rate_limit(rule_name, by=...) dependency
factory -- edition no-op behavior, identity selection, and its response/
handler pair."""
from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Request

import rate_limit
from edition import Edition
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_response,
    rate_limit,
    rate_limit_exceeded_response,
    rate_limit_unavailable_response,
)


def _request(edition: Edition, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "app": Mock(state=Mock(portfyl_edition=edition)),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


class TestByIp:
    def test_noops_in_local_edition(self, monkeypatch):
        consume = Mock()
        monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)
        dependency = rate_limit("auth_session", by="ip")
        dependency(_request(Edition.LOCAL))
        consume.assert_not_called()

    def test_calls_consume_rate_limit_with_the_client_ip_in_cloud(self, monkeypatch):
        rule = RateLimitRule(name="auth_session", limit=10, window_seconds=60)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {"auth_session": rule})
        consume = Mock()
        monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)
        dependency = rate_limit("auth_session", by="ip")

        dependency(_request(Edition.CLOUD, {"CF-Connecting-IP": "203.0.113.9"}))

        consume.assert_called_once_with(rule=rule, identity="203.0.113.9")


class TestByWorkspace:
    def test_noops_in_local_edition(self, monkeypatch):
        consume = Mock()
        monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)
        dependency = rate_limit("broker_sync", by="workspace")
        dependency(_request(Edition.LOCAL), context=Mock())
        consume.assert_not_called()

    def test_calls_consume_rate_limit_with_the_workspace_id_in_cloud(self, monkeypatch):
        rule = RateLimitRule(name="broker_sync", limit=5, window_seconds=60)
        monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {"broker_sync": rule})
        consume = Mock()
        monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)
        workspace_id = uuid4()
        context = Mock(workspace=Mock(id=workspace_id))
        dependency = rate_limit("broker_sync", by="workspace")

        dependency(_request(Edition.CLOUD), context=context)

        consume.assert_called_once_with(rule=rule, identity=str(workspace_id))


def test_unknown_by_value_raises_value_error():
    with pytest.raises(ValueError):
        rate_limit("global", by="user")  # type: ignore[arg-type]


class TestResponseBuilders:
    def test_rate_limit_exceeded_response(self):
        response = rate_limit_exceeded_response(RateLimitExceeded("broker_sync", 7))
        assert response.status_code == 429
        assert response.headers["retry-after"] == "7"
        assert response.headers["cache-control"] == "no-store"

    def test_rate_limit_unavailable_response(self):
        response = rate_limit_unavailable_response(RateLimitUnavailable("global", "OperationalError"))
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.headers["cache-control"] == "no-store"

    def test_invalid_client_ip_response(self):
        response = invalid_client_ip_response(InvalidClientIp())
        assert response.status_code == 400
        assert response.headers["cache-control"] == "no-store"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_rate_limit_dependency.py -v`
Expected: `ImportError: cannot import name 'rate_limit' from 'rate_limit'`

- [ ] **Step 3: Append to `backend/rate_limit.py`**

Add these imports at the top:

```python
from typing import Callable, Literal

from fastapi import Depends
from fastapi.responses import JSONResponse

from tenancy import RequestContext, get_request_context
```

Then append to the end of the file:

```python
def rate_limit(rule_name: str, *, by: Literal["ip", "workspace"]) -> Callable:
    """Dependency factory shaped like entitlements.require_capability. The
    rule is looked up from RATE_LIMIT_RULES (a bare module-global reference,
    always fresh -- see the module docstring) inside the returned
    dependency, never at rate_limit() call time, so this factory can be used
    identically in the decorator of every edition without RATE_LIMIT_RULES
    needing to already be populated at router-import time."""
    if by == "ip":
        def dependency(request: Request) -> None:
            if request.app.state.portfyl_edition is not Edition.CLOUD:
                return
            consume_rate_limit(rule=RATE_LIMIT_RULES[rule_name], identity=client_ip(request))
        return dependency
    if by == "workspace":
        def dependency(
            request: Request,
            context: RequestContext = Depends(get_request_context),
        ) -> None:
            if request.app.state.portfyl_edition is not Edition.CLOUD:
                return
            consume_rate_limit(rule=RATE_LIMIT_RULES[rule_name], identity=str(context.workspace.id))
        return dependency
    raise ValueError(f"Unknown rate_limit 'by': {by!r}")


def rate_limit_exceeded_response(exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        {"code": "rate_limit_exceeded", "rule": exc.rule_name},
        status_code=429,
        headers={"Retry-After": str(exc.retry_after_seconds), "Cache-Control": "no-store"},
    )


def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return rate_limit_exceeded_response(exc)


def rate_limit_unavailable_response(_exc: RateLimitUnavailable) -> JSONResponse:
    return JSONResponse(
        {"code": "rate_limiter_unavailable"},
        status_code=503,
        headers={"Retry-After": "1", "Cache-Control": "no-store"},
    )


def rate_limit_unavailable_handler(_request: Request, exc: RateLimitUnavailable) -> JSONResponse:
    return rate_limit_unavailable_response(exc)


def invalid_client_ip_response(_exc: InvalidClientIp) -> JSONResponse:
    return JSONResponse(
        {"code": "invalid_client_ip"},
        status_code=400,
        headers={"Cache-Control": "no-store"},
    )


def invalid_client_ip_handler(_request: Request, exc: InvalidClientIp) -> JSONResponse:
    return invalid_client_ip_response(exc)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_rate_limit_dependency.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/rate_limit.py backend/tests/test_rate_limit_dependency.py
git commit -m "feat: add the rate_limit() dependency factory"
```

---

## Task 5: `backend/edge_trust.py`

**Files:**
- Create: `backend/edge_trust.py`
- Test: `backend/tests/test_edge_trust.py`

**Interfaces:**
- Consumes: `edition.Edition`, `edition.edition_from_env`.
- Produces: `UntrustedEdge(Exception)`; `load_edge_token(env: Mapping[str,
  str]) -> str`; module global `EDGE_TOKEN: str | None`;
  `verify_edge_token(request: Request) -> None`; `untrusted_edge_response()
  -> JSONResponse`. Task 6 (`cloud_gate.py`) consumes all of these via
  `import edge_trust` / `edge_trust.EDGE_TOKEN` (never `from edge_trust
  import EDGE_TOKEN` — same staleness reason as `rate_limit.py`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_edge_trust.py`:

```python
"""backend/edge_trust.py: the PORTFYL_EDGE_TOKEN origin-auth contract."""
from __future__ import annotations

import pytest
from starlette.requests import Request

import edge_trust
from edge_trust import UntrustedEdge, load_edge_token, verify_edge_token

_HEADER = "X-Portfyl-Edge-Token"


def _request(headers: list[tuple[str, str]]) -> Request:
    scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers]}
    return Request(scope)


def test_load_edge_token_rejects_blank():
    with pytest.raises(RuntimeError, match="PORTFYL_EDGE_TOKEN"):
        load_edge_token({"PORTFYL_EDGE_TOKEN": "   "})


def test_load_edge_token_rejects_missing():
    with pytest.raises(RuntimeError, match="PORTFYL_EDGE_TOKEN"):
        load_edge_token({})


def test_load_edge_token_returns_stripped_value():
    assert load_edge_token({"PORTFYL_EDGE_TOKEN": " secret-value "}) == "secret-value"


def test_local_edition_module_level_edge_token_is_none():
    assert edge_trust.EDGE_TOKEN is None


class TestVerifyEdgeToken:
    @pytest.fixture(autouse=True)
    def _token(self, monkeypatch):
        monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "correct-token")

    def test_valid_token_passes(self):
        verify_edge_token(_request([(_HEADER, "correct-token")]))  # does not raise

    def test_missing_header_raises(self):
        with pytest.raises(UntrustedEdge):
            verify_edge_token(_request([]))

    def test_wrong_token_raises(self):
        with pytest.raises(UntrustedEdge):
            verify_edge_token(_request([(_HEADER, "wrong-token")]))

    def test_duplicated_header_raises(self):
        req = _request([(_HEADER, "correct-token"), (_HEADER, "correct-token")])
        with pytest.raises(UntrustedEdge):
            verify_edge_token(req)


def test_untrusted_edge_response_shape():
    response = edge_trust.untrusted_edge_response()
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_edge_trust.py -v`
Expected: `ModuleNotFoundError: No module named 'edge_trust'`

- [ ] **Step 3: Implement `backend/edge_trust.py`**

```python
"""Cloud-only origin-authentication contract: Cloudflare overwrites any
client-supplied value and injects a random Secret-Manager-held token into
`X-Portfyl-Edge-Token` only on requests it forwards to the origin. A valid
token proves a request came through the trusted edge before any IP-based
rate-limit state (rate_limit.py) is trusted or touched. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md."""
from __future__ import annotations

import hmac
import os
from typing import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse

from edition import Edition, edition_from_env

_EDGE_TOKEN_HEADER = "X-Portfyl-Edge-Token"


class UntrustedEdge(Exception):
    pass


def load_edge_token(env: Mapping[str, str]) -> str:
    token = env.get("PORTFYL_EDGE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PORTFYL_EDGE_TOKEN is required in the cloud edition and must not be blank")
    return token


EDGE_TOKEN: str | None = (
    load_edge_token(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else None
)


def verify_edge_token(request: Request) -> None:
    values = request.headers.getlist(_EDGE_TOKEN_HEADER)
    if len(values) != 1 or EDGE_TOKEN is None or not hmac.compare_digest(values[0], EDGE_TOKEN):
        raise UntrustedEdge()


def untrusted_edge_response() -> JSONResponse:
    return JSONResponse(
        {"code": "untrusted_edge"},
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_edge_trust.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/edge_trust.py backend/tests/test_edge_trust.py
git commit -m "feat: add the PORTFYL_EDGE_TOKEN trusted-edge contract"
```

---

## Task 6: `backend/cloud_gate.py` — the combined global HTTP gate

**Files:**
- Create: `backend/cloud_gate.py`
- Test: `backend/tests/test_cloud_gate.py`

**Interfaces:**
- Consumes: `edge_trust` module (`verify_edge_token`, `untrusted_edge_response`,
  `UntrustedEdge`); `rate_limit` module (`client_ip`, `InvalidClientIp`,
  `invalid_client_ip_response`, `consume_rate_limit`, `RATE_LIMIT_RULES`,
  `RateLimitExceeded`, `rate_limit_exceeded_response`,
  `RateLimitUnavailable`, `rate_limit_unavailable_response`).
- Produces: `CloudApiGateMiddleware` (a `BaseHTTPMiddleware` subclass with
  no constructor arguments). Task 7 registers it in `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_cloud_gate.py`:

```python
"""backend/cloud_gate.py: the combined edge-trust + global rate-limit HTTP
gate, exercised against a minimal Starlette app so each check is isolated.
test_main_rate_limit_wiring.py separately proves this middleware is wired
into the real app in the correct position relative to CORSMiddleware."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from cloud_gate import CloudApiGateMiddleware
from rate_limit import RateLimitRule

VALID_HEADERS = {
    "X-Portfyl-Edge-Token": "test-edge-token",
    "CF-Connecting-IP": "203.0.113.9",
    "Origin": "http://localhost:5173",
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CloudApiGateMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _rate_limit_env(monkeypatch, db_session):
    monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
    monkeypatch.setattr(
        rate_limit,
        "RATE_LIMIT_RULES",
        {"global": RateLimitRule(name="global", limit=2, window_seconds=60)},
    )
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)


def test_non_api_path_bypasses_the_gate():
    client = TestClient(_make_app())
    assert client.get("/health").status_code == 200


def test_options_request_is_never_counted():
    client = TestClient(_make_app())
    for _ in range(5):
        client.options(
            "/api/ping",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200


def test_missing_edge_token_is_403_with_cors_and_no_store(db_session):
    from models import RateLimitBucket

    client = TestClient(_make_app())
    response = client.get(
        "/api/ping",
        headers={"CF-Connecting-IP": "203.0.113.9", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 403
    assert response.json() == {"code": "untrusted_edge"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert db_session.query(RateLimitBucket).count() == 0  # untrusted request creates no bucket


def test_wrong_edge_token_is_403():
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS, "X-Portfyl-Edge-Token": "wrong"}
    assert client.get("/api/ping", headers=headers).status_code == 403


def test_malformed_client_ip_is_400():
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS, "CF-Connecting-IP": "not-an-ip"}
    response = client.get("/api/ping", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_client_ip"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_nth_request_succeeds_and_n_plus_1_is_429_with_cors():
    client = TestClient(_make_app())
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    third = client.get("/api/ping", headers=VALID_HEADERS)
    assert third.status_code == 429
    assert third.json() == {"code": "rate_limit_exceeded", "rule": "global"}
    assert int(third.headers["retry-after"]) >= 1
    assert third.headers["cache-control"] == "no-store"
    assert third.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_api_path_is_still_counted():
    # No route is registered for this path -- it would 404 downstream, but
    # the gate runs before routing and must count it anyway.
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS}
    assert client.get("/api/does-not-exist", headers=headers).status_code == 404
    assert client.get("/api/does-not-exist", headers=headers).status_code == 404
    third = client.get("/api/does-not-exist", headers=headers)
    assert third.status_code == 429


def test_distinct_ips_get_distinct_buckets():
    client = TestClient(_make_app())
    headers_a = {**VALID_HEADERS, "CF-Connecting-IP": "203.0.113.9"}
    headers_b = {**VALID_HEADERS, "CF-Connecting-IP": "198.51.100.4"}
    assert client.get("/api/ping", headers=headers_a).status_code == 200
    assert client.get("/api/ping", headers=headers_a).status_code == 200
    assert client.get("/api/ping", headers=headers_a).status_code == 429
    assert client.get("/api/ping", headers=headers_b).status_code == 200


def test_rate_limiter_db_error_is_503(monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    class _BrokenSession:
        def execute(self, *args, **kwargs):
            raise SQLAlchemyError("boom")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BrokenSession())
    client = TestClient(_make_app())
    response = client.get("/api/ping", headers=VALID_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"code": "rate_limiter_unavailable"}
    assert response.headers["retry-after"] == "1"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_cloud_gate.py -v`
Expected: `ModuleNotFoundError: No module named 'cloud_gate'`

- [ ] **Step 3: Implement `backend/cloud_gate.py`**

```python
"""The cloud-only global HTTP gate: trusted-edge verification followed by
the global per-IP rate limit, for every /api and /api/* request. Registered
in main.py *before* CORSMiddleware's own app.add_middleware() call so this
middleware ends up more inner than CORS in Starlette's wrap order --
CORSMiddleware then still decorates this middleware's own direct 400/403/
429/503 responses. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md."""
from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import edge_trust
import rate_limit

log = logging.getLogger("portfyl.cloud_gate")


class CloudApiGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or not (path == "/api" or path.startswith("/api/")):
            return await call_next(request)

        try:
            edge_trust.verify_edge_token(request)
        except edge_trust.UntrustedEdge:
            return edge_trust.untrusted_edge_response()

        try:
            ip = rate_limit.client_ip(request)
        except rate_limit.InvalidClientIp as exc:
            return rate_limit.invalid_client_ip_response(exc)

        try:
            await run_in_threadpool(
                rate_limit.consume_rate_limit,
                rule=rate_limit.RATE_LIMIT_RULES["global"],
                identity=ip,
            )
        except rate_limit.RateLimitExceeded as exc:
            log.info("rate_limit_exceeded rule=%s retry_after=%s", exc.rule_name, exc.retry_after_seconds)
            return rate_limit.rate_limit_exceeded_response(exc)
        except rate_limit.RateLimitUnavailable as exc:
            log.error("rate_limit_error rule=%s exception_type=%s", exc.rule_name, exc.original_exception_type)
            return rate_limit.rate_limit_unavailable_response(exc)

        return await call_next(request)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_cloud_gate.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/cloud_gate.py backend/tests/test_cloud_gate.py
git commit -m "feat: add the combined cloud API gate middleware"
```

---

## Task 7: Wire the gate into `main.py`

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_main_rate_limit_wiring.py`

**Interfaces:**
- Consumes: `cloud_gate.CloudApiGateMiddleware` (Task 6); `rate_limit.{RateLimitExceeded,
  RateLimitUnavailable, InvalidClientIp, rate_limit_exceeded_handler,
  rate_limit_unavailable_handler, invalid_client_ip_handler}` (Task 4).
- Produces: `main.app` with the gate registered cloud-only, more inner than
  CORS; the three new exception handlers registered; `main._JOB_MAX_AGES`
  gaining a cloud-only `"rate_limit_cleanup"` entry (consumed by Task 12's
  `/health` behavior).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_main_rate_limit_wiring.py`:

```python
"""main.py: the cloud-only rate-limit gate's registration position relative
to CORSMiddleware, its exception handlers, and the cloud-only
rate_limit_cleanup entry in _JOB_MAX_AGES."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from database import get_db
from rate_limit import RateLimitRule


def _reload_main(monkeypatch, edition: str):
    monkeypatch.setenv("PORTFYL_EDITION", edition)
    import main

    return importlib.reload(main)


def test_local_edition_never_registers_the_gate_middleware(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "local")
        middleware_classes = {m.cls for m in main.app.user_middleware}
        from cloud_gate import CloudApiGateMiddleware

        assert CloudApiGateMiddleware not in middleware_classes
    finally:
        _reload_main(monkeypatch, "local")


def test_cloud_edition_registers_the_gate_more_inner_than_cors(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")
        from cloud_gate import CloudApiGateMiddleware
        from fastapi.middleware.cors import CORSMiddleware

        classes = [m.cls for m in main.app.user_middleware]
        # user_middleware is listed outermost-first; the gate must appear
        # AFTER CORSMiddleware in this list (i.e. it is more inner / closer
        # to routing), so CORS still wraps the gate's direct error responses.
        assert classes.index(CORSMiddleware) < classes.index(CloudApiGateMiddleware)
    finally:
        _reload_main(monkeypatch, "local")


def test_cloud_health_thresholds_include_rate_limit_cleanup(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")
        assert "rate_limit_cleanup" in main._JOB_MAX_AGES
    finally:
        _reload_main(monkeypatch, "local")


def test_local_health_thresholds_never_include_rate_limit_cleanup(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "local")
        assert "rate_limit_cleanup" not in main._JOB_MAX_AGES
    finally:
        _reload_main(monkeypatch, "local")


def test_full_app_gate_wraps_routing_and_cors_survives_a_429(monkeypatch, db_session):
    try:
        main = _reload_main(monkeypatch, "cloud")
        main.app.dependency_overrides[get_db] = lambda: db_session
        monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
        monkeypatch.setattr(
            rate_limit,
            "RATE_LIMIT_RULES",
            {"global": RateLimitRule(name="global", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        headers = {
            "X-Portfyl-Edge-Token": "test-edge-token",
            "CF-Connecting-IP": "203.0.113.9",
            "Origin": "http://localhost:5173",
        }
        with TestClient(main.app) as client:
            first = client.get("/api/portfolios", headers=headers)
            second = client.get("/api/portfolios", headers=headers)

        assert first.status_code == 401  # past the gate, into real (unauthenticated) routing
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "global"}
        assert second.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert second.headers["cache-control"] == "no-store"
    finally:
        main.app.dependency_overrides.clear()
        _reload_main(monkeypatch, "local")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_main_rate_limit_wiring.py -v`
Expected: fails — the gate isn't registered yet, so `CloudApiGateMiddleware`
never appears in `user_middleware` and `_JOB_MAX_AGES` has no
`rate_limit_cleanup` key.

- [ ] **Step 3: Modify `backend/main.py`**

Add to the import block (near the other top-level imports, after line 23's
`from entitlements import EntitlementDenied, entitlement_denied_handler`):

```python
from cloud_gate import CloudApiGateMiddleware
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
```

Add exception handler registrations right after the existing
`app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)`
(line 42):

```python
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
```

Insert the gate's registration **immediately before** the existing
`app.add_middleware(CORSMiddleware, ...)` call (i.e. before line 59,
replacing the blank line between the `_cors_origins` block and that call):

```python
if PORTFYL_EDITION is Edition.CLOUD:
    # Registered before CORSMiddleware's own add_middleware() call so it
    # ends up more inner than CORS in Starlette's wrap order (later-added
    # middleware wraps outermost) -- CORS then still decorates this gate's
    # own direct 400/403/429/503 responses instead of skipping them.
    app.add_middleware(CloudApiGateMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Change `_JOB_MAX_AGES` (line 138-142) from an unconditional dict literal to
a conditionally-extended one — replace:

```python
_JOB_MAX_AGES = {
    "alerts": timedelta(minutes=30),
    "autosync": timedelta(hours=2),
    "dividends": timedelta(hours=25),
}
```

with:

```python
_JOB_MAX_AGES = {
    "alerts": timedelta(minutes=30),
    "autosync": timedelta(hours=2),
    "dividends": timedelta(hours=25),
}
if PORTFYL_EDITION is Edition.CLOUD:
    # rate_limit_cleanup only ever runs in cloud (internal_jobs.router is
    # cloud-only); local must never expect a heartbeat for a job it never
    # schedules, or /health would report permanently degraded there.
    _JOB_MAX_AGES["rate_limit_cleanup"] = timedelta(hours=2)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_main_rate_limit_wiring.py -v`
Expected: all pass.

- [ ] **Step 5: Run the full fast suite to check for regressions**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`
Expected: all pass, including the existing `tests/test_health.py` and
`tests/test_internal_jobs.py` (both run under the process's original local
boot and must be unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_main_rate_limit_wiring.py
git commit -m "feat: wire the cloud rate-limit gate into main.py"
```

---

## Task 8: Targeted limit on `/api/auth/session`

**Files:**
- Modify: `backend/routers/auth.py`
- Test: `backend/tests/test_rate_limit_routes.py` (new file)

**Interfaces:**
- Consumes: `rate_limit.rate_limit` (Task 4).
- Produces: `/api/auth/session` gains `Depends(rate_limit("auth_session",
  by="ip"))`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_rate_limit_routes.py`:

```python
"""The five targeted rate_limit(...) route dependencies: proves each route
is actually gated by hitting it enough times to trip a deliberately tiny
limit, using minimal mini-apps in the same style as
tests/test_hosted_assistant.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import rate_limit
from database import get_db
from edition import Edition
from entitlements import EntitlementDenied, entitlement_denied_handler
from firebase_identity import IdentityVerificationError
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
from routers.portfolios import require_portfolio
from tenancy import get_request_context, require_csrf


def _rate_limited_app(*, cloud: bool) -> FastAPI:
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD if cloud else Edition.LOCAL
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
    app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
    return app


class _FailingVerifier:
    """Deterministically fails like a real Firebase call would with a bad
    token, without needing Firebase Admin configured in tests. get_identity_verifier
    is used via Depends(...), so it must be swapped with
    app.dependency_overrides -- monkeypatching the module attribute would
    not change what FastAPI already captured at route-decoration time."""

    def verify_id_token(self, token: str):
        raise IdentityVerificationError("no real Firebase call in this test")


class TestAuthSessionRateLimit:
    def _app(self, db_session) -> FastAPI:
        from routers import auth as auth_router

        app = _rate_limited_app(cloud=True)
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: _FailingVerifier()
        return app

    def test_second_call_from_the_same_ip_is_429(self, monkeypatch, db_session):
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"auth_session": RateLimitRule(name="auth_session", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        client = TestClient(self._app(db_session))
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        first = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)
        second = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)

        assert first.status_code == 401  # IdentityVerificationError -- past the limiter
        assert first.json() == {"code": "authentication_required"}
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "auth_session"}

    def test_noops_in_local_edition(self, monkeypatch, db_session):
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"auth_session": RateLimitRule(name="auth_session", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        app = self._app(db_session)
        app.state.portfyl_edition = Edition.LOCAL
        client = TestClient(app)
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        for _ in range(5):
            response = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)
            assert response.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestAuthSessionRateLimit -v`
Expected: both calls return the same non-429 status (no rate limiting
applied yet).

- [ ] **Step 3: Modify `backend/routers/auth.py`**

Add to the import block (after line 10's `from sqlalchemy.orm import Session`):

```python
from rate_limit import rate_limit
```

Change the route decorator at line 166 from:

```python
@router.post("/session", status_code=201)
```

to:

```python
@router.post("/session", status_code=201, dependencies=[Depends(rate_limit("auth_session", by="ip"))])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestAuthSessionRateLimit -v`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/auth.py backend/tests/test_rate_limit_routes.py
git commit -m "feat: rate-limit /api/auth/session by IP"
```

---

## Task 9: Targeted limit on the three broker sync routes

**Files:**
- Modify: `backend/routers/broker.py`, `backend/routers/ibkr.py`,
  `backend/routers/polymarket.py`
- Modify: `backend/tests/test_rate_limit_routes.py` (append)

**Interfaces:**
- Consumes: `rate_limit.rate_limit` (Task 4).
- Produces: `/api/broker/trading212/sync`, `/api/broker/ibkr/sync`,
  `/api/broker/polymarket/sync` each gain `Depends(rate_limit("broker_sync",
  by="workspace"))`, sharing one `broker_sync` bucket per workspace (per
  spec, this is intentional — not a bug to fix later).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_rate_limit_routes.py`:

```python
class TestBrokerSyncRateLimit:
    """All three sync routes 404 immediately with no seeded BrokerConnection
    row -- so hitting them with none seeded proves the limiter runs (and
    commits) even though the route itself never gets past its own
    "not connected" check, exactly matching the spec's "the request counts
    even if the downstream provider fails" requirement.

    Every cloud workspace currently resolves to the FREE plan (no billing
    runtime -- see CLAUDE.md), and broker_sync requires PlanTier.INVESTOR
    (plans.py's MINIMUM_PLAN), so require_capability("broker_sync") would
    otherwise 403 before the limiter ever runs on every one of these routes.
    Bypass it the same way Task 10 does, by no-opping
    entitlements.ensure_capability."""

    def _app(self, router_module, prefix: str, db_session, request_context) -> FastAPI:
        app = _rate_limited_app(cloud=True)
        app.include_router(router_module.router, prefix=prefix)
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context
        return app

    def _assert_second_call_is_429(self, app, path, monkeypatch, db_session):
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"broker_sync": RateLimitRule(name="broker_sync", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        with TestClient(app) as client:
            first = client.post(path)
            second = client.post(path)

        assert first.status_code == 404  # "not connected" -- past the limiter
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "broker_sync"}

    def test_trading212_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import broker

        app = self._app(broker, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/trading212/sync", monkeypatch, db_session)

    def test_ibkr_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import ibkr

        app = self._app(ibkr, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/ibkr/sync", monkeypatch, db_session)

    def test_polymarket_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import polymarket

        app = self._app(polymarket, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/polymarket/sync", monkeypatch, db_session)

    def test_trading212_and_ibkr_share_one_workspace_bucket(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import broker, ibkr
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"broker_sync": RateLimitRule(name="broker_sync", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        app = _rate_limited_app(cloud=True)
        app.include_router(broker.router, prefix="/api")
        app.include_router(ibkr.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context

        with TestClient(app) as client:
            first = client.post("/api/broker/trading212/sync")
            second = client.post("/api/broker/ibkr/sync")

        assert first.status_code == 404
        assert second.status_code == 429  # same broker_sync bucket, intentionally shared
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestBrokerSyncRateLimit -v`
Expected: every "second call" assertion fails (both calls 404, no 429 yet).

- [ ] **Step 3: Modify the three routers**

In `backend/routers/broker.py`, add to the import block (after line 12's
`from entitlements import require_broker_capacity, require_capability,
require_writable_broker`):

```python
from rate_limit import rate_limit
```

Change line 380 from:

```python
@router.post("/trading212/sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("trading212"))])
```

to:

```python
@router.post("/trading212/sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("trading212")), Depends(rate_limit("broker_sync", by="workspace"))])
```

In `backend/routers/ibkr.py`, add to the import block (after line 13's
`from entitlements import require_broker_capacity, require_capability,
require_writable_broker`):

```python
from rate_limit import rate_limit
```

Change line 693 from:

```python
@router.post("/sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("ibkr"))])
```

to:

```python
@router.post("/sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("ibkr")), Depends(rate_limit("broker_sync", by="workspace"))])
```

In `backend/routers/polymarket.py`, add to the import block (after line 9's
`from entitlements import require_broker_capacity, require_capability,
require_writable_broker`):

```python
from rate_limit import rate_limit
```

Change line 142 from:

```python
@router.post("/broker/polymarket/sync", dependencies=[Depends(require_capability("polymarket")), Depends(require_writable_broker("polymarket"))])
```

to:

```python
@router.post("/broker/polymarket/sync", dependencies=[Depends(require_capability("polymarket")), Depends(require_writable_broker("polymarket")), Depends(rate_limit("broker_sync", by="workspace"))])
```

Note polymarket keeps its own `require_capability("polymarket")` (unchanged)
but shares the `broker_sync` **rate-limit rule and bucket** with the other
two, exactly as the spec's rule table specifies.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestBrokerSyncRateLimit -v`
Expected: all pass.

- [ ] **Step 5: Run the full fast suite to check for regressions**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`
Expected: all pass, including existing broker/ibkr/polymarket tests
(`test_broker.py`, `test_ibkr.py`, `test_polymarket.py` or equivalent) —
those tests run under the process's original local-edition boot, where
`rate_limit(...)` no-ops.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/broker.py backend/routers/ibkr.py backend/routers/polymarket.py backend/tests/test_rate_limit_routes.py
git commit -m "feat: rate-limit the three broker sync routes per workspace"
```

---

## Task 10: Targeted limit on `/api/assistant/chat`

**Files:**
- Modify: `backend/routers/assistant.py`
- Modify: `backend/tests/test_rate_limit_routes.py` (append)

**Interfaces:**
- Consumes: `rate_limit.rate_limit` (Task 4).
- Produces: `/api/assistant/chat` gains `Depends(rate_limit("assistant_chat",
  by="workspace"))`.

- [ ] **Step 1: Write the failing test**

Every cloud workspace currently resolves to the FREE plan (no billing
runtime — see `CLAUDE.md`), so `require_capability("assistant_byok")` would
otherwise always 403 before the limiter ever runs. Bypass it the same way
the codebase already lets any dependency's internal check be monkeypatched:
patch `entitlements.ensure_capability` (the function `require_capability`'s
dependency body calls by name) to a no-op, mirroring
`tests/test_hosted_assistant.py`'s use of `_call_deepseek` mocking.

Append to `backend/tests/test_rate_limit_routes.py`:

```python
class TestAssistantChatRateLimit:
    def test_second_call_from_the_same_workspace_is_429(
        self, monkeypatch, db_session, request_context, default_portfolio
    ):
        from routers import assistant
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"assistant_chat": RateLimitRule(name="assistant_chat", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        app = _rate_limited_app(cloud=True)
        app.include_router(assistant.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context
        app.dependency_overrides[require_portfolio] = lambda: default_portfolio

        provider = AsyncMock(return_value=("answer", {"total_tokens": 4}))
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        with patch("routers.assistant._call_deepseek", provider), TestClient(app) as client:
            first = client.post(
                "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "req-1"}
            )
            second = client.post(
                "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "req-2"}
            )

        assert first.status_code != 429  # capability check bypassed; limiter let it through
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "assistant_chat"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestAssistantChatRateLimit -v`
Expected: both calls succeed (or both fail identically for an unrelated
reason) — no 429 yet.

- [ ] **Step 3: Modify `backend/routers/assistant.py`**

Add to the import block (after line 16's `from tenancy import
RequestContext, get_request_context, require_csrf`):

```python
from rate_limit import rate_limit
```

Change line 284 from:

```python
@router.post("/chat", dependencies=[Depends(require_capability("assistant_byok"))])
```

to:

```python
@router.post("/chat", dependencies=[Depends(require_capability("assistant_byok")), Depends(rate_limit("assistant_chat", by="workspace"))])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_rate_limit_routes.py::TestAssistantChatRateLimit -v`
Expected: passes.

- [ ] **Step 5: Run the full fast suite**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`
Expected: all pass, including `tests/test_hosted_assistant.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/assistant.py backend/tests/test_rate_limit_routes.py
git commit -m "feat: rate-limit /api/assistant/chat per workspace"
```

---

## Task 11: `rate_limit_cleanup_pass` in `jobs.py`

**Files:**
- Modify: `backend/jobs.py`
- Test: `backend/tests/test_jobs.py` (append)

**Interfaces:**
- Consumes: `models.RateLimitBucket` (Task 1).
- Produces: `RECURRING_JOB_NAMES` gains `"rate_limit_cleanup"`;
  `rate_limit_cleanup_pass(db: Session, now: datetime | None = None, *,
  batch_size: int = 10_000, max_rows: int = 100_000) -> list[dict]` — the
  `Callable[[Session], Awaitable[list]]` shape `_run_job` requires. Task 12
  imports and calls this from a new internal-jobs endpoint.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_jobs.py`:

```python
from models import RateLimitBucket
from jobs import rate_limit_cleanup_pass


class TestRateLimitCleanupPass:
    NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def _seed(self, db_session, *, expired: int, live: int):
        for i in range(expired):
            db_session.add(RateLimitBucket(
                key=f"expired-{i}", count=1, expires_at=self.NOW - timedelta(minutes=1),
            ))
        for i in range(live):
            db_session.add(RateLimitBucket(
                key=f"live-{i}", count=1, expires_at=self.NOW + timedelta(minutes=5),
            ))
        db_session.commit()

    def test_deletes_only_expired_rows(self, db_session):
        self._seed(db_session, expired=3, live=2)

        result = _run(rate_limit_cleanup_pass(db_session, now=self.NOW))

        assert result == [{"deleted": 3}]
        remaining = db_session.query(RateLimitBucket).all()
        assert {row.key for row in remaining} == {"live-0", "live-1"}

    def test_records_nothing_when_no_expired_rows(self, db_session):
        self._seed(db_session, expired=0, live=2)

        result = _run(rate_limit_cleanup_pass(db_session, now=self.NOW))

        assert result == []

    def test_respects_batch_and_max_rows_bounds(self, db_session, caplog):
        self._seed(db_session, expired=10, live=0)

        with caplog.at_level(logging.INFO, logger="portfyl.jobs"):
            result = _run(rate_limit_cleanup_pass(db_session, now=self.NOW, batch_size=3, max_rows=7))

        assert result == [{"deleted": 7}]
        assert db_session.query(RateLimitBucket).count() == 3  # 10 - 7
        assert any("deleted=7 remaining_backlog=3" in message for message in caplog.messages)

    def test_logs_the_cleanup_event_even_when_nothing_expired(self, db_session, caplog):
        self._seed(db_session, expired=0, live=2)

        with caplog.at_level(logging.INFO, logger="portfyl.jobs"):
            _run(rate_limit_cleanup_pass(db_session, now=self.NOW))

        assert any("deleted=0 remaining_backlog=0" in message for message in caplog.messages)
```

`test_jobs.py:9` currently reads `from datetime import date` and has no
`import logging` — change line 9 to:

```python
from datetime import date, datetime, timedelta, timezone
```

and add `import logging` alongside the existing `import asyncio` (line 7):

```python
import asyncio
import logging
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_jobs.py::TestRateLimitCleanupPass -v`
Expected: `ImportError: cannot import name 'rate_limit_cleanup_pass' from 'jobs'`

- [ ] **Step 3: Modify `backend/jobs.py`**

Change the sqlalchemy import at line 62 from:

```python
from sqlalchemy import select, text
```

to:

```python
from sqlalchemy import delete, func, select, text
```

Change `RECURRING_JOB_NAMES` at line 88 from:

```python
RECURRING_JOB_NAMES = ("alerts", "autosync", "dividends")
```

to:

```python
RECURRING_JOB_NAMES = ("alerts", "autosync", "dividends", "rate_limit_cleanup")
```

Append near the end of the file, after `alert_check_all_workspaces`:

```python
async def rate_limit_cleanup_pass(
    db: Session,
    now: datetime | None = None,
    *,
    batch_size: int = 10_000,
    max_rows: int = 100_000,
) -> list[dict]:
    """Delete expired rate_limit_buckets rows in bounded batches. Global,
    non-tenant infrastructure state -- unlike every other pass in this
    module, this one never enumerates or scopes by workspace (see
    models.RateLimitBucket and docs/security/tenant-isolation-matrix.md's
    "Non-tenant infrastructure tables" section). Returns one summary dict
    (not one per deleted row -- there is no meaningful per-row "event" here)
    so _run_job's len(happened) still logs a truthy 1 when work occurred."""
    from models import RateLimitBucket

    cutoff = now or datetime.now(timezone.utc)
    deleted_total = 0
    while deleted_total < max_rows:
        remaining_budget = max_rows - deleted_total
        this_batch = batch_size if batch_size < remaining_budget else remaining_budget
        keys = db.scalars(
            select(RateLimitBucket.key)
            .where(RateLimitBucket.expires_at <= cutoff)
            .limit(this_batch)
        ).all()
        if not keys:
            break
        db.execute(delete(RateLimitBucket).where(RateLimitBucket.key.in_(keys)))
        db.commit()
        deleted_total += len(keys)
        if len(keys) < this_batch:
            break

    remaining = db.scalar(
        select(func.count()).select_from(RateLimitBucket).where(RateLimitBucket.expires_at <= cutoff)
    ) or 0
    # The spec's dedicated "rate_limit_cleanup" structured observability
    # event -- always emitted (not gated on remaining > 0), since this is a
    # low-frequency (hourly) job where "ran, nothing to clean" is itself
    # useful signal, unlike the generic per-check logs this module avoids.
    log.info("rate_limit_cleanup deleted=%d remaining_backlog=%d", deleted_total, remaining)
    return [{"deleted": deleted_total}] if deleted_total else []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_jobs.py::TestRateLimitCleanupPass -v`
Expected: all pass.

- [ ] **Step 5: Run the full fast suite**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`
Expected: all pass, including every existing `test_jobs.py`/`test_health.py`
test that calls `mark_job_succeeded` (unaffected — `RECURRING_JOB_NAMES`
only grew, nothing was removed).

- [ ] **Step 6: Commit**

```bash
git add backend/jobs.py backend/tests/test_jobs.py
git commit -m "feat: add rate_limit_cleanup_pass"
```

---

## Task 12: `/internal/jobs/rate_limit_cleanup` endpoint

**Files:**
- Modify: `backend/routers/internal_jobs.py`
- Test: `backend/tests/test_internal_jobs.py` (append)

**Interfaces:**
- Consumes: `jobs.rate_limit_cleanup_pass` (Task 11); `_run_job`,
  `verify_scheduler_token` (already in `internal_jobs.py`).
- Produces: `POST /internal/jobs/rate_limit_cleanup`, following the exact
  shape of the three existing endpoints.

- [ ] **Step 1: Write the failing test**

Append to the `TestJobEndpointsRunExactlyOnePass` class in
`backend/tests/test_internal_jobs.py`:

```python
    def test_rate_limit_cleanup_endpoint_runs_the_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[{"deleted": 42}])
        with patch("jobs.rate_limit_cleanup_pass", pass_fn):
            result = _run(internal_jobs.run_rate_limit_cleanup_job(authorization="Bearer x"))
        pass_fn.assert_awaited_once()
        assert result == {"job": "rate_limit_cleanup", "events": 1}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_internal_jobs.py -k rate_limit_cleanup -v`
Expected: `AttributeError: module 'routers.internal_jobs' has no attribute 'run_rate_limit_cleanup_job'`

- [ ] **Step 3: Modify `backend/routers/internal_jobs.py`**

Append after the existing `run_dividends_job` endpoint (after line 190):

```python
@router.post("/rate_limit_cleanup")
async def run_rate_limit_cleanup_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import rate_limit_cleanup_pass

    return await _run_job("rate_limit_cleanup", rate_limit_cleanup_pass)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_internal_jobs.py -k rate_limit_cleanup -v`
Expected: passes.

- [ ] **Step 5: Run the full fast suite**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/internal_jobs.py backend/tests/test_internal_jobs.py
git commit -m "feat: add the rate_limit_cleanup internal job endpoint"
```

---

## Task 13: Deploy runbook — secrets, env vars, and the fourth Cloud Scheduler job

**Files:**
- Modify: `deploy/cloudrun.md`

**Interfaces:**
- None (documentation only) — this task has no automated test; self-check
  by re-reading the diff against the spec's "Configuration" and "Cleanup and
  operational integration" sections before committing.

- [ ] **Step 1: Add the two new secrets to step 4**

In `deploy/cloudrun.md`, after the existing three `gcloud secrets create
portfyl-job-database-url` / `versions add` lines (after line 154), add:

```powershell
gcloud secrets create portfyl-edge-token --replication-policy=automatic
python -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets versions add portfyl-edge-token --data-file=-

gcloud secrets create portfyl-rate-limit-key-secret --replication-policy=automatic
python -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets versions add portfyl-rate-limit-key-secret --data-file=-
```

Add these two lines to the IAM-binding block right after the existing
`gcloud secrets add-iam-policy-binding portfyl-job-database-url ...` line
(after line 165):

```powershell
gcloud secrets add-iam-policy-binding portfyl-edge-token --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-rate-limit-key-secret --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

- [ ] **Step 2: Add a Cloudflare configuration note near step 4**

Insert this paragraph right after the two new secret blocks from Step 1:

```markdown
**Cloudflare must inject the edge token.** `PORTFYL_EDGE_TOKEN` (above) is
only half the contract — in the Cloudflare dashboard for portfyl.com,
create a Transform Rule (Rules → Transform Rules → Modify Request Header)
that runs on every request to the Cloud Run origin: **Set static** header
`X-Portfyl-Edge-Token` to the exact value stored in `portfyl-edge-token`,
overwriting any client-supplied value. Without this rule every request gets
403 `untrusted_edge` (see `backend/edge_trust.py`); a client-supplied
`X-Portfyl-Edge-Token` reaching the origin directly (bypassing Cloudflare)
must never be trusted, which is exactly why the middleware only accepts
this header, never falls back to anything else.
```

- [ ] **Step 3: Add the rate-limit env vars to the step 6 deploy command**

Change the `--set-secrets` and `--set-env-vars` flags in the `gcloud run
deploy` command (line 222) from:

```powershell
gcloud run deploy $SERVICE --source . --region $REGION --allow-unauthenticated --service-account "portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --set-secrets="DATABASE_URL=portfyl-database-url:latest,JOB_DATABASE_URL=portfyl-job-database-url:latest" --set-env-vars="PORTFYL_EDITION=cloud,PORTFYL_KMS_KEY_NAME=$KMS_KEY" --min-instances=0 --max-instances=5 --cpu=1 --memory=1Gi
```

to:

```powershell
gcloud run deploy $SERVICE --source . --region $REGION --allow-unauthenticated --service-account "portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --set-secrets="DATABASE_URL=portfyl-database-url:latest,JOB_DATABASE_URL=portfyl-job-database-url:latest,PORTFYL_EDGE_TOKEN=portfyl-edge-token:latest,RATE_LIMIT_KEY_SECRET=portfyl-rate-limit-key-secret:latest" --set-env-vars="PORTFYL_EDITION=cloud,PORTFYL_KMS_KEY_NAME=$KMS_KEY,RATE_LIMIT_GLOBAL_LIMIT=120,RATE_LIMIT_GLOBAL_WINDOW_SECONDS=60,RATE_LIMIT_AUTH_SESSION_LIMIT=10,RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS=60,RATE_LIMIT_BROKER_SYNC_LIMIT=5,RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS=60,RATE_LIMIT_ASSISTANT_CHAT_LIMIT=20,RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS=60" --min-instances=0 --max-instances=5 --cpu=1 --memory=1Gi
```

Add a note right after the command's existing "Why these flags" bullet list
(after line 235):

```markdown
- The eight `RATE_LIMIT_*` values are the spec's defaults, not
  evidence-based constants — the spec's own rollout gate requires a
  production-shaped load test before enforcement is trusted; raise any of
  them here (redeploy with `--update-env-vars`) if that load test or real
  traffic shows normal usage would otherwise trip a rule.
```

- [ ] **Step 4: Add the fourth Cloud Scheduler job to section 9**

Insert after the existing `portfyl-dividends` job creation command (after
line 331), before the `Verify:` paragraph:

```powershell
gcloud scheduler jobs create http portfyl-rate-limit-cleanup --location=$REGION --schedule="0 * * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/rate_limit_cleanup" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s
```

Extend the `Verify:` paragraph (lines 334-342) — after its existing overlap-
drill sentence, add:

```markdown
For `portfyl-rate-limit-cleanup`, `gcloud scheduler jobs run
portfyl-rate-limit-cleanup --location=$REGION` should log a
`rate_limit_cleanup pass: 1 event(s)` line (or nothing, if nothing was
expired) tagged with a `job-rate_limit_cleanup-…` correlation id, and the
same overlap drill must produce
`{"job":"rate_limit_cleanup","skipped":"already running"}`.
```

- [ ] **Step 4a: Extend section 7's verification with the deployment-acceptance checks**

Insert after the existing `## 7. Verify` section's paragraph (after
"...that means step 5 didn't run against the same database this service is
now pointed at."):

```markdown
**Rate limiting deployment acceptance** (per the rate limiting spec):
- A direct request to the printed Cloud Run URL (bypassing Cloudflare) to
  any `/api/*` path must get 403 `untrusted_edge`, even when the request
  forges `CF-Connecting-IP` and/or `X-Forwarded-For` headers — the origin
  must never be reachable without Cloudflare's injected
  `X-Portfyl-Edge-Token`.
- The same request through the normal Cloudflare hostname (portfyl.com)
  must reach the API, and two requests with distinct real client IPs must
  not share a bucket (confirm via two different networks, or Cloudflare's
  own IP for a WARP/VPN client vs. a plain connection).
- After running `portfyl-rate-limit-cleanup` at least once (see section 9),
  `/health`'s `checks.scheduler.jobs.rate_limit_cleanup` must read `"ok"`
  with a recent `last_success_at`; leaving it un-run for over two hours
  must flip it to `"stale"` and `checks.scheduler.status` to `"degraded"`.
- Before flipping enforcement on for real traffic, run the spec's
  production-shaped load test (20 concurrent distinct-IP clients, a
  30-request burst behind one shared IP, concurrent requests against one
  workspace) and confirm every numeric gate in the spec's "Observability
  and rollout" section — this is an operational validation step, not
  something any automated test in this repo can substitute for.
```

- [ ] **Step 5: Self-check against the spec**

Re-read `docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md`'s
"Configuration" and "Cleanup and operational integration" sections against
the diff. Confirm: both secrets are created and IAM-bound, all eight rule
env vars are on the deploy command, the Cloudflare header-injection
requirement is documented, and the fourth Scheduler job matches the other
three's exact flag style.

- [ ] **Step 6: Commit**

```bash
git add deploy/cloudrun.md
git commit -m "docs: add rate limiting secrets, env vars, and the cleanup scheduler job"
```

---

## Task 14: PostgreSQL suite — concurrency, lock release, migration reversibility

**Files:**
- Create: `backend/tests/postgres/test_rate_limit_postgres.py`
- Modify: `backend/tests/postgres/test_runtime_role.py`

**Interfaces:**
- Consumes: `rate_limit.consume_rate_limit`, `rate_limit.RateLimitRule`
  (Task 3); `postgres_engine`, `postgres_url`, `runtime_session` fixtures
  (`tests/postgres/conftest.py`).
- Produces: three new Postgres-only tests proving what SQLite structurally
  cannot: real concurrent commits, real row-lock release, and a clean
  migration round-trip; plus one grants test extending the existing
  `portfyl_runtime` privilege-invariant suite.

- [ ] **Step 1: Write the concurrency, lock-release, and migration tests**

Create `backend/tests/postgres/test_rate_limit_postgres.py`:

```python
"""consume_rate_limit's upsert and transaction-boundary guarantees need
real concurrent Postgres commits and real row locks -- postgres_session's
shared, rolled-back transaction can't represent either, so this opens
independent connections the same way test_job_advisory_lock.py does, and
runs its own isolated migration round-trip for 0012."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import rate_limit
from rate_limit import RateLimitRule, consume_rate_limit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _independent_session(engine: Engine):
    connection = engine.connect()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        connection.close()


def test_concurrent_increments_produce_the_exact_final_count(postgres_engine: Engine, monkeypatch):
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    concurrency_engine = create_engine(str(postgres_engine.url), pool_size=20, max_overflow=0)
    monkeypatch.setattr(
        rate_limit, "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=concurrency_engine),
    )
    rule = RateLimitRule(name="test_concurrency", limit=1000, window_seconds=3600)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    errors: list[Exception] = []

    def _worker():
        try:
            consume_rate_limit(rule=rule, identity="shared-bucket", now=now)
        except Exception as exc:  # RateLimitExceeded would also be a bug here (limit=1000, 20 workers)
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    key = rate_limit._bucket_key(
        rule_name=rule.name, identity="shared-bucket",
        window_index=int(now.timestamp() // rule.window_seconds),
    )
    with concurrency_engine.connect() as conn:
        count = conn.execute(text("SELECT count FROM rate_limit_buckets WHERE key = :key"), {"key": key}).scalar_one()
    assert count == 20
    concurrency_engine.dispose()


def test_limiter_transaction_releases_the_row_lock_before_returning(postgres_engine: Engine, monkeypatch):
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(
        rate_limit, "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=postgres_engine),
    )
    rule = RateLimitRule(name="test_lock_release", limit=100, window_seconds=3600)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    consume_rate_limit(rule=rule, identity="lock-test", now=now)  # commits and closes internally

    key = rate_limit._bucket_key(
        rule_name=rule.name, identity="lock-test",
        window_index=int(now.timestamp() // rule.window_seconds),
    )
    with _independent_session(postgres_engine) as second:
        # FOR UPDATE NOWAIT raises immediately instead of blocking if any
        # other session still holds the row lock -- proving the limiter's
        # own transaction already committed and released it.
        second.execute(text("SELECT 1 FROM rate_limit_buckets WHERE key = :key FOR UPDATE NOWAIT"), {"key": key})
        second.rollback()


def test_0012_migration_upgrades_and_downgrades_cleanly(postgres_engine: Engine, postgres_url: str):
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.downgrade(alembic_config, "0011_remove_payment_runtime")
        with postgres_engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public.rate_limit_buckets')")).scalar() is None

        command.upgrade(alembic_config, "0012_rate_limit_buckets")
        with postgres_engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public.rate_limit_buckets')")).scalar() == "rate_limit_buckets"
            grants = conn.execute(text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'portfyl_runtime' AND table_name = 'rate_limit_buckets' "
                "ORDER BY privilege_type"
            )).scalars().all()
            assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]
            indexes = conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'rate_limit_buckets'"
            )).scalars().all()
            assert "ix_rate_limit_buckets_expires_at" in indexes
```

Also extend `backend/tests/postgres/test_runtime_role.py` — append this
test after `test_runtime_role_can_read_head_but_cannot_mutate_migration_tables`:

```python
def test_runtime_role_has_exact_grants_on_rate_limit_buckets(runtime_session: Session):
    grants = runtime_session.execute(
        text(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'portfyl_runtime'
              AND table_schema = 'public'
              AND table_name = 'rate_limit_buckets'
            ORDER BY privilege_type
            """
        )
    ).scalars().all()
    assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Prerequisite: `docker compose -f deploy/docker-compose.postgres-test.yml up
-d --wait` (or an explicit `TEST_DATABASE_URL` containing `test`).

Run: `cd backend && python -m pytest tests/postgres/test_rate_limit_postgres.py tests/postgres/test_runtime_role.py -k rate_limit -v`
Expected: fails before Tasks 1-3 exist in this branch's working tree — if
you're executing this plan in order, Tasks 1-3 are already done, so this
step instead confirms the tests fail for the RIGHT reason if you introduce
a deliberate bug (e.g. comment out the `session.commit()` in
`consume_rate_limit` and confirm `test_limiter_transaction_releases_the_row_lock_before_returning`
fails) — then restore it before continuing.

- [ ] **Step 3: Run the tests for real against Task 1-3's implementation**

Run: `cd backend && python -m pytest tests/postgres/test_rate_limit_postgres.py tests/postgres/test_runtime_role.py -k rate_limit -v`
Expected: all pass.

- [ ] **Step 4: Run the full PostgreSQL suite**

Run: `cd backend && python -m pytest tests/postgres/ -v`
Expected: all pass, including
`tests/postgres/test_rls.py::test_all_tenant_tables_enable_and_force_rls`
(must NOT include `rate_limit_buckets` — it was never added to
`RLS_TABLES`) and the full Alice/Bob matrix (unaffected by this feature).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/postgres/test_rate_limit_postgres.py backend/tests/postgres/test_runtime_role.py
git commit -m "test: prove rate limiter concurrency, lock release, and migration reversibility"
```

---

## Final self-review checklist (run once, after Task 14)

- [ ] `cd backend && python -m pytest tests/ --ignore=tests/postgres -v` is
  fully green.
- [ ] `cd backend && python -m pytest tests/postgres/ -v` is fully green
  (disposable PostgreSQL running).
- [ ] `cd backend && alembic upgrade head` succeeds against a real local
  PostgreSQL, and `alembic downgrade -1` then `alembic upgrade head` again
  also succeeds.
- [ ] Grep the diff for the string `"rate_limit"` in `backend/main.py` and
  confirm the gate's `add_middleware` call is textually **before**
  `app.add_middleware(CORSMiddleware`.
- [ ] Grep every new/modified file for `print(` / raw `logging.info` calls
  containing an IP, workspace id, bucket key, edge token, or key secret —
  there must be none (only rule names and exception type names are logged).
- [ ] Confirm `local_features.py`, `App.jsx`, `Sidebar.jsx`, and `api.js`
  were **not** touched by this plan (out of scope; this is a backend-only
  feature).
