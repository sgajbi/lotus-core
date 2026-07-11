from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import PositionHistory, PositionState
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow import (  # noqa: E501
    PositionCalculationResult,
    PositionCalculationWorkflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_repository import (  # noqa: E501
    PositionRepository,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
    pytest.mark.resilience,
]


class _HeldLockPositionRepository(PositionRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        lock_acquired: asyncio.Event,
        release_lock: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._lock_acquired = lock_acquired
        self._release_lock = release_lock

    async def acquire_position_history_replay_lock(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
    ) -> None:
        await super().acquire_position_history_replay_lock(portfolio_id, security_id, epoch)
        self._lock_acquired.set()
        await self._release_lock.wait()


class _ObservedLockPositionRepository(PositionRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        lock_attempted: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._lock_attempted = lock_attempted

    async def acquire_position_history_replay_lock(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
    ) -> None:
        self._lock_attempted.set()
        await super().acquire_position_history_replay_lock(portfolio_id, security_id, epoch)


async def _calculate_position(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event,
    repository_factory,
) -> PositionCalculationResult:
    async with session_factory() as session, session.begin():
        return await PositionCalculationWorkflow.calculate(
            event,
            session,
            repository_factory(session),
            PositionStateRepository(session),
        )


async def test_same_key_recalculations_serialize_and_leave_exact_position_history(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-POSITION-LOCK-01"
    security_id = "SEC-POSITION-LOCK-01"
    first_event = booked_transaction_event(
        transaction_id="BUY-POSITION-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="10",
        gross_amount="100",
        net_cost=Decimal("100"),
        net_cost_local=Decimal("100"),
        epoch=0,
    )
    second_event = booked_transaction_event(
        transaction_id="BUY-POSITION-LOCK-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="5",
        price="12",
        gross_amount="60",
        net_cost=Decimal("60"),
        net_cost_local=Decimal("60"),
        epoch=0,
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Position Lock Proof Equity",
                isin="SG0000000482",
                currency="USD",
            ),
            canonical_transaction_record(first_event),
            canonical_transaction_record(second_event),
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=0,
                watermark_date=date(1970, 1, 1),
                status="CURRENT",
            ),
        ]
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    first_lock_acquired = asyncio.Event()
    release_first_lock = asyncio.Event()
    second_lock_attempted = asyncio.Event()

    first_task = asyncio.create_task(
        _calculate_position(
            session_factory=session_factory,
            event=first_event,
            repository_factory=lambda session: _HeldLockPositionRepository(
                session,
                lock_acquired=first_lock_acquired,
                release_lock=release_first_lock,
            ),
        )
    )
    await asyncio.wait_for(first_lock_acquired.wait(), timeout=2)
    second_task = asyncio.create_task(
        _calculate_position(
            session_factory=session_factory,
            event=second_event,
            repository_factory=lambda session: _ObservedLockPositionRepository(
                session,
                lock_attempted=second_lock_attempted,
            ),
        )
    )
    await asyncio.wait_for(second_lock_attempted.wait(), timeout=2)
    await asyncio.sleep(0.1)

    assert second_task.done() is False

    release_first_lock.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first_task, second_task),
        timeout=5,
    )

    assert first_result.position_record_count == 2
    assert second_result.position_record_count == 1
    async with session_factory() as verification_session:
        positions = list(
            (
                await verification_session.scalars(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                        PositionHistory.epoch == 0,
                    )
                    .order_by(PositionHistory.position_date, PositionHistory.transaction_id)
                )
            ).all()
        )

    assert [position.transaction_id for position in positions] == [
        "BUY-POSITION-LOCK-01",
        "BUY-POSITION-LOCK-02",
    ]
    assert [position.quantity for position in positions] == [Decimal("10"), Decimal("15")]
    assert [position.cost_basis for position in positions] == [Decimal("100"), Decimal("160")]
    assert [position.cost_basis_local for position in positions] == [
        Decimal("100"),
        Decimal("160"),
    ]


async def test_position_recalculation_lock_does_not_serialize_other_keys_or_epochs(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with (
        session_factory() as owning_session,
        owning_session.begin(),
        session_factory() as other_security_session,
        session_factory() as other_epoch_session,
    ):
        await PositionRepository(owning_session).acquire_position_history_replay_lock(
            "PORT-POSITION-LOCK-02",
            "SEC-POSITION-LOCK-01",
            0,
        )
        async with other_security_session.begin():
            await asyncio.wait_for(
                PositionRepository(other_security_session).acquire_position_history_replay_lock(
                    "PORT-POSITION-LOCK-02",
                    "SEC-POSITION-LOCK-02",
                    0,
                ),
                timeout=1,
            )
        async with other_epoch_session.begin():
            await asyncio.wait_for(
                PositionRepository(other_epoch_session).acquire_position_history_replay_lock(
                    "PORT-POSITION-LOCK-02",
                    "SEC-POSITION-LOCK-01",
                    1,
                ),
                timeout=1,
            )
