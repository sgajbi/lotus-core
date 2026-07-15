"""Prove application ownership of portfolio-timeseries materialization."""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import TypeVar

import pytest

from src.services.portfolio_aggregation_service.app.application.portfolio_timeseries import (
    MaterializePortfolioTimeseries,
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_aggregation_service.app.domain.aggregation_records import (
    AggregationJobCompletionDisposition,
    PortfolioAggregationCompletion,
    PortfolioAggregationScope,
    PortfolioTimeseriesRecord,
    PositionTimeseriesRecord,
)
from src.services.portfolio_aggregation_service.app.ports.aggregation_completion import (
    AggregationCompletionEventStager,
)
from src.services.portfolio_aggregation_service.app.ports.portfolio_timeseries import (
    PortfolioTimeseriesCalculation,
    PortfolioTimeseriesRepository,
)

pytestmark = pytest.mark.asyncio

T = TypeVar("T")


class InMemoryPortfolioTimeseriesRepository:
    """Record portfolio-timeseries application effects without framework objects."""

    def __init__(self) -> None:
        self.portfolio: PortfolioAggregationScope | None = PortfolioAggregationScope(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            base_currency="SGD",
        )
        self.epoch = 4
        self.positions: list[PositionTimeseriesRecord] = []
        self.disposition = AggregationJobCompletionDisposition.COMPLETE
        self.upserted: list[PortfolioTimeseriesRecord] = []
        self.failed_jobs: list[tuple[str, date]] = []

    async def get_portfolio(self, portfolio_id: str) -> PortfolioAggregationScope | None:
        del portfolio_id
        return self.portfolio

    async def get_current_epoch_for_portfolio(self, portfolio_id: str) -> int:
        del portfolio_id
        return self.epoch

    async def get_all_position_timeseries_for_date(
        self,
        portfolio_id: str,
        aggregation_date: date,
        epoch: int,
    ) -> list[PositionTimeseriesRecord]:
        del portfolio_id, aggregation_date, epoch
        return self.positions

    async def upsert_portfolio_timeseries(self, record: PortfolioTimeseriesRecord) -> None:
        self.upserted.append(record)

    async def complete_or_requeue_job(
        self,
        portfolio_id: str,
        aggregation_date: date,
    ) -> AggregationJobCompletionDisposition:
        del portfolio_id, aggregation_date
        return self.disposition

    async def mark_job_failed(self, portfolio_id: str, aggregation_date: date) -> bool:
        self.failed_jobs.append((portfolio_id, aggregation_date))
        return True


class RecordingCompletionEventStager:
    """Record completion evidence passed through the application port."""

    def __init__(self) -> None:
        self.calls: list[tuple[PortfolioAggregationCompletion, str | None]] = []

    async def stage_completion(
        self,
        completion: PortfolioAggregationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        self.calls.append((completion, correlation_id))


class InMemoryPortfolioTimeseriesUnitOfWorkProvider:
    """Execute operations against one in-memory repository and event stager."""

    def __init__(
        self,
        repository: InMemoryPortfolioTimeseriesRepository,
        event_stager: RecordingCompletionEventStager,
    ) -> None:
        self.repository = repository
        self.event_stager = event_stager
        self.transaction_count = 0

    async def run_in_transaction(
        self,
        operation: Callable[
            [PortfolioTimeseriesRepository, AggregationCompletionEventStager],
            Awaitable[T],
        ],
    ) -> T:
        self.transaction_count += 1
        return await operation(self.repository, self.event_stager)


class DeterministicPortfolioTimeseriesCalculator:
    """Return a deterministic aggregate or raise a configured calculation error."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.call_count = 0

    async def calculate_daily_record(
        self,
        portfolio: PortfolioAggregationScope,
        aggregation_date: date,
        epoch: int,
        position_timeseries: list[PositionTimeseriesRecord],
        repository: PortfolioTimeseriesRepository,
    ) -> PortfolioTimeseriesRecord:
        del position_timeseries, repository
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return PortfolioTimeseriesRecord(
            portfolio_id=portfolio.portfolio_id,
            date=aggregation_date,
            epoch=epoch,
            bod_market_value=Decimal("1000"),
            bod_cashflow=Decimal("10"),
            eod_cashflow=Decimal("20"),
            eod_market_value=Decimal("1100"),
            fees=Decimal("2"),
        )


def _command() -> MaterializePortfolioTimeseriesCommand:
    return MaterializePortfolioTimeseriesCommand(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        aggregation_date=date(2026, 4, 10),
        correlation_id="corr-derived-portfolio-001",
    )


def _use_case(
    repository: InMemoryPortfolioTimeseriesRepository,
    event_stager: RecordingCompletionEventStager,
    *,
    calculator: PortfolioTimeseriesCalculation | None = None,
) -> tuple[MaterializePortfolioTimeseries, InMemoryPortfolioTimeseriesUnitOfWorkProvider]:
    provider = InMemoryPortfolioTimeseriesUnitOfWorkProvider(repository, event_stager)
    return (
        MaterializePortfolioTimeseries(
            unit_of_work_provider=provider,
            calculator=calculator or DeterministicPortfolioTimeseriesCalculator(),
        ),
        provider,
    )


async def test_materialization_persists_aggregate_and_stages_completion_atomically() -> None:
    repository = InMemoryPortfolioTimeseriesRepository()
    event_stager = RecordingCompletionEventStager()
    use_case, provider = _use_case(repository, event_stager)

    result = await use_case.execute(_command())

    assert result.status is PortfolioTimeseriesMaterializationStatus.COMPLETE
    assert result.target_epoch == 4
    assert len(repository.upserted) == 1
    assert repository.upserted[0].eod_market_value == Decimal("1100")
    assert event_stager.calls == [
        (
            PortfolioAggregationCompletion(
                portfolio_id="PB_SG_GLOBAL_BAL_001",
                aggregation_date=date(2026, 4, 10),
                epoch=4,
            ),
            "corr-derived-portfolio-001",
        )
    ]
    assert repository.failed_jobs == []
    assert provider.transaction_count == 1


@pytest.mark.parametrize(
    ("disposition", "expected_status"),
    [
        (
            AggregationJobCompletionDisposition.REQUEUED,
            PortfolioTimeseriesMaterializationStatus.REQUEUED,
        ),
        (
            AggregationJobCompletionDisposition.LOST_OWNERSHIP,
            PortfolioTimeseriesMaterializationStatus.LOST_OWNERSHIP,
        ),
    ],
)
async def test_materialization_skips_outputs_without_completion_ownership(
    disposition: AggregationJobCompletionDisposition,
    expected_status: PortfolioTimeseriesMaterializationStatus,
) -> None:
    repository = InMemoryPortfolioTimeseriesRepository()
    repository.disposition = disposition
    event_stager = RecordingCompletionEventStager()
    use_case, provider = _use_case(repository, event_stager)

    result = await use_case.execute(_command())

    assert result.status is expected_status
    assert repository.upserted == []
    assert event_stager.calls == []
    assert repository.failed_jobs == []
    assert provider.transaction_count == 1


async def test_materialization_marks_missing_portfolio_job_failed() -> None:
    repository = InMemoryPortfolioTimeseriesRepository()
    repository.portfolio = None
    event_stager = RecordingCompletionEventStager()
    use_case, provider = _use_case(repository, event_stager)

    result = await use_case.execute(_command())

    assert result.status is PortfolioTimeseriesMaterializationStatus.FAILED
    assert result.target_epoch is None
    assert repository.upserted == []
    assert event_stager.calls == []
    assert repository.failed_jobs == [("PB_SG_GLOBAL_BAL_001", date(2026, 4, 10))]
    assert provider.transaction_count == 2


async def test_materialization_rolls_back_calculation_failure_then_marks_job_failed() -> None:
    repository = InMemoryPortfolioTimeseriesRepository()
    event_stager = RecordingCompletionEventStager()
    calculator = DeterministicPortfolioTimeseriesCalculator(
        error=RuntimeError("missing governed FX rate")
    )
    use_case, provider = _use_case(repository, event_stager, calculator=calculator)

    result = await use_case.execute(_command())

    assert result.status is PortfolioTimeseriesMaterializationStatus.FAILED
    assert repository.upserted == []
    assert event_stager.calls == []
    assert repository.failed_jobs == [("PB_SG_GLOBAL_BAL_001", date(2026, 4, 10))]
    assert provider.transaction_count == 2
