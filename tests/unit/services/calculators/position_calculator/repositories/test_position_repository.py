from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)

pytestmark = pytest.mark.asyncio


async def test_get_latest_completed_snapshot_date_trims_portfolio_and_security_ids():
    db_session = AsyncMock()
    repository = PositionRepository(db_session)

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = date(2026, 5, 28)
    db_session.execute.return_value = execute_result

    latest_date = await repository.get_latest_completed_snapshot_date(
        " PORT_COST_01 ", " SEC01 ", 42
    )

    assert latest_date == date(2026, 5, 28)
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(daily_position_snapshots.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(daily_position_snapshots.security_id) = 'SEC01'" in compiled_query
    assert "daily_position_snapshots.epoch = 42" in compiled_query


async def test_find_open_security_ids_as_of_trims_portfolio_and_security_id_partition():
    db_session = AsyncMock()
    repository = PositionRepository(db_session)

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = ["SEC01"]
    db_session.execute.return_value = execute_result

    security_ids = await repository.find_open_security_ids_as_of(
        " PORT_COST_01 ", date(2026, 5, 28)
    )

    assert security_ids == ["SEC01"]
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(daily_position_snapshots.security_id) AS security_id" in compiled_query
    assert "PARTITION BY trim(daily_position_snapshots.security_id)" in compiled_query
    assert "trim(daily_position_snapshots.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "daily_position_snapshots.date <= '2026-05-28'" in compiled_query


async def test_get_transactions_on_or_after_trims_portfolio_and_security_ids():
    db_session = AsyncMock()
    repository = PositionRepository(db_session)

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db_session.execute.return_value = execute_result

    transactions = await repository.get_transactions_on_or_after(
        " PORT_COST_01 ", " SEC01 ", date(2026, 5, 28)
    )

    assert transactions == []
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert "transactions.transaction_date >= '2026-05-28 00:00:00'" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC"
        in compiled_query
    )


async def test_get_transaction_by_id_trims_transaction_and_optional_portfolio_id():
    db_session = AsyncMock()
    repository = PositionRepository(db_session)

    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = None
    db_session.execute.return_value = execute_result

    transaction = await repository.get_transaction_by_id(" TX01 ", portfolio_id=" PORT_COST_01 ")

    assert transaction is None
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.transaction_id) = 'TX01'" in compiled_query
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query


async def test_delete_positions_from_trims_portfolio_and_security_ids():
    db_session = AsyncMock()
    repository = PositionRepository(db_session)

    execute_result = MagicMock()
    execute_result.rowcount = 3
    db_session.execute.return_value = execute_result

    deleted_count = await repository.delete_positions_from(
        " PORT_COST_01 ", " SEC01 ", date(2026, 5, 28), 42
    )

    assert deleted_count == 3
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "position_history.position_date >= '2026-05-28'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
