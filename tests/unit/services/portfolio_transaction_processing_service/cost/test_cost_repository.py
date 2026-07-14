from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    PositionLotState,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501  # noqa: E501
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
    CostBasisProcessingCheckpoint,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculatorRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyAverageCostPoolRepository,
)

pytestmark = pytest.mark.asyncio


async def test_get_transaction_history_trims_portfolio_security_and_excluded_transaction_ids():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    execute_result = MagicMock()
    persisted_transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )
    execute_result.scalars.return_value.all.return_value = [persisted_transaction]
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


async def test_get_booked_transaction_maps_domain_transaction_and_scopes_portfolio() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)
    persisted_transaction = DBTransaction(
        transaction_id="CASH01",
        portfolio_id="PORT_COST_01",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="CASH_OUTFLOW",
        transaction_date=datetime(2026, 1, 3, 10, 0, 0),
        quantity=Decimal("1000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
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
    )
    assert transaction is not persisted_transaction
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "transactions.transaction_id = 'CASH01'" in compiled_query
    assert "transactions.portfolio_id = 'PORT_COST_01'" in compiled_query


async def test_get_open_lot_checkpoint_records_returns_only_positive_lots() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)
    transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0),
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
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "position_lot_state.open_quantity > 0" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.quantity DESC, "
        "transactions.transaction_id ASC"
    ) in compiled_query


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
        transaction_date=datetime(2026, 1, 2),
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
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ON CONFLICT (portfolio_id, security_id) DO UPDATE" in compiled_query
    assert "updated_at = now()" in compiled_query
    assert stmt.compile().params["portfolio_id"] == "P1"
    assert stmt.compile().params["security_id"] == "S1"
    assert stmt.compile().params["instrument_id"] == "I1"
    assert stmt.compile().params["representative_source_transaction_id"] == "BUY-2"


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


def _average_cost_rebuild_plan() -> AverageCostPoolRebuildPlan:
    first = _average_cost_source(
        "BUY-1",
        transaction_date=datetime(2026, 1, 1, 10, 0),
        quantity="10",
        cost="100",
    )
    second = _average_cost_source(
        "BUY-2",
        transaction_date=datetime(2026, 1, 2, 10, 0),
        quantity="5",
        cost="80",
    )
    states = {
        "BUY-1": OpenLotState(
            quantity=Decimal("6"),
            cost_local=Decimal("72"),
            cost_base=Decimal("78"),
        ),
        "BUY-2": OpenLotState(
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
        source_transactions=(first, second),
        source_states=states,
    )


async def test_apply_average_cost_pool_rebuild_bulk_replaces_lot_and_pool_state() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    repository.REBUILD_UPSERT_CHUNK_SIZE = 1

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
    source_upsert_sql = str(
        db_session.execute.call_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "INSERT INTO position_lot_state" in source_upsert_sql
    assert "ON CONFLICT (source_transaction_id) DO UPDATE" in source_upsert_sql
    assert "'BUY-1'" in source_upsert_sql
    assert "open_quantity" in source_upsert_sql
    assert "6" in source_upsert_sql
    assert "INSERT INTO average_cost_pool_state" in str(
        db_session.execute.call_args_list[3].args[0]
    )


async def test_get_average_cost_pool_persisted_summary_maps_missing_pool_and_source_sums() -> None:
    db_session = AsyncMock()
    pool_result = MagicMock()
    pool_result.scalars.return_value.first.return_value = None
    source_result = MagicMock()
    source_result.one.return_value = (
        2,
        Decimal("9"),
        Decimal("108"),
        Decimal("117"),
    )
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


async def test_apply_average_cost_pool_transition_scales_sources_and_assigns_residual() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    scale_result = MagicMock()
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = (
        Decimal("7"),
        Decimal("70"),
        Decimal("77"),
    )
    residual_result = MagicMock(rowcount=1)
    upsert_result = MagicMock()
    db_session.execute.side_effect = [
        scale_result,
        aggregate_result,
        residual_result,
        upsert_result,
    ]
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            quantity=Decimal("9"),
            cost_local=Decimal("108"),
            cost_base=Decimal("117"),
        ),
        explicit_sources_after={},
    )

    await repository.apply_average_cost_pool_transition(transition)

    scale_sql = str(
        db_session.execute.call_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "open_quantity=trunc(" in scale_sql
    assert "position_lot_state.open_quantity * 9" in scale_sql
    assert "CAST(15 AS NUMERIC(18, 10))" in scale_sql
    assert "lot_cost_local=round(" in scale_sql
    assert "position_lot_state.lot_cost_local * 108" in scale_sql
    assert "source_transaction_id != 'BUY-2'" in scale_sql
    residual_sql = str(
        db_session.execute.call_args_list[2].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "source_transaction_id = 'BUY-2'" in residual_sql
    assert "open_quantity=2" in residual_sql
    assert "lot_cost_local=38" in residual_sql
    assert "lot_cost_base=40" in residual_sql
    upsert_sql = str(
        db_session.execute.call_args_list[3].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "INSERT INTO average_cost_pool_state" in upsert_sql


async def test_apply_average_cost_pool_transition_rejects_missing_close_sources() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    close_result = MagicMock(rowcount=0)
    db_session.execute.return_value = close_result
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
        ),
        explicit_sources_after={},
    )

    with pytest.raises(ValueError, match="found no persisted source lots"):
        await repository.apply_average_cost_pool_transition(transition)

    assert db_session.execute.await_count == 1


async def test_apply_average_cost_pool_transition_rejects_negative_residual() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = (
        Decimal("10"),
        Decimal("109"),
        Decimal("118"),
    )
    db_session.execute.side_effect = [MagicMock(), aggregate_result]
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=OpenLotState(
            quantity=Decimal("9"),
            cost_local=Decimal("108"),
            cost_base=Decimal("117"),
        ),
        explicit_sources_after={},
    )

    with pytest.raises(ValueError, match="exceeds the target pool aggregate"):
        await repository.apply_average_cost_pool_transition(transition)

    assert db_session.execute.await_count == 2


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
        quantity=Decimal("5"),
        cost_local=Decimal("70"),
        cost_base=Decimal("75"),
    )
    transition = AverageCostPoolTransition(
        before=_average_cost_checkpoint(),
        existing_sources_after=_average_cost_checkpoint().as_open_lot_state(),
        explicit_sources_after={"BUY-3": explicit_state},
    )

    await repository.apply_average_cost_pool_transition(transition)

    assert db_session.execute.await_count == 2
    selected_update_sql = str(
        db_session.execute.call_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "source_transaction_id IN ('BUY-3')" in selected_update_sql
    checkpoint_sql = str(
        db_session.execute.call_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "'BUY-3'" in checkpoint_sql


async def test_get_fifo_disposal_lots_streams_only_quantity_covering_oldest_lots() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)
    lots_and_transactions = []
    for sequence, (quantity, transaction_date) in enumerate(
        (
            ("4", datetime(2026, 1, 1, 10, 0, 0)),
            ("5", datetime(2026, 1, 2, 10, 0, 0)),
            ("7", datetime(2026, 1, 3, 10, 0, 0)),
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
    repository = CostCalculatorRepository(db_session)

    with pytest.raises(ValueError, match="quantity must be positive"):
        await repository.get_fifo_disposal_lot_checkpoint_records(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
            required_quantity=Decimal(0),
        )

    db_session.stream.assert_not_awaited()


async def test_update_open_lot_states_trims_ids_and_reconciles_quantity_and_cost():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

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
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [lot_row, closed_lot_row]
    db_session.execute.return_value = execute_result

    await repository.update_open_lot_states(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        states_by_source_transaction_id={
            "BUY01": OpenLotState(
                quantity=Decimal("4"),
                cost_local=Decimal("400"),
                cost_base=Decimal("420"),
            )
        },
    )

    assert lot_row.open_quantity == Decimal("4")
    assert lot_row.lot_cost_local == Decimal("400")
    assert lot_row.lot_cost_base == Decimal("420")
    assert closed_lot_row.open_quantity == Decimal("0")
    assert closed_lot_row.lot_cost_local == Decimal("0")
    assert closed_lot_row.lot_cost_base == Decimal("0")
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_lot_state.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_lot_state.security_id) = 'SEC01'" in compiled_query


async def test_update_selected_open_lot_states_does_not_close_omitted_lots() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
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
                quantity=Decimal("4"),
                cost_local=Decimal("400"),
                cost_base=Decimal("420"),
            )
        },
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


async def test_update_selected_open_lot_states_rejects_missing_source_lot() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="source lots are missing: BUY01"):
        await repository.update_selected_open_lot_states(
            portfolio_id="PORT_COST_01",
            security_id="SEC01",
            states_by_source_transaction_id={
                "BUY01": OpenLotState(
                    quantity=Decimal("4"),
                    cost_local=Decimal("400"),
                    cost_base=Decimal("420"),
                )
            },
        )


async def test_update_selected_open_lot_states_skips_empty_selection() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyAverageCostPoolRepository(db_session)

    await repository.update_selected_open_lot_states(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        states_by_source_transaction_id={},
    )

    db_session.execute.assert_not_awaited()


async def test_apply_transaction_costs_persists_linkage_metadata() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    db_transaction = DBTransaction(
        transaction_id="BUY01",
        portfolio_id="PORT_COST_01",
        instrument_id="SEC01",
        security_id="SEC01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1, 10, 0, 0),
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
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
        transaction_date=datetime(2026, 1, 1, 10, 0, 0),
        settlement_date=datetime(2026, 1, 3, 16, 0, 0),
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

    updated_transaction = await repository.apply_transaction_costs(engine_transaction)

    assert isinstance(updated_transaction, BookedTransaction)
    assert updated_transaction is not db_transaction
    assert updated_transaction.net_cost == Decimal("1002")
    assert db_transaction.net_cost == Decimal("1002")
    assert db_transaction.economic_event_id == "EVT-BUY-PORT_COST_01-BUY01"
    assert db_transaction.linked_transaction_group_id == "LTG-BUY-PORT_COST_01-BUY01"
    assert db_transaction.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert db_transaction.calculation_policy_version == "1.0.0"
    assert db_transaction.cash_entry_mode == "AUTO_GENERATE"
    assert db_transaction.settlement_cash_account_id == "CASH-USD-01"


async def test_upsert_transaction_event_ignores_event_envelope_fields() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    event = TransactionEvent(
        event_type="ProcessedTransactionPersisted",
        schema_version="1.0.0",
        correlation_id="ING:FX-CORR-01",
        transaction_id="FX-OPEN-001",
        portfolio_id="PORT_COST_01",
        instrument_id="FXC-2026-0001",
        security_id="FXC-2026-0001",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        settlement_date=datetime(2026, 7, 1, 0, 0, 0),
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
    )

    result = await repository.upsert_transaction_event(event)

    assert result is None
    db_session.execute.assert_awaited_once()
    statement = db_session.execute.await_args.args[0]
    parameters = statement.compile().params
    assert parameters["transaction_id"] == "FX-OPEN-001"
    assert "event_type" not in parameters
    assert "schema_version" not in parameters
    assert "correlation_id" not in parameters
