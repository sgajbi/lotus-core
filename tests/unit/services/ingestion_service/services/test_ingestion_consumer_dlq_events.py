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


async def test_list_consumer_dlq_event_responses_maps_rows() -> None:
    class _FakeSession:
        async def scalars(self, _stmt):
            return _FakeScalars([_event(event_id="dlq-1"), _event(event_id="dlq-2")])

    result = await list_consumer_dlq_event_responses(
        limit=50,
        original_topic="valuation.jobs",
        consumer_group="valuation-service-group",
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert [item.event_id for item in result] == ["dlq-1", "dlq-2"]


async def test_get_consumer_dlq_event_response_returns_none_when_missing() -> None:
    class _FakeSession:
        async def scalar(self, _stmt):
            return None

    result = await get_consumer_dlq_event_response(
        event_id="missing",
        session_factory=lambda: _SingleSessionAsyncIterator(_FakeSession()),
    )

    assert result is None
