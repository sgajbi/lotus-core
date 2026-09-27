from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.adapters.event_record_mapper import (
    transaction_event_to_record_values,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)


@pytest.mark.asyncio
async def test_create_or_update_transaction_requires_admitted_tenant() -> None:
    db = AsyncMock(spec=AsyncSession)
    event = TransactionEvent(
        transaction_id="TX_NO_TENANT_001",
        portfolio_id="P1",
        tenant_id=None,
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )

    with pytest.raises(ValueError, match="requires an admitted tenant"):
        await TransactionDBRepository(db).create_or_update_transaction(event)

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_update_transaction_uses_canonical_currency_codes() -> None:
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "TX_CANONICAL_CCY_001"
    db.execute.return_value = execute_result
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_CANONICAL_CCY_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency=" usd ",
        currency=" usd ",
        pair_base_currency=" eur ",
        pair_quote_currency=" usd ",
        buy_currency=" usd ",
        sell_currency=" eur ",
        synthetic_flow_currency=" sgd ",
    )

    outcome = await repo.create_or_update_transaction(event)
    persisted = outcome.transaction

    assert outcome.inserted is True
    assert persisted.trade_currency == "USD"
    assert persisted.currency == "USD"
    assert persisted.pair_base_currency == "EUR"
    assert persisted.pair_quote_currency == "USD"
    assert persisted.buy_currency == "USD"
    assert persisted.sell_currency == "EUR"
    assert persisted.synthetic_flow_currency == "SGD"
    db.execute.assert_awaited_once()
    db.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_create_or_update_transaction_persists_aggregated_trade_fee() -> None:
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "TX_FEE_COMPONENTS_001"
    db.execute.return_value = execute_result
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_FEE_COMPONENTS_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.00"),
        brokerage=Decimal("2.50"),
        stamp_duty=Decimal("1.20"),
        exchange_fee=Decimal("0.70"),
        gst=Decimal("0.45"),
        other_fees=Decimal("0.15"),
    )

    outcome = await repo.create_or_update_transaction(event)
    persisted = outcome.transaction

    assert outcome.inserted is True
    assert persisted.trade_fee == Decimal("5.00")
    assert not hasattr(persisted, "brokerage")
    assert db.execute.await_count == 2
    fee_insert = db.execute.await_args_list[1].args[0]
    assert "INSERT INTO transaction_costs" in str(fee_insert.compile())
    db.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_create_or_update_transaction_clears_explicit_zero_named_fee_authority() -> None:
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "TX_ZERO_FEE_COMPONENTS_001"
    db.execute.return_value = execute_result
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_ZERO_FEE_COMPONENTS_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        brokerage=Decimal(0),
        stamp_duty=Decimal(0),
        exchange_fee=Decimal(0),
        gst=Decimal(0),
        other_fees=Decimal(0),
    )

    outcome = await repo.create_or_update_transaction(event)
    persisted = outcome.transaction

    assert outcome.inserted is True
    assert persisted.trade_fee == Decimal(0)
    assert db.execute.await_count == 1
    db.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_create_or_update_transaction_rejects_changed_durable_payload() -> None:
    db = AsyncMock(spec=AsyncSession)
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = DBTransaction(
        transaction_id="TX_CONFLICT_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal(0),
        payload_fingerprint="sha256:" + "a" * 64,
    )
    db.execute.side_effect = [insert_result, existing_result]
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_CONFLICT_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("11"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1100"),
        trade_currency="USD",
        currency="USD",
    )

    with pytest.raises(
        TransactionSemanticConflictError,
        match="TRANSACTION_SEMANTIC_CONFLICT",
    ):
        await repo.create_or_update_transaction(event)

    assert db.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_tenant_id", "expected_error"),
    [
        ("tenant-test", TransactionSemanticConflictError),
        ("tenant-other", GeneratedTransactionIdentityCollisionError),
    ],
)
async def test_portfolio_change_classifies_tenant_boundary(
    existing_tenant_id: str,
    expected_error: type[Exception],
) -> None:
    db = AsyncMock(spec=AsyncSession)
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = DBTransaction(
        transaction_id="TX_PORTFOLIO_CONFLICT_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal(0),
        payload_fingerprint="sha256:" + "a" * 64,
    )
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = existing_tenant_id
    db.execute.side_effect = [insert_result, existing_result, tenant_result]
    event = TransactionEvent(
        transaction_id="TX_PORTFOLIO_CONFLICT_001",
        portfolio_id="P2",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )

    with pytest.raises(expected_error):
        await TransactionDBRepository(db).create_or_update_transaction(event)

    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_create_or_update_transaction_returns_locked_durable_replay_outcome() -> None:
    db = AsyncMock(spec=AsyncSession)
    event = TransactionEvent(
        transaction_id="TX_REPLAY_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"),
        tenant_id="tenant-test",
    )
    existing = DBTransaction(
        transaction_id=event.transaction_id,
        portfolio_id=event.portfolio_id,
        instrument_id=event.instrument_id,
        security_id=event.security_id,
        transaction_date=event.transaction_date,
        transaction_type=event.transaction_type,
        quantity=event.quantity,
        price=event.price,
        gross_transaction_amount=event.gross_transaction_amount,
        trade_currency=event.trade_currency,
        currency=event.currency,
        trade_fee=event.trade_fee,
        payload_fingerprint=identity.payload_fingerprint,
    )
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing
    db.execute.side_effect = [insert_result, existing_result]

    outcome = await TransactionDBRepository(db).create_or_update_transaction(event)

    assert outcome.inserted is False
    assert outcome.transaction is existing


@pytest.mark.asyncio
async def test_create_or_update_transaction_rejects_existing_foreign_identity() -> None:
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="SOURCE-1-CASHLEG",
        portfolio_id="PORT-1",
        tenant_id="tenant-test",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="ADJUSTMENT",
        quantity=Decimal("0"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        originating_transaction_id="SOURCE-1",
        originating_transaction_type="BUY",
        cash_entry_mode="AUTO_GENERATE",
        link_type="BUY_TO_CASH",
    )

    with pytest.raises(
        GeneratedTransactionIdentityCollisionError,
        match="generated_transaction_identity_collision",
    ):
        await repo.create_or_update_transaction(event)

    statement = db.execute.await_args.args[0]
    assert "WHERE" in str(statement.compile())


@pytest.mark.asyncio
async def test_create_or_update_transaction_persists_canonical_generated_identity() -> None:
    db = AsyncMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "SOURCE-1-CASHLEG"
    db.execute.return_value = execute_result
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="  SOURCE-1-CASHLEG  ",
        portfolio_id="  PORT-1  ",
        tenant_id="tenant-test",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="ADJUSTMENT",
        quantity=Decimal("0"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        originating_transaction_id="  SOURCE-1  ",
        originating_transaction_type=" buy ",
        cash_entry_mode="AUTO_GENERATE",
        link_type="BUY_TO_CASH",
    )

    outcome = await repo.create_or_update_transaction(event)
    persisted = outcome.transaction

    assert outcome.inserted is True
    assert persisted.transaction_id == "SOURCE-1-CASHLEG"
    assert persisted.portfolio_id == "PORT-1"
    assert persisted.originating_transaction_id == "SOURCE-1"
    assert persisted.originating_transaction_type == "BUY"


def test_transaction_event_to_record_values_excludes_traceparent_envelope() -> None:
    event = TransactionEvent(
        transaction_id="TX_TRACEPARENT_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        correlation_id="corr-transaction",
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    )

    values = transaction_event_to_record_values(event)

    assert "correlation_id" not in values
    assert "traceparent" not in values
    assert values["transaction_id"] == "TX_TRACEPARENT_001"


@pytest.mark.asyncio
async def test_transaction_reference_availability_uses_one_query_without_cash_account() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.one.return_value = (True, True, None)
    db.execute.return_value = result
    repo = TransactionDBRepository(db)

    availability = await repo.resolve_transaction_reference_availability(
        portfolio_id="P1",
        tenant_id="tenant-test",
        security_id=" SEC-1 ",
        cash_account_id=None,
        cash_security_id=None,
        as_of_date=date(2026, 3, 27),
    )

    stmt = db.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.portfolio_id = 'P1'" in compiled_query
    assert "trim(instruments.security_id) = 'SEC-1'" in compiled_query
    assert availability.portfolio_exists is True
    assert availability.instrument_exists is True
    assert availability.cash_account_exists is None
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_transaction_reference_availability_includes_active_cash_account() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.one.return_value = (True, True, True)
    db.execute.return_value = result
    repo = TransactionDBRepository(db)

    availability = await repo.resolve_transaction_reference_availability(
        portfolio_id="P1",
        tenant_id="tenant-test",
        security_id="SEC-1",
        cash_account_id=" CASH-ACC-1 ",
        cash_security_id=" CASH_USD ",
        as_of_date=date(2026, 3, 27),
    )

    stmt = db.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "cash_account_masters.portfolio_id = 'P1'" in compiled_query
    assert "cash_account_masters.cash_account_id = 'CASH-ACC-1'" in compiled_query
    assert "upper(trim(cash_account_masters.lifecycle_status)) = 'ACTIVE'" in compiled_query
    assert "cash_account_masters.opened_on <= '2026-03-27'" in compiled_query
    assert "cash_account_masters.closed_on >= '2026-03-27'" in compiled_query
    assert "trim(cash_account_masters.security_id) = 'CASH_USD'" in compiled_query
    assert availability.cash_account_exists is True
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_transaction_reference_availability_allows_cash_account_without_security_filter() -> (
    None
):
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.one.return_value = (True, True, True)
    db.execute.return_value = result

    availability = await TransactionDBRepository(db).resolve_transaction_reference_availability(
        portfolio_id="P1",
        tenant_id="tenant-test",
        security_id="SEC-1",
        cash_account_id="CASH-ACC-1",
        cash_security_id=None,
        as_of_date=date(2026, 3, 27),
    )

    compiled_query = str(
        db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "cash_account_masters.cash_account_id = 'CASH-ACC-1'" in compiled_query
    assert "trim(cash_account_masters.security_id)" not in compiled_query
    assert availability.cash_account_exists is True
