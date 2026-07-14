"""Cost workflow, persistence staging, FX, and reconciliation behavior tests."""

import inspect
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import InstrumentEvent, TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501
    CostCalculationError,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculationWorkflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    cost_calculation_workflow as cost_calculation_workflow_module,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CostBasisProcessingAdapter,
    PortfolioNotFoundError,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotStatePort,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
)

pytestmark = pytest.mark.asyncio


def _average_cost_pool_port() -> AsyncMock:
    return AsyncMock(spec=CostBasisAverageCostPoolPort)


def _lot_state_port() -> AsyncMock:
    return AsyncMock(spec=CostBasisLotStatePort)


def _income_offset_port() -> AsyncMock:
    return AsyncMock(spec=AccruedIncomeOffsetStatePort)


async def test_cost_workflow_does_not_depend_on_retired_delivery_subclass() -> None:
    workflow_source = inspect.getsource(CostCalculationWorkflow)

    assert "CostCalculatorConsumer" not in workflow_source
    assert "record_bundle_a_reconciliation_evidence" not in workflow_source
    assert "FinancialReconciliationRun" not in workflow_source


async def test_cost_workflow_constructs_without_kafka_delivery_runtime() -> None:
    workflow = CostCalculationWorkflow()

    assert callable(workflow._build_events_to_publish)
    assert not hasattr(workflow, "_prepare_transaction_event")
    assert not hasattr(workflow, "_assert_required_instrument_reference_available")
    assert not hasattr(workflow, "_consumer_config")


async def test_cost_basis_acquires_key_lock_before_reading_processing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = TransactionEvent(
        transaction_id="BUY-LOCK-01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150"),
        gross_transaction_amount=Decimal("1500"),
        trade_currency="USD",
        currency="USD",
    )
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    income_offsets = _income_offset_port()
    workflow = CostCalculationWorkflow()
    calculation = MagicMock(
        processed=[],
        errored=[],
        open_lot_states={},
        incremental=True,
        open_lot_persistence_scope=cost_basis_processing.OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
        average_cost_pool_transition=None,
    )
    workflow._calculate_cost_basis = AsyncMock(return_value=calculation)
    persist_transactions = AsyncMock(return_value=())
    monkeypatch.setattr(
        cost_calculation_workflow_module,
        "persist_cost_basis_transactions",
        persist_transactions,
    )
    workflow._persist_cost_basis_processing_checkpoint = AsyncMock()

    await workflow._build_cost_basis_events_to_publish(
        event=event,
        event_transaction_type="BUY",
        portfolio=MagicMock(base_currency="USD"),
        instrument=MagicMock(),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        fx_rates=fx_rates,
        processing_state=processing_state,
        cost_basis_method=CostBasisMethod.FIFO,
    )

    processing_state.acquire_cost_basis_processing_lock.assert_awaited_once_with(
        "PORT_COST_01", "SEC_COST_01"
    )


def _bundle_a_transaction_event(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str,
    allocated_cost_basis_local: str | None = None,
    dependency_reference_ids: list[str] | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
        net_cost_local=Decimal(net_cost_local),
        allocated_cost_basis_local=(
            Decimal(allocated_cost_basis_local) if allocated_cost_basis_local is not None else None
        ),
        dependency_reference_ids=dependency_reference_ids,
    )


@pytest.fixture
def cost_calculation_workflow() -> CostCalculationWorkflow:
    return CostCalculationWorkflow()


async def test_cost_compatibility_adapter_executes_workflow_without_kafka_consumer():
    event = TransactionEvent(
        transaction_id="BUY-PROC-01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD",
        currency="USD",
    )
    instrument_event = MagicMock()
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    income_offsets = _income_offset_port()
    outbox_repo = AsyncMock(spec=OutboxRepository)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    portfolio = CostBasisPortfolioReference(
        portfolio_id="PORT_COST_01",
        base_currency="USD",
        cost_basis_method=CostBasisMethod.FIFO,
    )
    instrument = CostBasisInstrumentReference(
        security_id="SEC_COST_01",
        product_type="EQUITY",
        asset_class="EQUITY",
    )

    workflow = CostCalculationWorkflow()
    workflow._build_events_to_publish = AsyncMock(return_value=([event], [instrument_event]))
    workflow._build_emitted_transaction_events = AsyncMock(return_value=[event])
    workflow._publish_transaction_events = AsyncMock()
    workflow._publish_instrument_events = AsyncMock()

    result = await workflow.stage_prepared_event(
        event=event,
        event_transaction_type="BUY",
        route=cost_basis_processing.CostProcessingRoute.COST_BASIS,
        portfolio=portfolio,
        instrument=instrument,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        cost_basis_method=CostBasisMethod.FIFO,
        outbox_repo=outbox_repo,
        correlation_id="cost-corr-id",
    )

    workflow._build_events_to_publish.assert_awaited_once_with(
        event=event,
        event_transaction_type="BUY",
        route=cost_basis_processing.CostProcessingRoute.COST_BASIS,
        portfolio=portfolio,
        instrument=instrument,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        fx_rates=fx_rates,
        processing_state=processing_state,
        cost_basis_method=CostBasisMethod.FIFO,
    )
    workflow._build_emitted_transaction_events.assert_awaited_once_with(
        events_to_publish=[event],
        repo=repo,
        reconciliation_repository=reconciliation_repository,
        correlation_id="cost-corr-id",
    )
    workflow._publish_transaction_events.assert_awaited_once_with(
        original_event=event,
        emitted_events=[event],
        outbox_repo=outbox_repo,
        correlation_id="cost-corr-id",
    )
    workflow._publish_instrument_events.assert_awaited_once_with(
        instrument_events=[instrument_event],
        outbox_repo=outbox_repo,
        correlation_id="cost-corr-id",
    )
    assert result.emitted_transactions == (event,)
    assert result.instrument_update_count == 1


async def test_cost_basis_stage_reports_missing_portfolio_dependency():
    event = TransactionEvent(
        transaction_id="BUY-STAGE-01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD",
        currency="USD",
    )
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    income_offsets = _income_offset_port()
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    outbox_repo = AsyncMock(spec=OutboxRepository)
    reference_data.get_cost_basis_portfolio.return_value = None

    with pytest.raises(PortfolioNotFoundError):
        await CostBasisProcessingAdapter(
            workflow=MagicMock(),
            repository=repo,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            income_offsets=income_offsets,
            reference_data=reference_data,
            fx_rates=fx_rates,
            processing_state=processing_state,
            reconciliation_repository=reconciliation_repository,
            outbox_repository=outbox_repo,
        ).stage_event(
            event=event,
            correlation_id="cost-corr-id",
        )

    reference_data.get_cost_basis_instrument.assert_not_awaited()


async def test_recalculation_rejects_historical_engine_error_before_suffix_write() -> None:
    with pytest.raises(
        ValueError,
        match="Cost-basis calculation failed for SELL-LATER: insufficient open quantity",
    ):
        CostCalculationWorkflow._raise_for_transaction_engine_errors(
            errored=[
                CostCalculationError(
                    transaction_id="SELL-LATER",
                    error_reason="insufficient open quantity",
                )
            ]
        )


async def test_build_emitted_events_maps_generated_cash_leg_back_to_event_contract(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    product_leg = TransactionEvent(
        transaction_id="DIV-GENERATED-01",
        portfolio_id="PORT_COST_01",
        instrument_id="FUND-001",
        security_id="SEC-FUND-001",
        transaction_date=datetime(2025, 1, 20),
        settlement_date=datetime(2025, 1, 22),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-001",
        settlement_cash_instrument_id="CASH-USD",
    )

    emitted = await cost_calculation_workflow._build_emitted_transaction_events(
        events_to_publish=[product_leg],
        repo=repo,
        reconciliation_repository=reconciliation_repository,
        correlation_id="corr-generated-01",
    )

    assert [event.transaction_id for event in emitted] == [
        "DIV-GENERATED-01",
        "DIV-GENERATED-01-CASHLEG",
    ]
    generated_cash_leg = emitted[1]
    assert generated_cash_leg.transaction_type == "ADJUSTMENT"
    assert generated_cash_leg.gross_transaction_amount == Decimal("25.00")
    assert generated_cash_leg.movement_direction == "INFLOW"
    assert generated_cash_leg.originating_transaction_id == "DIV-GENERATED-01"
    assert emitted[0].external_cash_transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert product_leg.external_cash_transaction_id is None
    assert repo.upsert_booked_transaction.await_count == 2
    persisted_transactions = [
        call.args[0] for call in repo.upsert_booked_transaction.await_args_list
    ]
    assert all(isinstance(transaction, BookedTransaction) for transaction in persisted_transactions)
    assert [transaction.transaction_id for transaction in persisted_transactions] == [
        "DIV-GENERATED-01-CASHLEG",
        "DIV-GENERATED-01",
    ]


async def test_emitted_corporate_action_group_uses_application_reconciliation_boundary(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    source = _bundle_a_transaction_event(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _bundle_a_transaction_event(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    reconciliation_repository.load_group.return_value = ()
    observer = MagicMock()
    cost_calculation_workflow.configure_corporate_action_reconciliation_observer(observer)

    emitted = await cost_calculation_workflow._build_emitted_transaction_events(
        events_to_publish=[source, target],
        repo=repo,
        reconciliation_repository=reconciliation_repository,
        correlation_id="corr-ca-01",
    )

    assert emitted == [source, target]
    reconciliation_repository.load_group.assert_awaited_once()
    reconciliation_repository.save_evidence.assert_awaited_once()
    observer.observe.assert_called_once()


async def test_cost_workflow_routes_foreign_exchange_and_cost_basis_independently() -> None:
    workflow = CostCalculationWorkflow()
    event = _bundle_a_transaction_event(
        transaction_id="ROUTE-01",
        transaction_type="BUY",
        net_cost_local="100",
    )
    fx_result = ([event], [MagicMock(spec=InstrumentEvent)])
    cost_result = ([event], [])
    workflow._build_fx_events_to_publish = AsyncMock(return_value=fx_result)
    workflow._build_cost_basis_events_to_publish = AsyncMock(return_value=cost_result)
    dependencies = {
        "event": event,
        "event_transaction_type": "BUY",
        "portfolio": MagicMock(spec=CostBasisPortfolioReference),
        "instrument": MagicMock(spec=CostBasisInstrumentReference),
        "repo": AsyncMock(spec=CostBasisTransactionStatePort),
        "average_cost_pools": _average_cost_pool_port(),
        "lot_states": _lot_state_port(),
        "income_offsets": _income_offset_port(),
        "fx_rates": AsyncMock(spec=CostBasisFxRatePort),
        "processing_state": AsyncMock(spec=CostBasisProcessingStatePort),
        "cost_basis_method": CostBasisMethod.FIFO,
    }

    assert (
        await workflow._build_events_to_publish(
            route=cost_basis_processing.CostProcessingRoute.FOREIGN_EXCHANGE,
            **dependencies,
        )
        == fx_result
    )
    assert (
        await workflow._build_events_to_publish(
            route=cost_basis_processing.CostProcessingRoute.COST_BASIS,
            **dependencies,
        )
        == cost_result
    )

    workflow._build_fx_events_to_publish.assert_awaited_once_with(
        event=event, repo=dependencies["repo"]
    )
    workflow._build_cost_basis_events_to_publish.assert_awaited_once()


@pytest.mark.parametrize("epoch", [None, 7])
async def test_transaction_outbox_preserves_processing_epoch(epoch: int | None) -> None:
    original = _bundle_a_transaction_event(
        transaction_id="OUTBOX-ORIGINAL-01",
        transaction_type="BUY",
        net_cost_local="100",
    )
    original.epoch = epoch
    emitted = _bundle_a_transaction_event(
        transaction_id="OUTBOX-EMITTED-01",
        transaction_type="BUY",
        net_cost_local="100",
    )
    outbox = AsyncMock(spec=OutboxRepository)

    await CostCalculationWorkflow()._publish_transaction_events(
        original_event=original,
        emitted_events=[emitted],
        outbox_repo=outbox,
        correlation_id="corr-outbox-01",
    )

    assert emitted.epoch == epoch
    call = outbox.create_outbox_event.await_args
    assert call.kwargs["aggregate_type"] == "ProcessedTransaction"
    assert call.kwargs["aggregate_id"] == "PORT_COST_01"
    assert call.kwargs["event_type"] == "ProcessedTransactionPersisted"
    assert call.kwargs["correlation_id"] == "corr-outbox-01"


async def test_instrument_update_is_written_to_outbox() -> None:
    instrument_event = MagicMock(spec=InstrumentEvent)
    instrument_event.security_id = "SEC-CREATED-01"
    instrument_event.model_dump.return_value = {"security_id": "SEC-CREATED-01"}
    outbox = AsyncMock(spec=OutboxRepository)

    await CostCalculationWorkflow()._publish_instrument_events(
        instrument_events=[instrument_event],
        outbox_repo=outbox,
        correlation_id="corr-instrument-01",
    )

    outbox.create_outbox_event.assert_awaited_once_with(
        aggregate_type="Instrument",
        aggregate_id="SEC-CREATED-01",
        event_type="InstrumentUpserted",
        topic="instruments.received",
        payload={"security_id": "SEC-CREATED-01"},
        correlation_id="corr-instrument-01",
    )
