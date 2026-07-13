"""Verify atomic position-history rebuild behavior against PostgreSQL."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
import pytest_asyncio
from portfolio_common.database_models import OutboxEvent, Portfolio, PositionHistory, PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.history import (
    PositionHistoryRecord,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.booked import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_position_history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_position_recalculation_state_store import (  # noqa: E501
    SqlAlchemyPositionRecalculationStateStore,
)
from src.services.portfolio_transaction_processing_service.app.ports.position_history import (
    PositionHistoryObserver,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]

PORTFOLIO_ID = "E2E_REPRO_ATOM_01"
SECURITY_ID = "SEC_REPRO_ATOM_01"


class _FailingPositionHistoryRepository(SqlAlchemyPositionHistoryRepository):
    """Fail the final persistence step to prove caller-owned transaction rollback."""

    async def save_records(self, records: tuple[PositionHistoryRecord, ...]) -> None:
        del records
        raise RuntimeError("position persistence failed")


@pytest_asyncio.fixture(scope="function")
async def setup_repro_atomicity_data(clean_db, async_db_session: AsyncSession) -> None:
    """Seed one current position stream with a later transaction."""
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


def _backdated_transaction() -> BookedTransaction:
    """Build the framework-neutral command that invalidates the current stream."""
    return BookedTransaction(
        transaction_id="TXN_ATOM_BACKDATED",
        portfolio_id=PORTFOLIO_ID,
        instrument_id="ATS",
        security_id=SECURITY_ID,
        transaction_date=datetime(2025, 9, 5, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("9"),
        gross_transaction_amount=Decimal("90"),
        net_cost=Decimal("90"),
        net_cost_local=Decimal("90"),
        trade_currency="USD",
        currency="USD",
        epoch=None,
    )


def _position_history_processor(
    session: AsyncSession,
    *,
    repository: SqlAlchemyPositionHistoryRepository | None = None,
) -> PositionHistoryProcessor:
    """Compose the application processor with caller-owned SQL adapters."""
    return PositionHistoryProcessor(
        repository=repository or SqlAlchemyPositionHistoryRepository(session),
        state_store=SqlAlchemyPositionRecalculationStateStore(PositionStateRepository(session)),
        observer=Mock(spec=PositionHistoryObserver),
    )


async def test_inline_reprocessing_rolls_back_epoch_when_position_persistence_fails(
    setup_repro_atomicity_data: None,
    async_db_session: AsyncSession,
) -> None:
    del setup_repro_atomicity_data
    processor = _position_history_processor(
        async_db_session,
        repository=_FailingPositionHistoryRepository(async_db_session),
    )
    with pytest.raises(RuntimeError, match="position persistence failed"):
        async with async_db_session.begin():
            await processor.process(_backdated_transaction())

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
    transaction = _backdated_transaction()
    async_db_session.add(
        DBTransaction(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            instrument_id=transaction.instrument_id,
            security_id=transaction.security_id,
            transaction_date=transaction.transaction_date,
            transaction_type=transaction.transaction_type,
            quantity=transaction.quantity,
            price=transaction.price,
            gross_transaction_amount=transaction.gross_transaction_amount,
            net_cost=transaction.net_cost,
            net_cost_local=transaction.net_cost_local,
            trade_currency=transaction.trade_currency,
            currency=transaction.currency,
        )
    )
    await async_db_session.commit()

    async with async_db_session.begin():
        result = await _position_history_processor(async_db_session).process(transaction)

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
