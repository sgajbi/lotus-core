"""Test SQLAlchemy mapping at the position-history repository boundary."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import PositionHistory, Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import PositionHistoryRecord
from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_position_history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
)


@pytest.mark.asyncio
async def test_list_all_transactions_maps_orm_rows_to_booked_transactions() -> None:
    session = AsyncMock(spec=AsyncSession)
    row = Transaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        linked_component_ids=["LEG-1", "LEG-2"],
        dependency_reference_ids=["PARENT-1"],
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    transactions = await repository.list_all_transactions(
        portfolio_id=" PB-001 ",
        security_id=" SEC-001 ",
    )

    assert len(transactions) == 1
    assert transactions[0].transaction_id == "TX-001"
    assert transactions[0].linked_component_ids == ("LEG-1", "LEG-2")
    assert transactions[0].dependency_reference_ids == ("PARENT-1",)
    assert transactions[0].epoch is None


@pytest.mark.asyncio
async def test_last_record_before_maps_nullable_local_basis_to_zero() -> None:
    session = AsyncMock(spec=AsyncSession)
    row = PositionHistory(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=None,
        epoch=2,
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = row
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    record = await repository.last_record_before(
        portfolio_id="PB-001",
        security_id="SEC-001",
        position_date=date(2026, 4, 10),
        epoch=2,
    )

    assert record == PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("0"),
        epoch=2,
    )


@pytest.mark.asyncio
async def test_save_records_maps_domain_records_to_orm_and_flushes() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)
    record = PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 10),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("95"),
        epoch=3,
    )

    await repository.save_records((record,))

    rows = session.add_all.call_args.args[0]
    assert len(rows) == 1
    assert isinstance(rows[0], PositionHistory)
    assert rows[0].portfolio_id == "PB-001"
    assert rows[0].transaction_id == "TX-001"
    assert rows[0].cost_basis_local == Decimal("95")
    session.flush.assert_awaited_once_with()


def test_repository_excludes_production_unused_legacy_reads() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)

    assert not hasattr(repository, "find_open_security_ids_as_of")
    assert not hasattr(repository, "get_latest_business_date")
    assert not hasattr(repository, "get_transaction_by_id")
