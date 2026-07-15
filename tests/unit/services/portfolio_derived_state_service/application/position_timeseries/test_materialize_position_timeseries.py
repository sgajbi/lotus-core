"""Prove application ownership of position-timeseries materialization."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import TypeVar

import pytest

from src.services.portfolio_derived_state_service.app.application.position_timeseries import (
    MaterializePositionTimeseries,
    MaterializePositionTimeseriesCommand,
    PositionSnapshotTriggerMismatch,
)
from src.services.portfolio_derived_state_service.app.application.position_timeseries import (
    materialize_position_timeseries as materialization_module,
)
from src.services.portfolio_derived_state_service.app.domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)
from src.services.portfolio_derived_state_service.app.ports.position_timeseries import (
    PositionTimeseriesRepository,
)

pytestmark = pytest.mark.asyncio

T = TypeVar("T")


class InMemoryPositionTimeseriesRepository:
    """Record application effects without exposing persistence framework objects."""

    def __init__(self, snapshot: PositionSnapshotRecord | None) -> None:
        self.snapshot = snapshot
        self.previous_snapshot: PositionSnapshotRecord | None = None
        self.future_snapshots: list[PositionSnapshotRecord] = []
        self.existing_by_date: dict[date, PositionTimeseriesRecord] = {}
        self.cashflows_by_date: dict[date, list[PositionCashflowRecord]] = {}
        self.upserted: list[PositionTimeseriesRecord] = []
        self.staged_dates: list[date] = []

    async def get_position_snapshot(
        self, snapshot_id: int, *, fallback_epoch: int
    ) -> PositionSnapshotRecord | None:
        del snapshot_id, fallback_epoch
        return self.snapshot

    async def get_position_timeseries(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> PositionTimeseriesRecord | None:
        del portfolio_id, security_id, epoch
        return self.existing_by_date.get(a_date)

    async def get_position_timeseries_for_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, PositionTimeseriesRecord]:
        del portfolio_id, security_id, epoch
        return {
            timeseries_date: self.existing_by_date[timeseries_date]
            for timeseries_date in dates
            if timeseries_date in self.existing_by_date
        }

    async def upsert_position_timeseries(self, record: PositionTimeseriesRecord) -> None:
        self.upserted.append(record)
        self.existing_by_date[record.date] = record

    async def get_all_cashflows_for_security_date(
        self, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> list[PositionCashflowRecord]:
        del portfolio_id, security_id, epoch
        return self.cashflows_by_date.get(a_date, [])

    async def get_last_snapshot_before(
        self, *, portfolio_id: str, security_id: str, a_date: date, epoch: int
    ) -> PositionSnapshotRecord | None:
        del portfolio_id, security_id, a_date, epoch
        return self.previous_snapshot

    async def get_next_snapshots_after(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
        limit: int,
    ) -> list[PositionSnapshotRecord]:
        del portfolio_id, security_id, epoch
        return [snapshot for snapshot in self.future_snapshots if snapshot.date > a_date][:limit]

    async def get_cashflows_for_security_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, list[PositionCashflowRecord]]:
        del portfolio_id, security_id, epoch
        return {
            cashflow_date: self.cashflows_by_date.get(cashflow_date, []) for cashflow_date in dates
        }

    async def stage_aggregation_jobs(
        self,
        portfolio_id: str,
        aggregation_dates: list[date],
        correlation_id: str | None,
    ) -> None:
        del portfolio_id, correlation_id
        self.staged_dates.extend(aggregation_dates)


class InMemoryRepositoryProvider:
    """Execute one application operation against the supplied repository."""

    def __init__(self, repository: InMemoryPositionTimeseriesRepository) -> None:
        self.repository = repository
        self.transaction_count = 0

    async def run_in_transaction(
        self,
        operation: Callable[[PositionTimeseriesRepository], Awaitable[T]],
    ) -> T:
        self.transaction_count += 1
        return await operation(self.repository)


def _snapshot(a_date: date = date(2026, 4, 10)) -> PositionSnapshotRecord:
    return PositionSnapshotRecord(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        security_id="SEC_DERIVED_001",
        date=a_date,
        epoch=3,
        quantity=Decimal("12"),
        cost_basis_local=Decimal("1200"),
        market_value_local=Decimal("1260"),
    )


def _command() -> MaterializePositionTimeseriesCommand:
    return MaterializePositionTimeseriesCommand(
        snapshot_id=41,
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        security_id="SEC_DERIVED_001",
        valuation_date=date(2026, 4, 10),
        epoch=3,
        correlation_id="corr-derived-001",
    )


def _timeseries_record(
    snapshot: PositionSnapshotRecord,
    *,
    bod_market_value: Decimal = Decimal("0"),
) -> PositionTimeseriesRecord:
    return PositionTimeseriesRecord(
        portfolio_id=snapshot.portfolio_id,
        security_id=snapshot.security_id,
        date=snapshot.date,
        epoch=snapshot.epoch,
        bod_market_value=bod_market_value,
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=snapshot.market_value_local or Decimal("0"),
        fees=Decimal("0"),
        quantity=snapshot.quantity,
        cost=(snapshot.cost_basis_local or Decimal("0")) / snapshot.quantity,
    )


async def test_materialization_persists_changed_day_and_stages_aggregation() -> None:
    repository = InMemoryPositionTimeseriesRepository(_snapshot())
    provider = InMemoryRepositoryProvider(repository)

    result = await MaterializePositionTimeseries(repository_provider=provider).execute(_command())

    assert result.snapshot_found is True
    assert result.current_day_changed is True
    assert result.dependent_days_changed == 0
    assert [record.date for record in repository.upserted] == [date(2026, 4, 10)]
    assert repository.staged_dates == [date(2026, 4, 10)]
    assert provider.transaction_count == 1


async def test_materialization_is_a_noop_when_snapshot_is_missing() -> None:
    repository = InMemoryPositionTimeseriesRepository(None)
    provider = InMemoryRepositoryProvider(repository)

    result = await MaterializePositionTimeseries(repository_provider=provider).execute(_command())

    assert result.snapshot_found is False
    assert result.current_day_changed is False
    assert result.dependent_days_changed == 0
    assert repository.upserted == []
    assert repository.staged_dates == []
    assert provider.transaction_count == 1


async def test_materialization_rejects_trigger_identity_mismatch_without_effects() -> None:
    repository = InMemoryPositionTimeseriesRepository(_snapshot())
    provider = InMemoryRepositoryProvider(repository)
    mismatched_command = MaterializePositionTimeseriesCommand(
        snapshot_id=41,
        portfolio_id="OTHER_PORTFOLIO",
        security_id="SEC_DERIVED_001",
        valuation_date=date(2026, 4, 10),
        epoch=3,
        correlation_id="corr-derived-001",
    )

    with pytest.raises(PositionSnapshotTriggerMismatch):
        await MaterializePositionTimeseries(repository_provider=provider).execute(
            mismatched_command
        )

    assert repository.upserted == []
    assert repository.staged_dates == []
    assert provider.transaction_count == 1


async def test_materialization_skips_identical_current_business_state() -> None:
    snapshot = _snapshot()
    repository = InMemoryPositionTimeseriesRepository(snapshot)
    repository.existing_by_date[snapshot.date] = _timeseries_record(snapshot)

    result = await MaterializePositionTimeseries(
        repository_provider=InMemoryRepositoryProvider(repository)
    ).execute(_command())

    assert result.current_day_changed is False
    assert repository.upserted == []
    assert repository.staged_dates == []


async def test_backdated_materialization_recalculates_dependent_beginning_value() -> None:
    current_snapshot = _snapshot()
    next_snapshot = _snapshot(date(2026, 4, 11))
    repository = InMemoryPositionTimeseriesRepository(current_snapshot)
    repository.future_snapshots = [next_snapshot]
    repository.existing_by_date[next_snapshot.date] = _timeseries_record(next_snapshot)

    result = await MaterializePositionTimeseries(
        repository_provider=InMemoryRepositoryProvider(repository)
    ).execute(_command())

    assert result.dependent_days_changed == 1
    propagated_record = repository.upserted[1]
    assert propagated_record.date == date(2026, 4, 11)
    assert propagated_record.bod_market_value == Decimal("1260")
    assert repository.staged_dates == [date(2026, 4, 10), date(2026, 4, 11)]


async def test_backdated_materialization_does_not_create_absent_future_day() -> None:
    current_snapshot = _snapshot()
    repository = InMemoryPositionTimeseriesRepository(current_snapshot)
    repository.future_snapshots = [_snapshot(date(2026, 4, 11))]

    result = await MaterializePositionTimeseries(
        repository_provider=InMemoryRepositoryProvider(repository)
    ).execute(_command())

    assert result.dependent_days_changed == 0
    assert [record.date for record in repository.upserted] == [date(2026, 4, 10)]
    assert repository.staged_dates == [date(2026, 4, 10)]


async def test_backdated_materialization_stops_when_future_state_converges() -> None:
    current_snapshot = _snapshot()
    first_future = _snapshot(date(2026, 4, 11))
    second_future = _snapshot(date(2026, 4, 12))
    repository = InMemoryPositionTimeseriesRepository(current_snapshot)
    repository.future_snapshots = [first_future, second_future]
    repository.existing_by_date[first_future.date] = _timeseries_record(first_future)
    repository.existing_by_date[second_future.date] = _timeseries_record(
        second_future,
        bod_market_value=first_future.market_value_local or Decimal("0"),
    )

    result = await MaterializePositionTimeseries(
        repository_provider=InMemoryRepositoryProvider(repository)
    ).execute(_command())

    assert result.dependent_days_changed == 1
    assert [record.date for record in repository.upserted] == [
        date(2026, 4, 10),
        date(2026, 4, 11),
    ]
    assert repository.staged_dates == [date(2026, 4, 10), date(2026, 4, 11)]


@pytest.mark.parametrize(
    ("future_day_count", "expected_truncated"),
    [(4, False), (5, True)],
)
async def test_backdated_materialization_bounds_each_command_without_false_cap_warning(
    future_day_count: int,
    expected_truncated: bool,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(materialization_module, "MAX_DEPENDENT_PROPAGATION_ROWS", 2)
    monkeypatch.setattr(materialization_module, "MAX_DEPENDENT_PROPAGATION_BATCHES", 2)
    monkeypatch.setattr(materialization_module, "MAX_DEPENDENT_PROPAGATION_ROWS_PER_COMMAND", 4)
    current_snapshot = _snapshot()
    future_snapshots = [_snapshot(date(2026, 4, 11 + index)) for index in range(future_day_count)]
    repository = InMemoryPositionTimeseriesRepository(current_snapshot)
    repository.future_snapshots = future_snapshots
    repository.existing_by_date = {
        snapshot.date: _timeseries_record(snapshot) for snapshot in future_snapshots
    }
    caplog.set_level(logging.WARNING)

    result = await MaterializePositionTimeseries(
        repository_provider=InMemoryRepositoryProvider(repository)
    ).execute(_command())

    assert result.dependent_days_changed == 4
    assert result.dependent_propagation_truncated is expected_truncated
    assert (
        "Dependent position-timeseries propagation reached its command limit." in caplog.text
    ) is expected_truncated
    assert repository.staged_dates == [
        date(2026, 4, 10),
        date(2026, 4, 11),
        date(2026, 4, 12),
        date(2026, 4, 13),
        date(2026, 4, 14),
    ]
