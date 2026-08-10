"""Verify the initial opening cost-state aggregate statement."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyInitialOpeningCostStateRepository,
)


@pytest.mark.asyncio
async def test_initial_opening_state_executes_three_writes_as_one_postgresql_statement() -> None:
    transaction = CostBasisTransaction(
        transaction_id="BUY-ATOMIC-INITIAL-1",
        portfolio_id="PORT-ATOMIC-1",
        instrument_id="INSTRUMENT-ATOMIC-1",
        security_id="SECURITY-ATOMIC-1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 8, 10, 10, 0),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("9800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("9840"),
        net_cost=Decimal("9840"),
        accrued_interest=Decimal("125"),
    )
    checkpoint = CostBasisProcessingCheckpoint.from_transaction(
        transaction,
        cost_basis_method=CostBasisMethod.FIFO,
    )
    transaction.calculation_lineage = build_calculation_lineage(
        algorithm_id="initial-opening-state-test",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"transaction_id": transaction.transaction_id},
        output_payload={"net_cost": transaction.net_cost},
    )
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result

    await SqlAlchemyInitialOpeningCostStateRepository(session).persist_initial_opening_cost_state(
        transaction=transaction,
        checkpoint=checkpoint,
    )

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert compiled.count("INSERT INTO") == 3
    assert "UPDATE transactions SET" in compiled
    assert "DELETE FROM transaction_costs" in compiled
    assert "persist_initial_opening_lot AS" in compiled
    assert "persist_initial_income_offset AS" in compiled
    assert "persist_initial_processing_checkpoint AS" in compiled
    assert "INSERT INTO cost_basis_processing_state" in compiled
    assert compiled.count("ON CONFLICT") == 3


@pytest.mark.parametrize(
    ("checkpoint_change", "value"),
    [
        ("portfolio_id", "PORT-OTHER"),
        ("security_id", "SECURITY-OTHER"),
        ("latest_transaction_id", "BUY-OTHER"),
    ],
)
@pytest.mark.asyncio
async def test_initial_opening_state_rejects_mismatched_aggregate_scope_before_sql(
    checkpoint_change: str,
    value: str,
) -> None:
    transaction = CostBasisTransaction(
        transaction_id="BUY-ATOMIC-INITIAL-1",
        portfolio_id="PORT-ATOMIC-1",
        instrument_id="INSTRUMENT-ATOMIC-1",
        security_id="SECURITY-ATOMIC-1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 8, 10, 10, 0),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("9800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )
    checkpoint = replace(
        CostBasisProcessingCheckpoint.from_transaction(
            transaction,
            cost_basis_method=CostBasisMethod.FIFO,
        ),
        **{checkpoint_change: value},
    )
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(ValueError, match="checkpoint scope must match"):
        await SqlAlchemyInitialOpeningCostStateRepository(
            session
        ).persist_initial_opening_cost_state(
            transaction=transaction,
            checkpoint=checkpoint,
        )

    session.execute.assert_not_awaited()
