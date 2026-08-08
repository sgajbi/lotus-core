"""PostgreSQL contract tests for lot amortized-cost profile persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from portfolio_common.database_models import LotAmortizedCostProfileRecord
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    materialize_active_lot_amortized_cost_profile,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    fixed_income_book_cost,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostProfileAppendOutcome,
)
from tests.test_support.fixed_income_book_cost import (
    fixed_income_book_cost_scope,
    resolved_fixed_income_book_cost_inputs,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

ConflictingLotAmortizedCostProfileError = (
    fixed_income_book_cost.ConflictingLotAmortizedCostProfileError
)
SqlAlchemyLotAmortizedCostProfileRepository = (
    fixed_income_book_cost.SqlAlchemyLotAmortizedCostProfileRepository
)


async def test_repository_appends_queries_and_idempotently_replays_complete_profile(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostProfileRepository(async_db_session)
    first = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    second = replace(
        materialize_active_lot_amortized_cost_profile(
            resolved_fixed_income_book_cost_inputs(),
            profile_version=2,
        ),
        effective_date=date(2026, 2, 1),
    )

    assert await repository.append(first) is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert await repository.append(first) is LotAmortizedCostProfileAppendOutcome.UNCHANGED
    assert await repository.append(second) is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert await repository.append(first) is LotAmortizedCostProfileAppendOutcome.UNCHANGED
    await async_db_session.commit()

    assert await repository.latest(fixed_income_book_cost_scope()) == second
    assert await repository.effective_boundaries_from(
        fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 15),
    ) == (date(2026, 2, 1),)
    first_head = await repository.latest_verified_head_for_effective_date(
        fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 1),
    )
    assert first_head is not None
    assert first_head.profile_version == first.profile_version
    assert first_head.profile_content_hash == first.content_hash()
    assert (
        await repository.effective_as_of(
            fixed_income_book_cost_scope(),
            effective_date=date(2026, 1, 1),
        )
        == first
    )
    profile_count = await async_db_session.scalar(
        text("SELECT COUNT(*) FROM lot_amortized_cost_profiles")
    )
    period_count = await async_db_session.scalar(
        text("SELECT COUNT(*) FROM lot_amortized_cost_periods")
    )
    assert (profile_count, period_count) == (2, 2)


async def test_repository_rejects_identity_collision_and_persisted_hash_tampering(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostProfileRepository(async_db_session)
    profile = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    await repository.append(profile)

    with pytest.raises(ConflictingLotAmortizedCostProfileError, match="different immutable"):
        await repository.append(replace(profile, currency="USD"))

    await async_db_session.execute(
        text(
            "UPDATE lot_amortized_cost_periods "
            "SET period_content_hash = :hash WHERE profile_id = :profile_id"
        ),
        {"hash": "0" * 64, "profile_id": profile.profile_id},
    )
    with pytest.raises(ConflictingLotAmortizedCostProfileError, match="period content"):
        await repository.append(profile)
    await async_db_session.execute(
        text(
            "UPDATE lot_amortized_cost_periods "
            "SET period_content_hash = :hash WHERE profile_id = :profile_id"
        ),
        {
            "hash": profile.periods[0].content_hash(),
            "profile_id": profile.profile_id,
        },
    )
    await async_db_session.execute(
        update(LotAmortizedCostProfileRecord)
        .where(LotAmortizedCostProfileRecord.profile_id == profile.profile_id)
        .values(profile_content_hash="0" * 64)
    )
    with pytest.raises(ConflictingLotAmortizedCostProfileError, match="immutable hash"):
        await repository.latest(fixed_income_book_cost_scope())


async def test_repository_rejects_unknown_profile_lineage_fields(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostProfileRepository(async_db_session)
    profile = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    await repository.append(profile)
    record = await async_db_session.scalar(
        select(LotAmortizedCostProfileRecord).where(
            LotAmortizedCostProfileRecord.profile_id == profile.profile_id,
            LotAmortizedCostProfileRecord.profile_version == profile.profile_version,
        )
    )
    assert record is not None
    assert isinstance(record.calculation_lineage, dict)
    lineage = dict(record.calculation_lineage)
    lineage["unsupported"] = "tampered"
    await async_db_session.execute(
        update(LotAmortizedCostProfileRecord)
        .where(LotAmortizedCostProfileRecord.id == record.id)
        .values(calculation_lineage=lineage)
    )

    with pytest.raises(
        ConflictingLotAmortizedCostProfileError,
        match="does not use its canonical representation",
    ):
        await repository.latest(fixed_income_book_cost_scope())


async def test_repository_validates_scope_and_returns_none_without_rows(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyLotAmortizedCostProfileRepository(async_db_session)

    assert await repository.latest(fixed_income_book_cost_scope()) is None
    first = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    second = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=2,
    )
    fourth = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=4,
    )
    with pytest.raises(ConflictingLotAmortizedCostProfileError, match="contiguously at 1"):
        await repository.append(second)
    await repository.append(first)
    with pytest.raises(ConflictingLotAmortizedCostProfileError, match="contiguously at 2"):
        await repository.append(fourth)
    with pytest.raises(TypeError, match="scope"):
        await repository.latest(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="effective_date"):
        await repository.effective_as_of(
            fixed_income_book_cost_scope(),
            effective_date="2026-01-01",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="effective_date"):
        await repository.effective_boundaries_from(
            fixed_income_book_cost_scope(),
            effective_date="2026-01-01",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="effective_date"):
        await repository.latest_verified_head_for_effective_date(
            fixed_income_book_cost_scope(),
            effective_date="2026-01-01",  # type: ignore[arg-type]
        )


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
