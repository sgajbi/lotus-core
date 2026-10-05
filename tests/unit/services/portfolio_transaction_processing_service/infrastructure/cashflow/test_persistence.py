from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow
from portfolio_common.domain.calculation_lineage import build_calculation_lineage

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
    numeric_policy,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    SqlAlchemyCashflowRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("missing", [None, "tenant", "epoch", "receipt"])
async def test_no_effect_requires_owned_semantic_stage_and_no_transaction_epoch_ledger(missing):
    transaction = BookedTransaction(
        transaction_id="TX",
        portfolio_id="PORT",
        security_id="SEC",
        instrument_id="SEC",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
        tenant_id=None if missing == "tenant" else "tenant-test",
        epoch=None if missing == "epoch" else 4,
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None if missing == "receipt" else 42
    session.execute.return_value = result
    receipt = await SqlAlchemyCashflowRepository(session).load_materialized_no_effect(
        transaction, semantic_event_id="cashflow:PORT:TX:4"
    )
    assert (receipt is None) == (missing is not None)
    if missing in {"tenant", "epoch"}:
        session.execute.assert_not_awaited()
        return
    statement = session.execute.await_args.args[0]
    query = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "processed_events.tenant_id = 'tenant-test'" in query
    assert "portfolios.tenant_id = 'tenant-test'" in query
    assert "processed_events.portfolio_id = 'PORT'" in query
    assert "processed_events.service_name = 'cashflow-calculator'" in query
    assert "processed_events.event_id = 'cashflow:PORT:TX:4'" in query
    assert "cashflows.transaction_id = 'TX'" in query
    assert "cashflows.epoch = 4" in query
    assert "cashflows.id IS NULL" in query
    assert statement._for_update_arg.read is True
    assert session.execute.await_count == 1


@pytest.mark.parametrize("missing", [None, "tenant", "receipt", "ledger"])
async def test_materialized_read_requires_preexisting_receipt_and_scoped_ledger(missing):
    calculated = CalculatedCashflow(
        transaction_id="TX-QUALIFIED",
        portfolio_id="PB-QUALIFIED",
        security_id="SEC-QUALIFIED",
        cashflow_date=date(2026, 4, 10),
        amount=Decimal("0"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=None,
        linked_transaction_group_id=None,
        epoch=4,
    )
    row = Cashflow(
        id=91,
        transaction_id=calculated.transaction_id,
        portfolio_id=calculated.portfolio_id,
        security_id=calculated.security_id,
        cashflow_date=calculated.cashflow_date,
        amount=calculated.amount,
        currency=calculated.currency,
        classification=calculated.classification,
        timing=calculated.timing,
        calculation_type=calculated.calculation_type,
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=4,
    )
    receipt_result, ledger_result = MagicMock(), MagicMock()
    receipt_result.scalar_one_or_none.return_value = None if missing == "receipt" else 42
    ledger_result.scalars.return_value.one_or_none.return_value = (
        None if missing == "ledger" else row
    )
    session = AsyncMock()
    session.execute.side_effect = [receipt_result, ledger_result]
    stored = await SqlAlchemyCashflowRepository(session).load_materialized(
        calculated,
        tenant_id="" if missing == "tenant" else "tenant-test",
        semantic_event_id="cashflow:PB-QUALIFIED:TX-QUALIFIED:4",
    )
    if missing is not None:
        assert stored is None
    else:
        assert stored is not None
        assert stored.amount == Decimal("0")
        assert stored.transaction_id == "TX-QUALIFIED"
        assert stored.epoch == 4
    if missing == "tenant":
        session.execute.assert_not_awaited()
        return
    receipt_statement = session.execute.await_args_list[0].args[0]
    assert receipt_statement._for_update_arg.read is True
    assert receipt_statement.compile().params == {
        "tenant_id_1": "tenant-test",
        "portfolio_id_1": "PB-QUALIFIED",
        "service_name_1": "cashflow-calculator",
        "event_id_1": "cashflow:PB-QUALIFIED:TX-QUALIFIED:4",
    }
    if missing == "receipt":
        assert session.execute.await_count == 1
        return
    ledger_statement = session.execute.await_args_list[1].args[0]
    assert ledger_statement._for_update_arg.read is True
    assert ledger_statement.compile().params == {
        "tenant_id_1": "tenant-test",
        "portfolio_id_1": "PB-QUALIFIED",
        "security_id_1": "SEC-QUALIFIED",
        "transaction_id_1": "TX-QUALIFIED",
        "epoch_1": 4,
    }
    assert session.execute.await_count == 2


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
