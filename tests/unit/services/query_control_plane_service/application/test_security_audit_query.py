"""Application-boundary proofs for durable security-audit queries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.infrastructure_errors import InfrastructureAuditReadFailed

from src.services.query_control_plane_service.app.application.security_audit_query import (
    InvalidSecurityAuditQuery,
    SecurityAuditQueryService,
)

NOW = datetime(2026, 8, 15, 1, 2, tzinfo=UTC)


@pytest.mark.asyncio
async def test_invalid_caller_cursor_is_rejected_before_store_query() -> None:
    store = SimpleNamespace(query=AsyncMock())
    service = SecurityAuditQueryService(store=store)

    with pytest.raises(
        InvalidSecurityAuditQuery,
    ):
        await service.list_events(
            tenant_id="bank-sg",
            occurred_from=NOW - timedelta(days=1),
            occurred_to=NOW,
            page_size=50,
            cursor_occurred_at=NOW,
            cursor_event_id=None,
            component=None,
            decision=None,
        )

    store.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_persisted_evidence_read_failure_crosses_application_boundary_typed() -> None:
    read_failure = InfrastructureAuditReadFailed(safe_context={"evidence_type": "security_audit"})
    store = SimpleNamespace(query=AsyncMock(side_effect=read_failure))
    service = SecurityAuditQueryService(store=store)

    with pytest.raises(InfrastructureAuditReadFailed) as exc_info:
        await service.list_events(
            tenant_id="bank-sg",
            occurred_from=NOW - timedelta(days=1),
            occurred_to=NOW,
            page_size=50,
            cursor_occurred_at=None,
            cursor_event_id=None,
            component=None,
            decision=None,
        )

    assert exc_info.value is read_failure
    store.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_value_error_is_not_reclassified_as_invalid_caller_query() -> None:
    store_failure = ValueError("persisted adapter detail must not become caller attribution")
    store = SimpleNamespace(query=AsyncMock(side_effect=store_failure))
    service = SecurityAuditQueryService(store=store)

    with pytest.raises(ValueError) as exc_info:
        await service.list_events(
            tenant_id="bank-sg",
            occurred_from=NOW - timedelta(days=1),
            occurred_to=NOW,
            page_size=50,
            cursor_occurred_at=None,
            cursor_event_id=None,
            component=None,
            decision=None,
        )

    assert exc_info.value is store_failure
