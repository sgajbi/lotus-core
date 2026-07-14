"""Cost workflow, persistence staging, FX, and reconciliation behavior tests."""

import inspect
import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostCalculationError,
    EffectiveFxRate,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculationWorkflow,
    CostProcessingCompatibilityAdapter,
    FxRateNotFoundError,
    OpenLotStateUpdateScope,
    PortfolioNotFoundError,
    normalize_cost_fee_amount,
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


class _StringCountedAmount:
    """Test value that records string normalization calls."""

    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


async def test_cost_workflow_constructs_without_kafka_delivery_runtime() -> None:
    workflow = CostCalculationWorkflow()

    assert callable(workflow._build_events_to_publish)
    assert not hasattr(workflow, "_prepare_transaction_event")
    assert not hasattr(workflow, "_assert_required_instrument_reference_available")
    assert not hasattr(workflow, "_consumer_config")


async def test_cost_basis_acquires_key_lock_before_reading_processing_state() -> None:
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
        open_lot_state_update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        average_cost_pool_transition=None,
    )
    workflow._calculate_cost_basis = AsyncMock(return_value=calculation)
    workflow._persist_affected_processed_transactions = AsyncMock(return_value=[])
    workflow._update_open_lot_states_if_required = AsyncMock()
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


@pytest.fixture
def mock_buy_kafka_message() -> MagicMock:
    """Creates a mock Kafka message for a BUY transaction with a fee."""
    buy_event = TransactionEvent(
        transaction_id="BUY_WITH_FEE_01",
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        trade_fee=Decimal("7.50"),
        trade_currency="USD",
        currency="USD",
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = buy_event.model_dump_json().encode("utf-8")
    mock_msg.topic.return_value = "transactions.persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 2
    mock_msg.headers.return_value = []
    return mock_msg


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


async def test_cost_compatibility_stage_reports_missing_portfolio_dependency():
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
        await CostProcessingCompatibilityAdapter(
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


async def test_backdated_cost_persistence_updates_suffix_but_publishes_only_incoming(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    prior = MagicMock(transaction_id="BUY-PRIOR")
    incoming = MagicMock(transaction_id="BUY-BACKDATED")
    later = MagicMock(transaction_id="SELL-LATER")
    incoming_event = MagicMock(spec=TransactionEvent)
    later_event = MagicMock(spec=TransactionEvent)
    repository = MagicMock()
    lot_states = _lot_state_port()
    income_offsets = _income_offset_port()
    cost_calculation_workflow._persist_processed_transaction = AsyncMock(
        side_effect=(incoming_event, later_event)
    )

    events = await cost_calculation_workflow._persist_affected_processed_transactions(
        processed=[prior, incoming, later],
        new_transaction_ids={incoming.transaction_id},
        repo=repository,
        lot_states=lot_states,
        income_offsets=income_offsets,
    )

    assert events == [incoming_event]
    assert [
        call.kwargs["processed_transaction"].transaction_id
        for call in cost_calculation_workflow._persist_processed_transaction.await_args_list
    ] == ["BUY-BACKDATED", "SELL-LATER"]


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


async def test_cost_persistence_fails_before_child_writes_when_canonical_row_is_missing(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    processed_transaction = MagicMock(
        transaction_id="BUY-MISSING-CANONICAL",
        transaction_type="BUY",
    )
    repository = AsyncMock(spec=CostBasisTransactionStatePort)
    lot_states = _lot_state_port()
    income_offsets = _income_offset_port()
    repository.apply_transaction_costs.return_value = None

    with pytest.raises(
        ValueError,
        match="Canonical transaction row was not found during cost persistence",
    ):
        await cost_calculation_workflow._persist_processed_transaction(
            processed_transaction=processed_transaction,
            repo=repository,
            lot_states=lot_states,
            income_offsets=income_offsets,
        )

    repository.replace_transaction_cost_breakdown.assert_not_awaited()
    lot_states.upsert_buy_lot_state.assert_not_awaited()
    income_offsets.upsert_accrued_income_offset.assert_not_awaited()


async def test_transform_event_rejects_post_validation_negative_trade_fee(
    cost_calculation_workflow: CostCalculationWorkflow,
    mock_buy_kafka_message: MagicMock,
):
    event = TransactionEvent.model_validate(json.loads(mock_buy_kafka_message.value()))
    event.trade_fee = Decimal("-0.01")

    with pytest.raises(ValueError, match="trade_fee"):
        cost_calculation_workflow._transform_event_for_engine(event)


async def test_transform_event_rejects_post_validation_negative_fee_component(
    cost_calculation_workflow: CostCalculationWorkflow,
    mock_buy_kafka_message: MagicMock,
):
    event = TransactionEvent.model_validate(json.loads(mock_buy_kafka_message.value()))
    event.brokerage = Decimal("-0.01")

    with pytest.raises(ValueError, match="brokerage"):
        cost_calculation_workflow._transform_event_for_engine(event)


async def test_transform_event_maps_positive_trade_fee_to_brokerage_fee(
    cost_calculation_workflow: CostCalculationWorkflow,
    mock_buy_kafka_message: MagicMock,
):
    event = TransactionEvent.model_validate(json.loads(mock_buy_kafka_message.value()))

    transformed = cost_calculation_workflow._transform_event_for_engine(event)

    assert transformed["trade_fee"] == "7.50"
    assert transformed["fees"] == {"brokerage": "7.50"}


async def test_transform_event_preserves_typed_corporate_action_metadata(
    cost_calculation_workflow: CostCalculationWorkflow,
    mock_buy_kafka_message: MagicMock,
) -> None:
    event = TransactionEvent.model_validate(json.loads(mock_buy_kafka_message.value()))
    event.synthetic_flow_effective_date = date(2026, 7, 5)
    event.synthetic_flow_amount_local = Decimal("-1200")
    event.synthetic_flow_amount_base = Decimal("-1450")

    transformed = cost_calculation_workflow._transform_event_for_engine(event)

    assert transformed["synthetic_flow_effective_date"] == date(2026, 7, 5)
    assert transformed["synthetic_flow_amount_local"] == Decimal("-1200")
    assert transformed["synthetic_flow_amount_base"] == Decimal("-1450")


async def test_fee_amount_normalizer_normalizes_counted_amount_once() -> None:
    amount = _StringCountedAmount("2.50")

    assert normalize_cost_fee_amount(amount, field_name="brokerage") == Decimal("2.50")
    assert normalize_cost_fee_amount(" ", field_name="stamp_duty") == Decimal("0")
    assert amount.string_call_count == 1


async def test_fx_enrichment_normalizes_same_currency_without_lookup(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    transactions = [
        {
            "transaction_id": "BUY_PADDED_CCY_01",
            "transaction_date": "2025-12-05T10:00:00Z",
            "trade_currency": " usd ",
        }
    ]

    enriched = await cost_calculation_workflow._enrich_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency=" USD ",
        fx_rates=fx_rates,
    )

    fx_rates.get_fx_rate_window.assert_not_awaited()
    assert enriched[0]["trade_currency"] == "USD"
    assert enriched[0]["portfolio_base_currency"] == "USD"
    assert "transaction_fx_rate" not in enriched[0]


async def test_fx_enrichment_batches_effective_dated_history_by_currency_pair(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(
            effective_date=date(2026, 4, 1),
            rate=Decimal("1.40"),
        ),
        EffectiveFxRate(
            effective_date=date(2026, 4, 10),
            rate=Decimal("1.45"),
        ),
    ]
    transaction_dates = ("05", "10", "15") * 100
    transactions = [
        {
            "transaction_id": f"EUR-{index:03d}",
            "transaction_date": f"2026-04-{day}T10:00:00Z",
            "trade_currency": " eur " if index == 0 else "EUR",
        }
        for index, day in enumerate(transaction_dates)
    ]

    enriched = await cost_calculation_workflow._enrich_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency="SGD",
        fx_rates=fx_rates,
    )

    fx_rates.get_fx_rate_window.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="SGD",
        start_date=date(2026, 4, 5),
        end_date=date(2026, 4, 15),
    )
    assert len(enriched) == 300
    assert [transaction["transaction_fx_rate"] for transaction in enriched] == [
        Decimal("1.40") if day == "05" else Decimal("1.45") for day in transaction_dates
    ]


async def test_fx_enrichment_issues_one_window_read_for_each_distinct_currency_pair(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.side_effect = [
        [EffectiveFxRate(effective_date=date(2026, 4, 1), rate=Decimal("1.40"))],
        [EffectiveFxRate(effective_date=date(2026, 4, 2), rate=Decimal("1.75"))],
    ]
    transactions = [
        {
            "transaction_id": "EUR-001",
            "transaction_date": "2026-04-05T10:00:00Z",
            "trade_currency": "EUR",
        },
        {
            "transaction_id": "EUR-002",
            "transaction_date": "2026-04-06T10:00:00Z",
            "trade_currency": "EUR",
        },
        {
            "transaction_id": "GBP-001",
            "transaction_date": "2026-04-07T10:00:00Z",
            "trade_currency": "GBP",
        },
    ]

    enriched = await cost_calculation_workflow._enrich_transactions_with_fx(
        transactions=transactions,
        portfolio_base_currency="SGD",
        fx_rates=fx_rates,
    )

    assert fx_rates.get_fx_rate_window.await_args_list == [
        call(
            from_currency="EUR",
            to_currency="SGD",
            start_date=date(2026, 4, 5),
            end_date=date(2026, 4, 6),
        ),
        call(
            from_currency="GBP",
            to_currency="SGD",
            start_date=date(2026, 4, 7),
            end_date=date(2026, 4, 7),
        ),
    ]
    assert [transaction["transaction_fx_rate"] for transaction in enriched] == [
        Decimal("1.40"),
        Decimal("1.40"),
        Decimal("1.75"),
    ]


async def test_fx_enrichment_rejects_a_transaction_before_the_first_available_rate(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("1.45"))
    ]

    with pytest.raises(FxRateNotFoundError, match="EUR->SGD"):
        await cost_calculation_workflow._enrich_transactions_with_fx(
            transactions=[
                {
                    "transaction_id": "EUR-BEFORE-FIRST-RATE",
                    "transaction_date": "2026-04-05T10:00:00Z",
                    "trade_currency": "EUR",
                }
            ],
            portfolio_base_currency="SGD",
            fx_rates=fx_rates,
        )


async def test_validate_upstream_cash_leg_requires_external_cash_transaction_id(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processed_event = TransactionEvent(
        transaction_id="INT-UP-01",
        portfolio_id="PORT_COST_01",
        instrument_id="BOND-001",
        security_id="SEC-BOND-001",
        transaction_date=datetime(2025, 1, 20),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=" ",
    )

    with pytest.raises(
        ValueError,
        match="UPSTREAM_PROVIDED requires external_cash_transaction_id on product leg.",
    ):
        await cost_calculation_workflow._validate_upstream_cash_leg(
            processed_event=processed_event,
            repo=repo,
        )

    repo.get_booked_transaction.assert_not_awaited()


async def test_load_upstream_cash_leg_maps_domain_transaction_to_event(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    repo.get_booked_transaction.return_value = BookedTransaction(
        transaction_id="CASH-UP-01",
        portfolio_id="PORT_COST_01",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_date=datetime(2025, 1, 20),
        transaction_type="CASH_INFLOW",
        quantity=Decimal("25"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
    )
    product_event = TransactionEvent(
        transaction_id="INT-UP-01",
        portfolio_id="PORT_COST_01",
        instrument_id="BOND-001",
        security_id="SEC-BOND-001",
        transaction_date=datetime(2025, 1, 20),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
    )

    cash_leg = await cost_calculation_workflow._load_upstream_cash_leg(
        external_cash_id="CASH-UP-01",
        processed_event=product_event,
        repo=repo,
    )

    assert cash_leg.transaction_id == "CASH-UP-01"
    assert cash_leg.transaction_type == "CASH_INFLOW"
    repo.get_booked_transaction.assert_awaited_once_with("CASH-UP-01", portfolio_id="PORT_COST_01")


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


async def test_update_open_lot_states_refreshes_full_rebuild_snapshots(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    event = TransactionEvent(
        transaction_id="DIV-LOT-01",
        portfolio_id="PORT_COST_01",
        instrument_id="DIV-INST",
        security_id="DIV-SEC",
        transaction_date=datetime(2025, 1, 20),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.0"),
        trade_currency="USD",
        currency="USD",
    )

    open_lot_states = {
        "BUY-1": OpenLotState(
            quantity=Decimal("3"),
            cost_local=Decimal("30"),
            cost_base=Decimal("30"),
        )
    }

    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="DIVIDEND",
        open_lot_states=open_lot_states,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    lot_states.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )

    lot_states.reset_mock()
    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="DIVIDEND",
        open_lot_states=open_lot_states,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    lot_states.update_open_lot_states.assert_not_awaited()

    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="SELL",
        open_lot_states=open_lot_states,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    lot_states.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )

    lot_states.reset_mock()
    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="SELL",
        open_lot_states=open_lot_states,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        update_scope=OpenLotStateUpdateScope.SELECTED_LOTS,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    lot_states.update_selected_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )
    lot_states.update_open_lot_states.assert_not_awaited()


async def test_update_open_lot_states_applies_average_cost_pool_transition(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    event = TransactionEvent(
        transaction_id="SELL-AVCO-1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2026, 1, 2),
        transaction_type="SELL",
        quantity=Decimal("4"),
        price=Decimal("12"),
        gross_transaction_amount=Decimal("48"),
        trade_currency="USD",
        currency="USD",
    )
    transition = AverageCostPoolTransition(
        before=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id="BUY-1",
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("100"),
        ),
        existing_sources_after=OpenLotState(
            quantity=Decimal("6"),
            cost_local=Decimal("60"),
            cost_base=Decimal("60"),
        ),
        explicit_sources_after={},
    )

    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="SELL",
        open_lot_states={"BUY-1": transition.existing_sources_after},
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=True,
        update_scope=OpenLotStateUpdateScope.AVERAGE_COST_POOL,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=transition,
    )

    average_cost_pools.apply_average_cost_pool_transition.assert_awaited_once_with(transition)
    lot_states.update_open_lot_states.assert_not_awaited()
    lot_states.update_selected_open_lot_states.assert_not_awaited()
    average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()


async def test_full_avco_rebuild_establishes_pool_checkpoint_for_non_lot_event(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    event = TransactionEvent(
        transaction_id="DIV-1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2026, 1, 2),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("20"),
        trade_currency="USD",
        currency="USD",
    )
    open_lot_states = {
        "BUY-1": OpenLotState(
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("105"),
        )
    }

    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="DIVIDEND",
        open_lot_states=open_lot_states,
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=None,
    )

    persisted_checkpoint = average_cost_pools.upsert_average_cost_pool_checkpoint.await_args.args[0]
    assert persisted_checkpoint.quantity == Decimal("10")
    assert persisted_checkpoint.cost_local == Decimal("100")
    assert persisted_checkpoint.cost_base == Decimal("105")
    assert persisted_checkpoint.representative_source_transaction_id == "BUY-1"
    lot_states.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
        states_by_source_transaction_id=open_lot_states,
    )


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
