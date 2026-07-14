"""Verify cost-basis stream locking and replay checkpoint persistence."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import CostBasisProcessingState

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisProcessingCheckpoint,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisProcessingStateRepository,
    cost_basis_processing_lock_key,
)

pytestmark = pytest.mark.asyncio


async def test_acquire_processing_lock_uses_stable_normalized_key() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisProcessingStateRepository(
        db_session,
        clock=MagicMock(side_effect=[10.0, 10.125]),
    )

    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis."
        "processing_state_repository.observe_cost_basis_processing_lock_wait"
    ) as observe_wait:
        await repository.acquire_cost_basis_processing_lock(" PORT_COST_01 ", " SEC01 ")

    statement = db_session.execute.call_args.args[0]
    assert str(statement) == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert statement.compile().params == {
        "lock_key": cost_basis_processing_lock_key("PORT_COST_01", "SEC01")
    }
    assert cost_basis_processing_lock_key(" PORT_COST_01 ", " SEC01 ") == (
        cost_basis_processing_lock_key("PORT_COST_01", "SEC01")
    )
    observe_wait.assert_called_once_with(outcome="acquired", seconds=0.125)


async def test_acquire_processing_lock_records_failure_without_swallowing() -> None:
    db_session = AsyncMock()
    db_session.execute.side_effect = RuntimeError("lock unavailable")
    repository = SqlAlchemyCostBasisProcessingStateRepository(
        db_session,
        clock=MagicMock(side_effect=[20.0, 20.25]),
    )

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis."
            "processing_state_repository.observe_cost_basis_processing_lock_wait"
        ) as observe_wait,
        pytest.raises(RuntimeError, match="lock unavailable"),
    ):
        await repository.acquire_cost_basis_processing_lock("P1", "S1")

    observe_wait.assert_called_once_with(outcome="failed", seconds=0.25)


async def test_get_processing_checkpoint_maps_durable_ordering_state() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisProcessingStateRepository(db_session)
    persisted = CostBasisProcessingState(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        cost_basis_method="FIFO",
        latest_transaction_date=datetime(2026, 1, 2, 10, 0, 0),
        latest_dependency_rank=4,
        latest_cash_dependency_rank=1,
        latest_child_sequence=2_147_483_647,
        latest_target_instrument_id="",
        latest_quantity=Decimal("10"),
        latest_transaction_id="BUY02",
        engine_state_version="open-lot-v1",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = persisted
    db_session.execute.return_value = execute_result

    checkpoint = await repository.get_cost_basis_processing_checkpoint(
        portfolio_id=" PORT_COST_01 ", security_id=" SEC01 "
    )

    assert checkpoint == CostBasisProcessingCheckpoint(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        cost_basis_method="FIFO",
        latest_transaction_date=datetime(2026, 1, 2, 10, 0, 0),
        latest_dependency_rank=4,
        latest_cash_dependency_rank=1,
        latest_child_sequence=2_147_483_647,
        latest_target_instrument_id="",
        latest_quantity=Decimal("10"),
        latest_transaction_id="BUY02",
        calculation_state_version="open-lot-v1",
    )


async def test_upsert_processing_checkpoint_maps_engine_state_version() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisProcessingStateRepository(db_session)
    checkpoint = CostBasisProcessingCheckpoint(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        cost_basis_method="AVCO",
        latest_transaction_date=datetime(2026, 1, 2, 10, 0, 0),
        latest_dependency_rank=4,
        latest_cash_dependency_rank=1,
        latest_child_sequence=3,
        latest_target_instrument_id="SEC02",
        latest_quantity=Decimal("10"),
        latest_transaction_id="BUY02",
        calculation_state_version="open-lot-v2",
    )

    await repository.upsert_cost_basis_processing_checkpoint(checkpoint)

    statement = db_session.execute.call_args.args[0]
    parameters = statement.compile().params
    assert parameters["portfolio_id"] == "PORT_COST_01"
    assert parameters["security_id"] == "SEC01"
    assert parameters["cost_basis_method"] == "AVCO"
    assert parameters["engine_state_version"] == "open-lot-v2"
    assert "ON CONFLICT (portfolio_id, security_id) DO UPDATE" in str(statement)
