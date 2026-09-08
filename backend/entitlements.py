"""Server-side edition, plan, resource-limit, and usage enforcement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
import uuid
from sqlalchemy.orm import Session

from app_settings import get_workspace_setting
from plans import MINIMUM_PLAN, PlanLimits, PlanTier, plan_allows, plan_limits
from database import get_db
from edition import CAPABILITY_REGISTRY, CapabilityClass, Edition, edition_allows
from models import UsageCounter, UsageReservation
from tenancy import RequestContext, get_request_context


PRIVATE_TEST_PLAN_SETTING_KEY = "private_test_plan"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EffectiveEntitlements:
    plan: PlanTier
    source: str
    effective_until: datetime | None
    in_grace: bool
    cancel_at_period_end: bool
    capabilities: tuple[str, ...]
    limits: PlanLimits

    def payload(self) -> dict[str, object]:
        return {
            "plan": self.plan.value,
            "source": self.source,
            "effective_until": self.effective_until.isoformat() if self.effective_until else None,
            "in_grace": self.in_grace,
            "cancel_at_period_end": self.cancel_at_period_end,
            "capabilities": list(self.capabilities),
            "limits": asdict(self.limits),
        }


class EntitlementDenied(Exception):
    def __init__(
        self,
        code: str,
        *,
        capability: str | None = None,
        plan: PlanTier | None = None,
        required_plan: PlanTier | None = None,
        resource: str | None = None,
        limit: int | None = None,
        used: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.capability = capability
        self.plan = plan
        self.required_plan = required_plan
        self.resource = resource
        self.limit = limit
        self.used = used

    def payload(self) -> dict[str, object]:
        result: dict[str, object] = {"code": self.code}
        for key, value in (
            ("capability", self.capability),
            ("plan", self.plan.value if self.plan else None),
            ("required_plan", self.required_plan.value if self.required_plan else None),
            ("resource", self.resource),
            ("limit", self.limit),
            ("used", self.used),
        ):
            if value is not None:
                result[key] = value
        return result


def entitlement_denied_handler(_request: Request, exc: EntitlementDenied) -> JSONResponse:
    return JSONResponse(exc.payload(), status_code=403)


def _local_entitlements() -> EffectiveEntitlements:
    return EffectiveEntitlements(
        plan=PlanTier.PRO,
        source="local",
        effective_until=None,
        in_grace=False,
        cancel_at_period_end=False,
        capabilities=tuple(CAPABILITY_REGISTRY),
        limits=PlanLimits(*(None for _ in range(7)), hosted_ai_monthly=0, autosync_min_hours=None),
    )


def resolve_entitlements(
    db: Session,
    *,
    edition: Edition,
    workspace_id: UUID,
    now: datetime | None = None,
    env: dict[str, str] | None = None,
) -> EffectiveEntitlements:
    if edition is Edition.LOCAL:
        return _local_entitlements()

    raw_tier = get_workspace_setting(db, workspace_id, PRIVATE_TEST_PLAN_SETTING_KEY)
    try:
        tier = PlanTier(raw_tier) if raw_tier else PlanTier.FREE
    except ValueError:
        # Fail closed if a stale or manually edited setting contains an
        # unsupported value.
        tier = PlanTier.FREE
    capabilities = tuple(
        key for key in CAPABILITY_REGISTRY
        if edition_allows(edition, key) and key in MINIMUM_PLAN and plan_allows(tier, key)
    )
    return EffectiveEntitlements(
        plan=tier,
        source="test_selection" if raw_tier == tier.value else "free",
        effective_until=None,
        in_grace=False,
        cancel_at_period_end=False,
        capabilities=capabilities,
        limits=plan_limits(env)[tier],
    )


def ensure_capability(
    entitlements: EffectiveEntitlements,
    capability: str,
    *,
    edition: Edition,
) -> None:
    if not edition_allows(edition, capability):
        raise EntitlementDenied("edition_unavailable", capability=capability)
    if capability not in entitlements.capabilities:
        required = MINIMUM_PLAN.get(capability)
        raise EntitlementDenied(
            "plan_upgrade_required",
            capability=capability,
            plan=entitlements.plan,
            required_plan=required,
        )


def ensure_count_limit(
    entitlements: EffectiveEntitlements,
    resource: str,
    *,
    used: int,
    increase: int = 1,
) -> None:
    if not hasattr(entitlements.limits, resource):
        raise KeyError(f"Unknown resource limit: {resource}")
    limit = getattr(entitlements.limits, resource)
    if limit is not None and used + increase > limit:
        raise EntitlementDenied(
            "quota_exceeded",
            plan=entitlements.plan,
            resource=resource,
            limit=limit,
            used=used,
        )


def ensure_final_count_limit(
    entitlements: EffectiveEntitlements,
    resource: str,
    *,
    current: int,
    final: int,
) -> None:
    """Allow reductions while rejecting any over-limit increase.

    This is used for derived aggregates such as active positions, where a sell
    can reduce usage without immediately bringing an already-downgraded
    workspace below its new limit.
    """
    if not hasattr(entitlements.limits, resource):
        raise KeyError(f"Unknown resource limit: {resource}")
    limit = getattr(entitlements.limits, resource)
    if limit is not None and final > limit and final > current:
        raise EntitlementDenied(
            "quota_exceeded",
            plan=entitlements.plan,
            resource=resource,
            limit=limit,
            used=current,
        )


def require_capability(capability: str) -> Callable:
    async def dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> EffectiveEntitlements:
        edition = request.app.state.portfyl_edition
        entitlements = resolve_entitlements(
            db, edition=edition, workspace_id=context.workspace.id
        )
        ensure_capability(entitlements, capability, edition=edition)
        return entitlements

    return dependency


def require_capacity(resource: str, model, *, increase: int = 1) -> Callable:
    """FastAPI dependency for workspace-wide create limits."""
    async def dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> EffectiveEntitlements:
        from models import Workspace

        edition = request.app.state.portfyl_edition
        entitlements = resolve_entitlements(db, edition=edition, workspace_id=context.workspace.id)
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                select(Workspace.id)
                .where(Workspace.id == context.workspace.id)
                .with_for_update()
            )
        used = db.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == context.workspace.id)
        ) or 0
        ensure_count_limit(entitlements, resource, used=used, increase=increase)
        return entitlements
    return dependency


def require_writable_resource(resource: str, model, path_parameter: str) -> Callable:
    """Reject updates to deterministic overflow rows while leaving DELETE free."""
    async def dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> None:
        edition = request.app.state.portfyl_edition
        entitlements = resolve_entitlements(db, edition=edition, workspace_id=context.workspace.id)
        limit = getattr(entitlements.limits, resource)
        if limit is None:
            return
        raw_id = request.path_params.get(path_parameter)
        rows = db.scalars(
            select(model)
            .where(model.workspace_id == context.workspace.id)
            .order_by(model.created_at, model.id)
        ).all()
        for index, row in enumerate(rows):
            if str(row.public_id) == str(raw_id):
                if index >= limit:
                    raise EntitlementDenied(
                        "resource_read_only",
                        plan=entitlements.plan,
                        resource=resource,
                        limit=limit,
                        used=len(rows),
                    )
                return
    return dependency


def require_broker_capacity(broker: str) -> Callable:
    """Count broker connections, while permitting credential rotation in place."""
    async def dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> EffectiveEntitlements:
        from models import BrokerConnection, Portfolio
        from models import Workspace

        edition = request.app.state.portfyl_edition
        entitlements = resolve_entitlements(db, edition=edition, workspace_id=context.workspace.id)
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                select(Workspace.id)
                .where(Workspace.id == context.workspace.id)
                .with_for_update()
            )
        raw_portfolio_id = request.query_params.get("portfolio_id")
        existing = None
        if raw_portfolio_id:
            try:
                portfolio_id = UUID(raw_portfolio_id)
            except ValueError:
                portfolio_id = None
            if portfolio_id:
                existing = db.scalar(
                    select(BrokerConnection)
                    .join(Portfolio, Portfolio.id == BrokerConnection.portfolio_id)
                    .where(
                        BrokerConnection.workspace_id == context.workspace.id,
                        Portfolio.public_id == portfolio_id,
                        BrokerConnection.broker == broker,
                    )
                )
        if existing is None:
            used = db.scalar(
                select(func.count()).select_from(BrokerConnection).where(
                    BrokerConnection.workspace_id == context.workspace.id
                )
            ) or 0
            ensure_count_limit(entitlements, "broker_connections", used=used)
        else:
            limit = entitlements.limits.broker_connections
            if limit is not None:
                rows = db.scalars(
                    select(BrokerConnection)
                    .where(BrokerConnection.workspace_id == context.workspace.id)
                    .order_by(BrokerConnection.created_at, BrokerConnection.id)
                ).all()
                if existing.id not in {row.id for row in rows[:limit]}:
                    raise EntitlementDenied(
                        "resource_read_only",
                        plan=entitlements.plan,
                        resource="broker_connections",
                        limit=limit,
                        used=len(rows),
                    )
        return entitlements
    return dependency


def require_writable_broker(broker: str) -> Callable:
    """Keep deterministic overflow connections readable/deletable, not usable."""
    async def dependency(
        request: Request,
        context: RequestContext = Depends(get_request_context),
        db: Session = Depends(get_db),
    ) -> None:
        from models import BrokerConnection, Portfolio

        edition = request.app.state.portfyl_edition
        entitlements = resolve_entitlements(db, edition=edition, workspace_id=context.workspace.id)
        limit = entitlements.limits.broker_connections
        if limit is None:
            return
        raw_portfolio_id = request.query_params.get("portfolio_id")
        try:
            portfolio_public_id = UUID(raw_portfolio_id) if raw_portfolio_id else None
        except ValueError:
            return
        target = db.scalar(
            select(BrokerConnection)
            .join(Portfolio, Portfolio.id == BrokerConnection.portfolio_id)
            .where(
                BrokerConnection.workspace_id == context.workspace.id,
                Portfolio.public_id == portfolio_public_id,
                BrokerConnection.broker == broker,
            )
        )
        if target is None:
            return
        rows = db.scalars(
            select(BrokerConnection)
            .where(BrokerConnection.workspace_id == context.workspace.id)
            .order_by(BrokerConnection.created_at, BrokerConnection.id)
        ).all()
        if target.id not in {row.id for row in rows[:limit]}:
            raise EntitlementDenied(
                "resource_read_only",
                plan=entitlements.plan,
                resource="broker_connections",
                limit=limit,
                used=len(rows),
            )

    return dependency


def reserve_usage(
    db: Session,
    *,
    workspace_id: UUID,
    metric: str,
    idempotency_key: str,
    limit: int,
    period_start: datetime,
    period_end: datetime,
    amount: int = 1,
) -> UsageReservation:
    if amount <= 0:
        raise ValueError("Usage reservation amount must be positive")
    prior = db.scalar(select(UsageReservation).where(
        UsageReservation.workspace_id == workspace_id,
        UsageReservation.metric == metric,
        UsageReservation.idempotency_key == idempotency_key,
    ))
    if prior is not None and prior.status in {"reserved", "finalized"}:
        prior._portfyl_reused = True
        return prior

    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("""
            INSERT INTO usage_counters
                (id, workspace_id, metric, period_start, period_end, used, updated_at)
            VALUES (:id, :workspace_id, :metric, :period_start, :period_end, 0, now())
            ON CONFLICT (workspace_id, metric, period_start) DO NOTHING
        """), {
            "id": uuid.uuid4(), "workspace_id": workspace_id, "metric": metric,
            "period_start": period_start, "period_end": period_end,
        })
    counter = db.scalar(
        select(UsageCounter).where(
            UsageCounter.workspace_id == workspace_id,
            UsageCounter.metric == metric,
            UsageCounter.period_start == period_start,
        ).with_for_update()
    )
    if counter is None:
        counter = UsageCounter(
            workspace_id=workspace_id,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
            used=0,
        )
        db.add(counter)
        db.flush()
    # A concurrent request with the same idempotency key may have committed
    # while this transaction was waiting for the counter row. Re-check after
    # acquiring the lock so the retry observes that reservation instead of
    # being rejected as fresh quota usage.
    if prior is None:
        prior = db.scalar(select(UsageReservation).where(
            UsageReservation.workspace_id == workspace_id,
            UsageReservation.metric == metric,
            UsageReservation.idempotency_key == idempotency_key,
        ))
        if prior is not None and prior.status in {"reserved", "finalized"}:
            prior._portfyl_reused = True
            return prior
    if counter.used + amount > limit:
        raise EntitlementDenied(
            "quota_exceeded", resource=metric, limit=limit, used=counter.used
        )
    counter.used += amount
    if prior is None:
        prior = UsageReservation(
            workspace_id=workspace_id,
            counter_id=counter.id,
            metric=metric,
            idempotency_key=idempotency_key,
            amount=amount,
            status="reserved",
        )
        db.add(prior)
    else:
        prior.counter_id = counter.id
        prior.status = "reserved"
        prior.finalized_at = None
    prior._portfyl_reused = False
    db.flush()
    return prior


def finalize_usage(db: Session, reservation: UsageReservation) -> None:
    if reservation.status == "reserved":
        reservation.status = "finalized"
        reservation.finalized_at = utcnow()
        db.flush()


def release_usage(db: Session, reservation: UsageReservation) -> None:
    if reservation.status != "reserved":
        return
    counter = db.scalar(select(UsageCounter).where(
        UsageCounter.id == reservation.counter_id,
        UsageCounter.workspace_id == reservation.workspace_id,
        UsageCounter.metric == reservation.metric,
    ).with_for_update())
    if counter is not None:
        counter.used = max(0, counter.used - reservation.amount)
    reservation.status = "released"
    reservation.finalized_at = utcnow()
    db.flush()
