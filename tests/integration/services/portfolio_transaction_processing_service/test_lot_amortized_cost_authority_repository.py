"""PostgreSQL contract tests for lot amortized-cost source authority."""

from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import LotAmortizedCostAuthorityRecord
from sqlalchemy import inspect, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost import (  # noqa: E501
    ConflictingLotAmortizedCostAuthorityError,
    SqlAlchemyLotAmortizedCostAuthorityRepository,
)
from services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostAuthorityAppendOutcome,
)
from tests.test_support.fixed_income_book_cost import (
    fixed_income_book_cost_scope,
    resolved_fixed_income_book_cost_inputs,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c140b2c3d50d_feat_add_lot_amortized_cost_authority.py"
)
PREDECESSOR_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c139b2c3d50c_feat_add_lot_amortized_cost_profiles.py"
)


@pytest.fixture
def authority_schema(clean_db, db_engine) -> None:
    """Apply the branch migration when the cached local integration image predates it."""

    with db_engine.begin() as connection:
        if inspect(connection).has_table("lot_amortized_cost_authority"):
            return
        if not inspect(connection).has_table("lot_amortized_cost_profiles"):
            predecessor = runpy.run_path(str(PREDECESSOR_MIGRATION))
            predecessor["upgrade"].__globals__["op"] = Operations(
                MigrationContext.configure(connection)
            )
            predecessor["upgrade"]()
        else:
            operations = Operations(MigrationContext.configure(connection))
            existing_portfolio_constraints = {
                item["name"] for item in inspect(connection).get_unique_constraints("portfolios")
            }
            if "uq_portfolios_book_scope_identity" not in existing_portfolio_constraints:
                operations.create_unique_constraint(
                    "uq_portfolios_book_scope_identity",
                    "portfolios",
                    ["tenant_id", "legal_book_id", "portfolio_id"],
                )
            existing_lot_constraints = {
                item["name"]
                for item in inspect(connection).get_unique_constraints("position_lot_state")
            }
            if "uq_position_lot_scope_identity" not in existing_lot_constraints:
                operations.create_unique_constraint(
                    "uq_position_lot_scope_identity",
                    "position_lot_state",
                    ["lot_id", "portfolio_id", "security_id"],
                )
        migration = runpy.run_path(str(MIGRATION))
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration["upgrade"]()


async def test_repository_round_trips_every_authority_family_and_exact_retry(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    resolved = resolved_fixed_income_book_cost_inputs()
    authorities = (
        resolved.assignment,
        resolved.basis_fact,
        resolved.schedule_fact,
        resolved.yield_fact,
    )

    for authority in authorities:
        assert authority is not None
        assert await repository.append(authority) is LotAmortizedCostAuthorityAppendOutcome.APPENDED
        assert (
            await repository.append(authority) is LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
        )

    bundle = await repository.load(fixed_income_book_cost_scope())
    assert bundle.assignments == (resolved.assignment,)
    assert bundle.basis_facts == (resolved.basis_fact,)
    assert bundle.schedule_facts == (resolved.schedule_fact,)
    assert bundle.yield_facts == (resolved.yield_fact,)
    assert await async_db_session.scalar(
        text("SELECT COUNT(*) FROM lot_amortized_cost_authority")
    ) == len(authorities)


async def test_repository_appends_corrections_and_rejects_version_collision(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    first = resolved_fixed_income_book_cost_inputs().basis_fact
    corrected = replace(
        first,
        source=replace(
            first.source,
            fact_version=2,
            source_revision="revision-2",
        ),
        initial_clean_cost_local=first.initial_clean_cost_local + 1,
    )
    collision = replace(first, source=replace(first.source, source_revision="different"))
    version_three = replace(
        first,
        source=replace(
            first.source,
            source_record_id="AMORT_LOT_001_BASIS_LATE",
            fact_version=3,
            source_revision="revision-3",
        ),
    )
    late_version_two = replace(
        version_three,
        source=replace(
            version_three.source,
            fact_version=2,
            source_revision="revision-2",
        ),
    )

    await repository.append(first)
    assert await repository.append(corrected) is LotAmortizedCostAuthorityAppendOutcome.APPENDED
    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="different content",
    ):
        await repository.append(collision)
    await repository.append(version_three)
    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="increase monotonically",
    ):
        await repository.append(late_version_two)

    bundle = await repository.load(fixed_income_book_cost_scope())
    assert bundle.basis_facts == (first, corrected, version_three)


async def test_repository_rejects_persisted_payload_tampering_and_wrong_scope(
    clean_db,
    authority_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostAuthorityRepository(async_db_session)
    basis = resolved_fixed_income_book_cost_inputs().basis_fact
    await repository.append(basis)
    await async_db_session.execute(
        update(LotAmortizedCostAuthorityRecord)
        .where(LotAmortizedCostAuthorityRecord.authority_content_hash == basis.content_hash())
        .values(
            authority_payload={
                "currency": "SGD",
                "discount_origin": "MARKET_DISCOUNT",
                "fees_in_basis_local": "0",
                "initial_clean_cost_local": "96",
                "redemption_value_local": "100",
            }
        )
    )

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityError,
        match="immutable hash",
    ):
        await repository.load(fixed_income_book_cost_scope())
    with pytest.raises(TypeError, match="scope"):
        await repository.load(object())  # type: ignore[arg-type]


async def _seed_source_lot(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'AMORT_PORTFOLIO', 'TENANT_SG', 'BOOK_SG_PB', 'SGD',
                DATE '2026-01-01', 'MODERATE', 'LONG_TERM', 'ADVISORY',
                'SG', 'CLIENT_001', FALSE, 'ACTIVE'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO instruments (security_id, name, isin, currency, product_type)
            VALUES (
                'AMORT_BOND_001', 'Amortization Test Bond',
                'XS000AMORT001', 'SGD', 'BOND'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            ) VALUES (
                'AMORT_BUY_001', 'AMORT_PORTFOLIO', 'AMORT_BOND_001',
                'AMORT_BOND_001', 'BUY', 100, 97, 9700, 'SGD', 'SGD',
                TIMESTAMPTZ '2026-01-01 08:00:00+00'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO position_lot_state (
                lot_id, source_transaction_id, portfolio_id, instrument_id,
                security_id, acquisition_date, original_quantity, open_quantity,
                lot_cost_local, lot_cost_base, accrued_interest_paid_local
            ) VALUES (
                'AMORT_LOT_001', 'AMORT_BUY_001', 'AMORT_PORTFOLIO',
                'AMORT_BOND_001', 'AMORT_BOND_001', DATE '2026-01-01',
                100, 100, 9700, 9700, 0
            )
            """
        )
    )
