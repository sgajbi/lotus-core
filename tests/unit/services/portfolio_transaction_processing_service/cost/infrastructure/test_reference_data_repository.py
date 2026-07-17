"""Verify SQLAlchemy mapping for cost-basis reference data."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceData,
)

pytestmark = pytest.mark.asyncio


async def test_get_cost_basis_reference_data_maps_both_owners_in_one_query() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisReferenceDataRepository(db_session)
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = {
        "portfolio_id": "PORT_COST_01",
        "base_currency": "SGD",
        "cost_basis_method": " avco ",
        "instrument_security_id": "SEC_A",
        "instrument_product_type": "BOND",
        "instrument_asset_class": "FIXED_INCOME",
    }
    db_session.execute.return_value = execute_result

    reference_data = await repository.get_cost_basis_reference_data(
        portfolio_id="PORT_COST_01",
        security_id=" SEC_A ",
    )

    assert reference_data == CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT_COST_01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.AVCO,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SEC_A",
            product_type="BOND",
            asset_class="FIXED_INCOME",
        ),
    )
    db_session.execute.assert_awaited_once()
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "portfolios.portfolio_id = 'PORT_COST_01'" in compiled_query
    assert "trim(instruments.security_id) = 'SEC_A'" in compiled_query
    assert "LEFT OUTER JOIN instruments" in compiled_query


async def test_get_cost_basis_reference_data_retains_portfolio_without_instrument() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisReferenceDataRepository(db_session)
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = {
        "portfolio_id": "PORT_COST_01",
        "base_currency": "SGD",
        "cost_basis_method": "FIFO",
        "instrument_security_id": None,
        "instrument_product_type": None,
        "instrument_asset_class": None,
    }
    db_session.execute.return_value = execute_result

    reference_data = await repository.get_cost_basis_reference_data(
        portfolio_id="PORT_COST_01",
        security_id="MISSING",
    )

    assert reference_data == CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT_COST_01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        instrument=None,
    )


async def test_get_cost_basis_reference_data_returns_none_without_portfolio() -> None:
    db_session = AsyncMock()
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = None
    db_session.execute.return_value = execute_result

    reference_data = await SqlAlchemyCostBasisReferenceDataRepository(
        db_session
    ).get_cost_basis_reference_data(
        portfolio_id="MISSING",
        security_id="SEC_A",
    )

    assert reference_data is None
    db_session.execute.assert_awaited_once()
