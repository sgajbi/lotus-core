import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionState,
    PositionTimeseries,
)
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


def _snapshot(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> DailyPositionSnapshot:
    return DailyPositionSnapshot(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
        market_price=Decimal("10"),
        market_value=Decimal("100"),
        market_value_local=Decimal("100"),
        unrealized_gain_loss=Decimal("0"),
        unrealized_gain_loss_local=Decimal("0"),
        valuation_status="VALUED",
    )


def _position_ts(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> PositionTimeseries:
    return PositionTimeseries(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        bod_market_value=Decimal("100"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("100"),
        fees=Decimal("0"),
        quantity=Decimal("10"),
        cost=Decimal("100"),
    )


@pytest.fixture(scope="function")
def setup_sequential_jobs_with_snapshot_completeness(db_engine, clean_db):
    portfolio_id = "SEQ_JOB_TEST_01"
    day1 = date(2025, 8, 18)
    day2 = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
            ]
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id, aggregation_date=day1, status="PENDING"
                ),
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id, aggregation_date=day2, status="PENDING"
                ),
            ]
        )
        session.flush()

        # Day1 inputs: 2 expected snapshots, only 1 produced position-timeseries (incomplete).
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day1),
                _snapshot(portfolio_id, "SEC_B", day1),
                _position_ts(portfolio_id, "SEC_A", day1),
            ]
        )
        # Day2 inputs: keep complete for SEC_A so day2 can claim once day1 portfolio timeseries exists.
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day2),
                _position_ts(portfolio_id, "SEC_A", day2),
            ]
        )
        session.commit()

    return {"portfolio_id": portfolio_id, "day1": day1, "day2": day2}


async def test_find_and_claim_eligible_jobs_enforces_snapshot_completeness_gate(
    setup_sequential_jobs_with_snapshot_completeness,
    async_db_session: AsyncSession,
    db_engine,
):
    repo = TimeseriesRepository(async_db_session)
    portfolio_id = setup_sequential_jobs_with_snapshot_completeness["portfolio_id"]
    day1 = setup_sequential_jobs_with_snapshot_completeness["day1"]
    day2 = setup_sequential_jobs_with_snapshot_completeness["day2"]

    # Day1 should not claim while input set is incomplete (2 expected snapshots vs 1 position-timeseries).
    claimed_jobs_1 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    assert claimed_jobs_1 == []

    # Complete day1 input set.
    with Session(db_engine) as session:
        session.add(_position_ts(portfolio_id, "SEC_B", day1))
        session.commit()

    claimed_jobs_2 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    assert len(claimed_jobs_2) == 1
    assert claimed_jobs_2[0].aggregation_date == day1

    # Simulate day1 aggregation completion; day2 should now claim (prior-day + completeness satisfied).
    with Session(db_engine) as session:
        session.add(
            PortfolioTimeseries(
                portfolio_id=portfolio_id,
                date=day1,
                epoch=0,
                bod_market_value=Decimal("0"),
                bod_cashflow=Decimal("0"),
                eod_cashflow=Decimal("0"),
                eod_market_value=Decimal("0"),
                fees=Decimal("0"),
            )
        )
        session.commit()

    claimed_jobs_3 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    assert len(claimed_jobs_3) == 1
    assert claimed_jobs_3[0].aggregation_date == day2
