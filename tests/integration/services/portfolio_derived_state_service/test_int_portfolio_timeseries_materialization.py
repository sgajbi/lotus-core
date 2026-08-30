"""Prove lease-fenced portfolio materialization against PostgreSQL."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import (
    OutboxEvent,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
)
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_derived_state_service.app.application.portfolio_timeseries import (
    MaterializePortfolioTimeseries,
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_derived_state_service.app.domain.portfolio_timeseries import (
    numeric_policy,
)
from src.services.portfolio_derived_state_service.app.domain.portfolio_timeseries.models import (
    PortfolioTimeseriesRecord,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_timeseries_unit_of_work_provider as unit_of_work_provider_module,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest.mark.lifecycle
async def test_owned_lease_persists_portfolio_output_lineage_atomically(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Prove the calculated portfolio receipt survives the PostgreSQL upsert boundary."""

    del clean_db
    portfolio_id = "PORT-AGG-LINEAGE-01"
    aggregation_date = date(2025, 8, 22)
    lease_token = "lineage-lease-token"
    job = PortfolioAggregationJob(
        portfolio_id=portfolio_id,
        aggregation_date=aggregation_date,
        status="PROCESSING",
        lease_owner="aggregation-runtime-lineage",
        lease_token=lease_token,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    async_db_session.add_all(
        [
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-AGG-LINEAGE-01",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            job,
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(job)
    job_id = int(job.id)
    target_epoch = int(job.target_epoch)
    source_revision = int(job.source_revision)
    await async_db_session.rollback()

    output_payload = {
        "portfolio_id": portfolio_id,
        "date": aggregation_date,
        "epoch": target_epoch,
        "bod_market_value": Decimal("0"),
        "bod_cashflow": Decimal("0"),
        "eod_cashflow": Decimal("0"),
        "eod_market_value": Decimal("0"),
        "fees": Decimal("0"),
    }
    lineage = build_calculation_lineage(
        algorithm_id="portfolio-timeseries-daily",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={"portfolio_id": portfolio_id, "position_count": 0},
        output_payload=output_payload,
        numeric_output_policy=(
            numeric_policy.PORTFOLIO_TIMESERIES_LEDGER_OUTPUT_V1.lineage_identity()
        ),
    )
    calculator = AsyncMock()
    calculator.calculate_daily_record.return_value = PortfolioTimeseriesRecord(
        **output_payload,
        calculation_lineage=lineage,
    )

    async def override_session():
        session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    use_case = MaterializePortfolioTimeseries(
        unit_of_work_provider=(
            unit_of_work_provider_module.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()
        ),
        calculator=calculator,
    )
    with patch(
        "src.services.portfolio_derived_state_service.app.infrastructure."
        "portfolio_timeseries_unit_of_work_provider.get_async_db_session",
        new=override_session,
    ):
        result = await use_case.execute(
            MaterializePortfolioTimeseriesCommand(
                job_id=job_id,
                lease_token=lease_token,
                portfolio_id=portfolio_id,
                aggregation_date=aggregation_date,
                aggregation_revision=1,
                target_epoch=target_epoch,
                source_revision=source_revision,
                correlation_id="corr-agg-lineage-01",
            )
        )

    persisted = await async_db_session.scalar(
        select(PortfolioTimeseries).where(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date == aggregation_date,
            PortfolioTimeseries.epoch == target_epoch,
        )
    )
    completion = await async_db_session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id
            == f"{portfolio_id}:{aggregation_date.isoformat()}:{target_epoch}"
        )
    )

    assert result.status is PortfolioTimeseriesMaterializationStatus.COMPLETE
    assert persisted is not None
    assert persisted.calculation_lineage == lineage.lineage_payload()
    assert completion is not None


@pytest.mark.lifecycle
async def test_stale_lease_cannot_persist_portfolio_output_or_completion_event(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    job = PortfolioAggregationJob(
        portfolio_id="PORT-AGG-INT-01",
        aggregation_date=date(2025, 8, 21),
        status="PROCESSING",
        lease_owner="aggregation-runtime-current",
        lease_token="current-lease-token",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    async_db_session.add_all(
        [
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id="PORT-AGG-INT-01",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-AGG-INT-01",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            job,
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(job)
    job_id = int(job.id)
    portfolio_id = str(job.portfolio_id)
    aggregation_date = job.aggregation_date
    target_epoch = int(job.target_epoch)
    source_revision = int(job.source_revision)
    await async_db_session.rollback()

    async def override_session():
        session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    calculator = AsyncMock()
    calculator.calculate_daily_record.return_value = PortfolioTimeseries(
        portfolio_id="PORT-AGG-INT-01",
        date=date(2025, 8, 21),
        epoch=0,
        bod_market_value=Decimal("0"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("0"),
        eod_market_value=Decimal("0"),
        fees=Decimal("0"),
    )
    use_case = MaterializePortfolioTimeseries(
        unit_of_work_provider=(
            unit_of_work_provider_module.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()
        ),
        calculator=calculator,
    )

    with patch(
        "src.services.portfolio_derived_state_service.app.infrastructure."
        "portfolio_timeseries_unit_of_work_provider.get_async_db_session",
        new=override_session,
    ):
        result = await use_case.execute(
            MaterializePortfolioTimeseriesCommand(
                job_id=job_id,
                lease_token="expired-lease-token",
                portfolio_id=portfolio_id,
                aggregation_date=aggregation_date,
                aggregation_revision=1,
                target_epoch=target_epoch,
                source_revision=source_revision,
                correlation_id="corr-agg-int-01",
            )
        )

    portfolio_rows = (
        (
            await async_db_session.execute(
                select(PortfolioTimeseries).where(
                    PortfolioTimeseries.portfolio_id == portfolio_id,
                    PortfolioTimeseries.date == aggregation_date,
                    PortfolioTimeseries.epoch == 0,
                )
            )
        )
        .scalars()
        .all()
    )
    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == "PORT-AGG-INT-01:2025-08-21:0",
                    OutboxEvent.event_type == "PortfolioAggregationDayCompleted",
                )
            )
        )
        .scalars()
        .all()
    )
    await async_db_session.refresh(job)

    assert result.status is PortfolioTimeseriesMaterializationStatus.LOST_OWNERSHIP
    assert portfolio_rows == []
    assert outbox_rows == []
    assert job.status == "PROCESSING"
    assert job.lease_token == "current-lease-token"
