from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services.ingestion_consumer_dlq_events import (
    get_consumer_dlq_event_response,
    list_consumer_dlq_event_responses,
    to_consumer_dlq_event_response,
)

pytestmark = pytest.mark.asyncio


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


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _EmptySessionAsyncIterator:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _event(**overrides):
    values = {
        "event_id": "dlq-1",
        "original_topic": "valuation.jobs",
        "consumer_group": "valuation-service-group",
        "dlq_topic": "valuation.jobs.dlq",
        "original_key": "portfolio-1",
        "error_reason_code": "VALIDATION_ERROR",
        "error_reason": "invalid payload",
        "correlation_id": "corr-1",
        "ingestion_job_id": "job-1",
        "payload_excerpt": '{"portfolio_id":"portfolio-1"}',
        "observed_at": datetime(2026, 6, 17, 1, 2, 3, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_to_consumer_dlq_event_response_preserves_operator_fields() -> None:
    response = to_consumer_dlq_event_response(_event())

    assert response.event_id == "dlq-1"
    assert response.original_topic == "valuation.jobs"
    assert response.consumer_group == "valuation-service-group"
    assert response.error_reason_code == "VALIDATION_ERROR"
    assert response.correlation_id == "corr-1"
    assert response.ingestion_job_id == "job-1"
    assert response.correlation_missing_reason is None
    assert response.alternate_lookup_key is None
    assert response.payload_excerpt == '{"portfolio_id":"portfolio-1"}'


async def test_to_consumer_dlq_event_response_derives_missing_correlation_lineage() -> None:
    response = to_consumer_dlq_event_response(
        _event(correlation_id=None, original_key=None, event_id="dlq-missing-corr")
    )

    assert response.correlation_id is None
    assert response.correlation_missing_reason == "message_correlation_id_absent"
    assert response.alternate_lookup_key == (
        "consumer_dlq|topic=valuation.jobs|group=valuation-service-group|"
        "dlq=valuation.jobs.dlq|key=unkeyed|event=dlq-missing-corr"
    )


async def test_to_consumer_dlq_event_response_preserves_persisted_fallback_lineage() -> None:
    response = to_consumer_dlq_event_response(
        _event(
            correlation_id=None,
            correlation_missing_reason="upstream_header_absent",
            alternate_lookup_key="custody-feed|batch-001|record-007",
        )
    )

    assert response.correlation_missing_reason == "upstream_header_absent"
    assert response.alternate_lookup_key == "custody-feed|batch-001|record-007"


async def test_list_consumer_dlq_event_responses_maps_rows() -> None:
    class _FakeSession:
        async def scalars(self, _stmt):
            return _FakeScalars([_event(event_id="dlq-1"), _event(event_id="dlq-2")])

    result = await list_consumer_dlq_event_responses(
        tenant_id="tenant-a",
        limit=50,
        original_topic="valuation.jobs",
        consumer_group="valuation-service-group",
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert [item.event_id for item in result] == ["dlq-1", "dlq-2"]


async def test_list_consumer_dlq_event_responses_filters_by_durable_job_owner() -> None:
    statements = []

    class _FakeSession:
        async def scalars(self, stmt):
            statements.append(stmt)
            return _FakeScalars([])

    await list_consumer_dlq_event_responses(
        tenant_id="tenant-a",
        limit=50,
        original_topic=None,
        consumer_group=None,
        ingestion_job_id="job-1",
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    compiled = str(statements[0])
    assert "JOIN ingestion_jobs" in compiled
    assert "ingestion_jobs.tenant_id =" in compiled
    assert "consumer_dlq_events.ingestion_job_id =" in compiled
    assert "consumer_dlq_events.observed_at DESC, consumer_dlq_events.id DESC" in compiled


async def test_list_consumer_dlq_event_responses_filters_replay_event_ids() -> None:
    statements = []

    class _FakeSession:
        async def scalars(self, stmt):
            statements.append(stmt)
            return _FakeScalars([])

    await list_consumer_dlq_event_responses(
        tenant_id="tenant-a",
        limit=50,
        original_topic=None,
        consumer_group=None,
        event_ids=("dlq-1", "dlq-2"),
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert "consumer_dlq_events.event_id IN" in str(statements[0])


async def test_get_consumer_dlq_event_response_returns_none_when_missing() -> None:
    class _FakeSession:
        async def scalar(self, _stmt):
            return None

    result = await get_consumer_dlq_event_response(
        tenant_id="tenant-a",
        event_id="missing",
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert result is None


async def test_dlq_queries_return_empty_when_session_factory_yields_no_session() -> None:
    session_factory = _EmptySessionAsyncIterator

    assert (
        await list_consumer_dlq_event_responses(
            tenant_id="tenant-a",
            limit=50,
            original_topic=None,
            consumer_group=None,
            session_factory=session_factory,
        )
        == []
    )
    assert (
        await get_consumer_dlq_event_response(
            tenant_id="tenant-a",
            event_id="missing",
            session_factory=session_factory,
        )
        is None
    )
