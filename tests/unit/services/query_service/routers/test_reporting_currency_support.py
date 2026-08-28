"""Tenant-scope controls for reporting-currency support reads."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.query_service.app.application.reporting_currency_support import (
    ReportingCurrencySupportQuery,
    ReportingCurrencySupportResult,
)
from src.services.query_service.app.routers.reporting_currency_support import (
    get_reporting_currency_support,
)


def _request(tenant_id: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(enterprise_verified_tenant_id=tenant_id))


def _result(tenant_id: str) -> ReportingCurrencySupportResult:
    return ReportingCurrencySupportResult(
        portfolio_id="PF-1",
        tenant_id=tenant_id,
        reporting_currency="USD",
        as_of_date=date(2026, 8, 28),
        status="SUPPORTED",
        reason_code="supported",
    )


@pytest.mark.asyncio
async def test_reporting_currency_support_binds_omitted_tenant_to_authenticated_scope() -> None:
    service = AsyncMock()
    service.evaluate.return_value = _result("TENANT_A")

    await get_reporting_currency_support(
        request=_request("TENANT_A"),
        portfolio_id="PF-1",
        reporting_currency="USD",
        as_of_date=date(2026, 8, 28),
        tenant_id=None,
        service=service,
    )

    service.evaluate.assert_awaited_once_with(
        ReportingCurrencySupportQuery(
            portfolio_id="PF-1",
            reporting_currency="USD",
            as_of_date=date(2026, 8, 28),
            tenant_id="TENANT_A",
        )
    )


@pytest.mark.asyncio
async def test_reporting_currency_support_rejects_cross_tenant_scope() -> None:
    service = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_reporting_currency_support(
            request=_request("TENANT_A"),
            portfolio_id="PF-1",
            reporting_currency="USD",
            as_of_date=date(2026, 8, 28),
            tenant_id="TENANT_B",
            service=service,
        )

    assert exc_info.value.status_code == 403
    service.evaluate.assert_not_awaited()
