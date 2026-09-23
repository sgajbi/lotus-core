"""PostgreSQL evidence for atomic business-date valuation admission."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.events import BusinessDateEvent
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.repositories.business_date_repository import (
    BusinessDateRepository,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

ADMITTED_DATE = date(2026, 4, 11)


def _portfolio(portfolio_id: str) -> Portfolio:
    return Portfolio(
        tenant_id="tenant-calendar-admission",
        portfolio_id=portfolio_id,
        base_currency="USD",
        open_date=date(2026, 4, 1),
        risk_exposure="moderate",
        investment_time_horizon="long_term",
        portfolio_type="discretionary",
        booking_center_code="Singapore",
        client_id=f"CLIENT_{portfolio_id}",
        status="ACTIVE",
    )


def _transaction(portfolio_id: str, security_id: str) -> Transaction:
    return Transaction(
        transaction_id=f"TXN_{portfolio_id}",
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        transaction_date=datetime(2026, 4, 1, 9, tzinfo=UTC),
    )


async def _seed_position(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    quantity: str,
    history_security_id: str | None = None,
) -> None:
    session.add(_portfolio(portfolio_id))
    session.add(_transaction(portfolio_id, security_id))
    await session.flush()
    session.add(
        PositionState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=0,
            watermark_date=date(2026, 4, 13),
            status="CURRENT",
        )
    )
    session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id=history_security_id or security_id,
            transaction_id=f"TXN_{portfolio_id}",
            position_date=date(2026, 4, 1),
            epoch=0,
            quantity=Decimal(quantity),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        )
    )


async def test_new_default_business_date_rearms_exact_current_epoch_work(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session = async_db_session
    await _seed_position(
        session,
        portfolio_id="CALENDAR_COMPLETE",
        security_id="SEC_COMPLETE",
        quantity="10",
    )
    await _seed_position(
        session,
        portfolio_id="CALENDAR_PROCESSING",
        security_id="SEC_PROCESSING",
        quantity="10",
    )
    await _seed_position(
        session,
        portfolio_id="CALENDAR_CLOSED",
        security_id="SEC_CLOSED",
        quantity="0",
    )
    await _seed_position(
        session,
        portfolio_id="CALENDAR_LEGACY",
        security_id="SEC_LEGACY",
        history_security_id="\tSEC_LEGACY\n",
        quantity="10",
    )
    session.add_all(
        [
            PortfolioValuationJob(
                portfolio_id="CALENDAR_COMPLETE",
                security_id="SEC_COMPLETE",
                valuation_date=ADMITTED_DATE,
                epoch=0,
                status="COMPLETE",
                source_correction_id="prior-price-correction",
            ),
            PortfolioValuationJob(
                portfolio_id="CALENDAR_PROCESSING",
                security_id="SEC_PROCESSING",
                valuation_date=ADMITTED_DATE,
                epoch=0,
                status="PROCESSING",
                source_correction_id="prior-fx-correction",
                valuation_lease_owner="calendar-admission-test",
                valuation_claim_token="a" * 32,
                valuation_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            ),
        ]
    )
    await session.commit()

    event = BusinessDateEvent(
        business_date=ADMITTED_DATE,
        calendar_code="GLOBAL",
        source_system="calendar-master",
        source_batch_id="calendar-batch-20260411",
        correlation_id="calendar-admission-20260411",
    )
    async with session.begin():
        await BusinessDateRepository(session).upsert_business_date(event)

    jobs = list(
        (
            await session.execute(
                select(PortfolioValuationJob)
                .where(PortfolioValuationJob.valuation_date == ADMITTED_DATE)
                .order_by(PortfolioValuationJob.portfolio_id)
            )
        )
        .scalars()
        .all()
    )
    assert [(job.portfolio_id, job.status, job.requeue_requested) for job in jobs] == [
        ("CALENDAR_COMPLETE", "PENDING", False),
        ("CALENDAR_LEGACY", "PENDING", False),
        ("CALENDAR_PROCESSING", "PROCESSING", True),
    ]
    assert all(
        job.source_correction_id == "BUSINESS_DATE_ADMISSION:GLOBAL:2026-04-11" for job in jobs
    )

    await session.commit()
    async with session.begin():
        await BusinessDateRepository(session).upsert_business_date(event)
    jobs_after_duplicate = list(
        (
            await session.execute(
                select(PortfolioValuationJob)
                .where(PortfolioValuationJob.valuation_date == ADMITTED_DATE)
                .order_by(PortfolioValuationJob.portfolio_id)
            )
        )
        .scalars()
        .all()
    )
    assert [(job.id, job.status, job.requeue_requested) for job in jobs_after_duplicate] == [
        (jobs[0].id, "PENDING", False),
        (jobs[1].id, "PENDING", False),
        (jobs[2].id, "PROCESSING", True),
    ]


async def test_business_date_and_jobs_rollback_together_on_staging_failure(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = async_db_session
    await _seed_position(
        session,
        portfolio_id="CALENDAR_ROLLBACK",
        security_id="SEC_ROLLBACK",
        quantity="10",
    )
    await session.commit()

    async def _fail_job_staging(*args, **kwargs):
        raise RuntimeError("representative valuation staging failure")

    monkeypatch.setattr(ValuationJobRepository, "upsert_jobs", _fail_job_staging)
    event = BusinessDateEvent(business_date=ADMITTED_DATE, calendar_code="GLOBAL")
    with pytest.raises(RuntimeError, match="representative valuation staging failure"):
        async with session.begin():
            await BusinessDateRepository(session).upsert_business_date(event)

    assert (
        await session.scalar(
            select(BusinessDate.date).where(
                BusinessDate.calendar_code == "GLOBAL",
                BusinessDate.date == ADMITTED_DATE,
            )
        )
        is None
    )
    assert (
        await session.scalar(
            select(PortfolioValuationJob.id).where(
                PortfolioValuationJob.valuation_date == ADMITTED_DATE
            )
        )
        is None
    )


async def test_calendar_activation_waits_for_fallback_valuation_transaction(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(
        bind=async_db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    admission_started = asyncio.Event()

    async def _admit_calendar() -> None:
        async with session_factory() as admission_session:
            async with admission_session.begin():
                admission_started.set()
                await BusinessDateRepository(admission_session).upsert_business_date(
                    BusinessDateEvent(
                        business_date=ADMITTED_DATE,
                        calendar_code="GLOBAL",
                    )
                )

    async with session_factory() as classification_session:
        async with classification_session.begin():
            classification = await ValuationRepository(
                classification_session
            ).classify_valuation_business_date(ADMITTED_DATE)
            assert classification.is_business_date is True

            admission = asyncio.create_task(_admit_calendar())
            await admission_started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(admission), timeout=0.2)

    await asyncio.wait_for(admission, timeout=5)
    assert (
        await async_db_session.scalar(
            select(BusinessDate.date).where(
                BusinessDate.calendar_code == "GLOBAL",
                BusinessDate.date == ADMITTED_DATE,
            )
        )
        == ADMITTED_DATE
    )


async def test_empty_calendar_allows_concurrent_fallback_valuation_transactions(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(
        bind=async_db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    release = asyncio.Event()

    async def _classify_and_hold(ready: asyncio.Event):
        async with session_factory() as session:
            async with session.begin():
                classification = await ValuationRepository(
                    session
                ).classify_valuation_business_date(ADMITTED_DATE)
                ready.set()
                await release.wait()
                return classification

    first = asyncio.create_task(_classify_and_hold(first_ready))
    await asyncio.wait_for(first_ready.wait(), timeout=5)
    second = asyncio.create_task(_classify_and_hold(second_ready))
    try:
        await asyncio.wait_for(second_ready.wait(), timeout=5)
    finally:
        release.set()

    first_result, second_result = await asyncio.gather(first, second)
    assert first_result.is_business_date is True
    assert second_result.is_business_date is True
