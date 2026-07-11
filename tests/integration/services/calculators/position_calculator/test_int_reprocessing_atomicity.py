from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from portfolio_common.database_models import OutboxEvent, Portfolio, PositionHistory, PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow import (  # noqa: E501
    PositionCalculationWorkflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_repository import (  # noqa: E501
    PositionRepository,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]

PORTFOLIO_ID = "E2E_REPRO_ATOM_01"
SECURITY_ID = "SEC_REPRO_ATOM_01"


class _FailingPositionRepository(PositionRepository):
    async def save_positions(self, positions) -> None:
        del positions
        raise RuntimeError("position persistence failed")


@pytest_asyncio.fixture(scope="function")
async def setup_repro_atomicity_data(clean_db, async_db_session: AsyncSession) -> None:
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id=PORTFOLIO_ID,
                base_currency="USD",
                open_date=date(2025, 1, 1),
                client_id="ATOM_CIF",
                status="ACTIVE",
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
            ),
            PositionState(
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                watermark_date=date(2025, 9, 9),
                epoch=0,
                status="CURRENT",
            ),
            DBTransaction(
                transaction_id="TXN_ATOM_CURRENT",
                portfolio_id=PORTFOLIO_ID,
                instrument_id="ATS",
                security_id=SECURITY_ID,
                transaction_date=datetime(2025, 9, 10, 10, tzinfo=timezone.utc),
                transaction_type="BUY",
                quantity=100,
                price=10,
                gross_transaction_amount=1000,
                net_cost=1000,
                net_cost_local=1000,
                trade_currency="USD",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()


def _backdated_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN_ATOM_BACKDATED",
        portfolio_id=PORTFOLIO_ID,
        instrument_id="ATS",
        security_id=SECURITY_ID,
        transaction_date=datetime(2025, 9, 5, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=10,
        price=9,
        gross_transaction_amount=90,
        net_cost=90,
        net_cost_local=90,
        trade_currency="USD",
        currency="USD",
        epoch=None,
    )


async def test_inline_reprocessing_rolls_back_epoch_when_position_persistence_fails(
    setup_repro_atomicity_data: None,
    async_db_session: AsyncSession,
) -> None:
    del setup_repro_atomicity_data
    with pytest.raises(RuntimeError, match="position persistence failed"):
        async with async_db_session.begin():
            await PositionCalculationWorkflow.calculate(
                event=_backdated_event(),
                db_session=async_db_session,
                repo=_FailingPositionRepository(async_db_session),
                position_state_repo=PositionStateRepository(async_db_session),
            )

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as verification_session:
        state = (
            await verification_session.scalars(
                select(PositionState).where(
                    PositionState.portfolio_id == PORTFOLIO_ID,
                    PositionState.security_id == SECURITY_ID,
                )
            )
        ).one()
        position_count = await verification_session.scalar(select(func.count(PositionHistory.id)))

    assert state.epoch == 0
    assert state.status == "CURRENT"
    assert position_count == 0


async def test_inline_reprocessing_deduplicates_trigger_and_emits_no_replay_event(
    setup_repro_atomicity_data: None,
    async_db_session: AsyncSession,
) -> None:
    del setup_repro_atomicity_data
    event = _backdated_event()
    async_db_session.add(
        DBTransaction(
            transaction_id=event.transaction_id,
            portfolio_id=event.portfolio_id,
            instrument_id=event.instrument_id,
            security_id=event.security_id,
            transaction_date=event.transaction_date,
            transaction_type=event.transaction_type,
            quantity=event.quantity,
            price=event.price,
            gross_transaction_amount=event.gross_transaction_amount,
            net_cost=event.net_cost,
            net_cost_local=event.net_cost_local,
            trade_currency=event.trade_currency,
            currency=event.currency,
        )
    )
    await async_db_session.commit()

    async with async_db_session.begin():
        result = await PositionCalculationWorkflow.calculate(
            event=event,
            db_session=async_db_session,
            repo=PositionRepository(async_db_session),
            position_state_repo=PositionStateRepository(async_db_session),
        )

    positions = list(
        (
            await async_db_session.scalars(
                select(PositionHistory)
                .where(
                    PositionHistory.portfolio_id == PORTFOLIO_ID,
                    PositionHistory.security_id == SECURITY_ID,
                    PositionHistory.epoch == 1,
                )
                .order_by(PositionHistory.position_date, PositionHistory.transaction_id)
            )
        ).all()
    )
    replay_event_count = await async_db_session.scalar(
        select(func.count(OutboxEvent.id)).where(
            OutboxEvent.event_type == "ReprocessTransactionReplay"
        )
    )

    assert result.position_record_count == 2
    assert [position.transaction_id for position in positions] == [
        "TXN_ATOM_BACKDATED",
        "TXN_ATOM_CURRENT",
    ]
    assert [position.quantity for position in positions] == [10, 110]
    assert replay_event_count == 0
