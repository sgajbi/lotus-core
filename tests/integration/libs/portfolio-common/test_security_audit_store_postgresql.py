"""PostgreSQL proof for append-only tenant-bound security-audit evidence."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from portfolio_common.database_models import EnterpriseSecurityAuditEvent
from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditEvent,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditQuery,
    SecurityAuditReason,
)
from portfolio_common.infrastructure.persistence.security_audit_store import (
    PostgresSecurityAuditStore,
)
from portfolio_common.infrastructure_errors import InfrastructureAuditReadFailed
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 15, 2, 3, tzinfo=UTC)
EVENT_IDS = (
    "50000000-0000-4000-8000-000000000001",
    "50000000-0000-4000-8000-000000000002",
    "50000000-0000-4000-8000-000000000003",
    "50000000-0000-4000-8000-000000000004",
    "zzzzzzzz-zzzz-4zzz-8zzz-zzzzzzzzzzzz",
)


def _async_database_url() -> str:
    database_url = (
        os.getenv("LOTUS_SECURITY_AUDIT_POSTGRESQL_URL")
        or os.getenv("HOST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    if not database_url:
        pytest.skip("PostgreSQL URL is required for the security-audit integration proof")
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _verified_event(*, event_id: str, tenant_id: str) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_id=event_id,
        occurred_at=NOW,
        component=SecurityAuditComponent.QUERY_CONTROL_PLANE,
        route_template="/support/security-audit/events",
        method=SecurityAuditMethod.GET,
        decision=SecurityAuditDecision.ALLOW,
        reason=SecurityAuditReason.AUTHORIZED,
        required_capability="core.security_audit.read",
        service_identity="lotus-gateway",
        actor_id="operations-user-1",
        tenant_id=tenant_id,
        role="operations_support",
        identity_posture=SecurityAuditIdentityPosture.VERIFIED,
        correlation_id="QCP-SECURITY-AUDIT-1",
        trace_id=None,
        policy_version="1.0.0",
    )


def _record(event: SecurityAuditEvent) -> EnterpriseSecurityAuditEvent:
    return EnterpriseSecurityAuditEvent(
        **{
            field: getattr(event, field).value
            if hasattr(getattr(event, field), "value")
            else getattr(event, field)
            for field in EnterpriseSecurityAuditEvent.__table__.columns.keys()
        }
    )


async def test_postgresql_store_is_append_only_tenant_bound_and_keyset_stable() -> None:
    engine = create_async_engine(_async_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = PostgresSecurityAuditStore(sessions)
    tenant_event = _verified_event(event_id=EVENT_IDS[0], tenant_id="ISSUE500_TENANT_A")
    second_tenant_event = _verified_event(event_id=EVENT_IDS[1], tenant_id="ISSUE500_TENANT_A")
    other_tenant_event = _verified_event(event_id=EVENT_IDS[2], tenant_id="ISSUE500_TENANT_B")
    unverified_denial = replace(
        tenant_event,
        event_id=EVENT_IDS[3],
        decision=SecurityAuditDecision.DENY,
        reason=SecurityAuditReason.AUTHORIZATION_POLICY_DENIED,
        service_identity=None,
        actor_id=None,
        tenant_id=None,
        role=None,
        identity_posture=SecurityAuditIdentityPosture.UNVERIFIED,
    )

    try:
        async with sessions() as session:
            await session.execute(
                delete(EnterpriseSecurityAuditEvent).where(
                    EnterpriseSecurityAuditEvent.event_id.in_(EVENT_IDS)
                )
            )
            await session.commit()

        await asyncio.gather(
            store.append(tenant_event),
            store.append(second_tenant_event),
            store.append(other_tenant_event),
            store.append(unverified_denial),
        )

        page = await store.query(
            SecurityAuditQuery(
                tenant_id="ISSUE500_TENANT_A",
                occurred_from=NOW - timedelta(minutes=1),
                occurred_to=NOW + timedelta(minutes=1),
                page_size=1,
            )
        )
        assert page.events == (second_tenant_event,)
        assert page.next_cursor_occurred_at == NOW
        assert page.next_cursor_event_id == second_tenant_event.event_id
        next_page = await store.query(
            SecurityAuditQuery(
                tenant_id="ISSUE500_TENANT_A",
                occurred_from=NOW - timedelta(minutes=1),
                occurred_to=NOW + timedelta(minutes=1),
                page_size=1,
                cursor_occurred_at=page.next_cursor_occurred_at,
                cursor_event_id=page.next_cursor_event_id,
            )
        )
        assert next_page.events == (tenant_event,)
        assert next_page.next_cursor_occurred_at is None
        assert next_page.next_cursor_event_id is None
        assert other_tenant_event not in page.events
        assert unverified_denial not in page.events
    finally:
        async with sessions() as session:
            await session.execute(
                delete(EnterpriseSecurityAuditEvent).where(
                    EnterpriseSecurityAuditEvent.event_id.in_(EVENT_IDS)
                )
            )
            await session.commit()
        await engine.dispose()


async def test_postgresql_store_fails_source_safely_for_db_valid_domain_invalid_row() -> None:
    engine = create_async_engine(_async_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = PostgresSecurityAuditStore(sessions)
    tenant_id = "ISSUE954_CORRUPT_EVIDENCE"
    record = _record(_verified_event(event_id=EVENT_IDS[0], tenant_id=tenant_id))
    record.event_id = EVENT_IDS[4]

    try:
        async with sessions() as session:
            await session.execute(
                delete(EnterpriseSecurityAuditEvent).where(
                    EnterpriseSecurityAuditEvent.event_id == EVENT_IDS[4]
                )
            )
            session.add(record)
            await session.commit()

        with pytest.raises(InfrastructureAuditReadFailed) as exc_info:
            await store.query(
                SecurityAuditQuery(
                    tenant_id=tenant_id,
                    occurred_from=NOW - timedelta(minutes=1),
                    occurred_to=NOW + timedelta(minutes=1),
                    page_size=20,
                )
            )

        assert str(exc_info.value) == "Audit evidence could not be read."
        assert EVENT_IDS[4] not in str(exc_info.value.safe_diagnostics())
    finally:
        async with sessions() as session:
            await session.execute(
                delete(EnterpriseSecurityAuditEvent).where(
                    EnterpriseSecurityAuditEvent.event_id == EVENT_IDS[4]
                )
            )
            await session.commit()
        await engine.dispose()
