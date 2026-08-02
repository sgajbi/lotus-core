"""Unit contracts for lot amortized-cost profile serialization controls."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    lot_amortized_cost_profile_id,
)
from services.portfolio_transaction_processing_service.app.infrastructure import (
    fixed_income_book_cost,
)
from tests.test_support.fixed_income_book_cost import fixed_income_book_cost_scope

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
