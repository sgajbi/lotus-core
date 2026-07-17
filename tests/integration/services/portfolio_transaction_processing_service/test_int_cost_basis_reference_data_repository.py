"""Verify cost-basis reference data is loaded atomically in one SQL round trip."""

from __future__ import annotations

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceData,
)
from tests.test_support.transaction_processing import instrument_record, portfolio_record

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_reference_bundle_uses_one_statement_and_maps_both_owners(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            portfolio_record(
                "PORT-REF-BUNDLE-01",
                base_currency="SGD",
                cost_basis_method="AVCO",
            ),
            instrument_record(
                "SEC-REF-BUNDLE-01",
                name="Reference Bundle Equity",
                isin="SG0000000001",
                currency="SGD",
            ),
        ]
    )
    await async_db_session.commit()
    statements: list[str] = []

    def capture_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.split()))

    sync_engine = async_db_session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        reference_data = await SqlAlchemyCostBasisReferenceDataRepository(
            async_db_session
        ).get_cost_basis_reference_data(
            portfolio_id="PORT-REF-BUNDLE-01",
            security_id=" SEC-REF-BUNDLE-01 ",
        )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", capture_statement)

    assert reference_data == CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            portfolio_id="PORT-REF-BUNDLE-01",
            base_currency="SGD",
            cost_basis_method=CostBasisMethod.AVCO,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SEC-REF-BUNDLE-01",
            product_type="EQUITY",
            asset_class="Equity",
        ),
    )
    assert len(statements) == 1
    assert "LEFT OUTER JOIN instruments" in statements[0]


async def test_reference_bundle_keeps_portfolio_when_instrument_is_absent(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add(portfolio_record("PORT-REF-BUNDLE-02"))
    await async_db_session.commit()

    reference_data = await SqlAlchemyCostBasisReferenceDataRepository(
        async_db_session
    ).get_cost_basis_reference_data(
        portfolio_id="PORT-REF-BUNDLE-02",
        security_id="MISSING",
    )

    assert reference_data is not None
    assert reference_data.portfolio.portfolio_id == "PORT-REF-BUNDLE-02"
    assert reference_data.instrument is None
