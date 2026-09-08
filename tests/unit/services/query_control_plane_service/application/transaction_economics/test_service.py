"""Application-boundary tests for tenant-authoritative transaction economics."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, sentinel

import pytest
from portfolio_common.domain.tenant import TenantId

from src.services.query_control_plane_service.app.application.transaction_economics import service
from src.services.query_control_plane_service.app.contracts.performance_component_economics import (
    PerformanceComponentEconomicsRequest,
)
from src.services.query_control_plane_service.app.contracts.transaction_cost_curve import (
    TransactionCostCurveRequest,
)


def _service() -> service.TransactionEconomicsService:
    clock = MagicMock()
    clock.utc_now.return_value = datetime(2026, 5, 10, tzinfo=UTC)
    page_tokens = MagicMock()
    return service.TransactionEconomicsService(
        reader=sentinel.reader,
        page_tokens=page_tokens,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_cost_curve_overwrites_body_scope_with_typed_admitted_tenant(monkeypatch) -> None:
    resolver = AsyncMock(return_value=sentinel.response)
    monkeypatch.setattr(service, "resolve_transaction_cost_curve_response", resolver)
    request = TransactionCostCurveRequest(
        as_of_date="2026-05-10",
        window={"start_date": "2026-05-01", "end_date": "2026-05-10"},
        tenant_id="caller-assertion",
    )

    response = await _service().get_transaction_cost_curve(
        portfolio_id="PORT-1",
        tenant_id=TenantId("tenant-admitted"),
        request=request,
    )

    assert response is sentinel.response
    assert resolver.await_args.kwargs["tenant_id"] == TenantId("tenant-admitted")
    assert resolver.await_args.kwargs["request"].tenant_id == "tenant-admitted"
    assert request.tenant_id == "caller-assertion"


@pytest.mark.asyncio
async def test_performance_economics_fills_omitted_scope_from_typed_admission(monkeypatch) -> None:
    resolver = AsyncMock(return_value=sentinel.response)
    monkeypatch.setattr(service, "resolve_performance_component_economics_response", resolver)
    request = PerformanceComponentEconomicsRequest(
        as_of_date="2026-05-10",
        window={"start_date": "2026-05-01", "end_date": "2026-05-10"},
    )

    response = await _service().get_performance_component_economics(
        portfolio_id="PORT-1",
        tenant_id=TenantId("tenant-admitted"),
        request=request,
    )

    assert response is sentinel.response
    assert resolver.await_args.kwargs["tenant_id"] == TenantId("tenant-admitted")
    assert resolver.await_args.kwargs["request"].tenant_id == "tenant-admitted"
    assert request.tenant_id is None
