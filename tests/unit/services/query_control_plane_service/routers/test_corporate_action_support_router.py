"""Specify tenant isolation and non-enumerating route failures."""

from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.routers.corporate_action_support import (
    list_corporate_action_event_support,
)
from src.services.query_control_plane_service.app.routers.response_helpers import (
    QueryControlPlaneProblem,
)


@pytest.mark.asyncio
async def test_router_rejects_tenant_header_mismatch_before_service_access() -> None:
    service = AsyncMock()

    with pytest.raises(QueryControlPlaneProblem) as raised:
        await list_corporate_action_event_support(
            portfolio_id="PORT-001",
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            corporate_action_event_id=None,
            readiness_status=None,
            execution_status=None,
            skip=0,
            limit=50,
            x_tenant_id="TENANT-OTHER",
            service=service,
        )

    assert raised.value.status_code == 403
    assert raised.value.error_code == "QCP_CORPORATE_ACTION_SUPPORT_FORBIDDEN"
    service.list_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_maps_absent_and_wrong_scope_to_same_not_found_problem() -> None:
    service = AsyncMock()
    service.list_current.side_effect = LookupError("internal scope detail")

    with pytest.raises(QueryControlPlaneProblem) as raised:
        await list_corporate_action_event_support(
            portfolio_id="PORT-404",
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            corporate_action_event_id="CA-404",
            readiness_status=None,
            execution_status=None,
            skip=0,
            limit=50,
            x_tenant_id="TENANT-SG",
            service=service,
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == "Requested corporate-action support scope was not found."
    assert "internal" not in raised.value.detail


@pytest.mark.asyncio
async def test_router_maps_validation_failures_to_bounded_problem_detail() -> None:
    service = AsyncMock()
    service.list_current.side_effect = ValueError("internal filter implementation detail")

    with pytest.raises(QueryControlPlaneProblem) as raised:
        await list_corporate_action_event_support(
            portfolio_id="PORT-001",
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            corporate_action_event_id=None,
            readiness_status="UNKNOWN",
            execution_status=None,
            skip=0,
            limit=50,
            x_tenant_id="TENANT-SG",
            service=service,
        )

    assert raised.value.status_code == 422
    assert raised.value.error_code == "QCP_CORPORATE_ACTION_SUPPORT_INVALID"
    assert raised.value.detail == (
        "Requested corporate-action support filters or paging are invalid."
    )
    assert "internal" not in raised.value.detail
