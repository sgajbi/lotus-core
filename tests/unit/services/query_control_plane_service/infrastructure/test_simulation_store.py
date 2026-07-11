"""Test SQLAlchemy generic simulation adapters and record mapping."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.domain.simulation import SimulationSession
from src.services.query_control_plane_service.app.infrastructure.simulation_store import (
    SqlAlchemySimulationBaselineReader,
    SqlAlchemySimulationStore,
)

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _session() -> SimulationSession:
    return SimulationSession(
        session_id="S1",
        portfolio_id="P1",
        status="ACTIVE",
        version=2,
        created_by="tester",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )


async def test_stage_session_adds_row_without_committing(db: AsyncMock):
    store = SqlAlchemySimulationStore(db)

    await store.stage_session(
        session_id="S1",
        portfolio_id="P1",
        created_by="tester",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=12),
    )

    row = db.add.call_args.args[0]
    assert row.session_id == "S1"
    assert row.status == "ACTIVE"
    assert row.version == 1
    db.commit.assert_not_awaited()


async def test_get_session_returns_immutable_record(db: AsyncMock):
    result = MagicMock()
    row = SimpleNamespace(
        session_id="S1",
        portfolio_id="P1",
        status="ACTIVE",
        version=2,
        created_by="tester",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )
    result.scalars.return_value.first.return_value = row
    db.execute.return_value = result

    session = await SqlAlchemySimulationStore(db).get_session("S1")

    assert session == _session()
    assert session is not row


async def test_stage_session_close_updates_status_and_version(db: AsyncMock):
    await SqlAlchemySimulationStore(db).stage_session_close("S1", version=3)

    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "UPDATE simulation_sessions" in sql
    assert "status='CLOSED'" in sql
    assert "version=3" in sql


async def test_stage_changes_updates_version_and_adds_normalized_rows(db: AsyncMock):
    store = SqlAlchemySimulationStore(db)

    await store.stage_changes(
        _session(),
        version=3,
        changes=[
            {
                "change_id": "C1",
                "security_id": "SEC_AAPL_US",
                "transaction_type": "BUY",
                "quantity": "10",
                "price": "100.5",
                "amount": " ",
                "currency": "USD",
                "effective_date": date(2026, 7, 1),
                "metadata": {"source": "test"},
            }
        ],
    )

    update_sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    row = db.add.call_args.args[0]
    assert "version=3" in update_sql
    assert row.quantity == Decimal("10")
    assert row.price == Decimal("100.5")
    assert row.amount is None


async def test_stage_change_delete_returns_false_without_version_update(db: AsyncMock):
    delete_result = SimpleNamespace(rowcount=0)
    db.execute.return_value = delete_result

    deleted = await SqlAlchemySimulationStore(db).stage_change_delete("S1", "C404", version=3)

    assert deleted is False
    assert db.execute.await_count == 1


async def test_stage_change_delete_updates_version_after_delete(db: AsyncMock):
    db.execute.side_effect = [SimpleNamespace(rowcount=1), MagicMock()]

    deleted = await SqlAlchemySimulationStore(db).stage_change_delete("S1", "C1", version=3)

    assert deleted is True
    update_sql = str(
        db.execute.await_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "UPDATE simulation_sessions" in update_sql
    assert "version=3" in update_sql


async def test_get_changes_returns_ordered_immutable_records(db: AsyncMock):
    row = SimpleNamespace(
        change_id="C1",
        session_id="S1",
        portfolio_id="P1",
        security_id="SEC_AAPL_US",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=None,
        amount=None,
        currency="USD",
        effective_date=date(2026, 7, 1),
        change_metadata={"source": "test"},
        created_at=NOW,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db.execute.return_value = result

    changes = await SqlAlchemySimulationStore(db).get_changes("S1")

    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY simulation_changes.created_at ASC, simulation_changes.id ASC" in sql
    assert changes[0].quantity == Decimal("10")
    assert changes[0].metadata == {"source": "test"}
    assert changes[0] is not row


async def test_portfolio_exists_uses_bounded_identity_query(db: AsyncMock):
    result = MagicMock()
    result.scalar_one_or_none.return_value = "P1"
    db.execute.return_value = result

    exists = await SqlAlchemySimulationBaselineReader(db).portfolio_exists("P1")

    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert exists is True
    assert "WHERE portfolios.portfolio_id = 'P1'" in sql
    assert "LIMIT 1" in sql


async def test_current_positions_map_reconciled_snapshot_rows(db: AsyncMock):
    snapshot = SimpleNamespace(
        security_id="SEC_AAPL_US",
        date=date(2026, 6, 30),
        quantity=Decimal("100"),
        cost_basis=Decimal("900"),
        cost_basis_local=Decimal("1000"),
    )
    instrument = SimpleNamespace(name="Apple", asset_class="Equity")
    result = MagicMock()
    result.all.return_value = [(snapshot, instrument)]
    db.execute.return_value = result

    positions = await SqlAlchemySimulationBaselineReader(db).get_current_positions("P1")

    sql = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "daily_position_snapshots.quantity = anon_2.quantity" in sql
    assert "position_state" in sql
    assert positions[0].security_id == "SEC_AAPL_US"
    assert positions[0].cost_basis_local == Decimal("1000")


async def test_current_positions_fall_back_to_current_epoch_history(db: AsyncMock):
    snapshot_result = MagicMock()
    snapshot_result.all.return_value = []
    history = SimpleNamespace(
        security_id="SEC_AAPL_US",
        position_date=date(2026, 6, 30),
        quantity=Decimal("100"),
        cost_basis=Decimal("900"),
        cost_basis_local=Decimal("1000"),
    )
    instrument = SimpleNamespace(name="Apple", asset_class="Equity")
    history_result = MagicMock()
    history_result.all.return_value = [(history, instrument)]
    db.execute.side_effect = [snapshot_result, history_result]

    positions = await SqlAlchemySimulationBaselineReader(db).get_current_positions("P1")

    history_sql = str(
        db.execute.await_args_list[1]
        .args[0]
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "position_history.epoch = position_state.epoch" in history_sql
    assert positions[0].position_date == date(2026, 6, 30)


async def test_get_instruments_normalizes_ids_and_returns_records(db: AsyncMock):
    result = MagicMock()
    row = SimpleNamespace(security_id="SEC_AAPL_US", name="Apple", asset_class="Equity")
    result.scalars.return_value.all.return_value = [row]
    db.execute.return_value = result

    instruments = await SqlAlchemySimulationBaselineReader(db).get_instruments(
        [" SEC_AAPL_US ", ""]
    )

    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "trim(instruments.security_id) IN ('SEC_AAPL_US')" in sql
    assert instruments[0].name == "Apple"
    assert instruments[0] is not row
