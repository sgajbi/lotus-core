"""Unit proofs for the PostgreSQL security-audit adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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
from portfolio_common.infrastructure_errors import (
    DatabaseUnavailable,
    InfrastructureAuditWriteFailed,
)
from portfolio_common.runtime_settings import RuntimeConfigurationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

NOW = datetime(2026, 8, 15, 1, 2, tzinfo=UTC)


def _event(*, event_id: str = "12345678-1234-4234-8234-123456789abc") -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_id=event_id,
        occurred_at=NOW,
        component=SecurityAuditComponent.QUERY,
        route_template="/portfolios/{portfolio_id}",
        method=SecurityAuditMethod.GET,
        decision=SecurityAuditDecision.ALLOW,
        reason=SecurityAuditReason.AUTHORIZED,
        required_capability="portfolio.read",
        service_identity="gateway",
        actor_id="advisor-1",
        tenant_id="bank-sg",
        role="advisor",
        identity_posture=SecurityAuditIdentityPosture.VERIFIED,
        correlation_id="corr-1",
        trace_id="trace-1",
        policy_version="enterprise-readiness-v1",
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


def _session_factory(session: MagicMock) -> MagicMock:
    factory = MagicMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.asyncio
async def test_append_commits_exact_typed_record() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    store = PostgresSecurityAuditStore(_session_factory(session))

    await store.append(_event())

    session.add.assert_called_once()
    record = session.add.call_args.args[0]
    assert isinstance(record, EnterpriseSecurityAuditEvent)
    assert record.tenant_id == "bank-sg"
    assert record.route_template == "/portfolios/{portfolio_id}"
    assert not hasattr(record, "payload")
    session.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_append_fails_closed_with_source_safe_error_and_rolls_back() -> None:
    session = MagicMock()
    session.commit = AsyncMock(side_effect=OperationalError("insert", {}, RuntimeError("secret")))
    session.rollback = AsyncMock()
    store = PostgresSecurityAuditStore(_session_factory(session))

    with pytest.raises(InfrastructureAuditWriteFailed) as exc_info:
        await store.append(_event())

    assert str(exc_info.value) == "Audit persistence failed."
    assert "secret" not in str(exc_info.value)
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_append_maps_lazy_runtime_configuration_failure_source_safely() -> None:
    factory = MagicMock(side_effect=RuntimeConfigurationError("secret database URL"))
    store = PostgresSecurityAuditStore(factory)

    with pytest.raises(InfrastructureAuditWriteFailed) as exc_info:
        await store.append(_event())

    assert str(exc_info.value) == "Audit persistence failed."
    assert "secret database URL" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_query_is_tenant_bound_filtered_keyset_and_returns_next_cursor() -> None:
    first = _record(_event())
    second = _record(_event(event_id="22345678-1234-4234-8234-123456789abc"))
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = [first, second]
    session = MagicMock()
    session.execute = AsyncMock(return_value=scalar_result)
    store = PostgresSecurityAuditStore(_session_factory(session))
    query = SecurityAuditQuery(
        tenant_id="bank-sg",
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW,
        page_size=1,
        cursor_occurred_at=NOW,
        cursor_event_id="32345678-1234-4234-8234-123456789abc",
        component=SecurityAuditComponent.QUERY,
        decision=SecurityAuditDecision.ALLOW,
    )

    page = await store.query(query)

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = str(compiled)
    assert "tenant_id = 'bank-sg'" in sql
    assert "component = 'query_service'" in sql
    assert "decision = 'ALLOW'" in sql
    assert "occurred_at < '2026-08-15 01:02:00+00:00'" in sql
    assert "event_id < '32345678-1234-4234-8234-123456789abc'" in sql
    assert "ORDER BY enterprise_security_audit_events.occurred_at DESC" in sql
    assert "LIMIT 2" in sql
    assert page.events == (_event(),)
    assert page.next_cursor_occurred_at == NOW
    assert page.next_cursor_event_id == first.event_id


@pytest.mark.asyncio
async def test_query_returns_terminal_page_without_cursor() -> None:
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = [_record(_event())]
    session = MagicMock()
    session.execute = AsyncMock(return_value=scalar_result)
    store = PostgresSecurityAuditStore(_session_factory(session))

    page = await store.query(
        SecurityAuditQuery(
            tenant_id="bank-sg",
            occurred_from=NOW - timedelta(days=1),
            occurred_to=NOW,
            page_size=20,
        )
    )

    assert page.events == (_event(),)
    assert page.next_cursor_occurred_at is None
    assert page.next_cursor_event_id is None


@pytest.mark.asyncio
async def test_query_failure_does_not_disclose_database_exception() -> None:
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=OperationalError("select", {}, RuntimeError("postgres-host-secret"))
    )
    store = PostgresSecurityAuditStore(_session_factory(session))
    query = SecurityAuditQuery(
        tenant_id="bank-sg",
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW,
        page_size=20,
    )

    with pytest.raises(DatabaseUnavailable) as exc_info:
        await store.query(query)

    assert str(exc_info.value) == "Security-audit evidence is unavailable."
    assert "postgres-host-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_query_maps_lazy_runtime_configuration_failure_source_safely() -> None:
    factory = MagicMock(side_effect=RuntimeConfigurationError("secret database URL"))
    store = PostgresSecurityAuditStore(factory)
    query = SecurityAuditQuery(
        tenant_id="bank-sg",
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW,
        page_size=20,
    )

    with pytest.raises(DatabaseUnavailable) as exc_info:
        await store.query(query)

    assert str(exc_info.value) == "Security-audit evidence is unavailable."
    assert "secret database URL" not in str(exc_info.value)
