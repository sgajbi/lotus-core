"""Unit contracts for lot amortized-cost profile serialization controls."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.database_models import (
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
)
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    lot_amortized_cost_profile_id,
    materialize_active_lot_amortized_cost_profile,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    fixed_income_book_cost,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    EffectiveLotAmortizedCostProfileRequest,
)
from tests.test_support.fixed_income_book_cost import (
    fixed_income_book_cost_scope,
    resolved_fixed_income_book_cost_inputs,
)

pytestmark = pytest.mark.unit

SqlAlchemyLotAmortizedCostProfileRepository = (
    fixed_income_book_cost.SqlAlchemyLotAmortizedCostProfileRepository
)
lot_amortized_cost_profile_lock_key = fixed_income_book_cost.lot_amortized_cost_profile_lock_key


@pytest.mark.asyncio
async def test_materialization_lock_uses_stable_transaction_advisory_key() -> None:
    session = AsyncMock()
    repository = SqlAlchemyLotAmortizedCostProfileRepository(session)

    await repository.acquire_materialization_lock(fixed_income_book_cost_scope())

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert str(compiled) == "SELECT pg_advisory_xact_lock(%(lock_key)s)"
    expected_key = lot_amortized_cost_profile_lock_key(
        lot_amortized_cost_profile_id(fixed_income_book_cost_scope())
    )
    assert compiled.params["lock_key"] == expected_key


def test_materialization_lock_key_is_stable_namespaced_and_fail_closed() -> None:
    profile_id = "lot-amortized-cost:abc"

    assert lot_amortized_cost_profile_lock_key(profile_id) == (
        lot_amortized_cost_profile_lock_key(profile_id)
    )
    assert lot_amortized_cost_profile_lock_key(profile_id) != (
        lot_amortized_cost_profile_lock_key("lot-amortized-cost:def")
    )
    with pytest.raises(ValueError, match="nonblank"):
        lot_amortized_cost_profile_lock_key(" ")


@pytest.mark.asyncio
async def test_verified_head_propagates_full_profile_integrity_failure() -> None:
    session = AsyncMock()
    repository = SqlAlchemyLotAmortizedCostProfileRepository(session)
    repository.latest = AsyncMock(
        side_effect=fixed_income_book_cost.ConflictingLotAmortizedCostProfileError(
            "persisted profile content does not match its immutable hash"
        )
    )

    with pytest.raises(
        fixed_income_book_cost.ConflictingLotAmortizedCostProfileError,
        match="immutable hash",
    ):
        await repository.latest_verified_head(fixed_income_book_cost_scope())


@pytest.mark.asyncio
async def test_bulk_effective_lookup_is_empty_without_database_round_trips() -> None:
    session = AsyncMock()
    repository = SqlAlchemyLotAmortizedCostProfileRepository(session)

    assert await repository.effective_as_of_many(()) == {}

    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_effective_lookup_loads_headers_and_periods_in_two_round_trips() -> None:
    profile = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    header = LotAmortizedCostProfileRecord(
        **fixed_income_book_cost.profile_repository._profile_values(
            profile,
            profile_hash=profile.content_hash(),
        )
    )
    periods = [
        LotAmortizedCostPeriodRecord(
            **fixed_income_book_cost.profile_repository._period_values(period)
        )
        for period in profile.periods
    ]
    header_result = Mock()
    header_result.all.return_value = [header]
    period_result = Mock()
    period_result.all.return_value = periods
    session = AsyncMock()
    session.scalars.side_effect = (header_result, period_result)
    repository = SqlAlchemyLotAmortizedCostProfileRepository(session)
    request = EffectiveLotAmortizedCostProfileRequest(
        scope=profile.scope,
        effective_date=date(2027, 1, 1),
    )

    result = await repository.effective_as_of_many((request, request))

    assert result == {request: profile}
    assert session.scalars.await_count == 2
