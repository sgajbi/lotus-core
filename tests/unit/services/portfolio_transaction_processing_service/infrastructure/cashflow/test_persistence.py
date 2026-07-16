from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    SqlAlchemyCashflowRepository,
)

pytestmark = pytest.mark.asyncio


async def test_create_reuses_existing_row_on_duplicate() -> None:
    db_session = AsyncMock()

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
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalars.return_value.first.return_value = existing_cashflow
    db_session.execute.side_effect = [insert_result, existing_result]

    repository = SqlAlchemyCashflowRepository(db_session)
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

    saved_cashflow = await repository.create(duplicate_cashflow)

    assert saved_cashflow.cashflow_id == 17
    assert saved_cashflow.transaction_id == "TXN-001"
    assert saved_cashflow.amount == Decimal("-1000")
    assert db_session.execute.await_count == 2


async def test_create_maps_domain_result_at_repository_boundary() -> None:
    db_session = AsyncMock()
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
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        epoch=4,
    )
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalars.return_value.first.return_value = existing_cashflow
    db_session.execute.side_effect = [insert_result, existing_result]
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

    saved = await SqlAlchemyCashflowRepository(db_session).create(calculated)

    assert saved.cashflow_id == 18
    assert saved.economic_event_id == "EVENT-001"
    assert saved.linked_transaction_group_id == "GROUP-001"
    assert db_session.execute.await_count == 2


async def test_create_persists_domain_result_successfully() -> None:
    db_session = AsyncMock()
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = 19
    db_session.execute.return_value = insert_result
    calculated = CalculatedCashflow(
        transaction_id="TXN-DOMAIN-002",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 13),
        amount=Decimal("995"),
        currency="USD",
        classification="INVESTMENT_INFLOW",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=None,
        linked_transaction_group_id=None,
        epoch=5,
    )

    saved = await SqlAlchemyCashflowRepository(db_session).create(calculated)

    assert saved.cashflow_id == 19
    assert saved.transaction_id == "TXN-DOMAIN-002"
    assert saved.amount == Decimal("995")
    db_session.execute.assert_awaited_once()


async def test_replace_returns_updated_domain_result_from_one_database_write() -> None:
    db_session = AsyncMock()
    update_result = MagicMock()
    update_result.scalar_one.return_value = 21
    db_session.execute.return_value = update_result
    calculated = CalculatedCashflow(
        transaction_id="TXN-DOMAIN-003",
        portfolio_id="PORT-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 14),
        amount=Decimal("125"),
        currency="USD",
        classification="INCOME",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id="EVENT-003",
        linked_transaction_group_id="GROUP-003",
        epoch=6,
    )

    saved = await SqlAlchemyCashflowRepository(db_session).replace(calculated)

    assert saved.cashflow_id == 21
    assert saved.transaction_id == "TXN-DOMAIN-003"
    assert saved.amount == Decimal("125")
    assert saved.economic_event_id == "EVENT-003"
    assert saved.linked_transaction_group_id == "GROUP-003"
    db_session.execute.assert_awaited_once()
