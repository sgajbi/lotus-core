from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501  # noqa: E501
    AmortizedCostCarryState,
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
    CostBasisProcessingCheckpoint,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.state_lineage import (  # noqa: E501
    CostBasisStateTransitionEvidence,
    build_cost_basis_state_lineage,
    canonical_cost_basis_output_payload,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyAverageCostPoolRepository,
    SqlAlchemyCostBasisLotRepository,
    SqlAlchemyCostBasisTransactionRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    transaction_repository as transaction_repository_module,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_state_lineage import (  # noqa: E501
    LOT_STATE_LINEAGE_OUTPUT_FIELDS,
    lot_state_lineage_output_from_mapping,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_state_mapper import (  # noqa: E501
    buy_lot_state_payload,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
async def test_redemption_metadata_projection_clears_absent_correction_authority(
    transaction_type: str,
) -> None:
    transaction = SimpleNamespace(transaction_type=transaction_type)

    values = transaction_repository_module._transaction_metadata_update_values(transaction)

    assert {
        field_name: values[field_name]
        for field_name in transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS
    } == dict.fromkeys(transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS)


async def test_non_redemption_metadata_projection_clears_stale_redemption_authority() -> None:
    transaction = SimpleNamespace(
        transaction_type="SELL",
        redemption_price_type="PAR",
        old_factor=Decimal("1"),
        new_factor=Decimal("0.5"),
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("5"),
        embedded_fee_amount_local=Decimal("2"),
        embedded_tax_amount_local=Decimal("1"),
    )

    values = transaction_repository_module._transaction_metadata_update_values(transaction)

    assert {
        field_name: values[field_name]
        for field_name in transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS
    } == dict.fromkeys(transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS)


def _transition_evidence() -> CostBasisStateTransitionEvidence:
    return CostBasisStateTransitionEvidence(
        trigger_transaction_id="SELL01",
        transition_kind="selected_lots",
        transition_lineage=build_calculation_lineage(
            algorithm_id="test-cost-basis-calculation",
            algorithm_version=1,
            intermediate_precision=28,
            input_payload={"transaction_id": "SELL01"},
            output_payload={"realized_gain_loss": Decimal("10")},
        ),
    )


def _persisted_source_lot(
    source_transaction_id: str,
    *,
    quantity: str,
    cost_local: str,
    cost_base: str,
    calculation_lineage: dict[str, object] | None = None,
) -> PositionLotState:
    return PositionLotState(
        lot_id=f"LOT-{source_transaction_id}",
        source_transaction_id=source_transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        acquisition_date=date(2026, 1, 1),
        original_quantity=Decimal("10"),
        open_quantity=Decimal(quantity),
        lot_cost_local=Decimal(cost_local),
        lot_cost_base=Decimal(cost_base),
        accrued_interest_paid_local=Decimal(0),
        calculation_lineage=calculation_lineage,
    )


async def test_get_transaction_history_trims_portfolio_security_and_excluded_transaction_ids():
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)

    execute_result = MagicMock()
    calculation_lineage = build_calculation_lineage(
        algorithm_id="transaction-cost-basis-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"transaction_id": "BUY01"},
        output_payload={"net_cost": Decimal("1000")},
    )
    persisted_transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        calculation_lineage=calculation_lineage.lineage_payload(),
    )
    execute_result.unique.return_value.scalars.return_value.all.return_value = [
        persisted_transaction
    ]
    db_session.execute.return_value = execute_result

    transactions = await repository.get_transaction_history(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        exclude_id=" SELL01 ",
    )

    assert transactions == [
        BookedTransaction(
            transaction_id="BUY01",
            portfolio_id="PORT_COST_01",
            instrument_id="SEC01",
            security_id="SEC01",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            trade_currency="USD",
            currency="USD",
            trade_fee=None,
            calculation_lineage=calculation_lineage,
        )
    ]
    assert transactions[0] is not persisted_transaction
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert "trim(transactions.transaction_id) != 'SELL01'" in compiled_query
    assert "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC" in (
        compiled_query
    )
    assert "LEFT OUTER JOIN transaction_costs" in compiled_query


async def test_get_transaction_history_rehydrates_lossless_named_fee_authority() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    persisted_transaction = DBTransaction(
        transaction_id="BUY-FEES-01",
        portfolio_id="P1",
        instrument_id="S1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="usd",
        currency="USD",
        trade_fee=Decimal("99"),
        costs=[
            TransactionCost(fee_type="brokerage", amount=Decimal("1.25"), currency="USD"),
            TransactionCost(fee_type="stamp_duty", amount=Decimal("0.75"), currency="usd"),
            TransactionCost(fee_type="exchange_fee", amount=Decimal("0.50"), currency="USD"),
            TransactionCost(fee_type="gst", amount=Decimal("0.25"), currency="USD"),
            TransactionCost(fee_type="other_fees", amount=Decimal("0.10"), currency="USD"),
        ],
    )
    execute_result = MagicMock()
    execute_result.unique.return_value.scalars.return_value.all.return_value = [
        persisted_transaction
    ]
    db_session.execute.return_value = execute_result

    transactions = await repository.get_transaction_history("P1", "S1")

    assert transactions[0].trade_fee == Decimal("99")
    assert {
        field_name: getattr(transactions[0], field_name)
        for field_name in transaction_repository_module.FEE_COMPONENT_FIELDS
    } == {
        "brokerage": Decimal("1.25"),
        "stamp_duty": Decimal("0.75"),
        "exchange_fee": Decimal("0.50"),
        "gst": Decimal("0.25"),
        "other_fees": Decimal("0.10"),
    }
    db_session.execute.assert_awaited_once()


@pytest.mark.parametrize(
    ("costs", "expected_message"),
    [
        (
            [TransactionCost(fee_type="custody_fee", amount=Decimal("1"), currency="USD")],
            "unsupported fee type",
        ),
        (
            [
                TransactionCost(fee_type="gst", amount=Decimal("1"), currency="USD"),
                TransactionCost(fee_type=" GST ", amount=Decimal("2"), currency="USD"),
            ],
            "duplicate fee-type authority",
        ),
        (
            [TransactionCost(fee_type="gst", amount=Decimal("1"), currency="EUR")],
            "currency conflicts",
        ),
    ],
)
async def test_get_transaction_history_rejects_invalid_named_fee_authority(
    costs: list[TransactionCost], expected_message: str
) -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    persisted_transaction = DBTransaction(
        transaction_id="BUY-FEES-INVALID",
        portfolio_id="P1",
        instrument_id="S1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        costs=costs,
    )
    execute_result = MagicMock()
    execute_result.unique.return_value.scalars.return_value.all.return_value = [
        persisted_transaction
    ]
    db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match=expected_message):
        await repository.get_transaction_history("P1", "S1")


async def test_get_linked_transaction_group_scopes_portfolio_without_security_filter() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    persisted_interest = DBTransaction(
        transaction_id="INTEREST01",
        portfolio_id="PORT_COST_01",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="INTEREST",
        transaction_date=datetime(2026, 1, 2, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="GROUP_REDEMPTION_01",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [persisted_interest]
    db_session.execute.return_value = execute_result

    transactions = await repository.get_linked_transaction_group(
        portfolio_id=" PORT_COST_01 ",
        linked_transaction_group_id=" GROUP_REDEMPTION_01 ",
        exclude_id=" REDEMPTION01 ",
    )

    assert [transaction.transaction_id for transaction in transactions] == ["INTEREST01"]
    statement = db_session.execute.call_args.args[0]
    compiled_query = str(statement.compile(compile_kwargs={"literal_binds": True}))
    compiled_predicates = str(statement.whereclause.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.portfolio_id = 'PORT_COST_01'" in compiled_query
    assert "transactions.linked_transaction_group_id = 'GROUP_REDEMPTION_01'" in compiled_query
    assert "transactions.transaction_id != 'REDEMPTION01'" in compiled_query
    assert "transactions.security_id" not in compiled_predicates
    assert "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC" in (
        compiled_query
    )


async def test_get_booked_transaction_maps_domain_transaction_and_scopes_portfolio() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    calculation_lineage = build_calculation_lineage(
        algorithm_id="cash-settlement-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"transaction_id": "CASH01"},
        output_payload={"amount": Decimal("1000")},
    )
    persisted_transaction = DBTransaction(
        transaction_id="CASH01",
        portfolio_id="PORT_COST_01",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_OUTFLOW",
        transaction_date=datetime(2026, 1, 3, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("1000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        calculation_lineage=calculation_lineage.lineage_payload(),
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = persisted_transaction
    db_session.execute.return_value = execute_result

    transaction = await repository.get_booked_transaction("CASH01", portfolio_id="PORT_COST_01")

    assert transaction == BookedTransaction(
        transaction_id="CASH01",
        portfolio_id="PORT_COST_01",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_OUTFLOW",
        transaction_date=datetime(2026, 1, 3, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("1000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        trade_fee=None,
        calculation_lineage=calculation_lineage,
    )
    assert transaction is not persisted_transaction
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "transactions.transaction_id = 'CASH01'" in compiled_query
    assert "transactions.portfolio_id = 'PORT_COST_01'" in compiled_query


async def test_get_open_lot_checkpoint_records_returns_only_positive_lots() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)
    transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )
    lot = PositionLotState(
        lot_id="LOT-BUY01",
        source_transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        acquisition_date=date(2026, 1, 1),
        original_quantity=Decimal("10"),
        open_quantity=Decimal("4"),
        lot_cost_local=Decimal("400"),
        lot_cost_base=Decimal("420"),
        amortized_cost_profile_id="PROFILE-1",
        amortized_cost_profile_version=2,
        amortized_cost_profile_content_hash="a" * 64,
        amortized_cost_recognized_through=date(2026, 6, 30),
        amortized_cost_scheduled_local=Decimal("970"),
        amortized_book_carrying_local=Decimal("400"),
        amortized_book_carrying_base=Decimal("420"),
        amortized_cost_book_fx_rate_to_base=Decimal("1.05"),
    )
    execute_result = MagicMock()
    execute_result.all.return_value = [(lot, transaction)]
    db_session.execute.return_value = execute_result

    records = await repository.get_open_lot_checkpoint_records(
        portfolio_id="PORT_COST_01", security_id="SEC01"
    )

    assert len(records) == 1
    assert isinstance(records[0].transaction, BookedTransaction)
    assert records[0].transaction is not transaction
    assert records[0].transaction.transaction_id == "BUY01"
    assert records[0].quantity == Decimal("4")
    assert records[0].cost_local == Decimal("400")
    assert records[0].cost_base == Decimal("420")
    assert records[0].amortized_cost == AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=2,
        profile_content_hash="a" * 64,
        recognized_through_date=date(2026, 6, 30),
        scheduled_cost_local=Decimal("970"),
        carrying_amount_local=Decimal("400"),
        carrying_amount_base=Decimal("420"),
        book_cost_fx_rate_to_base=Decimal("1.05"),
    )
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "position_lot_state.open_quantity > 0" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.quantity DESC, "
        "transactions.transaction_id ASC"
    ) in compiled_query


async def test_get_open_lot_checkpoint_rejects_partial_amortized_carry_state() -> None:
    db_session = AsyncMock()
    transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )
    lot = _persisted_source_lot(
        "BUY01",
        quantity="4",
        cost_local="400",
        cost_base="420",
    )
    lot.amortized_cost_profile_id = "PROFILE-1"
    execute_result = MagicMock()
    execute_result.all.return_value = [(lot, transaction)]
    db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="partial amortized-cost carry state"):
        await SqlAlchemyCostBasisLotRepository(db_session).get_open_lot_checkpoint_records(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
        )


async def test_get_average_cost_pool_checkpoint_maps_aggregate_and_source_lineage() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    persisted = AverageCostPoolState(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-2",
        pool_quantity=Decimal("15"),
        pool_cost_local=Decimal("180"),
        pool_cost_base=Decimal("195"),
        state_version="avco-pool-v1",
    )
    transaction = DBTransaction(
        transaction_id="BUY-2",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 2, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("12"),
        gross_transaction_amount=Decimal("120"),
        trade_currency="USD",
        currency="USD",
    )
    execute_result = MagicMock()
    execute_result.first.return_value = (persisted, transaction)
    db_session.execute.return_value = execute_result

    record = await repository.get_average_cost_pool_checkpoint_record(
        portfolio_id=" P1 ",
        security_id=" S1 ",
    )

    assert record is not None
    assert isinstance(record.representative_transaction, BookedTransaction)
    assert record.representative_transaction is not transaction
    assert record.representative_transaction.transaction_id == "BUY-2"
    assert record.checkpoint == AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-2",
        quantity=Decimal("15"),
        cost_local=Decimal("180"),
        cost_base=Decimal("195"),
    )
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "average_cost_pool_state.portfolio_id = 'P1'" in compiled_query
    assert "average_cost_pool_state.security_id = 'S1'" in compiled_query
    assert "FOR UPDATE OF average_cost_pool_state" in compiled_query


async def test_upsert_average_cost_pool_checkpoint_is_idempotent_and_normalized() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)

    await repository.upsert_average_cost_pool_checkpoint(
        AverageCostPoolCheckpoint(
            portfolio_id=" P1 ",
            instrument_id=" I1 ",
            security_id=" S1 ",
            representative_source_transaction_id=" BUY-2 ",
            quantity=Decimal("15"),
            cost_local=Decimal("180"),
            cost_base=Decimal("195"),
        )
    )

    stmt = db_session.execute.call_args.args[0]
    compiled_query = str(stmt.compile())
    assert "ON CONFLICT (portfolio_id, security_id) DO UPDATE" in compiled_query
    assert "updated_at = now()" in compiled_query
    assert stmt.compile().params["portfolio_id"] == "P1"
    assert stmt.compile().params["security_id"] == "S1"
    assert stmt.compile().params["instrument_id"] == "I1"
    assert stmt.compile().params["representative_source_transaction_id"] == "BUY-2"
    lineage = stmt.compile().params["calculation_lineage"]
    assert lineage["algorithm_id"] == "average-cost-pool-checkpoint-materialization"
    assert lineage["numeric_output_policy"]["name"] == "cost-basis-state-ledger-output"


def _average_cost_checkpoint() -> AverageCostPoolCheckpoint:
    return AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-2",
        quantity=Decimal("15"),
        cost_local=Decimal("180"),
        cost_base=Decimal("195"),
    )


def _average_cost_source(
    transaction_id: str,
    *,
    transaction_date: datetime,
    quantity: str,
    cost: str,
) -> EngineTransaction:
    return EngineTransaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=transaction_date,
        quantity=Decimal(quantity),
        gross_transaction_amount=Decimal(cost),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost=Decimal(cost),
        gross_cost=Decimal(cost),
        realized_gain_loss=Decimal(0),
        net_cost_local=Decimal(cost),
        realized_gain_loss_local=Decimal(0),
    )


async def test_opening_lot_lineage_hashes_persisted_accrued_interest() -> None:
    first = _average_cost_source(
        "BUY-ACCRUED",
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        quantity="10",
        cost="100",
    )
    second = _average_cost_source(
        "BUY-ACCRUED",
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        quantity="10",
        cost="100",
    )
    first.accrued_interest = Decimal("1.25")
    second.accrued_interest = Decimal("1.50")

    first_payload = buy_lot_state_payload(first)
    second_payload = buy_lot_state_payload(second)

    assert first_payload["accrued_interest_paid_local"] == Decimal("1.25")
    assert second_payload["accrued_interest_paid_local"] == Decimal("1.50")
    assert isinstance(first_payload["calculation_lineage"], dict)
    assert isinstance(second_payload["calculation_lineage"], dict)
    assert (
        first_payload["calculation_lineage"]["output_content_hash"]
        != second_payload["calculation_lineage"]["output_content_hash"]
    )


def _average_cost_rebuild_plan(*, replay_revision: str = "1") -> AverageCostPoolRebuildPlan:
    first = _average_cost_source(
        "BUY-1",
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        quantity="10",
        cost="100",
    )
    second = _average_cost_source(
        "BUY-2",
        transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        quantity="5",
        cost="80",
    )
    states = {
        "BUY-1": OpenLotState(
            original_quantity=Decimal("10"),
            quantity=Decimal("6"),
            cost_local=Decimal("72"),
            cost_base=Decimal("78"),
        ),
        "BUY-2": OpenLotState(
            original_quantity=Decimal("5"),
            quantity=Decimal("3"),
            cost_local=Decimal("36"),
            cost_base=Decimal("39"),
        ),
    }
    checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        states_by_source_transaction_id=states,
    )
    return AverageCostPoolRebuildPlan(
        checkpoint=checkpoint,
        processing_checkpoint=CostBasisProcessingCheckpoint.from_transaction(
            second,
            cost_basis_method="AVCO",
        ),
        replay_lineage=build_cost_basis_state_lineage(
            algorithm_id="test-average-cost-replay",
            input_payload={"history_revision": replay_revision},
            output_payload={"quantity": checkpoint.quantity},
        ),
        source_transactions=(first, second),
        source_states=states,
    )


async def test_apply_average_cost_pool_rebuild_bulk_replaces_lot_and_pool_state() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    repository.REBUILD_UPSERT_CHUNK_SIZE = 1
    db_session.execute.side_effect = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    await repository.apply_average_cost_pool_rebuild(_average_cost_rebuild_plan())

    assert db_session.execute.await_count == 4
    close_sql = str(
        db_session.execute.call_args_list[0]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "UPDATE position_lot_state" in close_sql
    assert "open_quantity=0" in close_sql
    source_statement = db_session.execute.call_args_list[1].args[0]
    source_compiled = source_statement.compile(dialect=postgresql.dialect())
    source_upsert_sql = str(source_compiled)
    assert "INSERT INTO position_lot_state" in source_upsert_sql
    assert "ON CONFLICT (source_transaction_id) DO UPDATE" in source_upsert_sql
    assert "open_quantity" in source_upsert_sql
    assert "BUY-1" in source_compiled.params.values()
    assert Decimal("6") in source_compiled.params.values()
    assert "INSERT INTO average_cost_pool_state" in str(
        db_session.execute.call_args_list[3].args[0]
    )


async def test_average_cost_rebuild_receipts_are_replay_bound_and_idempotent() -> None:
    async def receipt(*, replay_revision: str) -> tuple[str, str]:
        db_session = AsyncMock()
        db_session.execute.side_effect = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]
        repository = SqlAlchemyAverageCostPoolRepository(db_session)
        await repository.apply_average_cost_pool_rebuild(
            _average_cost_rebuild_plan(replay_revision=replay_revision)
        )
        source_params = db_session.execute.call_args_list[1].args[0].compile().params
        source_lineage = next(
            value for key, value in source_params.items() if key.startswith("calculation_lineage")
        )
        checkpoint_statement = db_session.execute.call_args_list[-1].args[0]
        checkpoint_lineage = checkpoint_statement.compile().params["calculation_lineage"]
        return (
            str(checkpoint_lineage["input_content_hash"]),
            str(source_lineage["input_content_hash"]),
        )

    baseline = await receipt(replay_revision="1")
    repeated = await receipt(replay_revision="1")
    changed_replay = await receipt(replay_revision="2")

    assert repeated == baseline
    assert changed_replay[0] != baseline[0]
    assert changed_replay[1] != baseline[1]


async def test_get_average_cost_pool_persisted_summary_maps_missing_pool_and_source_sums() -> None:
    db_session = AsyncMock()
    pool_result = MagicMock()
    pool_result.scalars.return_value.first.return_value = None
    source_result = MagicMock()
    first_payload = buy_lot_state_payload(
        _average_cost_source(
            "BUY-1",
            transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            quantity="4",
            cost="48",
        )
    )
    second_payload = buy_lot_state_payload(
        _average_cost_source(
            "BUY-2",
            transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
            quantity="5",
            cost="60",
        )
    )
    second_payload["lot_cost_base"] = Decimal("69")
    second_payload["calculation_lineage"] = build_cost_basis_state_lineage(
        algorithm_id="average-cost-source-rebuild",
        input_payload={"source_transaction_id": "BUY-2"},
        output_payload=lot_state_lineage_output_from_mapping(second_payload),
    ).lineage_payload()
    source_result.all.return_value = [
        SimpleNamespace(**first_payload),
        SimpleNamespace(**second_payload),
    ]
    db_session.execute.side_effect = [pool_result, source_result]

    summary = await SqlAlchemyAverageCostPoolRepository(
        db_session
    ).get_average_cost_pool_persisted_summary(
        portfolio_id=" P1 ",
        security_id=" S1 ",
    )

    assert summary.source_count == 2
    assert summary.source_quantity == Decimal("9")
    assert summary.source_cost_local == Decimal("108")
    assert summary.source_cost_base == Decimal("117")
    assert summary.source_lineage_valid is True
    assert summary.pool_quantity is None
    source_sql = str(
        db_session.execute.call_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "trim(position_lot_state.portfolio_id) = 'P1'" in source_sql
    assert "trim(position_lot_state.security_id) = 'S1'" in source_sql
    for field_name in LOT_STATE_LINEAGE_OUTPUT_FIELDS:
        assert f"position_lot_state.{field_name}" in source_sql


async def test_get_average_cost_pool_persisted_summary_rejects_unbound_source_receipt() -> None:
    db_session = AsyncMock()
    pool_result = MagicMock()
    pool_result.scalars.return_value.first.return_value = None
    source_result = MagicMock()
    source_payload = buy_lot_state_payload(
        _average_cost_source(
            "BUY-1",
            transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            quantity="4",
            cost="48",
        )
    )
    source_payload["open_quantity"] = Decimal("3")
    source_result.all.return_value = [SimpleNamespace(**source_payload)]
    db_session.execute.side_effect = [pool_result, source_result]

    summary = await SqlAlchemyAverageCostPoolRepository(
        db_session
    ).get_average_cost_pool_persisted_summary(portfolio_id="P1", security_id="S1")

    assert summary.source_lineage_valid is False


async def test_persisted_summary_rejects_transition_receipt_after_durable_identity_drift() -> None:
    db_session = AsyncMock()
    pool_result = MagicMock()
    pool_result.scalars.return_value.first.return_value = None
    source_result = MagicMock()
    source_payload = buy_lot_state_payload(
        _average_cost_source(
            "BUY-1",
            transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            quantity="4",
            cost="48",
        )
    )
    source_payload["calculation_lineage"] = build_cost_basis_state_lineage(
        algorithm_id="average-cost-source-transition",
        input_payload={"source_transaction_id": "BUY-1"},
        output_payload=lot_state_lineage_output_from_mapping(source_payload),
    ).lineage_payload()
    source_payload["instrument_id"] = "CORRUPTED-INSTRUMENT"
    source_result.all.return_value = [SimpleNamespace(**source_payload)]
    db_session.execute.side_effect = [pool_result, source_result]

    summary = await SqlAlchemyAverageCostPoolRepository(
        db_session
    ).get_average_cost_pool_persisted_summary(portfolio_id="P1", security_id="S1")

    assert summary.source_lineage_valid is False


async def test_persisted_summary_rejects_self_consistent_receipt_with_unknown_version() -> None:
    db_session = AsyncMock()
    pool_result = MagicMock()
    pool_result.scalars.return_value.first.return_value = None
    source_result = MagicMock()
    source_payload = buy_lot_state_payload(
        _average_cost_source(
            "BUY-1",
            transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            quantity="4",
            cost="48",
        )
    )
    output_payload = canonical_cost_basis_output_payload(
        lot_state_lineage_output_from_mapping(source_payload)
    )
    source_payload["calculation_lineage"] = build_calculation_lineage(
        algorithm_id="average-cost-source-transition",
        algorithm_version=999,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"source_transaction_id": "BUY-1"},
        output_payload=output_payload,
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    source_result.all.return_value = [SimpleNamespace(**source_payload)]
    db_session.execute.side_effect = [pool_result, source_result]

    summary = await SqlAlchemyAverageCostPoolRepository(
        db_session
    ).get_average_cost_pool_persisted_summary(portfolio_id="P1", security_id="S1")

    assert summary.source_lineage_valid is False


async def test_apply_average_cost_pool_transition_scales_sources_and_assigns_residual() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    states_before_result = MagicMock()
    prior_source_lineage = build_calculation_lineage(
        algorithm_id="prior-average-cost-source",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"source_revision": "1"},
        output_payload={"quantity": Decimal("10")},
    ).lineage_payload()
    states_before_result.all.return_value = [
        ("BUY-1", Decimal("10"), Decimal("120"), Decimal("130"), prior_source_lineage),
        ("BUY-2", Decimal("5"), Decimal("60"), Decimal("65"), prior_source_lineage),
    ]
    scale_result = MagicMock()
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = (
        Decimal("7"),
        Decimal("70"),
        Decimal("77"),
    )
    residual_result = MagicMock(rowcount=1)
    first_source = _persisted_source_lot(
        "BUY-1",
        quantity="7",
        cost_local="70",
        cost_base="77",
        calculation_lineage=prior_source_lineage,
    )
    second_source = _persisted_source_lot(
        "BUY-2",
        quantity="2",
        cost_local="38",
        cost_base="40",
        calculation_lineage=prior_source_lineage,
    )
    final_states_result = MagicMock()
    final_states_result.scalars.return_value.all.return_value = [first_source, second_source]
    upsert_result = MagicMock()
    db_session.execute.side_effect = [
        states_before_result,
        scale_result,
        aggregate_result,
        residual_result,
        final_states_result,
        upsert_result,
    ]
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            original_quantity=Decimal("15"),
            quantity=Decimal("9"),
            cost_local=Decimal("108"),
            cost_base=Decimal("117"),
        ),
        explicit_sources_after={},
    )

    await repository.apply_average_cost_pool_transition(
        transition,
        transition_evidence=_transition_evidence(),
    )

    scale_compiled = db_session.execute.call_args_list[1].args[0].compile()
    scale_sql = str(scale_compiled)
    assert "open_quantity=trunc(" in scale_sql
    assert "position_lot_state.open_quantity *" in scale_sql
    assert "NUMERIC(18, 10)" in scale_sql
    assert "lot_cost_local=round(" in scale_sql
    assert "position_lot_state.lot_cost_local *" in scale_sql
    assert "BUY-2" in scale_compiled.params.values()
    residual_compiled = db_session.execute.call_args_list[3].args[0].compile()
    residual_sql = str(residual_compiled)
    assert "source_transaction_id =" in residual_sql
    assert "BUY-2" in residual_compiled.params.values()
    assert Decimal("2") in residual_compiled.params.values()
    assert Decimal("38") in residual_compiled.params.values()
    assert Decimal("40") in residual_compiled.params.values()
    assert first_source.calculation_lineage["algorithm_id"] == ("average-cost-source-transition")
    assert second_source.calculation_lineage["algorithm_id"] == ("average-cost-source-transition")
    assert (
        first_source.calculation_lineage["output_content_hash"]
        != (second_source.calculation_lineage["output_content_hash"])
    )
    upsert_sql = str(db_session.execute.call_args_list[5].args[0].compile())
    assert "INSERT INTO average_cost_pool_state" in upsert_sql


async def test_average_cost_source_lineage_binds_prior_and_transition_revisions() -> None:
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            original_quantity=Decimal("15"),
            quantity=Decimal("9"),
            cost_local=Decimal("108"),
            cost_base=Decimal("117"),
        ),
        explicit_sources_after={},
    )

    async def receipt(*, prior_revision: str, transition_revision: str) -> str:
        db_session = AsyncMock()
        row = _persisted_source_lot(
            "BUY-1",
            quantity="9",
            cost_local="108",
            cost_base="117",
            calculation_lineage=build_calculation_lineage(
                algorithm_id="prior-average-cost-source",
                algorithm_version=1,
                intermediate_precision=28,
                input_payload={"source_revision": prior_revision},
                output_payload={"quantity": Decimal("10")},
            ).lineage_payload(),
        )
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        db_session.execute.return_value = result
        await SqlAlchemyAverageCostPoolRepository(db_session)._refresh_average_cost_source_lineage(
            predicates=[],
            source_states_before={
                "BUY-1": {
                    "cost_base": Decimal("130"),
                    "cost_local": Decimal("120"),
                    "prior_calculation_lineage": row.calculation_lineage,
                    "quantity": Decimal("10"),
                    "source_transaction_id": "BUY-1",
                }
            },
            transition=transition,
            transition_lineage=build_calculation_lineage(
                algorithm_id="average-cost-pool-transition",
                algorithm_version=1,
                intermediate_precision=28,
                input_payload={"source_revision": transition_revision},
                output_payload={"quantity": Decimal("9")},
            ),
        )
        return str(row.calculation_lineage["input_content_hash"])

    baseline = await receipt(prior_revision="1", transition_revision="1")
    changed_prior = await receipt(prior_revision="2", transition_revision="1")
    changed_transition = await receipt(prior_revision="1", transition_revision="2")

    assert changed_prior != baseline
    assert changed_transition != baseline


async def test_apply_average_cost_pool_transition_rejects_missing_close_sources() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    close_result = MagicMock(rowcount=0)
    db_session.execute.side_effect = [MagicMock(), close_result]
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            original_quantity=Decimal("15"),
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
        ),
        explicit_sources_after={},
    )

    with pytest.raises(ValueError, match="found no persisted source lots"):
        await repository.apply_average_cost_pool_transition(
            transition,
            transition_evidence=_transition_evidence(),
        )

    assert db_session.execute.await_count == 2


async def test_apply_average_cost_pool_transition_rejects_negative_residual() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = (
        Decimal("10"),
        Decimal("109"),
        Decimal("118"),
    )
    db_session.execute.side_effect = [MagicMock(), MagicMock(), aggregate_result]
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            original_quantity=Decimal("15"),
            quantity=Decimal("9"),
            cost_local=Decimal("108"),
            cost_base=Decimal("117"),
        ),
        explicit_sources_after={},
    )

    with pytest.raises(ValueError, match="exceeds the target pool aggregate"):
        await repository.apply_average_cost_pool_transition(
            transition,
            transition_evidence=_transition_evidence(),
        )

    assert db_session.execute.await_count == 3


async def test_apply_average_cost_pool_transition_updates_explicit_new_source() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    new_lot = PositionLotState(
        lot_id="LOT-BUY-3",
        source_transaction_id="BUY-3",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        acquisition_date=date(2026, 1, 3),
        original_quantity=Decimal("5"),
        open_quantity=Decimal("5"),
        lot_cost_local=Decimal("70"),
        lot_cost_base=Decimal("75"),
    )
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [new_lot]
    db_session.execute.side_effect = [select_result, MagicMock()]
    explicit_state = OpenLotState(
        original_quantity=Decimal("5"),
        quantity=Decimal("5"),
        cost_local=Decimal("70"),
        cost_base=Decimal("75"),
    )
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=_average_cost_checkpoint().as_open_lot_state(),
        explicit_sources_after={"BUY-3": explicit_state},
    )

    evidence = _transition_evidence()
    await repository.apply_average_cost_pool_transition(
        transition,
        transition_evidence=evidence,
    )

    assert db_session.execute.await_count == 2
    selected_update_sql = str(
        db_session.execute.call_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "source_transaction_id IN ('BUY-3')" in selected_update_sql
    assert (
        new_lot.calculation_lineage["input_content_hash"]
        == build_cost_basis_state_lineage(
            algorithm_id="cost-basis-selected-lot-update",
            input_payload={
                "prior_calculation_lineage": None,
                "transition": evidence.lineage_payload(),
            },
            output_payload={
                "cost_base": Decimal("75"),
                "cost_local": Decimal("70"),
                "quantity": Decimal("5"),
                "source_transaction_id": "BUY-3",
            },
        ).input_content_hash
    )
    checkpoint_compiled = db_session.execute.call_args_list[1].args[0].compile()
    assert "BUY-3" in checkpoint_compiled.params.values()


async def test_average_cost_pool_receipt_binds_application_transition_evidence() -> None:
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=_average_cost_checkpoint().as_open_lot_state(),
        explicit_sources_after={},
    )

    async def receipt(*, trigger_transaction_id: str) -> str:
        db_session = AsyncMock()
        evidence = CostBasisStateTransitionEvidence(
            trigger_transaction_id=trigger_transaction_id,
            transition_kind="average_cost_pool",
            transition_lineage=build_calculation_lineage(
                algorithm_id="test-application-transition",
                algorithm_version=1,
                intermediate_precision=28,
                input_payload={"transaction_id": trigger_transaction_id},
                output_payload={"quantity": Decimal("10")},
            ),
        )
        await SqlAlchemyAverageCostPoolRepository(db_session).apply_average_cost_pool_transition(
            transition,
            transition_evidence=evidence,
        )
        checkpoint_statement = db_session.execute.await_args.args[0]
        calculation_lineage = checkpoint_statement.compile().params["calculation_lineage"]
        return str(calculation_lineage["input_content_hash"])

    baseline = await receipt(trigger_transaction_id="SELL-1")

    assert await receipt(trigger_transaction_id="SELL-2") != baseline


async def test_get_fifo_disposal_lots_streams_only_quantity_covering_oldest_lots() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)
    lots_and_transactions = []
    for sequence, (quantity, transaction_date) in enumerate(
        (
            ("4", datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)),
            ("5", datetime(2026, 1, 2, 10, 0, 0, tzinfo=UTC)),
            ("7", datetime(2026, 1, 3, 10, 0, 0, tzinfo=UTC)),
        ),
        start=1,
    ):
        transaction_id = f"BUY0{sequence}"
        transaction = DBTransaction(
            transaction_id=transaction_id,
            portfolio_id="PORT_COST_01",
            instrument_id="SEC01",
            security_id="SEC01",
            transaction_type="BUY",
            transaction_date=transaction_date,
            quantity=Decimal(quantity),
            price=Decimal("100"),
            gross_transaction_amount=Decimal(quantity) * Decimal("100"),
            trade_currency="USD",
            currency="USD",
        )
        lot = PositionLotState(
            lot_id=f"LOT-{transaction_id}",
            source_transaction_id=transaction_id,
            portfolio_id="PORT_COST_01",
            instrument_id="SEC01",
            security_id="SEC01",
            acquisition_date=transaction_date.date(),
            original_quantity=Decimal(quantity),
            open_quantity=Decimal(quantity),
            lot_cost_local=Decimal(quantity) * Decimal("100"),
            lot_cost_base=Decimal(quantity) * Decimal("100"),
        )
        lots_and_transactions.append((lot, transaction))

    stream_result = AsyncMock()
    stream_result.__aiter__.return_value = iter(lots_and_transactions)
    db_session.stream.return_value = stream_result

    records = await repository.get_fifo_disposal_lot_checkpoint_records(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        required_quantity=Decimal("6"),
    )

    assert [record.transaction.transaction_id for record in records] == ["BUY01", "BUY02"]
    assert sum((record.quantity for record in records), start=Decimal(0)) == Decimal("9")
    stream_result.close.assert_awaited_once_with()
    compiled_query = str(
        db_session.stream.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_lot_state.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_lot_state.security_id) = 'SEC01'" in compiled_query
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.quantity DESC, "
        "transactions.transaction_id ASC"
    ) in compiled_query


async def test_get_fifo_disposal_lots_rejects_non_positive_quantity_without_query() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)

    with pytest.raises(ValueError, match="quantity must be positive"):
        await repository.get_fifo_disposal_lot_checkpoint_records(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
            required_quantity=Decimal(0),
        )

    db_session.stream.assert_not_awaited()


async def test_update_open_lot_states_trims_ids_and_reconciles_quantity_and_cost():
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)

    lot_row = PositionLotState(
        lot_id="LOT-BUY01",
        source_transaction_id="BUY01",
        portfolio_id=" PORT_COST_01 ",
        instrument_id="SEC01",
        security_id=" SEC01 ",
        acquisition_date=date(2026, 1, 1),
        original_quantity=Decimal("10"),
        open_quantity=Decimal("10"),
        lot_cost_local=Decimal("1000"),
        lot_cost_base=Decimal("1000"),
    )
    closed_lot_row = PositionLotState(
        lot_id="LOT-BUY02",
        source_transaction_id="BUY02",
        portfolio_id=" PORT_COST_01 ",
        instrument_id="SEC01",
        security_id=" SEC01 ",
        acquisition_date=date(2026, 1, 2),
        original_quantity=Decimal("5"),
        open_quantity=Decimal("5"),
        lot_cost_local=Decimal("500"),
        lot_cost_base=Decimal("500"),
        amortized_cost_profile_id="PROFILE-OLD",
        amortized_cost_profile_version=1,
        amortized_cost_profile_content_hash="b" * 64,
        amortized_cost_recognized_through=date(2026, 6, 30),
        amortized_cost_scheduled_local=Decimal("500"),
        amortized_book_carrying_local=Decimal("500"),
        amortized_book_carrying_base=Decimal("500"),
        amortized_cost_book_fx_rate_to_base=Decimal("1"),
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [lot_row, closed_lot_row]
    db_session.execute.return_value = execute_result

    await repository.update_open_lot_states(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        states_by_source_transaction_id={
            "BUY01": OpenLotState(
                original_quantity=Decimal("10"),
                quantity=Decimal("4"),
                cost_local=Decimal("400"),
                cost_base=Decimal("420"),
                amortized_cost=AmortizedCostCarryState(
                    profile_id="PROFILE-1",
                    profile_version=2,
                    profile_content_hash="a" * 64,
                    recognized_through_date=date(2026, 6, 30),
                    scheduled_cost_local=Decimal("970"),
                    carrying_amount_local=Decimal("400"),
                    carrying_amount_base=Decimal("420"),
                    book_cost_fx_rate_to_base=Decimal("1.05"),
                ),
            )
        },
        transition_evidence=_transition_evidence(),
    )

    assert lot_row.open_quantity == Decimal("4")
    assert lot_row.lot_cost_local == Decimal("400")
    assert lot_row.lot_cost_base == Decimal("420")
    assert lot_row.amortized_cost_profile_id == "PROFILE-1"
    assert lot_row.amortized_cost_scheduled_local == Decimal("970")
    assert lot_row.amortized_book_carrying_local == Decimal("400")
    assert lot_row.amortized_book_carrying_base == Decimal("420")
    assert lot_row.calculation_lineage["algorithm_id"] == ("cost-basis-complete-lot-snapshot")
    assert closed_lot_row.open_quantity == Decimal("0")
    assert closed_lot_row.lot_cost_local == Decimal("0")
    assert closed_lot_row.lot_cost_base == Decimal("0")
    assert closed_lot_row.amortized_cost_profile_id is None
    assert closed_lot_row.amortized_cost_scheduled_local is None
    assert closed_lot_row.amortized_book_carrying_local is None
    assert closed_lot_row.amortized_book_carrying_base is None
    assert closed_lot_row.calculation_lineage["numeric_output_policy"]["name"] == (
        "cost-basis-state-ledger-output"
    )
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_lot_state.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_lot_state.security_id) = 'SEC01'" in compiled_query


async def test_update_selected_open_lot_states_does_not_close_omitted_lots() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)
    selected_lot = PositionLotState(
        lot_id="LOT-BUY01",
        source_transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        acquisition_date=date(2026, 1, 1),
        original_quantity=Decimal("10"),
        open_quantity=Decimal("10"),
        lot_cost_local=Decimal("1000"),
        lot_cost_base=Decimal("1000"),
    )
    omitted_lot = PositionLotState(
        lot_id="LOT-BUY02",
        source_transaction_id="BUY02",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        acquisition_date=date(2026, 1, 2),
        original_quantity=Decimal("5"),
        open_quantity=Decimal("5"),
        lot_cost_local=Decimal("500"),
        lot_cost_base=Decimal("500"),
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [selected_lot]
    db_session.execute.return_value = execute_result

    await repository.update_selected_open_lot_states(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        states_by_source_transaction_id={
            "BUY01": OpenLotState(
                original_quantity=Decimal("10"),
                quantity=Decimal("4"),
                cost_local=Decimal("400"),
                cost_base=Decimal("420"),
            )
        },
        transition_evidence=_transition_evidence(),
    )

    assert selected_lot.open_quantity == Decimal("4")
    assert selected_lot.lot_cost_local == Decimal("400")
    assert selected_lot.lot_cost_base == Decimal("420")
    assert omitted_lot.open_quantity == Decimal("5")
    assert omitted_lot.lot_cost_local == Decimal("500")
    assert omitted_lot.lot_cost_base == Decimal("500")
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "position_lot_state.source_transaction_id IN ('BUY01')" in compiled_query


async def test_lot_state_lineage_binds_trigger_and_prior_state_for_identical_output() -> None:
    def lot_row(*, prior_marker: str) -> PositionLotState:
        prior_lineage = build_calculation_lineage(
            algorithm_id="prior-lot-state",
            algorithm_version=1,
            intermediate_precision=28,
            input_payload={"marker": prior_marker},
            output_payload={"quantity": Decimal("10")},
        )
        return PositionLotState(
            lot_id=f"LOT-{prior_marker}",
            source_transaction_id="BUY01",
            portfolio_id="PORT_COST_01",
            instrument_id="SEC01",
            security_id="SEC01",
            acquisition_date=date(2026, 1, 1),
            original_quantity=Decimal("10"),
            open_quantity=Decimal("10"),
            lot_cost_local=Decimal("1000"),
            lot_cost_base=Decimal("1000"),
            calculation_lineage=prior_lineage.lineage_payload(),
        )

    async def update(
        row: PositionLotState,
        *,
        trigger_marker: str,
    ) -> str:
        db_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        db_session.execute.return_value = result
        evidence = CostBasisStateTransitionEvidence(
            trigger_transaction_id="SELL01",
            transition_kind="selected_lots",
            transition_lineage=build_calculation_lineage(
                algorithm_id="trigger-cost-basis",
                algorithm_version=1,
                intermediate_precision=28,
                input_payload={"marker": trigger_marker},
                output_payload={"realized_gain_loss": Decimal("10")},
            ),
        )
        await SqlAlchemyCostBasisLotRepository(db_session).update_selected_open_lot_states(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
            states_by_source_transaction_id={
                "BUY01": OpenLotState(
                    original_quantity=Decimal("10"),
                    quantity=Decimal("4"),
                    cost_local=Decimal("400"),
                    cost_base=Decimal("420"),
                )
            },
            transition_evidence=evidence,
        )
        return str(row.calculation_lineage["input_content_hash"])

    baseline_hash = await update(lot_row(prior_marker="prior-a"), trigger_marker="trigger-a")
    changed_trigger_hash = await update(lot_row(prior_marker="prior-a"), trigger_marker="trigger-b")
    changed_prior_hash = await update(lot_row(prior_marker="prior-b"), trigger_marker="trigger-a")

    assert changed_trigger_hash != baseline_hash
    assert changed_prior_hash != baseline_hash


async def test_update_selected_open_lot_states_rejects_missing_source_lot() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="source lots are missing: BUY01"):
        await repository.update_selected_open_lot_states(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
            states_by_source_transaction_id={
                "BUY01": OpenLotState(
                    original_quantity=Decimal("10"),
                    quantity=Decimal("4"),
                    cost_local=Decimal("400"),
                    cost_base=Decimal("420"),
                )
            },
            transition_evidence=_transition_evidence(),
        )


async def test_update_selected_open_lot_states_skips_empty_selection() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisLotRepository(db_session)

    await repository.update_selected_open_lot_states(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        states_by_source_transaction_id={},
        transition_evidence=_transition_evidence(),
    )

    db_session.execute.assert_not_awaited()


async def test_apply_transaction_costs_and_replace_breakdown_uses_one_atomic_statement() -> None:
    db_session = AsyncMock()
    db_session.add_all = MagicMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)

    db_transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("1002"),
        gross_cost=Decimal("1000"),
        realized_gain_loss=Decimal("0"),
        net_cost_local=Decimal("1002"),
        realized_gain_loss_local=Decimal("0"),
        economic_event_id="EVT-BUY-PORT_COST_01-BUY01",
        linked_transaction_group_id="LTG-BUY-PORT_COST_01-BUY01",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-01",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = db_transaction
    db_session.execute.return_value = execute_result

    engine_transaction = EngineTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 1, 3, 16, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost=Decimal("1002"),
        gross_cost=Decimal("1000"),
        realized_gain_loss=Decimal("0"),
        net_cost_local=Decimal("1002"),
        realized_gain_loss_local=Decimal("0"),
        economic_event_id="EVT-BUY-PORT_COST_01-BUY01",
        linked_transaction_group_id="LTG-BUY-PORT_COST_01-BUY01",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-01",
    )
    calculation_lineage = build_calculation_lineage(
        algorithm_id="transaction-cost-basis-calculation",
        algorithm_version=1,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"transaction_id": "BUY01"},
        output_payload={"net_cost": Decimal("1002")},
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    engine_transaction.set_calculated_field("calculation_lineage", calculation_lineage)
    db_transaction.calculation_lineage = calculation_lineage.lineage_payload()

    updated_transaction = await repository.apply_transaction_costs_and_replace_breakdown(
        engine_transaction
    )

    assert isinstance(updated_transaction, BookedTransaction)
    assert updated_transaction is not db_transaction
    assert updated_transaction.net_cost == Decimal("1002")
    db_session.execute.assert_awaited_once()
    persisted_statement = db_session.execute.await_args.args[0]
    statement_sql = str(persisted_statement)
    assert statement_sql.startswith("WITH updated_transaction AS")
    assert "UPDATE transactions SET" in statement_sql
    assert "economic_event_id=" in statement_sql
    assert "calculation_policy_version=" in statement_sql
    assert "calculation_lineage=" in statement_sql
    assert "DELETE FROM transaction_costs" in statement_sql
    assert "transaction_costs.transaction_id = updated_transaction.transaction_id" in statement_sql
    assert "LEFT OUTER JOIN deleted_transaction_costs ON true" in statement_sql
    assert "RETURNING transactions.id" in statement_sql
    update_parameters = persisted_statement.compile().params
    for field_name in transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS:
        assert f"{field_name}=" in statement_sql
    assert sum(value is None for value in update_parameters.values()) >= len(
        transaction_repository_module.REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS
    )
    db_session.add_all.assert_called_once_with([])


async def test_apply_transaction_costs_fails_closed_without_calculation_lineage() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    transaction = EngineTransaction(
        transaction_id="BUY-NO-LINEAGE",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )

    with pytest.raises(ValueError, match="missing governed calculation lineage"):
        await repository.apply_transaction_costs_and_replace_breakdown(transaction)

    db_session.execute.assert_not_awaited()


async def test_upsert_booked_transaction_persists_only_canonical_table_fields() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCostBasisTransactionRepository(db_session)
    calculation_lineage = build_calculation_lineage(
        algorithm_id="foreign-exchange-baseline-processing",
        algorithm_version=1,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"transaction_id": "FX-OPEN-001"},
        output_payload={"net_cost": Decimal("0")},
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    )

    transaction = BookedTransaction(
        transaction_id=" FX-OPEN-001 ",
        portfolio_id="PORT_COST_01",
        instrument_id="FXC-2026-0001",
        security_id="FXC-2026-0001",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_contract_id="FXC-2026-0001",
        brokerage=Decimal("10"),
        epoch=7,
        calculation_lineage=calculation_lineage,
    )

    persisted_transaction = DBTransaction(
        transaction_id="FX-OPEN-001",
        portfolio_id=transaction.portfolio_id,
        instrument_id=transaction.instrument_id,
        security_id=transaction.security_id,
        transaction_type=transaction.transaction_type,
        component_type=transaction.component_type,
        transaction_date=transaction.transaction_date,
        settlement_date=transaction.settlement_date,
        quantity=transaction.quantity,
        price=transaction.price,
        gross_transaction_amount=transaction.gross_transaction_amount,
        trade_currency=transaction.trade_currency,
        currency=transaction.currency,
        buy_currency=transaction.buy_currency,
        sell_currency=transaction.sell_currency,
        buy_amount=transaction.buy_amount,
        sell_amount=transaction.sell_amount,
        contract_rate=transaction.contract_rate,
        fx_contract_id=transaction.fx_contract_id,
        calculation_lineage=calculation_lineage.lineage_payload(),
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.one_or_none.return_value = persisted_transaction
    db_session.execute.return_value = execute_result

    result = await repository.upsert_booked_transaction(
        transaction,
        fields_to_clear=frozenset({"external_cash_transaction_id", "linked_component_ids"}),
    )

    assert result.transaction_id == "FX-OPEN-001"
    assert result.calculation_lineage == calculation_lineage
    db_session.execute.assert_awaited_once()
    statement = db_session.execute.await_args.args[0]
    parameters = statement.compile().params
    assert parameters["transaction_id"] == "FX-OPEN-001"
    assert parameters["calculation_lineage"] == calculation_lineage.lineage_payload()
    assert parameters["external_cash_transaction_id"] is None
    assert parameters["linked_component_ids"] is None
    assert "brokerage" not in parameters
    assert "epoch" not in parameters
