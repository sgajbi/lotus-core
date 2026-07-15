"""Materialize position timeseries and stage affected portfolio-day aggregation work."""

from __future__ import annotations

import logging
from datetime import date
from typing import Final, cast

from portfolio_common.timeseries_constants import (
    DEPENDENT_POSITION_TIMESERIES_PROPAGATION_BATCH_SIZE,
    DEPENDENT_POSITION_TIMESERIES_PROPAGATION_MAX_BATCHES_PER_MESSAGE,
    DEPENDENT_POSITION_TIMESERIES_PROPAGATION_ROW_CAP,
)

from ...domain.position_timeseries.calculator import calculate_position_timeseries
from ...domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)
from ...ports.position_timeseries import (
    PositionTimeseriesRepository,
    PositionTimeseriesRepositoryProvider,
)
from .commands import (
    MaterializePositionTimeseriesCommand,
    PositionTimeseriesMaterializationResult,
)
from .errors import PositionSnapshotTriggerMismatch

logger = logging.getLogger(__name__)

MAX_DEPENDENT_PROPAGATION_ROWS = DEPENDENT_POSITION_TIMESERIES_PROPAGATION_BATCH_SIZE
MAX_DEPENDENT_PROPAGATION_BATCHES = (
    DEPENDENT_POSITION_TIMESERIES_PROPAGATION_MAX_BATCHES_PER_MESSAGE
)
MAX_DEPENDENT_PROPAGATION_ROWS_PER_COMMAND = DEPENDENT_POSITION_TIMESERIES_PROPAGATION_ROW_CAP
_UNSET_PRELOAD: Final = object()


class MaterializePositionTimeseries:
    """Coordinate one atomic position-timeseries materialization command."""

    def __init__(self, *, repository_provider: PositionTimeseriesRepositoryProvider) -> None:
        self._repository_provider = repository_provider

    async def execute(
        self,
        command: MaterializePositionTimeseriesCommand,
    ) -> PositionTimeseriesMaterializationResult:
        """Materialize the current day and every materially dependent future day."""

        async def materialize(
            repository: PositionTimeseriesRepository,
        ) -> PositionTimeseriesMaterializationResult:
            return await self._materialize_in_transaction(repository, command)

        return await self._repository_provider.run_in_transaction(materialize)

    async def _materialize_in_transaction(
        self,
        repository: PositionTimeseriesRepository,
        command: MaterializePositionTimeseriesCommand,
    ) -> PositionTimeseriesMaterializationResult:
        current_snapshot = await repository.get_position_snapshot(
            command.snapshot_id,
            fallback_epoch=command.epoch,
        )
        if current_snapshot is None:
            logger.warning(
                "Authoritative position snapshot was not found; materialization skipped.",
                extra={"snapshot_id": command.snapshot_id},
            )
            return PositionTimeseriesMaterializationResult(
                snapshot_found=False,
                current_day_changed=False,
                dependent_days_changed=0,
            )

        self._validate_trigger_identity(command, current_snapshot)

        previous_snapshot = await repository.get_last_snapshot_before(
            portfolio_id=current_snapshot.portfolio_id,
            security_id=current_snapshot.security_id,
            a_date=current_snapshot.date,
            epoch=current_snapshot.epoch,
        )
        current_day_changed, _ = await self._materialize_day(
            repository,
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            epoch=current_snapshot.epoch,
        )
        if current_day_changed:
            await repository.stage_aggregation_jobs(
                current_snapshot.portfolio_id,
                [current_snapshot.date],
                command.correlation_id,
            )

        dependent_days_changed, propagation_truncated = await self._propagate_dependent_days(
            repository,
            current_snapshot=current_snapshot,
            epoch=current_snapshot.epoch,
            correlation_id=command.correlation_id,
        )
        return PositionTimeseriesMaterializationResult(
            snapshot_found=True,
            current_day_changed=current_day_changed,
            dependent_days_changed=dependent_days_changed,
            dependent_propagation_truncated=propagation_truncated,
        )

    @staticmethod
    def _validate_trigger_identity(
        command: MaterializePositionTimeseriesCommand,
        snapshot: PositionSnapshotRecord,
    ) -> None:
        trigger_identity = (
            command.portfolio_id,
            command.security_id,
            command.valuation_date,
            command.epoch,
        )
        snapshot_identity = (
            snapshot.portfolio_id,
            snapshot.security_id,
            snapshot.date,
            snapshot.epoch,
        )
        if trigger_identity != snapshot_identity:
            raise PositionSnapshotTriggerMismatch(
                "Position snapshot trigger identity does not match authoritative persistence."
            )

    @staticmethod
    def _material_state(record: PositionTimeseriesRecord) -> tuple[object, ...]:
        return (
            record.bod_market_value,
            record.bod_cashflow_position,
            record.eod_cashflow_position,
            record.bod_cashflow_portfolio,
            record.eod_cashflow_portfolio,
            record.eod_market_value,
            record.fees,
            record.quantity,
            record.cost,
        )

    @classmethod
    def _has_material_change(
        cls,
        existing_record: PositionTimeseriesRecord | None,
        new_record: PositionTimeseriesRecord,
    ) -> bool:
        return existing_record is None or cls._material_state(
            existing_record
        ) != cls._material_state(new_record)

    @staticmethod
    def _requires_source_refresh(
        existing_record: PositionTimeseriesRecord | None,
        current_snapshot: PositionSnapshotRecord,
    ) -> bool:
        if existing_record is None or current_snapshot.source_updated_at is None:
            return False
        if existing_record.materialized_at is None:
            return True
        return current_snapshot.source_updated_at > existing_record.materialized_at

    async def _materialize_day(
        self,
        repository: PositionTimeseriesRepository,
        *,
        current_snapshot: PositionSnapshotRecord,
        previous_snapshot: PositionSnapshotRecord | None,
        epoch: int,
        require_existing: bool = False,
        existing_timeseries: PositionTimeseriesRecord | None | object = _UNSET_PRELOAD,
        cashflows: list[PositionCashflowRecord] | object = _UNSET_PRELOAD,
    ) -> tuple[bool, PositionTimeseriesRecord | None]:
        if existing_timeseries is _UNSET_PRELOAD:
            existing_timeseries = await repository.get_position_timeseries(
                current_snapshot.portfolio_id,
                current_snapshot.security_id,
                current_snapshot.date,
                epoch,
            )
        if require_existing and existing_timeseries is None:
            return False, None
        if cashflows is _UNSET_PRELOAD:
            cashflows = await repository.get_all_cashflows_for_security_date(
                current_snapshot.portfolio_id,
                current_snapshot.security_id,
                current_snapshot.date,
                epoch,
            )

        new_record = calculate_position_timeseries(
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            cashflows=cast(list[PositionCashflowRecord], cashflows),
            epoch=epoch,
        )
        existing_record = cast(PositionTimeseriesRecord | None, existing_timeseries)
        if not self._has_material_change(
            existing_record, new_record
        ) and not self._requires_source_refresh(existing_record, current_snapshot):
            return False, new_record

        await repository.upsert_position_timeseries(new_record)
        return True, new_record

    async def _propagate_dependent_days(
        self,
        repository: PositionTimeseriesRepository,
        *,
        current_snapshot: PositionSnapshotRecord,
        epoch: int,
        correlation_id: str | None,
    ) -> tuple[int, bool]:
        previous_snapshot = current_snapshot
        changed_dates: list[date] = []
        has_more_future_snapshots = False
        stop_propagation = False

        for _ in range(MAX_DEPENDENT_PROPAGATION_BATCHES):
            next_snapshots = await repository.get_next_snapshots_after(
                previous_snapshot.portfolio_id,
                previous_snapshot.security_id,
                previous_snapshot.date,
                epoch,
                MAX_DEPENDENT_PROPAGATION_ROWS + 1,
            )
            if not next_snapshots:
                break

            has_more_future_snapshots = len(next_snapshots) > MAX_DEPENDENT_PROPAGATION_ROWS
            snapshots_to_process = next_snapshots[:MAX_DEPENDENT_PROPAGATION_ROWS]
            next_dates = [snapshot.date for snapshot in snapshots_to_process]
            existing_by_date = await repository.get_position_timeseries_for_dates(
                previous_snapshot.portfolio_id,
                previous_snapshot.security_id,
                next_dates,
                epoch,
            )
            cashflows_by_date = await repository.get_cashflows_for_security_dates(
                previous_snapshot.portfolio_id,
                previous_snapshot.security_id,
                next_dates,
                epoch,
            )

            for next_snapshot in snapshots_to_process:
                changed, _ = await self._materialize_day(
                    repository,
                    current_snapshot=next_snapshot,
                    previous_snapshot=previous_snapshot,
                    epoch=epoch,
                    require_existing=True,
                    existing_timeseries=existing_by_date.get(next_snapshot.date),
                    cashflows=cashflows_by_date.get(next_snapshot.date, []),
                )
                if not changed:
                    stop_propagation = True
                    has_more_future_snapshots = False
                    break

                changed_dates.append(next_snapshot.date)
                previous_snapshot = next_snapshot

            if stop_propagation or not has_more_future_snapshots:
                break

        await repository.stage_aggregation_jobs(
            current_snapshot.portfolio_id,
            changed_dates,
            correlation_id,
        )
        if has_more_future_snapshots:
            logger.warning(
                "Dependent position-timeseries propagation reached its command limit.",
                extra={
                    "portfolio_id": current_snapshot.portfolio_id,
                    "security_id": current_snapshot.security_id,
                    "row_limit": MAX_DEPENDENT_PROPAGATION_ROWS_PER_COMMAND,
                },
            )
        return len(changed_dates), has_more_future_snapshots
