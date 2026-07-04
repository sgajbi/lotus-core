from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services.ingestion_job_listing import (
    REPLAYABLE_INGESTION_JOB_STATUSES,
    IngestionJobListFilters,
    build_ingestion_job_list_statement,
    build_replayable_correlation_lookup_statement,
    ingestion_job_list_page,
    load_job_list_response,
    load_latest_replayable_job_by_correlation_id,
)


def test_ingestion_job_list_page_returns_rows_and_next_cursor():
    rows = [
        SimpleNamespace(job_id="job_3"),
        SimpleNamespace(job_id="job_2"),
        SimpleNamespace(job_id="job_1"),
    ]

    page = ingestion_job_list_page(rows=rows, limit=2)

    assert [row.job_id for row in page.rows] == ["job_3", "job_2"]
    assert page.next_cursor == "job_2"


def test_ingestion_job_list_page_has_no_cursor_when_final_page():
    rows = [SimpleNamespace(job_id="job_1")]

    page = ingestion_job_list_page(rows=rows, limit=2)

    assert [row.job_id for row in page.rows] == ["job_1"]
    assert page.next_cursor is None


def test_build_ingestion_job_list_statement_applies_filters_and_cursor():
    statement = build_ingestion_job_list_statement(
        filters=IngestionJobListFilters(
            status="accepted",
            entity_type="transaction",
            submitted_from=datetime(2026, 6, 1, tzinfo=UTC),
            submitted_to=datetime(2026, 6, 5, tzinfo=UTC),
        ),
        cursor_row=SimpleNamespace(id=100),
        limit=25,
    )

    compiled_sql = str(statement)

    assert "ingestion_jobs.status = :status_1" in compiled_sql
    assert "ingestion_jobs.entity_type = :entity_type_1" in compiled_sql
    assert "ingestion_jobs.submitted_at >= :submitted_at_1" in compiled_sql
    assert "ingestion_jobs.submitted_at <= :submitted_at_2" in compiled_sql
    assert "ingestion_jobs.id < :id_1" in compiled_sql
    assert "ORDER BY ingestion_jobs.id DESC" in compiled_sql


def test_build_replayable_correlation_lookup_statement_is_index_shaped():
    statement = build_replayable_correlation_lookup_statement(correlation_id="corr-001")

    compiled = statement.compile()
    compiled_sql = str(compiled)

    assert "ingestion_jobs.correlation_id = :correlation_id_1" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "ORDER BY ingestion_jobs.id DESC" in compiled_sql
    assert compiled.params["correlation_id_1"] == "corr-001"
    assert tuple(compiled.params["status_1"]) == REPLAYABLE_INGESTION_JOB_STATUSES


class _SingleSessionAsyncIterable:
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


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.scalar_calls = 0
        self.scalars_calls = 0

    async def scalar(self, _stmt):
        self.scalar_calls += 1
        return SimpleNamespace(id=100)

    async def scalars(self, _stmt):
        self.scalars_calls += 1
        return _FakeScalars(self.rows)


class _FakeScalarSession:
    def __init__(self, row):
        self.row = row
        self.scalar_calls = 0
        self.last_statement = None

    async def scalar(self, stmt):
        self.scalar_calls += 1
        self.last_statement = stmt
        return self.row


def _job_row(job_id: str):
    return SimpleNamespace(
        job_id=job_id,
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status="queued",
        accepted_count=10,
        idempotency_key=f"idem-{job_id}",
        correlation_id=f"corr-{job_id}",
        request_id=f"req-{job_id}",
        trace_id=f"trace-{job_id}",
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
        completed_at=None,
        failure_reason=None,
        retry_count=0,
        last_retried_at=None,
    )


@pytest.mark.asyncio
async def test_load_job_list_response_maps_rows_and_next_cursor():
    rows = [_job_row("job_3"), _job_row("job_2"), _job_row("job_1")]
    session = _FakeSession(rows)

    result, next_cursor = await load_job_list_response(
        filters=IngestionJobListFilters(
            status="queued",
            entity_type="transaction",
            submitted_from=datetime(2026, 6, 1, tzinfo=UTC),
            submitted_to=datetime(2026, 6, 5, tzinfo=UTC),
        ),
        cursor="job_4",
        limit=2,
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert session.scalar_calls == 1
    assert session.scalars_calls == 1
    assert [job.job_id for job in result] == ["job_3", "job_2"]
    assert result[0].endpoint == "/ingest/transactions"
    assert next_cursor == "job_2"


@pytest.mark.asyncio
async def test_load_latest_replayable_job_by_correlation_id_maps_latest_row():
    session = _FakeScalarSession(_job_row("job_500_plus"))

    result = await load_latest_replayable_job_by_correlation_id(
        correlation_id="corr-job_500_plus",
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert session.scalar_calls == 1
    assert result is not None
    assert result.job_id == "job_500_plus"
    assert result.correlation_id == "corr-job_500_plus"
    assert "correlation_id = :correlation_id_1" in str(session.last_statement)
    assert "ORDER BY ingestion_jobs.id DESC" in str(session.last_statement)


@pytest.mark.asyncio
async def test_load_latest_replayable_job_by_correlation_id_returns_none_when_missing():
    session = _FakeScalarSession(None)

    result = await load_latest_replayable_job_by_correlation_id(
        correlation_id="corr-missing",
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert session.scalar_calls == 1
    assert result is None
