"""Cost workflow, persistence staging, FX, and reconciliation behavior tests."""

import inspect
import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from portfolio_common.cost_basis import CostBasisMethod
from portfolio_common.database_models import Portfolio
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.transaction_domain import (
    evaluate_ca_bundle_a_reconciliation,
)

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostCalculationError,
    EffectiveFxRate,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculationWorkflow,
    CostCalculatorRepository,
    CostProcessingCompatibilityAdapter,
    FxRateNotFoundError,
    OpenLotStateUpdateScope,
    PortfolioNotFoundError,
    normalize_cost_fee_amount,
)

pytestmark = pytest.mark.asyncio



async def test_cost_workflow_does_not_depend_on_retired_delivery_subclass() -> None:
    workflow_source = inspect.getsource(CostCalculationWorkflow)

    assert "CostCalculatorConsumer" not in workflow_source


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

    assert callable(workflow._prepare_transaction_event)
    assert callable(workflow._build_events_to_publish)
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
    repo = AsyncMock(spec=CostCalculatorRepository)
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
        cost_basis_method=CostBasisMethod.FIFO,
    )

    repo.acquire_cost_basis_processing_lock.assert_awaited_once_with("PORT_COST_01", "SEC_COST_01")
    assert repo.method_calls[0] == call.acquire_cost_basis_processing_lock(
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
    repo = AsyncMock(spec=CostCalculatorRepository)
    outbox_repo = AsyncMock(spec=OutboxRepository)
    repo.get_portfolio.return_value = Portfolio(base_currency="USD", portfolio_id="PORT_COST_01")
    repo.get_instrument.return_value = MagicMock(product_type="EQUITY", asset_class="EQUITY")

    workflow = MagicMock()
    workflow._prepare_transaction_event = AsyncMock(return_value=(event, "BUY", "FIFO"))
    workflow._assert_required_instrument_reference_available = MagicMock()
    workflow._build_events_to_publish = AsyncMock(return_value=([event], [instrument_event]))
    workflow._build_emitted_transaction_events = AsyncMock(return_value=[event])
    workflow._publish_transaction_events = AsyncMock()
    workflow._publish_instrument_events = AsyncMock()

    result = await CostProcessingCompatibilityAdapter(
        workflow=workflow,
        repository=repo,
        outbox_repository=outbox_repo,
    ).stage_event(
        event=event,
        correlation_id="cost-corr-id",
    )

    workflow._build_emitted_transaction_events.assert_awaited_once_with(
        events_to_publish=[event],
        repo=repo,
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
    assert result.emitted_events == (event,)
    assert result.instrument_event_count == 1

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
    repo = AsyncMock(spec=CostCalculatorRepository)
    outbox_repo = AsyncMock(spec=OutboxRepository)
    repo.get_portfolio.return_value = None

    with pytest.raises(PortfolioNotFoundError):
        await CostProcessingCompatibilityAdapter(
            workflow=MagicMock(),
            repository=repo,
            outbox_repository=outbox_repo,
        ).stage_event(
            event=event,
            correlation_id="cost-corr-id",
        )

    repo.get_instrument.assert_not_awaited()

async def test_backdated_cost_persistence_updates_suffix_but_publishes_only_incoming(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    prior = MagicMock(transaction_id="BUY-PRIOR")
    incoming = MagicMock(transaction_id="BUY-BACKDATED")
    later = MagicMock(transaction_id="SELL-LATER")
    incoming_event = MagicMock(spec=TransactionEvent)
    later_event = MagicMock(spec=TransactionEvent)
    repository = MagicMock()
    cost_calculation_workflow._persist_processed_transaction = AsyncMock(
        side_effect=(incoming_event, later_event)
    )

    events = await cost_calculation_workflow._persist_affected_processed_transactions(
        processed=[prior, incoming, later],
        new_transaction_ids={incoming.transaction_id},
        repo=repository,
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
    repository = AsyncMock(spec=CostCalculatorRepository)
    repository.update_transaction_costs.return_value = None

    with pytest.raises(
        ValueError,
        match="Canonical transaction row was not found during cost persistence",
    ):
        await cost_calculation_workflow._persist_processed_transaction(
            processed_transaction=processed_transaction,
            repo=repository,
        )

    repository.replace_transaction_cost_breakdown.assert_not_awaited()
    repository.upsert_buy_lot_state.assert_not_awaited()
    repository.upsert_accrued_income_offset_state.assert_not_awaited()

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
    repo = AsyncMock(spec=CostCalculatorRepository)
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
        repo=repo,
    )

    repo.get_fx_rate_window.assert_not_awaited()
    assert enriched[0]["trade_currency"] == "USD"
    assert enriched[0]["portfolio_base_currency"] == "USD"
    assert "transaction_fx_rate" not in enriched[0]

async def test_fx_enrichment_batches_effective_dated_history_by_currency_pair(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostCalculatorRepository)
    repo.get_fx_rate_window.return_value = [
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
        repo=repo,
    )

    repo.get_fx_rate_window.assert_awaited_once_with(
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
    repo = AsyncMock(spec=CostCalculatorRepository)
    repo.get_fx_rate_window.side_effect = [
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
        repo=repo,
    )

    assert repo.get_fx_rate_window.await_args_list == [
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
    repo = AsyncMock(spec=CostCalculatorRepository)
    repo.get_fx_rate_window.return_value = [
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
            repo=repo,
        )

async def test_validate_upstream_cash_leg_requires_external_cash_transaction_id(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    repo = AsyncMock(spec=CostCalculatorRepository)
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

    repo.get_transaction_by_id.assert_not_awaited()

async def test_update_open_lot_states_refreshes_full_rebuild_snapshots(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    repo = AsyncMock(spec=CostCalculatorRepository)
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
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    repo.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )

    repo.reset_mock()
    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="DIVIDEND",
        open_lot_states=open_lot_states,
        repo=repo,
        incremental=True,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    repo.update_open_lot_states.assert_not_awaited()

    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="SELL",
        open_lot_states=open_lot_states,
        repo=repo,
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    repo.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )

    repo.reset_mock()
    await cost_calculation_workflow._update_open_lot_states_if_required(
        event=event,
        event_transaction_type="SELL",
        open_lot_states=open_lot_states,
        repo=repo,
        incremental=True,
        update_scope=OpenLotStateUpdateScope.SELECTED_LOTS,
        cost_basis_method=CostBasisMethod.FIFO,
        average_cost_pool_transition=None,
    )
    repo.update_selected_open_lot_states.assert_awaited_once_with(
        portfolio_id="PORT_COST_01",
        security_id="DIV-SEC",
        states_by_source_transaction_id=open_lot_states,
    )
    repo.update_open_lot_states.assert_not_awaited()

async def test_update_open_lot_states_applies_average_cost_pool_transition(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostCalculatorRepository)
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
        incremental=True,
        update_scope=OpenLotStateUpdateScope.AVERAGE_COST_POOL,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=transition,
    )

    repo.apply_average_cost_pool_transition.assert_awaited_once_with(transition)
    repo.update_open_lot_states.assert_not_awaited()
    repo.update_selected_open_lot_states.assert_not_awaited()
    repo.upsert_average_cost_pool_checkpoint.assert_not_awaited()

async def test_full_avco_rebuild_establishes_pool_checkpoint_for_non_lot_event(
    cost_calculation_workflow: CostCalculationWorkflow,
) -> None:
    repo = AsyncMock(spec=CostCalculatorRepository)
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
        incremental=False,
        update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
        cost_basis_method=CostBasisMethod.AVCO,
        average_cost_pool_transition=None,
    )

    persisted_checkpoint = repo.upsert_average_cost_pool_checkpoint.await_args.args[0]
    assert persisted_checkpoint.quantity == Decimal("10")
    assert persisted_checkpoint.cost_local == Decimal("100")
    assert persisted_checkpoint.cost_base == Decimal("105")
    assert persisted_checkpoint.representative_source_transaction_id == "BUY-1"
    repo.update_open_lot_states.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
        states_by_source_transaction_id=open_lot_states,
    )

async def test_bundle_a_basis_mismatch_creates_reconciliation_finding(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    processed_event = _bundle_a_transaction_event(
        transaction_id="CA-DEM-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    group_events = [
        processed_event,
        _bundle_a_transaction_event(
            transaction_id="CA-DEM-IN-01",
            transaction_type="DEMERGER_IN",
            net_cost_local="60",
        ),
    ]

    run, findings = cost_calculation_workflow._bundle_a_reconciliation_evidence(
        processed_event=processed_event,
        linked_group="LTG-CA-DEM-01",
        parent_ref="CA-PARENT-DEM-01",
        reconciliation=evaluate_ca_bundle_a_reconciliation(group_events),
        missing_dependencies=[],
        correlation_id="corr-basis",
    )

    assert run["summary"]["passed"] is False
    assert run["summary"]["error_count"] == 1
    assert run["dedupe_key"].startswith("auto:corporate_action_bundle_a:")
    assert [finding["finding_type"] for finding in findings] == ["ca_bundle_a_basis_mismatch"]
    assert findings[0]["severity"] == "ERROR"
    assert findings[0]["detail"]["reason_code"] == "CA_BUNDLE_A_BASIS_MISMATCH"
    assert findings[0]["observed_value"]["net_basis_delta_local"] == "-40"

async def test_bundle_a_insufficient_legs_creates_reconciliation_finding(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    processed_event = _bundle_a_transaction_event(
        transaction_id="CA-DEM-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )

    run, findings = cost_calculation_workflow._bundle_a_reconciliation_evidence(
        processed_event=processed_event,
        linked_group="LTG-CA-DEM-01",
        parent_ref="CA-PARENT-DEM-01",
        reconciliation=evaluate_ca_bundle_a_reconciliation([processed_event]),
        missing_dependencies=[],
        correlation_id="corr-insufficient",
    )

    assert run["summary"]["reconciliation_status"] == "insufficient_legs"
    assert run["summary"]["passed"] is False
    assert [finding["finding_type"] for finding in findings] == ["ca_bundle_a_insufficient_legs"]
    assert findings[0]["expected_value"] == {"source_leg_count": ">=1", "target_leg_count": ">=1"}
    assert findings[0]["detail"]["reason_code"] == "CA_BUNDLE_A_INSUFFICIENT_LEGS"

async def test_bundle_a_missing_cash_basis_creates_reconciliation_finding(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    processed_event = _bundle_a_transaction_event(
        transaction_id="CA-DEM-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    group_events = [
        processed_event,
        _bundle_a_transaction_event(
            transaction_id="CA-DEM-IN-01",
            transaction_type="DEMERGER_IN",
            net_cost_local="100",
        ),
        _bundle_a_transaction_event(
            transaction_id="CA-CASH-01",
            transaction_type="CASH_CONSIDERATION",
            net_cost_local="0",
        ),
    ]

    run, findings = cost_calculation_workflow._bundle_a_reconciliation_evidence(
        processed_event=processed_event,
        linked_group="LTG-CA-DEM-01",
        parent_ref="CA-PARENT-DEM-01",
        reconciliation=evaluate_ca_bundle_a_reconciliation(group_events),
        missing_dependencies=[],
        correlation_id="corr-cash-basis",
    )

    assert run["summary"]["reconciliation_status"] == "insufficient_cash_basis"
    assert run["summary"]["missing_cash_basis_count"] == 1
    assert run["summary"]["cash_basis_local"] == "0"
    assert [finding["finding_type"] for finding in findings] == [
        "ca_bundle_a_insufficient_cash_basis"
    ]
    assert findings[0]["detail"]["reason_code"] == "CA_BUNDLE_A_INSUFFICIENT_CASH_BASIS"

async def test_bundle_a_dependency_gap_creates_reconciliation_finding(
    cost_calculation_workflow: CostCalculationWorkflow,
):
    processed_event = _bundle_a_transaction_event(
        transaction_id="CA-DEM-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
        dependency_reference_ids=["CA-DEM-OUT-01", "CA-DEM-OUT-MISSING"],
    )
    group_events = [
        _bundle_a_transaction_event(
            transaction_id="CA-DEM-OUT-01",
            transaction_type="DEMERGER_OUT",
            net_cost_local="-100",
        ),
        processed_event,
    ]
    missing_dependencies = cost_calculation_workflow._bundle_a_missing_dependencies(
        processed_event=processed_event,
        group_events=group_events,
    )

    run, findings = cost_calculation_workflow._bundle_a_reconciliation_evidence(
        processed_event=processed_event,
        linked_group="LTG-CA-DEM-01",
        parent_ref="CA-PARENT-DEM-01",
        reconciliation=evaluate_ca_bundle_a_reconciliation(group_events),
        missing_dependencies=missing_dependencies,
        correlation_id="corr-dependency",
    )

    assert run["summary"]["reconciliation_status"] == "balanced"
    assert run["summary"]["missing_dependency_count"] == 1
    assert run["summary"]["passed"] is False
    assert [finding["finding_type"] for finding in findings] == ["ca_bundle_a_missing_dependency"]
    assert findings[0]["detail"]["reason_code"] == "CA_BUNDLE_A_MISSING_DEPENDENCY"
    assert findings[0]["observed_value"] == {
        "missing_dependency_reference_ids": ["CA-DEM-OUT-MISSING"]
    }

async def test_bundle_a_reconciliation_key_skips_non_bundle_a_events(
    cost_calculation_workflow: CostCalculationWorkflow,
    mock_buy_kafka_message: MagicMock,
):
    event = TransactionEvent.model_validate(json.loads(mock_buy_kafka_message.value()))
    event.linked_transaction_group_id = "LTG-NON-CA"
    event.parent_event_reference = "PARENT-NON-CA"

    assert cost_calculation_workflow._bundle_a_reconciliation_key(event) is None
