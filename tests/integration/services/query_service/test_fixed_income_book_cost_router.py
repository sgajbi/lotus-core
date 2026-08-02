"""Verify public fixed-income book-cost routing and exact-scope parameters."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from services.query_service.app.dependencies import get_fixed_income_book_cost_service
from services.query_service.app.dtos.fixed_income_book_cost_dto import (
    FixedIncomeBookCostAsOfResponse,
)
from services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    service = MagicMock()
    service.get_as_of = AsyncMock(
        return_value=FixedIncomeBookCostAsOfResponse(
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_001",
            requested_as_of_date=date(2026, 6, 30),
            profile_id="profile-001",
            profile_version=1,
            profile_effective_date=date(2026, 1, 1),
            status="ACTIVE",
            eligibility_reason=None,
            policy_id="IFRS9_EIR_LOCAL",
            policy_version=1,
            schedule_version=1,
            currency="USD",
            direction="DISCOUNT_ACCRETION",
            book_cost_local_as_of=Decimal("984.5"),
            recognized_through_date=date(2026, 6, 30),
            next_recognition_date=date(2026, 12, 31),
            recognized_period_count=1,
            total_period_count=2,
            initial_amortized_cost_local=Decimal("980"),
            redemption_value_local=Decimal("1000"),
            final_amortized_cost_local=Decimal("1000"),
            residual_local=Decimal("0"),
            authority_content_hash="a" * 64,
            profile_content_hash="b" * 64,
            source_references=[],
            calculation_lineage=None,
            latest_recognized_period=None,
        )
    )
    app.dependency_overrides[get_fixed_income_book_cost_service] = lambda: service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, service
    app.dependency_overrides.pop(get_fixed_income_book_cost_service, None)


async def test_get_as_of_passes_complete_source_lot_scope(async_test_client) -> None:
    client, service = async_test_client

    response = await client.get(
        "/portfolios/PORTFOLIO_001/positions/BOND_001/lots/LOT_001/book-cost",
        params={
            "tenant_id": "TENANT_SG",
            "legal_book_id": "BOOK_SG_PB",
            "as_of_date": "2026-06-30",
        },
    )

    assert response.status_code == 200
    assert response.json()["book_cost_local_as_of"] == "984.5"
    service.get_as_of.assert_awaited_once_with(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        as_of_date=date(2026, 6, 30),
    )


async def test_missing_exact_scope_returns_investigative_404(async_test_client) -> None:
    client, service = async_test_client
    service.get_as_of.side_effect = LookupError("exact source-lot profile missing")

    response = await client.get(
        "/portfolios/PORTFOLIO_001/positions/BOND_001/lots/LOT_404/book-cost",
        params={
            "tenant_id": "TENANT_SG",
            "legal_book_id": "BOOK_SG_PB",
            "as_of_date": "2026-06-30",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "exact source-lot profile missing"


async def test_missing_legal_book_scope_is_validation_error(async_test_client) -> None:
    client, service = async_test_client

    response = await client.get(
        "/portfolios/PORTFOLIO_001/positions/BOND_001/lots/LOT_001/book-cost",
        params={"tenant_id": "TENANT_SG", "as_of_date": "2026-06-30"},
    )

    assert response.status_code == 422
    service.get_as_of.assert_not_awaited()


async def test_unsupported_service_response_fails_closed(async_test_client) -> None:
    client, service = async_test_client
    service.get_as_of.return_value = {"book_cost_local_as_of": "984.5"}

    response = await client.get(
        "/portfolios/PORTFOLIO_001/positions/BOND_001/lots/LOT_001/book-cost",
        params={
            "tenant_id": "TENANT_SG",
            "legal_book_id": "BOOK_SG_PB",
            "as_of_date": "2026-06-30",
        },
    )

    assert response.status_code == 500
