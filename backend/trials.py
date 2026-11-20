"""The free Pro trial: grant, abuse guards, lookup and purge.

Every new cloud workspace gets `PORTFYL_TRIAL_DAYS` days (default 10) of Pro
without a card, unless a guard says no. Nothing else in the codebase knows the
`trial_*` tables; `entitlements.resolve_entitlements` calls `trial_state`.

Abuse guards, in the order `trial_block_reason` applies them:

* the e-mail domain is on the disposable-domain list (`disposable_domain`);
* the canonical e-mail already had a trial, ever (`email_reused`);
* 3 trials were already granted from the same client IP in 30 days
  (`ip_limit`).

`record_broker_marks` is the decisive broker check: the broker account is
unknown at registration, so it runs at every import commit and broker sync
of a workspace whose trial is active.

A failing guard never blocks the account: the workspace simply starts on Free,
a `trial.withheld` audit event records the reason, and the workspace setting
`trial_withheld` = "1" makes `trial_state` report `"not_eligible"` so the app
can say a trial was already used (never which guard fired). Only HMAC fingerprints
are stored or logged, never the raw e-mail or IP address.

All functions are plain synchronous code (no `async def`): they run in the
request threadpool like the rest of the database layer.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app_settings import get_workspace_setting, set_workspace_setting
from audit import record_audit_event
from models import Membership, TrialBrokerMark, TrialGrant, TrialIdentity, TrialIpMark

logger = logging.getLogger(__name__)


TRIAL_DAYS_ENV = "PORTFYL_TRIAL_DAYS"
FINGERPRINT_KEY_ENV = "PORTFYL_TRIAL_FINGERPRINT_KEY"
DEFAULT_TRIAL_DAYS = 10
MIN_KEY_LENGTH = 32

IDENTITY_RETENTION = timedelta(days=365)
BROKER_MARK_RETENTION = timedelta(days=365)
IP_WINDOW = timedelta(days=30)
IP_TRIAL_LIMIT = 3  # the 4th trial from one IP within IP_WINDOW is withheld

EMAIL_REUSED = "email_reused"
DISPOSABLE_DOMAIN = "disposable_domain"
IP_LIMIT = "ip_limit"
EXPIRED = "expired"
BROKER_ACCOUNT_REUSED = "broker_account_reused"
HISTORY_REUSED = "history_reused"
NOT_ELIGIBLE = "not_eligible"
TRIAL_WITHHELD_SETTING = "trial_withheld"

HISTORY_SAMPLE = 5  # the oldest ledger rows whose event ids are fingerprinted
HISTORY_MATCHES_TO_END = 3  # of HISTORY_SAMPLE, so 2 coincidences end nothing
_ACCOUNT_KIND = "account"
_HISTORY_KIND = "history"
# Rows the product itself created; they say nothing about a real broker.
_NON_BROKER_SOURCES = frozenset({"demo"})

_DISPOSABLE_FILE = Path(__file__).resolve().parent / "data" / "disposable_domains.txt"
_FINGERPRINT_VERSION = "1"


# --- configuration ---------------------------------------------------------


def trial_days(env: Mapping[str, str]) -> int:
    """Trial length in days; 0 switches the trial off."""
    raw = env.get(TRIAL_DAYS_ENV, "").strip()
    if not raw:
        return DEFAULT_TRIAL_DAYS
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{TRIAL_DAYS_ENV} must be a non-negative integer") from exc
    if value < 0:
        raise RuntimeError(f"{TRIAL_DAYS_ENV} must be a non-negative integer")
    return value


def _key(env: Mapping[str, str]) -> bytes:
    secret = env.get(FINGERPRINT_KEY_ENV, "").strip()
    if len(secret) < MIN_KEY_LENGTH:
        raise RuntimeError(
            f"{FINGERPRINT_KEY_ENV} must contain at least {MIN_KEY_LENGTH} characters"
        )
    return secret.encode("utf-8")


def _encode_field(value: str) -> bytes:
    data = value.encode("utf-8")
    return len(data).to_bytes(4, "big") + data


def _hmac(purpose: str, value: str, env: Mapping[str, str]) -> str:
    # The purpose is part of the message so the e-mail, IP and broker
    # fingerprints made with one key can never be compared with each other.
    message = b"".join(_encode_field(f) for f in (_FINGERPRINT_VERSION, purpose, value))
    return hmac.new(_key(env), message, hashlib.sha256).hexdigest()


# --- e-mail and IP normalisation --------------------------------------------


def canonical_email(email: str) -> str:
    """The form used only for the trial fingerprint (login, `beta_access` and
    the stored e-mail keep the address exactly as typed): lower-cased, no
    `+tag`, `googlemail.com` folded into `gmail.com`, and no dots in a Gmail
    local part."""
    value = email.strip().lower()
    local, separator, domain = value.rpartition("@")
    if not separator:
        return value
    local = local.split("+", 1)[0]
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain == "gmail.com":
        local = local.replace(".", "")
    return f"{local}@{domain}"


def identity_fingerprint(email: str, env: Mapping[str, str]) -> str:
    """Hex HMAC-SHA256 of the canonical e-mail. Raises `RuntimeError` when the
    key is missing or too short (fail closed; `grant_trial` only gets here
    while trials are on)."""
    return _hmac("email", canonical_email(email), env)


def _ip_fingerprint(client_ip: str, env: Mapping[str, str]) -> str | None:
    """HMAC of the client IP, or None for an unparseable address. IPv6 is
    reduced to its /64, because one subscriber owns the whole prefix and could
    otherwise rotate addresses freely."""
    try:
        address = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        else:
            address = ipaddress.ip_network(f"{address}/64", strict=False).network_address
    return _hmac("ip", str(address), env)


@lru_cache(maxsize=1)
def _disposable_domains() -> frozenset[str]:
    domains = set()
    for line in _DISPOSABLE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            domains.add(line)
    return frozenset(domains)


def is_disposable_domain(email: str) -> bool:
    """Exact-domain match (no subdomains, no substrings) against the list."""
    _local, separator, domain = email.strip().lower().rpartition("@")
    return bool(separator) and domain in _disposable_domains()


# --- time helpers ------------------------------------------------------------


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# --- guards and grant --------------------------------------------------------


def _identity_exists(db: Session, fingerprint: str) -> bool:
    return db.get(TrialIdentity, fingerprint) is not None


def _ip_trials_in_window(db: Session, ip_fingerprint: str, now: datetime) -> int:
    return db.scalar(
        select(func.count()).select_from(TrialIpMark).where(
            TrialIpMark.ip_fingerprint == ip_fingerprint,
            TrialIpMark.granted_at > now - IP_WINDOW,
        )
    ) or 0


def trial_block_reason(
    db: Session,
    *,
    email: str,
    client_ip: str | None,
    now: datetime,
    env: Mapping[str, str],
) -> str | None:
    """`"disposable_domain"`, `"email_reused"`, `"ip_limit"` or `None`.

    A missing `client_ip` skips only the IP guard. Read-only: nothing is
    recorded here."""
    if is_disposable_domain(email):
        return DISPOSABLE_DOMAIN
    if _identity_exists(db, identity_fingerprint(email, env)):
        return EMAIL_REUSED
    if client_ip is not None:
        fingerprint = _ip_fingerprint(client_ip, env)
        if fingerprint is not None and _ip_trials_in_window(db, fingerprint, now) >= IP_TRIAL_LIMIT:
            return IP_LIMIT
    return None


def _insert_identity(db: Session, fingerprint: str, now: datetime) -> bool:
    """Record the mailbox as used; False when it already was (also under a race)."""
    if db.get_bind().dialect.name == "postgresql":
        inserted = db.execute(
            postgresql_insert(TrialIdentity)
            .values(fingerprint=fingerprint, granted_at=now)
            .on_conflict_do_nothing(index_elements=[TrialIdentity.fingerprint])
            .returning(TrialIdentity.fingerprint)
        ).scalar_one_or_none()
        return inserted is not None
    if _identity_exists(db, fingerprint):
        return False
    db.add(TrialIdentity(fingerprint=fingerprint, granted_at=now))
    db.flush()
    return True


def _record_withheld(
    db: Session, *, workspace_id: UUID, actor_user_id: UUID | None, reason: str
) -> None:
    # The marker lets the UI tell "trial withheld" from "trials are off"; it
    # carries no reason, so nothing reveals which guard fired.
    set_workspace_setting(db, workspace_id, TRIAL_WITHHELD_SETTING, "1")
    if actor_user_id is None:
        return
    record_audit_event(
        db,
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        action="trial.withheld",
        target_type="workspace",
        target_id=str(workspace_id),
        metadata={"reason": reason},
    )


def grant_trial(
    db: Session,
    *,
    workspace_id: UUID,
    email: str,
    now: datetime,
    env: Mapping[str, str] | None = None,
    client_ip: str | None = None,
    actor_user_id: UUID | None = None,
) -> TrialGrant | None:
    """Start the trial of a new workspace, or return None.

    None when trials are off, a guard fails, or the mailbox already has a
    trial. When a guard fails and `actor_user_id` is given, a `trial.withheld`
    audit event (reason only, no e-mail or IP) is staged. The caller owns the
    transaction. Raises `RuntimeError` when trials are on and
    `PORTFYL_TRIAL_FINGERPRINT_KEY` is missing or too short."""
    env = os.environ if env is None else env
    days = trial_days(env)
    if days <= 0:
        return None

    reason = trial_block_reason(db, email=email, client_ip=client_ip, now=now, env=env)
    if reason is None and not _insert_identity(db, identity_fingerprint(email, env), now):
        reason = EMAIL_REUSED  # lost a race with a concurrent registration
    if reason is not None:
        _record_withheld(db, workspace_id=workspace_id, actor_user_id=actor_user_id, reason=reason)
        return None

    if client_ip is not None:
        fingerprint = _ip_fingerprint(client_ip, env)
        if fingerprint is not None:
            db.add(TrialIpMark(id=uuid4(), ip_fingerprint=fingerprint, granted_at=now))
    grant = TrialGrant(
        workspace_id=workspace_id,
        started_at=now,
        ends_at=now + timedelta(days=days),
    )
    db.add(grant)
    db.flush()
    return grant


# --- lookup ------------------------------------------------------------------


def _grant_for(db: Session, workspace_id: UUID) -> TrialGrant | None:
    return db.scalar(select(TrialGrant).where(TrialGrant.workspace_id == workspace_id))


def _is_active(grant: TrialGrant, now: datetime) -> bool:
    return grant.ended_reason is None and _utc(grant.ends_at) > _utc(now)


def active_trial(db: Session, workspace_id: UUID, now: datetime) -> TrialGrant | None:
    grant = _grant_for(db, workspace_id)
    return grant if grant is not None and _is_active(grant, now) else None


def trial_state(
    db: Session, workspace_id: UUID, now: datetime
) -> tuple[TrialGrant | None, str | None]:
    """`(active grant, ended reason)` from one query. The reason is None while
    a trial runs or none existed; otherwise the stored `ended_reason` when the
    trial was cut short, else `"expired"`. A workspace without any grant whose
    trial was withheld at registration reports `"not_eligible"`."""
    grant = _grant_for(db, workspace_id)
    if grant is None:
        if get_workspace_setting(db, workspace_id, TRIAL_WITHHELD_SETTING) == "1":
            return None, NOT_ELIGIBLE
        return None, None
    if _is_active(grant, now):
        return grant, None
    return None, grant.ended_reason or EXPIRED


# --- purge -------------------------------------------------------------------


def purge_old_identities(db: Session, now: datetime) -> int:
    """Delete `trial_identities` rows granted more than 365 days ago."""
    result = db.execute(
        delete(TrialIdentity).where(TrialIdentity.granted_at < now - IDENTITY_RETENTION)
    )
    return result.rowcount or 0


def purge_trial_records(db: Session, now: datetime) -> dict[str, int]:
    """All time-limited trial guard rows: identities and broker marks after 12
    months, IP marks after 30 days. The caller commits."""
    identities = purge_old_identities(db, now)
    ip_marks = db.execute(
        delete(TrialIpMark).where(TrialIpMark.granted_at < now - IP_WINDOW)
    ).rowcount or 0
    broker_marks = db.execute(
        delete(TrialBrokerMark).where(
            TrialBrokerMark.first_seen_at < now - BROKER_MARK_RETENTION
        )
    ).rowcount or 0
    return {"identities": identities, "ip_marks": ip_marks, "broker_marks": broker_marks}


# --- broker check ------------------------------------------------------------


def _history_fingerprint(key: tuple[str, str, str], env: Mapping[str, str]) -> str:
    # Length-prefixed fields, like `_hmac`, but one field per key part so no
    # separator can make two different keys collide.
    message = b"".join(
        _encode_field(f) for f in (_FINGERPRINT_VERSION, "broker_history", *key)
    )
    return hmac.new(_key(env), message, hashlib.sha256).hexdigest()


def oldest_history_keys(
    rows: Iterable[object], limit: int = HISTORY_SAMPLE
) -> list[tuple[str, str, str]]:
    """The `limit` oldest distinct `(source, source_event_stream,
    source_event_id)` keys of `rows` (dicts or `Transaction`s), oldest first.

    Rows without a full event identity (the native CSV, `sample_portfolio.csv`)
    and rows the product created itself (the onboarding demo) are never
    included. Sorting is by `(date, stream, id)` in Python, so a file import
    and a later read of the stored rows pick the same keys."""

    def field(row: object, name: str):
        return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)

    found: dict[tuple[str, str, str], object] = {}
    for row in rows:
        source = field(row, "source")
        stream = field(row, "source_event_stream")
        event_id = field(row, "source_event_id")
        if not source or not stream or not event_id or source in _NON_BROKER_SOURCES:
            continue
        found.setdefault((str(source), str(stream), str(event_id)), field(row, "date"))
    ordered = sorted(found, key=lambda k: (str(found[k] or ""), k[1], k[2]))
    return ordered[:limit]


def _foreign_marks(
    db: Session, fingerprints: Sequence[str], workspace_id: UUID, kind: str
) -> int:
    """How many of `fingerprints` already belong to a different workspace or
    to a deleted one (`workspace_id` NULL)."""
    if not fingerprints:
        return 0
    return db.scalar(
        select(func.count()).select_from(TrialBrokerMark).where(
            TrialBrokerMark.fingerprint.in_(list(fingerprints)),
            TrialBrokerMark.kind == kind,
            (TrialBrokerMark.workspace_id.is_(None))
            | (TrialBrokerMark.workspace_id != workspace_id),
        )
    ) or 0


def _insert_marks(
    db: Session, fingerprints: Iterable[str], kind: str, workspace_id: UUID, now: datetime
) -> None:
    """Remember fingerprints for this workspace; an existing mark (of any
    workspace) is left as it is, also under a race."""
    unique = list(dict.fromkeys(fingerprints))
    if not unique:
        return
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            postgresql_insert(TrialBrokerMark)
            .values([
                {"fingerprint": f, "kind": kind, "workspace_id": workspace_id, "first_seen_at": now}
                for f in unique
            ])
            .on_conflict_do_nothing(index_elements=[TrialBrokerMark.fingerprint])
        )
        return
    known = set(db.scalars(
        select(TrialBrokerMark.fingerprint).where(TrialBrokerMark.fingerprint.in_(unique))
    ))
    for fingerprint in unique:
        if fingerprint not in known:
            db.add(TrialBrokerMark(
                fingerprint=fingerprint, kind=kind, workspace_id=workspace_id, first_seen_at=now
            ))
    db.flush()


def _audit_actor(db: Session, workspace_id: UUID, actor_user_id: UUID | None) -> UUID | None:
    """The user an audit event is attributed to: the caller when known (an
    import), else the workspace owner (a background sync)."""
    if actor_user_id is not None:
        return actor_user_id
    return db.scalar(
        select(Membership.user_id)
        .where(Membership.workspace_id == workspace_id, Membership.status == "active")
        .order_by(Membership.created_at, Membership.id)
        .limit(1)
    )


def record_broker_marks(
    db: Session,
    *,
    workspace_id: UUID,
    account_fingerprints: Sequence[str],
    oldest_event_keys: Sequence[tuple[str, str, str]],
    now: datetime,
    env: Mapping[str, str] | None = None,
    actor_user_id: UUID | None = None,
) -> str | None:
    """The broker check ("Trial rules" item 11).

    Does nothing (returns None) when the workspace has no active trial. Else it
    ends the trial now when a known account-number fingerprint, or at least 3
    of the 5 oldest-row fingerprints, already belong to a different or deleted
    workspace, and returns `"broker_account_reused"` or `"history_reused"`.
    Either way the fingerprints are remembered for this workspace, so a later
    trial can be compared against them. The caller's import always completes:
    only the plan changes. `account_fingerprints` come ready-made from
    `account_identity.account_fingerprint`; raw account ids and API keys never
    reach this module. Raises `RuntimeError` when history keys are given and
    `PORTFYL_TRIAL_FINGERPRINT_KEY` is missing. The caller owns the
    transaction."""
    env = os.environ if env is None else env
    grant = active_trial(db, workspace_id, now)
    if grant is None:
        return None

    accounts = list(dict.fromkeys(account_fingerprints))
    history = list(dict.fromkeys(
        _history_fingerprint(k, env) for k in list(oldest_event_keys)[:HISTORY_SAMPLE]
    ))

    reason = None
    if _foreign_marks(db, accounts, workspace_id, _ACCOUNT_KIND):
        reason = BROKER_ACCOUNT_REUSED
    elif _foreign_marks(db, history, workspace_id, _HISTORY_KIND) >= HISTORY_MATCHES_TO_END:
        reason = HISTORY_REUSED

    _insert_marks(db, accounts, _ACCOUNT_KIND, workspace_id, now)
    _insert_marks(db, history, _HISTORY_KIND, workspace_id, now)
    if reason is None:
        return None

    grant.ended_reason = reason
    # ck_trial_period_order needs ends_at > started_at, also when the trial
    # started in this very instant.
    grant.ends_at = max(_utc(now), _utc(grant.started_at) + timedelta(microseconds=1))
    db.flush()
    actor = _audit_actor(db, workspace_id, actor_user_id)
    if actor is not None:
        record_audit_event(
            db,
            actor_user_id=actor,
            workspace_id=workspace_id,
            action="trial.ended_early",
            target_type="workspace",
            target_id=str(workspace_id),
            metadata={"reason": reason},
        )
    return reason


def _is_real_account_id(broker: str, account_id: object) -> bool:
    """False for ids that cannot identify a live account: empty or masked ids
    (a mask would match strangers), and IBKR paper accounts, which anyone can
    open without limit (their ids start with `D`: DU, DF, DI)."""
    value = str(account_id or "").strip()
    if not value or "*" in value:
        return False
    return not (broker.strip().lower() == "ibkr" and value.upper().startswith("D"))


def check_broker(
    db: Session,
    *,
    workspace_id: UUID,
    broker: str,
    environment: str = "live",
    account_ids: Iterable[object] = (),
    account_fingerprints: Iterable[str] = (),
    history_rows: Iterable[object] | Callable[[], Iterable[object]] = (),
    now: datetime | None = None,
    actor_user_id: UUID | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Best-effort wrapper the import and sync call sites use.

    Cheap when the workspace has no active trial (nothing is computed). It
    derives account fingerprints with `account_identity.account_fingerprint`
    (a Trading 212 `demo` environment and IBKR paper or masked ids are
    skipped), uses the 5 oldest ledger rows only when no account number is
    available (`history_rows` may be a callable, evaluated only then), and
    runs inside a SAVEPOINT: any failure is logged and swallowed, because a
    broken check must never fail the import. Returns the `ended_reason` when
    it ended the trial."""
    from account_identity import account_fingerprint

    now = now or datetime.now(timezone.utc)
    demo = environment.strip().lower() == "demo"
    try:
        if active_trial(db, workspace_id, now) is None:
            return None
        with db.begin_nested():
            fingerprints = [] if demo else list(account_fingerprints)
            if not demo:
                for account_id in account_ids:
                    if _is_real_account_id(broker, account_id):
                        fingerprints.append(account_fingerprint(
                            broker=broker, environment=environment,
                            provider_account_id=account_id, env=env,
                        ))
            keys: list[tuple[str, str, str]] = []
            if not demo and not fingerprints:
                # A callable defers the query until a trial is known to be active.
                rows = history_rows() if callable(history_rows) else history_rows
                keys = oldest_history_keys(rows)
            return record_broker_marks(
                db,
                workspace_id=workspace_id,
                account_fingerprints=fingerprints,
                oldest_event_keys=keys,
                now=now,
                env=env,
                actor_user_id=actor_user_id,
            )
    except Exception:
        logger.warning("Trial broker check failed; the import is unaffected", exc_info=True)
        return None
