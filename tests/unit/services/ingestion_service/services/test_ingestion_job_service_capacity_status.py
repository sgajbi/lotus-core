import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import SQLAlchemyError

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    _derive_capacity_group,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "records,expected",
    [
        ([("completed", 60)], (60, 60, 0, 0)),
        ([("completed", 60), ("queued", 20), ("failed", 10), ("accepted", 30)], (120, 90, 30, 1)),
    ],
)
async def test_capacity_executes_status_aggregation_sql(service, monkeypatch, records, expected):
    # Execute the production aggregation, not precomputed fake result rows.
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            "CREATE TABLE ingestion_jobs (endpoint TEXT, entity_type TEXT, "
            "accepted_count INTEGER, status TEXT, submitted_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO ingestion_jobs VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "/observations",
                    "observation",
                    count,
                    status,
                    datetime.now(UTC).replace(tzinfo=None).isoformat(" "),
                )
                for status, count in records
            ],
        )

        class Session:
            async def execute(self, statement):
                sql = statement.compile(
                    dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
                )
                return connection.execute(str(sql)).fetchall()

        monkeypatch.setattr(
            service_module, "get_async_db_session", lambda: _SingleSessionAsyncIterator(Session())
        )
        result = await service.get_capacity_status(lookback_minutes=1, limit=10, assumed_replicas=1)
    group = result.groups[0]
    assert (
        group.total_records,
        group.processed_records,
        group.backlog_records,
        group.backlog_jobs,
    ) == expected
    assert group.mu_msg_per_replica_events_per_second == Decimal(expected[1]) / Decimal(60)


class _SingleSessionAsyncIterator:
    def __init__(self, session):
        self._session = session
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return self._session


@pytest.fixture
def service() -> IngestionJobService:
    return IngestionJobService()


async def test_derive_capacity_group_marks_over_capacity_when_utilization_exceeds_one() -> None:
    result = _derive_capacity_group(
        endpoint="/ingest/transactions",
        entity_type="transaction",
        total_records=720,
        processed_records=360,
        backlog_records=120,
        backlog_jobs=3,
        lookback_seconds=Decimal("60"),
        assumed_replicas=1,
    )

    assert result.lambda_in_events_per_second == Decimal("12")
    assert result.mu_msg_per_replica_events_per_second == Decimal("6")
    assert result.effective_capacity_events_per_second == Decimal("6")
    assert result.utilization_ratio == Decimal("2")
    assert result.headroom_ratio == Decimal("-1")
    assert result.saturation_state == "over_capacity"
    assert result.estimated_drain_seconds is None


async def test_get_capacity_status_aggregates_groups(service: IngestionJobService, monkeypatch):
    class _FakeSession:
        async def execute(self, _stmt):
            return [
                ("/ingest/transactions", "transaction", 1200, 900, 300, 6),
                ("/ingest/instruments", "instrument", 200, 200, 0, 0),
            ]

    def _mock_get_async_db_session():
        return _SingleSessionAsyncIterator(_FakeSession())

    monkeypatch.setattr(service_module, "get_async_db_session", _mock_get_async_db_session)

    result = await service.get_capacity_status(
        lookback_minutes=60,
        limit=10,
        assumed_replicas=2,
    )

    assert result.lookback_minutes == 60
    assert result.assumed_replicas == 2
    assert result.total_groups == 2
    assert result.total_backlog_records == 300
    assert result.as_of <= datetime.now(UTC)

    first = result.groups[0]
    assert first.endpoint == "/ingest/transactions"
    assert first.total_records == 1200
    assert first.processed_records == 900
    assert first.backlog_records == 300
    assert first.lambda_in_events_per_second == Decimal("0.3333333333333333333333333333")
    assert first.mu_msg_per_replica_events_per_second == Decimal("0.25")
    assert first.effective_capacity_events_per_second == Decimal("0.50")
    assert first.utilization_ratio == Decimal("0.6666666666666666666666666666")
    assert first.saturation_state == "stable"
    assert first.estimated_drain_seconds is not None


async def test_capacity_without_session_returns_empty_default_replica_posture(service, monkeypatch):
    async def sessions():
        for session in ():
            yield session

    monkeypatch.setattr(service_module, "get_async_db_session", sessions)
    monkeypatch.setattr(service_module, "CAPACITY_ASSUMED_REPLICAS", 3)
    result = await service.get_capacity_status(lookback_minutes=15, limit=10)
    assert result.assumed_replicas == 3
    assert result.lookback_minutes == 15
    assert result.groups == [] and result.total_groups == result.total_backlog_records == 0


async def test_capacity_query_failure_propagates_instead_of_fabricating_available_metrics(
    service, monkeypatch
):
    error = SQLAlchemyError("synthetic capacity lookup unavailable")
    db = SimpleNamespace(execute=AsyncMock(side_effect=error))
    monkeypatch.setattr(
        service_module, "get_async_db_session", lambda: _SingleSessionAsyncIterator(db)
    )
    with pytest.raises(SQLAlchemyError) as observed:
        await service.get_capacity_status()
    assert observed.value is error
    db.execute.assert_awaited_once()


@pytest.mark.parametrize("rows", [[], [("/observations", "observation", None, None, None, None)]])
async def test_capacity_empty_query_and_null_counts_do_not_invent_backlog(
    service, monkeypatch, rows
):
    db = SimpleNamespace(execute=AsyncMock(return_value=rows))
    monkeypatch.setattr(
        service_module, "get_async_db_session", lambda: _SingleSessionAsyncIterator(db)
    )
    result = await service.get_capacity_status(assumed_replicas=0)
    assert result.assumed_replicas == 1
    assert result.total_backlog_records == 0 and result.total_groups == len(rows)
    if rows:
        group = result.groups[0]
        assert group.total_records == group.processed_records == group.backlog_records == 0
        assert group.utilization_ratio == 0 and group.headroom_ratio == 1
        assert group.estimated_drain_seconds is None and group.saturation_state == "stable"


@pytest.mark.parametrize("replicas,expected_state", [(1, "near_capacity"), (2, "stable")])
async def test_capacity_distinguishes_near_capacity_from_drainable_headroom(
    replicas, expected_state
):
    group = _derive_capacity_group(
        endpoint="/observations",
        entity_type="observation",
        total_records=100,
        processed_records=120,
        backlog_records=100,
        backlog_jobs=1,
        lookback_seconds=Decimal("60"),
        assumed_replicas=replicas,
    )
    assert group.saturation_state == expected_state
    expected_drain = float(Decimal(100) / (Decimal(2 * replicas) - Decimal(100) / Decimal(60)))
    assert group.estimated_drain_seconds == expected_drain
    assert group.effective_capacity_events_per_second == Decimal(2 * replicas)
    assert group.total_records == 100 and group.backlog_records == 100
