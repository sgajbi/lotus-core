from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import CostBasisProcessingState, PositionLotState
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BUY_DEFAULT_POLICY_ID,
    BUY_DEFAULT_POLICY_VERSION,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculationWorkflow,
    CostCalculatorRepository,
    CostProcessingCompatibilityAdapter,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyAverageCostPoolRepository,
    SqlAlchemyCorporateActionReconciliationRepository,
    SqlAlchemyCostBasisFxRateRepository,
    SqlAlchemyCostBasisLotRepository,
    SqlAlchemyCostBasisProcessingStateRepository,
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.income import (
    SqlAlchemyAccruedIncomeOffsetRepository,
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


class _HeldHistoryCostRepository(CostCalculatorRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        history_read: asyncio.Event,
        release_history: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._history_read = history_read
        self._release_history = release_history

    async def get_transaction_history(
        self,
        portfolio_id: str,
        security_id: str,
        exclude_id: str | None = None,
    ):
        history = await super().get_transaction_history(portfolio_id, security_id, exclude_id)
        self._history_read.set()
        await self._release_history.wait()
        return history


class _ObservedProcessingStateRepository(SqlAlchemyCostBasisProcessingStateRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        lock_attempted: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._lock_attempted = lock_attempted

    async def acquire_cost_basis_processing_lock(
        self,
        portfolio_id: str,
        security_id: str,
    ) -> None:
        self._lock_attempted.set()
        await super().acquire_cost_basis_processing_lock(portfolio_id, security_id)


async def _stage_cost_calculation(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event,
    repository_factory,
    processing_state_factory=SqlAlchemyCostBasisProcessingStateRepository,
) -> None:
    async with session_factory() as session, session.begin():
        await CostProcessingCompatibilityAdapter(
            workflow=CostCalculationWorkflow(),
            repository=repository_factory(session),
            average_cost_pools=SqlAlchemyAverageCostPoolRepository(session),
            lot_states=SqlAlchemyCostBasisLotRepository(session),
            income_offsets=SqlAlchemyAccruedIncomeOffsetRepository(session),
            reference_data=SqlAlchemyCostBasisReferenceDataRepository(session),
            fx_rates=SqlAlchemyCostBasisFxRateRepository(session),
            processing_state=processing_state_factory(session),
            reconciliation_repository=SqlAlchemyCorporateActionReconciliationRepository(session),
            outbox_repository=AsyncMock(spec=OutboxRepository),
        ).stage_event(
            event=event,
            correlation_id=f"corr-{event.transaction_id}",
        )


async def test_same_key_buy_sell_and_replay_serialize_to_deterministic_fifo_lot_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COST-LOCK-01"
    security_id = "SEC-COST-LOCK-01"
    buy = booked_transaction_event(
        transaction_id="BUY-COST-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    sell = booked_transaction_event(
        transaction_id="SELL-COST-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="60",
        price="15",
        gross_amount="900",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Cost Lock Proof Equity",
                isin="SG0000000484",
                currency="USD",
            ),
            canonical_transaction_record(buy),
        ]
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    buy_history_read = asyncio.Event()
    release_buy_history = asyncio.Event()
    sell_lock_attempted = asyncio.Event()
    replay_lock_attempted = asyncio.Event()

    buy_task = asyncio.create_task(
        _stage_cost_calculation(
            session_factory=session_factory,
            event=buy,
            repository_factory=lambda session: _HeldHistoryCostRepository(
                session,
                history_read=buy_history_read,
                release_history=release_buy_history,
            ),
        )
    )
    await asyncio.wait_for(buy_history_read.wait(), timeout=2)

    async with session_factory() as insert_session, insert_session.begin():
        insert_session.add(canonical_transaction_record(sell))

    sell_task = asyncio.create_task(
        _stage_cost_calculation(
            session_factory=session_factory,
            event=sell,
            repository_factory=CostCalculatorRepository,
            processing_state_factory=lambda session: _ObservedProcessingStateRepository(
                session,
                lock_attempted=sell_lock_attempted,
            ),
        )
    )
    replay_task = asyncio.create_task(
        _stage_cost_calculation(
            session_factory=session_factory,
            event=sell,
            repository_factory=CostCalculatorRepository,
            processing_state_factory=lambda session: _ObservedProcessingStateRepository(
                session,
                lock_attempted=replay_lock_attempted,
            ),
        )
    )
    await asyncio.wait_for(
        asyncio.gather(sell_lock_attempted.wait(), replay_lock_attempted.wait()),
        timeout=2,
    )
    await asyncio.sleep(0.1)

    assert sell_task.done() is False
    assert replay_task.done() is False

    release_buy_history.set()
    await asyncio.wait_for(
        asyncio.gather(buy_task, sell_task, replay_task),
        timeout=8,
    )

    async with session_factory() as verification_session:
        lots = list(
            (
                await verification_session.scalars(
                    select(PositionLotState).where(
                        PositionLotState.portfolio_id == portfolio_id,
                        PositionLotState.security_id == security_id,
                    )
                )
            ).all()
        )
        checkpoint = (
            await verification_session.scalars(
                select(CostBasisProcessingState).where(
                    CostBasisProcessingState.portfolio_id == portfolio_id,
                    CostBasisProcessingState.security_id == security_id,
                )
            )
        ).one()

    assert len(lots) == 1
    assert lots[0].source_transaction_id == buy.transaction_id
    assert lots[0].open_quantity == Decimal("40")
    assert lots[0].lot_cost_local == Decimal("400")
    assert lots[0].lot_cost_base == Decimal("400")
    assert lots[0].calculation_policy_id == BUY_DEFAULT_POLICY_ID
    assert lots[0].calculation_policy_version == BUY_DEFAULT_POLICY_VERSION
    assert checkpoint.cost_basis_method == "FIFO"
    assert checkpoint.latest_transaction_id == sell.transaction_id
    assert checkpoint.engine_state_version == "open-lot-v1"


async def test_cost_basis_processing_lock_does_not_serialize_other_security_keys(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with (
        session_factory() as owning_session,
        owning_session.begin(),
        session_factory() as other_security_session,
        other_security_session.begin(),
    ):
        await SqlAlchemyCostBasisProcessingStateRepository(
            owning_session
        ).acquire_cost_basis_processing_lock(
            "PORT-COST-LOCK-02",
            "SEC-COST-LOCK-01",
        )
        await asyncio.wait_for(
            SqlAlchemyCostBasisProcessingStateRepository(
                other_security_session
            ).acquire_cost_basis_processing_lock(
                "PORT-COST-LOCK-02",
                "SEC-COST-LOCK-02",
            ),
            timeout=1,
        )
