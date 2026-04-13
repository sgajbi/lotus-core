from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction as DBTransaction

from src.services.calculators.cost_calculator_service.app.cost_engine.domain.models.transaction import (
    Transaction as EngineTransaction,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)


pytestmark = pytest.mark.asyncio


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
