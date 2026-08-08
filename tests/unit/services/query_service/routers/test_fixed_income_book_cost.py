"""Boundary controls for fixed-income book-cost supportability reads."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.query_service.app.routers.fixed_income_book_cost import (
    get_fixed_income_book_cost_as_of,
)


@pytest.mark.asyncio
async def test_book_cost_read_rejects_cross_tenant_scope() -> None:
    service = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_fixed_income_book_cost_as_of(
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_001",
            tenant_id="TENANT_B",
            legal_book_id="BOOK_001",
            as_of_date=date(2026, 8, 3),
            x_tenant_id="TENANT_A",
            service=service,
        )

    assert exc_info.value.status_code == 403
    service.get_as_of.assert_not_awaited()


@pytest.mark.asyncio
async def test_book_cost_read_maps_blank_normalized_scope_to_validation_error() -> None:
    service = AsyncMock()
    service.get_as_of.side_effect = ValueError("legal_book_id must not be blank")

    with pytest.raises(HTTPException) as exc_info:
        await get_fixed_income_book_cost_as_of(
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_001",
            tenant_id="TENANT_A",
            legal_book_id=" ",
            as_of_date=date(2026, 8, 3),
            x_tenant_id="TENANT_A",
            service=service,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "legal_book_id must not be blank"
