from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    cashflow_repository,
)

pytestmark = pytest.mark.asyncio


async def test_create_cashflow_reuses_existing_row_on_duplicate() -> None:
    db_session = AsyncMock()
    db_session.add = MagicMock()
    nested_tx = AsyncMock()
    nested_tx.__aenter__.return_value = None
    nested_tx.__aexit__.return_value = None
    db_session.begin_nested = MagicMock(return_value=nested_tx)
    db_session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    existing_cashflow = Cashflow(
        id=17,
        transaction_id="TXN-001",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 12),
        amount=Decimal("-1000"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=3,
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = existing_cashflow
    db_session.execute.return_value = execute_result

    repository = cashflow_repository.SqlAlchemyCashflowRepository(db_session)
    duplicate_cashflow = Cashflow(
        transaction_id="TXN-001",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 12),
        amount=Decimal("-1000"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=3,
    )

    saved_cashflow = await repository.create_cashflow(duplicate_cashflow)

    assert saved_cashflow.cashflow_id == 17
    assert saved_cashflow.transaction_id == "TXN-001"
    assert saved_cashflow.amount == Decimal("-1000")
    db_session.refresh.assert_not_awaited()
    db_session.execute.assert_awaited_once()


async def test_create_cashflow_maps_domain_result_at_repository_boundary() -> None:
    db_session = AsyncMock()
    db_session.add = MagicMock()
    nested_tx = AsyncMock()
    nested_tx.__aenter__.return_value = None
    nested_tx.__aexit__.return_value = None
    db_session.begin_nested = MagicMock(return_value=nested_tx)
    db_session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    existing_cashflow = Cashflow(
        id=18,
        transaction_id="TXN-DOMAIN-001",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 12),
        amount=Decimal("-1000"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=4,
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = existing_cashflow
    db_session.execute.return_value = execute_result
    calculated = CalculatedCashflow(
        transaction_id="TXN-DOMAIN-001",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 12),
        amount=Decimal("-1000"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        epoch=4,
    )

    saved = await cashflow_repository.SqlAlchemyCashflowRepository(
        db_session
    ).create_cashflow(calculated)

    mapped_row = db_session.add.call_args.args[0]
    assert isinstance(mapped_row, Cashflow)
    assert mapped_row.transaction_id == calculated.transaction_id
    assert mapped_row.economic_event_id == "EVENT-001"
    assert mapped_row.linked_transaction_group_id == "GROUP-001"
    assert saved.cashflow_id == 18
