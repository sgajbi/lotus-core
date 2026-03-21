from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.valuation_orchestrator_service.app.core.valuation_scheduler import (
    ValuationScheduler,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def scheduler() -> ValuationScheduler:
    with patch(
        "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.get_kafka_producer",
        return_value=MagicMock(),
    ):
        yield ValuationScheduler(poll_interval=0.01, batch_size=2)


def _seed_backlog_state(
    session: Session,
    *,
    portfolio_id: str,
    security_id: str,
    updated_at: datetime,
    with_history: bool,
) -> None:
    session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    )
    session.add(
        PositionState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=0,
            watermark_date=date(1970, 1, 1),
            status="CURRENT",
            updated_at=updated_at,
        )
    )

    if not with_history:
        return

    tx_id = f"TX-{portfolio_id}-{security_id}"
    session.add(
        Transaction(
            transaction_id=tx_id,
            portfolio_id=portfolio_id,
            instrument_id=security_id,
            security_id=security_id,
            transaction_date=date(2025, 8, 10),
            transaction_type="BUY",
            quantity=1,
            price=1,
            gross_transaction_amount=1,
            trade_currency="USD",
            currency="USD",
        )
    )
    session.flush()
    session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_id=tx_id,
            position_date=date(2025, 8, 10),
            quantity=Decimal("10"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
            epoch=0,
        )
    )


async def test_scheduler_drains_zombie_backlog_and_reaches_fresh_live_key(
    scheduler: ValuationScheduler,
    clean_db,
    async_db_session: AsyncSession,
    db_engine,
):
    latest_business_date = date(2025, 8, 12)
    with Session(db_engine) as session:
        session.add_all(
            [
                BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 10)),
                BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 11)),
                BusinessDate(calendar_code="GLOBAL", date=latest_business_date),
            ]
        )
        base_time = datetime(2025, 8, 12, tzinfo=timezone.utc)
        _seed_backlog_state(
            session,
            portfolio_id="ZOMBIE_P1",
            security_id="ZOMBIE_S1",
            updated_at=base_time,
            with_history=False,
        )
        _seed_backlog_state(
            session,
            portfolio_id="ZOMBIE_P2",
            security_id="ZOMBIE_S2",
            updated_at=base_time + timedelta(seconds=1),
            with_history=False,
        )
        _seed_backlog_state(
            session,
            portfolio_id="ZOMBIE_P3",
            security_id="ZOMBIE_S3",
            updated_at=base_time + timedelta(seconds=2),
            with_history=False,
        )
        _seed_backlog_state(
            session,
            portfolio_id="LIVE_P1",
            security_id="LIVE_S1",
            updated_at=base_time + timedelta(seconds=3),
            with_history=True,
        )
        session.commit()

    await scheduler._create_backfill_jobs(async_db_session)
    await async_db_session.commit()
    async_db_session.expire_all()

    zombie_p1 = await async_db_session.get(PositionState, ("ZOMBIE_P1", "ZOMBIE_S1"))
    zombie_p2 = await async_db_session.get(PositionState, ("ZOMBIE_P2", "ZOMBIE_S2"))
    zombie_p3 = await async_db_session.get(PositionState, ("ZOMBIE_P3", "ZOMBIE_S3"))
    live_state = await async_db_session.get(PositionState, ("LIVE_P1", "LIVE_S1"))

    assert zombie_p1.watermark_date == latest_business_date
    assert zombie_p2.watermark_date == latest_business_date
    assert zombie_p3.watermark_date == date(1970, 1, 1)
    assert live_state.watermark_date == date(1970, 1, 1)

    jobs_after_first_poll = (
        (
            await async_db_session.execute(
                select(PortfolioValuationJob).where(
                    PortfolioValuationJob.portfolio_id == "LIVE_P1"
                )
            )
        )
        .scalars()
        .all()
    )
    assert jobs_after_first_poll == []

    await scheduler._create_backfill_jobs(async_db_session)
    await async_db_session.commit()
    async_db_session.expire_all()

    zombie_p3 = await async_db_session.get(PositionState, ("ZOMBIE_P3", "ZOMBIE_S3"))
    assert zombie_p3.watermark_date == latest_business_date

    jobs_after_second_poll = (
        (
            await async_db_session.execute(
                select(PortfolioValuationJob)
                .where(PortfolioValuationJob.portfolio_id == "LIVE_P1")
                .order_by(PortfolioValuationJob.valuation_date.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [job.valuation_date for job in jobs_after_second_poll] == [
        date(2025, 8, 10),
        date(2025, 8, 11),
        date(2025, 8, 12),
    ]


async def test_scheduler_advances_live_watermark_from_first_open_date_not_sentinel(
    scheduler: ValuationScheduler,
    clean_db,
    async_db_session: AsyncSession,
    db_engine,
):
    latest_business_date = date(2025, 8, 12)
    with Session(db_engine) as session:
        session.add_all(
            [
                BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 10)),
                BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 11)),
                BusinessDate(calendar_code="GLOBAL", date=latest_business_date),
            ]
        )
        _seed_backlog_state(
            session,
            portfolio_id="LIVE_ADVANCE_P1",
            security_id="LIVE_ADVANCE_S1",
            updated_at=datetime(2025, 8, 12, tzinfo=timezone.utc),
            with_history=True,
        )
        session.add_all(
            [
                DailyPositionSnapshot(
                    portfolio_id="LIVE_ADVANCE_P1",
                    security_id="LIVE_ADVANCE_S1",
                    date=date(2025, 8, 10),
                    epoch=0,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                    market_price=Decimal("10"),
                    market_value=Decimal("100"),
                    market_value_local=Decimal("100"),
                    unrealized_gain_loss=Decimal("0"),
                    unrealized_gain_loss_local=Decimal("0"),
                    valuation_status="VALUED_CURRENT",
                ),
                DailyPositionSnapshot(
                    portfolio_id="LIVE_ADVANCE_P1",
                    security_id="LIVE_ADVANCE_S1",
                    date=date(2025, 8, 11),
                    epoch=0,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                    market_price=Decimal("10"),
                    market_value=Decimal("100"),
                    market_value_local=Decimal("100"),
                    unrealized_gain_loss=Decimal("0"),
                    unrealized_gain_loss_local=Decimal("0"),
                    valuation_status="VALUED_CURRENT",
                ),
                DailyPositionSnapshot(
                    portfolio_id="LIVE_ADVANCE_P1",
                    security_id="LIVE_ADVANCE_S1",
                    date=latest_business_date,
                    epoch=0,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                    market_price=Decimal("10"),
                    market_value=Decimal("100"),
                    market_value_local=Decimal("100"),
                    unrealized_gain_loss=Decimal("0"),
                    unrealized_gain_loss_local=Decimal("0"),
                    valuation_status="VALUED_CURRENT",
                ),
            ]
        )
        session.commit()

    await scheduler._advance_watermarks(async_db_session)
    await async_db_session.commit()
    async_db_session.expire_all()

    live_state = await async_db_session.get(
        PositionState, ("LIVE_ADVANCE_P1", "LIVE_ADVANCE_S1")
    )
    assert live_state is not None
    assert live_state.watermark_date == latest_business_date
    assert live_state.status == "CURRENT"
