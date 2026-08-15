"""Contract proofs for the tenant-bound security-audit support endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditEvent,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditPage,
    SecurityAuditReason,
)
from portfolio_common.infrastructure_errors import DatabaseUnavailable

from src.services.query_control_plane_service.app.application.security_audit_query import (
    SecurityAuditQueryService,
)
from src.services.query_control_plane_service.app.routers.response_helpers import (
    QueryControlPlaneProblem,
)
from src.services.query_control_plane_service.app.routers.security_audit import (
    list_security_audit_events,
)

NOW = datetime(2026, 8, 15, 1, 2, tzinfo=UTC)


def _request(*, tenant_id: str | None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/support/security-audit/events",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    if tenant_id is not None:
        request.state.enterprise_verified_tenant_id = tenant_id
    return request


def _event() -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_id="12345678-1234-4234-8234-123456789abc",
        occurred_at=NOW,
        component=SecurityAuditComponent.QUERY,
        route_template="/portfolios/{portfolio_id}",
        method=SecurityAuditMethod.GET,
        decision=SecurityAuditDecision.ALLOW,
        reason=SecurityAuditReason.AUTHORIZED,
        required_capability="portfolio.read",
        service_identity="lotus-gateway",
        actor_id="advisor-1",
        tenant_id="bank-sg",
        role="advisor",
        identity_posture=SecurityAuditIdentityPosture.VERIFIED,
        correlation_id="corr-1",
        trace_id=None,
        policy_version="policy-v1",
    )


@pytest.mark.asyncio
async def test_endpoint_uses_only_verified_request_tenant_and_maps_typed_page() -> None:
    service = AsyncMock(spec=SecurityAuditQueryService)
    service.list_events.return_value = SecurityAuditPage(
        events=(_event(),),
        next_cursor_occurred_at=NOW,
        next_cursor_event_id="12345678-1234-4234-8234-123456789abc",
    )

    response = await list_security_audit_events(
        request=_request(tenant_id="bank-sg"),
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW,
        page_size=50,
        cursor_occurred_at=None,
        cursor_event_id=None,
        component=SecurityAuditComponent.QUERY,
        decision=SecurityAuditDecision.ALLOW,
        service=service,
    )

    service.list_events.assert_awaited_once_with(
        tenant_id="bank-sg",
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW,
        page_size=50,
        cursor_occurred_at=None,
        cursor_event_id=None,
        component=SecurityAuditComponent.QUERY,
        decision=SecurityAuditDecision.ALLOW,
    )
    assert response.events[0].tenant_id == "bank-sg"
    assert response.events[0].route_template == "/portfolios/{portfolio_id}"
    assert response.next_cursor_event_id == "12345678-1234-4234-8234-123456789abc"
    assert "payload" not in response.model_dump()


@pytest.mark.asyncio
async def test_endpoint_rejects_missing_verified_tenant_before_query() -> None:
    service = AsyncMock(spec=SecurityAuditQueryService)

    with pytest.raises(QueryControlPlaneProblem) as exc_info:
        await list_security_audit_events(
            request=_request(tenant_id=None),
            occurred_from=NOW - timedelta(days=1),
            occurred_to=NOW,
            page_size=50,
            cursor_occurred_at=None,
            cursor_event_id=None,
            component=None,
            decision=None,
            service=service,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "QCP_SECURITY_AUDIT_TENANT_CONTEXT_REQUIRED"
    assert exc_info.value.detail == "The request does not carry verified tenant authority."
    service.list_events.assert_not_awaited()


@pytest.mark.asyncio
async def test_endpoint_maps_invalid_cursor_and_database_failure_source_safely() -> None:
    service = AsyncMock(spec=SecurityAuditQueryService)
    service.list_events.side_effect = ValueError(
        "security-audit cursor fields must be supplied together"
    )
    arguments = {
        "request": _request(tenant_id="bank-sg"),
        "occurred_from": NOW - timedelta(days=1),
        "occurred_to": NOW,
        "page_size": 50,
        "cursor_occurred_at": NOW,
        "cursor_event_id": None,
        "component": None,
        "decision": None,
        "service": service,
    }

    with pytest.raises(QueryControlPlaneProblem) as invalid:
        await list_security_audit_events(**arguments)
    assert invalid.value.status_code == 422
    assert invalid.value.error_code == "QCP_SECURITY_AUDIT_QUERY_INVALID"
    assert invalid.value.detail == (
        "The requested evidence window or cursor is outside governed bounds."
    )

    service.list_events.side_effect = DatabaseUnavailable(safe_context={"host": "must-not-leak"})
    with pytest.raises(QueryControlPlaneProblem) as unavailable:
        await list_security_audit_events(**arguments)
    assert unavailable.value.status_code == 503
    assert unavailable.value.error_code == "QCP_SECURITY_AUDIT_QUERY_UNAVAILABLE"
    assert unavailable.value.detail == "Durable security-audit evidence is temporarily unavailable."
    assert "must-not-leak" not in str(unavailable.value.detail)
