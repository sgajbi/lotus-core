from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow
from portfolio_common.domain.calculation_lineage import build_calculation_lineage

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
    numeric_policy,
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
    lineage = build_calculation_lineage(
        algorithm_id="transaction-cashflow",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={"gross_transaction_amount": Decimal("1000")},
        output_payload={"amount": Decimal("995")},
        numeric_output_policy=numeric_policy.CASHFLOW_LEDGER_OUTPUT_V1.lineage_identity(),
    )
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
        calculation_lineage=lineage,
    )

    saved = await SqlAlchemyCashflowRepository(db_session).create(calculated)

    assert saved.cashflow_id == 19
    assert saved.transaction_id == "TXN-DOMAIN-002"
    assert saved.amount == Decimal("995")
    assert saved.calculation_lineage == lineage
    statement = db_session.execute.await_args.args[0]
    assert statement.compile().params["calculation_lineage"] == lineage.lineage_payload()
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


@pytest.mark.parametrize(
    ("portfolio_exists", "transaction_exists"),
    [
        (True, True),
        (False, False),
    ],
)
async def test_reference_existence_reads_return_database_truth(
    portfolio_exists: bool,
    transaction_exists: bool,
) -> None:
    db_session = AsyncMock()
    portfolio_result = MagicMock()
    portfolio_result.scalar_one_or_none.return_value = "PORT-001" if portfolio_exists else None
    transaction_result = MagicMock()
    transaction_result.scalar_one_or_none.return_value = "TXN-001" if transaction_exists else None
    db_session.execute.side_effect = [portfolio_result, transaction_result]
    repository = SqlAlchemyCashflowRepository(db_session)

    assert await repository.portfolio_exists("PORT-001") is portfolio_exists
    assert (
        await repository.transaction_exists("TXN-001", portfolio_id="PORT-001")
        is transaction_exists
    )

    transaction_statement = db_session.execute.await_args_list[1].args[0]
    assert "transactions.portfolio_id" in str(transaction_statement)


async def test_transaction_existence_read_allows_unscoped_identity_lookup() -> None:
    db_session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "TXN-001"
    db_session.execute.return_value = result

    exists = await SqlAlchemyCashflowRepository(db_session).transaction_exists("TXN-001")

    assert exists is True
    statement = db_session.execute.await_args.args[0]
    assert "transactions.portfolio_id" not in str(statement)


async def test_create_fails_closed_when_conflict_winner_cannot_be_read() -> None:
    db_session = AsyncMock()
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    missing_result = MagicMock()
    missing_result.scalars.return_value.first.return_value = None
    db_session.execute.side_effect = [insert_result, missing_result]
    cashflow = Cashflow(
        transaction_id="TXN-MISSING-001",
        portfolio_id="PORT-001",
        security_id=None,
        cashflow_date=date(2026, 4, 15),
        amount=Decimal("10"),
        currency="USD",
        classification="INCOME",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=False,
        is_portfolio_flow=True,
        epoch=7,
    )

    with pytest.raises(
        RuntimeError,
        match="conflicted without an existing transaction/epoch row",
    ):
        await SqlAlchemyCashflowRepository(db_session).create(cashflow)
