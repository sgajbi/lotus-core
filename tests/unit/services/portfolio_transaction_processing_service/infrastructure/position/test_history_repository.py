"""Test SQLAlchemy mapping at the position-history repository boundary."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import PositionHistory, Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import PositionHistoryRecord
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
    _position_history_replay_lock_key,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    PositionMaterializationProgress,
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
async def test_save_records_maps_domain_records_without_eager_flush() -> None:
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
    session.flush.assert_not_awaited()


def test_repository_excludes_production_unused_legacy_reads() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)

    assert not hasattr(repository, "find_open_security_ids_as_of")
    assert not hasattr(repository, "get_latest_business_date")
    assert not hasattr(repository, "get_transaction_by_id")


@pytest.mark.asyncio
async def test_load_materialization_progress_normalizes_position_key_in_one_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.one.return_value = (date(2026, 5, 27), date(2026, 5, 28))
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    progress = await repository.load_materialization_progress(
        portfolio_id=" PORT_COST_01 ", security_id=" SEC01 ", epoch=42
    )

    assert progress == PositionMaterializationProgress(
        latest_history_date=date(2026, 5, 27),
        latest_completed_snapshot_date=date(2026, 5, 28),
    )
    session.execute.assert_awaited_once()
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
    assert "trim(daily_position_snapshots.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(daily_position_snapshots.security_id) = 'SEC01'" in compiled_query
    assert "daily_position_snapshots.epoch = 42" in compiled_query


@pytest.mark.asyncio
async def test_acquire_replay_lock_uses_stable_normalized_key() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(
        session,
        clock=MagicMock(side_effect=[10.0, 10.125]),
    )

    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure."
        "position.history_repository.observe_position_history_replay_lock_wait"
    ) as observe_wait:
        await repository.acquire_replay_lock(
            portfolio_id=" PORT_COST_01 ", security_id=" SEC01 ", epoch=42
        )

    statement = session.execute.call_args.args[0]
    assert str(statement) == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert statement.compile().params == {
        "lock_key": _position_history_replay_lock_key("PORT_COST_01", "SEC01", 42)
    }
    assert _position_history_replay_lock_key(" PORT_COST_01 ", " SEC01 ", 42) == (
        _position_history_replay_lock_key("PORT_COST_01", "SEC01", 42)
    )
    observe_wait.assert_called_once_with(outcome="acquired", seconds=0.125)


@pytest.mark.asyncio
async def test_acquire_replay_lock_records_failure_without_swallowing() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = RuntimeError("lock unavailable")
    repository = SqlAlchemyPositionHistoryRepository(
        session,
        clock=MagicMock(side_effect=[20.0, 20.25]),
    )

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "position.history_repository.observe_position_history_replay_lock_wait"
        ) as observe_wait,
        pytest.raises(RuntimeError, match="lock unavailable"),
    ):
        await repository.acquire_replay_lock(portfolio_id="P1", security_id="S1", epoch=7)

    observe_wait.assert_called_once_with(outcome="failed", seconds=0.25)


@pytest.mark.asyncio
async def test_contains_transaction_normalizes_lineage_and_position_key() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = 42
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    materialized = await repository.contains_transaction(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        transaction_id=" TX01 ",
        epoch=7,
    )

    assert materialized is True
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "trim(position_history.transaction_id) = 'TX01'" in compiled_query
    assert "position_history.epoch = 7" in compiled_query
    assert "LIMIT 1" in compiled_query


@pytest.mark.asyncio
async def test_list_transactions_from_normalizes_key_and_orders_deterministically() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    transactions = await repository.list_transactions_from(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        transaction_date=date(2026, 5, 28),
    )

    assert transactions == ()
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert "transactions.transaction_date >= '2026-05-28 00:00:00'" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC"
        in compiled_query
    )


@pytest.mark.asyncio
async def test_delete_records_from_normalizes_key_and_epoch() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.rowcount = 3
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    deleted_count = await repository.delete_records_from(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        position_date=date(2026, 5, 28),
        epoch=42,
    )

    assert deleted_count == 3
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "position_history.position_date >= '2026-05-28'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
