"""Application tests for deterministic cost-basis lot-state persistence."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostBasisTransaction,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisAverageCostPoolPort,
    CostBasisLotStatePort,
)

pytestmark = pytest.mark.asyncio

OpenLotPersistenceScope = cost_basis_processing.OpenLotPersistenceScope
persist_open_lot_state = cost_basis_processing.persist_open_lot_state


def _transaction(transaction_type: str = "SELL") -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type}-1",
        portfolio_id="PORT-1",
        instrument_id="INST-1",
        security_id="SEC-1",
        transaction_date=datetime(2026, 1, 2),
        transaction_type=transaction_type,
        quantity=Decimal("4"),
        price=Decimal("12"),
        gross_transaction_amount=Decimal("48"),
        trade_currency="USD",
        currency="USD",
    )


def _open_lot_states() -> dict[str, OpenLotState]:
    return {
        "BUY-1": OpenLotState(
            original_quantity=Decimal("10"),
            quantity=Decimal("6"),
            cost_local=Decimal("60"),
            cost_base=Decimal("63"),
        )
    }


def _processed(transaction_type: str = "SELL") -> list[CostBasisTransaction]:
    transaction = CostBasisTransaction(
        transaction_id=f"{transaction_type}-1",
        portfolio_id="PORT-1",
        instrument_id="INST-1",
        security_id="SEC-1",
        transaction_type=transaction_type,
        transaction_date=datetime(2026, 1, 2),
        quantity=Decimal("4"),
        gross_transaction_amount=Decimal("48"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    transaction.calculation_lineage = build_calculation_lineage(
        algorithm_id="test-cost-basis-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"transaction_id": transaction.transaction_id},
        output_payload={"net_cost": Decimal("48")},
    )
    return [transaction]


async def test_full_rebuild_replaces_complete_open_lot_snapshot() -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    states = _open_lot_states()

    await persist_open_lot_state(
        transaction=_transaction("DIVIDEND"),
        effective_transaction_type="DIVIDEND",
        open_lot_states=states,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
        processed=_processed("DIVIDEND"),
    )

    lot_states.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT-1",
        security_id="SEC-1",
        states_by_source_transaction_id=states,
        transition_evidence=lot_states.update_open_lot_states.await_args.kwargs[
            "transition_evidence"
        ],
    )
    lot_states.update_selected_open_lot_states.assert_not_awaited()
    average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()


@pytest.mark.parametrize("cost_basis_method", [CostBasisMethod.FIFO, CostBasisMethod.AVCO])
async def test_initial_opening_lot_does_not_reread_complete_snapshot(
    cost_basis_method: CostBasisMethod,
) -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    states = {
        "BUY-1": OpenLotState(
            original_quantity=Decimal("10"),
            quantity=Decimal("4"),
            cost_local=Decimal("48"),
            cost_base=Decimal("48"),
        )
    }

    await persist_open_lot_state(
        transaction=_transaction("BUY"),
        effective_transaction_type="BUY",
        open_lot_states=states,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        persistence_scope=OpenLotPersistenceScope.INITIAL_OPENING_LOT,
        cost_basis_method=cost_basis_method,
        average_cost_pool_transition=None,
        processed=_processed("BUY"),
    )

    lot_states.update_open_lot_states.assert_not_awaited()
    lot_states.update_selected_open_lot_states.assert_not_awaited()
    if cost_basis_method is CostBasisMethod.AVCO:
        checkpoint = average_cost_pools.upsert_average_cost_pool_checkpoint.await_args.args[0]
        assert checkpoint.quantity == Decimal("4")
        assert checkpoint.representative_source_transaction_id == "BUY-1"
    else:
        average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()


async def test_incremental_non_lot_transaction_preserves_existing_snapshot() -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)

    await persist_open_lot_state(
        transaction=_transaction("DIVIDEND"),
        effective_transaction_type="DIVIDEND",
        open_lot_states=_open_lot_states(),
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
        processed=_processed("DIVIDEND"),
    )

    lot_states.update_open_lot_states.assert_not_awaited()
    lot_states.update_selected_open_lot_states.assert_not_awaited()
    average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()


async def test_incremental_fifo_disposal_updates_only_selected_lots() -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    states = _open_lot_states()

    await persist_open_lot_state(
        transaction=_transaction(),
        effective_transaction_type="SELL",
        open_lot_states=states,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        persistence_scope=OpenLotPersistenceScope.SELECTED_LOTS,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
        processed=_processed(),
    )

    lot_states.update_selected_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT-1",
        security_id="SEC-1",
        states_by_source_transaction_id=states,
        transition_evidence=lot_states.update_selected_open_lot_states.await_args.kwargs[
            "transition_evidence"
        ],
    )
    lot_states.update_open_lot_states.assert_not_awaited()


async def test_average_cost_transition_is_applied_atomically() -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    transition = AverageCostPoolTransition(
        before=AverageCostPoolCheckpoint(
            portfolio_id="PORT-1",
            instrument_id="INST-1",
            security_id="SEC-1",
            representative_source_transaction_id="BUY-1",
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("105"),
        ),
        existing_sources_after=_open_lot_states()["BUY-1"],
        explicit_sources_after={},
    )

    await persist_open_lot_state(
        transaction=_transaction(),
        effective_transaction_type="SELL",
        open_lot_states=_open_lot_states(),
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        persistence_scope=OpenLotPersistenceScope.AVERAGE_COST_POOL,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=transition,
        processed=_processed(),
    )

    average_cost_pools.apply_average_cost_pool_transition.assert_awaited_once()
    assert average_cost_pools.apply_average_cost_pool_transition.await_args.args == (transition,)
    transition_evidence = average_cost_pools.apply_average_cost_pool_transition.await_args.kwargs[
        "transition_evidence"
    ]
    assert transition_evidence.trigger_transaction_id == "SELL-1"
    assert transition_evidence.transition_kind == "average_cost_pool"
    transition_payload = transition_evidence.transition_lineage.lineage_payload()
    assert transition_payload["algorithm_id"] == "cost-basis-lot-state-transition"
    average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()
    lot_states.update_open_lot_states.assert_not_awaited()
    lot_states.update_selected_open_lot_states.assert_not_awaited()


async def test_full_avco_rebuild_establishes_pool_checkpoint() -> None:
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    states = _open_lot_states()

    await persist_open_lot_state(
        transaction=_transaction("DIVIDEND"),
        effective_transaction_type="DIVIDEND",
        open_lot_states=states,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=None,
        processed=_processed("DIVIDEND"),
    )

    checkpoint = average_cost_pools.upsert_average_cost_pool_checkpoint.await_args.args[0]
    assert checkpoint.portfolio_id == "PORT-1"
    assert checkpoint.instrument_id == "INST-1"
    assert checkpoint.security_id == "SEC-1"
    assert checkpoint.quantity == Decimal("6")
    assert checkpoint.cost_local == Decimal("60")
    assert checkpoint.cost_base == Decimal("63")
    assert checkpoint.representative_source_transaction_id == "BUY-1"
    assert checkpoint.calculation_lineage is not None
    assert checkpoint.calculation_lineage.algorithm_id == "average-cost-pool-processing-rebuild"


async def test_full_avco_rebuild_checkpoint_binds_processed_transaction_evidence() -> None:
    async def checkpoint_input_hash(*, revision: str) -> str:
        average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
        processed = _processed("DIVIDEND")
        processed[0].calculation_lineage = build_calculation_lineage(
            algorithm_id="test-cost-basis-calculation",
            algorithm_version=1,
            intermediate_precision=28,
            input_payload={"revision": revision},
            output_payload={"net_cost": Decimal("48")},
        )
        await persist_open_lot_state(
            transaction=_transaction("DIVIDEND"),
            effective_transaction_type="DIVIDEND",
            open_lot_states=_open_lot_states(),
            average_cost_pools=average_cost_pools,
            lot_states=AsyncMock(spec=CostBasisLotStatePort),
            incremental=False,
            persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
            cost_basis_method=CostBasisMethod.AVCO,
            average_cost_pool_transition=None,
            processed=processed,
        )
        checkpoint = average_cost_pools.upsert_average_cost_pool_checkpoint.await_args.args[0]
        assert checkpoint.calculation_lineage is not None
        return checkpoint.calculation_lineage.input_content_hash

    assert await checkpoint_input_hash(revision="1") != await checkpoint_input_hash(revision="2")
