import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.events import PortfolioDayReadyForValuationEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.consumers.valuation_readiness_consumer import (
    SERVICE_NAME,
    ValuationReadinessConsumer,
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


@pytest.fixture
def consumer() -> ValuationReadinessConsumer:
    consumer = ValuationReadinessConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_security_day.valuation.ready",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> PortfolioDayReadyForValuationEvent:
    return PortfolioDayReadyForValuationEvent(
        portfolio_id="PORT-VAL-1",
        security_id="SEC-VAL-1",
        valuation_date=date(2026, 3, 7),
        epoch=0,
    )


@pytest.fixture
def mock_kafka_message(mock_event: PortfolioDayReadyForValuationEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"PORT-VAL-1:SEC-VAL-1"
    msg.topic.return_value = "portfolio_security_day.valuation.ready"
    msg.partition.return_value = 0
    msg.offset.return_value = 1
    msg.headers.return_value = []
    return msg


@pytest.fixture
def mock_dependencies():
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_job_repo = AsyncMock(spec=ValuationJobRepository)
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()

    def get_session_gen():
        return _SingleSessionAsyncIterator(mock_db_session)

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.valuation_readiness_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.valuation_readiness_consumer.IdempotencyRepository",
            return_value=mock_idempotency_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.consumers.valuation_readiness_consumer.ValuationJobRepository",
            return_value=mock_job_repo,
        ),
    ):
        yield {"idempotency_repo": mock_idempotency_repo, "job_repo": mock_job_repo}


async def test_readiness_event_upserts_valuation_job_and_marks_idempotency(
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioDayReadyForValuationEvent,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_awaited_once()
    job_kwargs = mock_job_repo.upsert_job.await_args.kwargs
    assert job_kwargs["portfolio_id"] == mock_event.portfolio_id
    assert job_kwargs["security_id"] == mock_event.security_id
    assert job_kwargs["valuation_date"] == mock_event.valuation_date
    assert job_kwargs["epoch"] == mock_event.epoch
    assert isinstance(job_kwargs["correlation_id"], str)

    mock_idempotency_repo.claim_event_processing.assert_awaited_once()
    mark_args = mock_idempotency_repo.claim_event_processing.await_args.args
    assert mark_args[0] == "portfolio_security_day.valuation.ready-0-1"
    assert mark_args[1] == mock_event.portfolio_id
    assert mark_args[2] == SERVICE_NAME


async def test_readiness_event_is_noop_when_already_processed(
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = False

    await consumer.process_message(mock_kafka_message)

    mock_job_repo.upsert_job.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()


async def test_invalid_payload_is_sent_to_dlq(consumer: ValuationReadinessConsumer):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"portfolio_id": "x"}).encode("utf-8")
    msg.key.return_value = b"bad"
    msg.topic.return_value = "portfolio_security_day.valuation.ready"
    msg.partition.return_value = 0
    msg.offset.return_value = 2
    msg.headers.return_value = []

    await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_awaited_once()


async def test_readiness_event_uses_header_correlation_for_direct_processing(
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_kafka_message.headers.return_value = [("correlation_id", b"test-corr-id")]

    await consumer.process_message(mock_kafka_message)

    assert mock_job_repo.upsert_job.await_args.kwargs["correlation_id"] == "test-corr-id"
    assert mock_idempotency_repo.claim_event_processing.await_args.args[3] == "test-corr-id"
