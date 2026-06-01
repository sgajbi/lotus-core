from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import FxRate, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction

from src.services.calculators.cost_calculator_service.app.cost_engine.domain.models.transaction import (  # noqa: E501
    Transaction as EngineTransaction,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)

pytestmark = pytest.mark.asyncio


async def test_get_fx_rate_normalizes_currency_codes_and_uses_functional_index_predicates():
    db_session = AsyncMock()
    repository = CostCalculatorRepository(db_session)

    execute_result = MagicMock()
    expected_rate = FxRate(
        from_currency="EUR",
        to_currency="USD",
        rate_date=date(2026, 5, 28),
        rate=Decimal("1.0875"),
    )
    execute_result.scalars.return_value.first.return_value = expected_rate
    db_session.execute.return_value = execute_result

    fx_rate = await repository.get_fx_rate(" eur ", " usd ", date(2026, 5, 28))

    assert fx_rate is expected_rate
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "upper(trim(fx_rates.from_currency)) = 'eur'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'usd'" in compiled_query
    assert "fx_rates.rate_date <= '2026-05-28'" in compiled_query
    assert "order by fx_rates.rate_date desc" in compiled_query


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


async def test_update_lot_open_quantities_trims_portfolio_and_security_ids_before_query():
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
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [lot_row]
    db_session.execute.return_value = execute_result

    await repository.update_lot_open_quantities(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        open_quantities_by_source_transaction_id={"BUY01": Decimal("4")},
    )

    assert lot_row.open_quantity == Decimal("4")
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
