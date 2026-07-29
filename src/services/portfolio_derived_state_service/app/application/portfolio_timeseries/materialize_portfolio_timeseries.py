"""Materialize one portfolio day and stage its downstream completion evidence."""

from __future__ import annotations

import logging

from ...domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobFailureDisposition,
)
from ...domain.portfolio_timeseries.models import PortfolioAggregationCompletion
from ...ports.aggregation_completion import AggregationCompletionEventStager
from ...ports.portfolio_timeseries import (
    PortfolioTimeseriesCalculation,
    PortfolioTimeseriesRepository,
    PortfolioTimeseriesUnitOfWorkProvider,
)
from .calculation import CalculatePortfolioTimeseries
from .commands import (
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationResult,
    PortfolioTimeseriesMaterializationStatus,
)
from .errors import PortfolioAggregationSourceMissing
from .stage_aggregation_completion import StagePortfolioAggregationCompletion

logger = logging.getLogger(__name__)


class MaterializePortfolioTimeseries:
    """Coordinate one atomic portfolio-timeseries materialization command."""

    def __init__(
        self,
        *,
        unit_of_work_provider: PortfolioTimeseriesUnitOfWorkProvider,
        calculator: PortfolioTimeseriesCalculation | None = None,
    ) -> None:
        self._unit_of_work_provider = unit_of_work_provider
        self._calculator = calculator or CalculatePortfolioTimeseries()

    async def execute(
        self,
        command: MaterializePortfolioTimeseriesCommand,
    ) -> PortfolioTimeseriesMaterializationResult:
        """Materialize one claimed portfolio day or record its terminal failure."""

        async def materialize(
            repository: PortfolioTimeseriesRepository,
            event_stager: AggregationCompletionEventStager,
        ) -> PortfolioTimeseriesMaterializationResult:
            return await self._materialize_in_transaction(repository, event_stager, command)

        try:
            return await self._unit_of_work_provider.run_in_transaction(materialize)
        except Exception:
            logger.error(
                "Portfolio-timeseries materialization failed; marking the owned job failed.",
                extra={
                    "portfolio_id": command.portfolio_id,
                    "aggregation_date": command.aggregation_date.isoformat(),
                },
                exc_info=True,
            )

            async def mark_failed(
                repository: PortfolioTimeseriesRepository,
                _event_stager: AggregationCompletionEventStager,
            ) -> AggregationJobFailureDisposition:
                return await repository.fail_or_requeue_job(
                    job_id=command.job_id,
                    lease_token=command.lease_token,
                    target_epoch=command.target_epoch,
                    source_revision=command.source_revision,
                )

            failure_disposition = await self._unit_of_work_provider.run_in_transaction(mark_failed)
            return PortfolioTimeseriesMaterializationResult(
                status=PortfolioTimeseriesMaterializationStatus(failure_disposition.value),
                failure_recorded=(failure_disposition is AggregationJobFailureDisposition.FAILED),
            )

    async def _materialize_in_transaction(
        self,
        repository: PortfolioTimeseriesRepository,
        event_stager: AggregationCompletionEventStager,
        command: MaterializePortfolioTimeseriesCommand,
    ) -> PortfolioTimeseriesMaterializationResult:
        portfolio = await repository.get_portfolio(command.portfolio_id)
        if portfolio is None:
            raise PortfolioAggregationSourceMissing(
                "Authoritative portfolio scope was not found for aggregation."
            )

        position_timeseries = await repository.get_all_position_timeseries_for_date(
            command.portfolio_id,
            command.aggregation_date,
            command.target_epoch,
        )
        portfolio_timeseries = await self._calculator.calculate_daily_record(
            portfolio,
            command.aggregation_date,
            command.target_epoch,
            position_timeseries,
            repository,
        )
        disposition = await repository.complete_or_requeue_job(
            job_id=command.job_id,
            lease_token=command.lease_token,
            target_epoch=command.target_epoch,
            source_revision=command.source_revision,
        )
        if disposition is not AggregationJobCompletionDisposition.COMPLETE:
            return PortfolioTimeseriesMaterializationResult(
                status=PortfolioTimeseriesMaterializationStatus(disposition.value),
                target_epoch=command.target_epoch,
            )

        await repository.upsert_portfolio_timeseries(portfolio_timeseries)
        await StagePortfolioAggregationCompletion(event_stager=event_stager).execute(
            PortfolioAggregationCompletion(
                portfolio_id=command.portfolio_id,
                aggregation_date=command.aggregation_date,
                epoch=command.target_epoch,
                aggregation_revision=command.aggregation_revision,
            ),
            correlation_id=command.correlation_id,
        )
        return PortfolioTimeseriesMaterializationResult(
            status=PortfolioTimeseriesMaterializationStatus.COMPLETE,
            target_epoch=command.target_epoch,
        )
