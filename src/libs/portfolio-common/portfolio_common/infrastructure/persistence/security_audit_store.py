"""PostgreSQL adapter for durable enterprise security-audit evidence."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import EnterpriseSecurityAuditEvent
from portfolio_common.db import get_async_session_factory
from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditEvent,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditPage,
    SecurityAuditQuery,
    SecurityAuditReason,
)
from portfolio_common.infrastructure_errors import (
    DatabaseUnavailable,
    InfrastructureAuditWriteFailed,
)

SessionFactory = Callable[[], AsyncSession]


class PostgresSecurityAuditStore:
    """Append and query typed audit evidence without request payload material."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_async_session_factory()

    async def append(self, event: SecurityAuditEvent) -> None:
        session = self._session_factory()
        try:
            async with session:
                session.add(_to_record(event))
                await session.commit()
        except SQLAlchemyError:
            await _safe_rollback(session)
            raise InfrastructureAuditWriteFailed() from None

    async def query(self, query: SecurityAuditQuery) -> SecurityAuditPage:
        statement = (
            select(EnterpriseSecurityAuditEvent)
            .where(
                EnterpriseSecurityAuditEvent.tenant_id == query.tenant_id,
                EnterpriseSecurityAuditEvent.occurred_at >= query.occurred_from,
                EnterpriseSecurityAuditEvent.occurred_at <= query.occurred_to,
            )
            .order_by(
                EnterpriseSecurityAuditEvent.occurred_at.desc(),
                EnterpriseSecurityAuditEvent.event_id.desc(),
            )
            .limit(query.page_size + 1)
        )
        if query.component is not None:
            statement = statement.where(
                EnterpriseSecurityAuditEvent.component == query.component.value
            )
        if query.decision is not None:
            statement = statement.where(
                EnterpriseSecurityAuditEvent.decision == query.decision.value
            )
        if query.cursor_occurred_at is not None and query.cursor_event_id is not None:
            statement = statement.where(
                or_(
                    EnterpriseSecurityAuditEvent.occurred_at < query.cursor_occurred_at,
                    and_(
                        EnterpriseSecurityAuditEvent.occurred_at == query.cursor_occurred_at,
                        EnterpriseSecurityAuditEvent.event_id < query.cursor_event_id,
                    ),
                )
            )

        try:
            async with self._session_factory() as session:
                records = list((await session.execute(statement)).scalars().all())
        except SQLAlchemyError:
            raise DatabaseUnavailable(
                message="Security-audit evidence is unavailable.",
                reason_code="security_audit_query_unavailable",
            ) from None

        has_next_page = len(records) > query.page_size
        page_records = records[: query.page_size]
        events = tuple(_to_domain(record) for record in page_records)
        if not has_next_page or not events:
            return SecurityAuditPage(
                events=events,
                next_cursor_occurred_at=None,
                next_cursor_event_id=None,
            )
        last_event = events[-1]
        return SecurityAuditPage(
            events=events,
            next_cursor_occurred_at=last_event.occurred_at,
            next_cursor_event_id=last_event.event_id,
        )


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except SQLAlchemyError:
        pass


def _to_record(event: SecurityAuditEvent) -> EnterpriseSecurityAuditEvent:
    return EnterpriseSecurityAuditEvent(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        component=event.component.value,
        route_template=event.route_template,
        method=event.method.value,
        decision=event.decision.value,
        reason=event.reason.value,
        required_capability=event.required_capability,
        service_identity=event.service_identity,
        actor_id=event.actor_id,
        tenant_id=event.tenant_id,
        role=event.role,
        identity_posture=event.identity_posture.value,
        correlation_id=event.correlation_id,
        trace_id=event.trace_id,
        policy_version=event.policy_version,
        schema_version=event.schema_version,
        classification=event.classification,
    )


def _to_domain(record: EnterpriseSecurityAuditEvent) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_id=record.event_id,
        occurred_at=record.occurred_at,
        component=SecurityAuditComponent(record.component),
        route_template=record.route_template,
        method=SecurityAuditMethod(record.method),
        decision=SecurityAuditDecision(record.decision),
        reason=SecurityAuditReason(record.reason),
        required_capability=record.required_capability,
        service_identity=record.service_identity,
        actor_id=record.actor_id,
        tenant_id=record.tenant_id,
        role=record.role,
        identity_posture=SecurityAuditIdentityPosture(record.identity_posture),
        correlation_id=record.correlation_id,
        trace_id=record.trace_id,
        policy_version=record.policy_version,
        schema_version=record.schema_version,
        classification=record.classification,
    )
