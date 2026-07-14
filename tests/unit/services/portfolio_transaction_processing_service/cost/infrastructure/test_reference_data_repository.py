"""Verify SQLAlchemy mapping for cost-basis reference data."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Instrument, Portfolio
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
)

pytestmark = pytest.mark.asyncio


async def test_get_cost_basis_portfolio_maps_orm_to_immutable_reference() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisReferenceDataRepository(db_session)
    persisted_portfolio = Portfolio(
        portfolio_id="PORT_COST_01",
        base_currency="SGD",
        cost_basis_method=" avco ",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = persisted_portfolio
    db_session.execute.return_value = execute_result

    portfolio = await repository.get_cost_basis_portfolio("PORT_COST_01")

    assert portfolio == CostBasisPortfolioReference(
        portfolio_id="PORT_COST_01",
        base_currency="SGD",
        cost_basis_method=CostBasisMethod.AVCO,
    )
    assert portfolio is not persisted_portfolio


async def test_get_cost_basis_instrument_maps_reference_and_trims_lookup_identifier() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisReferenceDataRepository(db_session)
    persisted_instrument = Instrument(
        security_id="SEC_A",
        product_type="BOND",
        asset_class="FIXED_INCOME",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = persisted_instrument
    db_session.execute.return_value = execute_result

    instrument = await repository.get_cost_basis_instrument(" SEC_A ")

    assert instrument == CostBasisInstrumentReference(
        security_id="SEC_A",
        product_type="BOND",
        asset_class="FIXED_INCOME",
    )
    assert instrument is not persisted_instrument
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(instruments.security_id) = 'SEC_A'" in compiled_query
