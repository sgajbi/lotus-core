from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import CostBasisProcessingState, FxRate, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from src.services.calculators.cost_calculator_service.app.cost_engine.domain.models.effective_fx_rate import (  # noqa: E501
    EffectiveFxRate,
)
from src.services.calculators.cost_calculator_service.app.cost_engine.domain.models.transaction import (  # noqa: E501
    Transaction as EngineTransaction,
)
from src.services.calculators.cost_calculator_service.app.cost_engine.processing.cost_objects import (  # noqa: E501
    OpenLotState,
)
from src.services.calculators.cost_calculator_service.app.cost_processing_checkpoint import (
    CostBasisProcessingCheckpoint,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)

pytestmark = pytest.mark.asyncio


async def test_get_fx_rate_window_fetches_one_seed_plus_bounded_effective_window():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)
    execute_result = MagicMock()
    persisted_rates = [
        FxRate(
            from_currency="EUR",
            to_currency="SGD",
            rate_date=date(2026, 4, 1),
            rate=Decimal("1.40"),
        ),
        FxRate(
            from_currency="EUR",
            to_currency="SGD",
            rate_date=date(2026, 4, 10),
            rate=Decimal("1.45"),
        ),
    ]
    execute_result.scalars.return_value.all.return_value = persisted_rates
    db_session.execute.return_value = execute_result

    rates = await repository.get_fx_rate_window(
        " eur ",
        " sgd ",
        start_date=date(2026, 4, 5),
        end_date=date(2026, 4, 15),
    )

    assert rates == [
        EffectiveFxRate(effective_date=date(2026, 4, 1), rate=Decimal("1.40")),
        EffectiveFxRate(effective_date=date(2026, 4, 10), rate=Decimal("1.45")),
    ]
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "upper(trim(fx_rates.from_currency)) = 'eur'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'sgd'" in compiled_query
    assert "fx_rates.rate_date <= '2026-04-15'" in compiled_query
    assert "fx_rates.rate_date >= '2026-04-05'" in compiled_query
    assert "max(fx_rates_1.rate_date)" in compiled_query
    assert "fx_rates_1.rate_date < '2026-04-05'" in compiled_query
    assert "order by fx_rates.rate_date asc" in compiled_query


async def test_get_fx_rate_window_rejects_reversed_date_bounds():
    repository = CostCalculatorRepository(AsyncMock())

    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        await repository.get_fx_rate_window(
            "EUR",
            "SGD",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 5),
        )


async def test_get_instrument_trims_security_id_before_query():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = None
    db_session.execute.return_value = execute_result

    instrument = await repository.get_instrument(" SEC_A ")

    assert instrument is None
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(instruments.security_id) = 'SEC_A'" in compiled_query


async def test_get_transaction_history_trims_portfolio_security_and_excluded_transaction_ids():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    execute_result = MagicMock()
    expected_transactions = [
        DBTransaction(
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
    ]
    execute_result.scalars.return_value.all.return_value = expected_transactions
    db_session.execute.return_value = execute_result

    transactions = await repository.get_transaction_history(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        exclude_id=" SELL01 ",
    )

    assert transactions == expected_transactions
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert "trim(transactions.transaction_id) != 'SELL01'" in compiled_query
    assert "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC" in (
        compiled_query
    )


async def test_get_cost_basis_processing_checkpoint_maps_durable_ordering_state() -> None:
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)
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
        engine_state_version="open-lot-v1",
    )


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
    assert records[0].transaction is transaction
    assert records[0].quantity == Decimal("4")
    assert records[0].cost_local == Decimal("400")
    assert records[0].cost_base == Decimal("420")
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "position_lot_state.open_quantity > 0" in compiled_query


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


async def test_update_transaction_costs_persists_linkage_metadata() -> None:
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

    updated_transaction = await repository.update_transaction_costs(engine_transaction)

    assert updated_transaction is db_transaction
    assert db_transaction.net_cost == Decimal("1002")
    assert db_transaction.economic_event_id == "EVT-BUY-PORT_COST_01-BUY01"
    assert db_transaction.linked_transaction_group_id == "LTG-BUY-PORT_COST_01-BUY01"
    assert db_transaction.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert db_transaction.calculation_policy_version == "1.0.0"
    assert db_transaction.cash_entry_mode == "AUTO_GENERATE"
    assert db_transaction.settlement_cash_account_id == "CASH-USD-01"


async def test_create_or_update_transaction_event_ignores_event_envelope_fields() -> None:
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

    persisted = await repository.create_or_update_transaction_event(event)

    assert persisted.transaction_id == "FX-OPEN-001"
    assert not hasattr(persisted, "event_type")
    db_session.execute.assert_awaited_once()
