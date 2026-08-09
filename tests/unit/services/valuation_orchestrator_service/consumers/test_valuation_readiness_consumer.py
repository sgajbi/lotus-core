import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.event_mapping import EventContractValidationError
from portfolio_common.events import (
    GOVERNED_EVENT_SCHEMA_VERSION,
    PortfolioDayReadyForValuationEvent,
)
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.consumers.valuation_readiness_consumer import (
    SERVICE_NAME,
    ValuationReadinessConsumer,
    _readiness_outbox_id,
    _readiness_source_mutation_id,
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
        event_type="PortfolioDayReadyForValuation",
        schema_version=GOVERNED_EVENT_SCHEMA_VERSION,
    )


@pytest.fixture
def mock_kafka_message(mock_event: PortfolioDayReadyForValuationEvent) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    msg.key.return_value = b"PORT-VAL-1:SEC-VAL-1"
    msg.topic.return_value = "portfolio_security_day.valuation.ready"
    msg.partition.return_value = 0
    msg.offset.return_value = 1
    msg.headers.return_value = [("outbox_id", b"417")]
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

    mock_job_repo.upsert_position_readiness_job.assert_awaited_once()
    job_kwargs = mock_job_repo.upsert_position_readiness_job.await_args.kwargs
    assert job_kwargs["portfolio_id"] == mock_event.portfolio_id
    assert job_kwargs["security_id"] == mock_event.security_id
    assert job_kwargs["valuation_date"] == mock_event.valuation_date
    assert job_kwargs["epoch"] == mock_event.epoch
    assert isinstance(job_kwargs["correlation_id"], str)
    assert job_kwargs["source_mutation_id"] == _readiness_source_mutation_id(417)
    assert job_kwargs["readiness_outbox_id"] == 417

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
    mock_job_repo.upsert_position_readiness_job.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()


async def test_invalid_payload_is_raised_to_shared_recovery_boundary(
    consumer: ValuationReadinessConsumer,
):
    msg = MagicMock()
    msg.value.return_value = json.dumps({"portfolio_id": "x"}).encode("utf-8")
    msg.key.return_value = b"bad"
    msg.topic.return_value = "portfolio_security_day.valuation.ready"
    msg.partition.return_value = 0
    msg.offset.return_value = 2
    msg.headers.return_value = []

    with pytest.raises(EventContractValidationError):
        await consumer.process_message(msg)

    consumer._send_to_dlq_async.assert_not_awaited()


async def test_readiness_event_uses_header_correlation_for_direct_processing(
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo.claim_event_processing.return_value = True
    mock_kafka_message.headers.return_value = [
        ("correlation_id", b"test-corr-id"),
        ("outbox_id", b"417"),
    ]

    await consumer.process_message(mock_kafka_message)

    assert (
        mock_job_repo.upsert_position_readiness_job.await_args.kwargs["correlation_id"]
        == "test-corr-id"
    )
    assert mock_idempotency_repo.claim_event_processing.await_args.args[3] == "test-corr-id"


async def test_headerless_readiness_event_preserves_non_rearming_compatibility(
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
):
    mock_dependencies["idempotency_repo"].claim_event_processing.return_value = True
    mock_kafka_message.headers.return_value = []

    await consumer.process_message(mock_kafka_message)

    job_kwargs = mock_dependencies["job_repo"].upsert_job.await_args.kwargs
    assert job_kwargs.get("source_correction_id") is None
    assert job_kwargs.get("rearm_completed", False) is False
    assert job_kwargs.get("requeue_if_processing", False) is False
    mock_dependencies["job_repo"].upsert_position_readiness_job.assert_not_called()


async def test_readiness_source_mutation_identity_is_redelivery_stable_and_event_specific():
    first = MagicMock()
    first.headers.return_value = [("outbox_id", b"417"), ("correlation_id", b"transport-a")]
    duplicate = MagicMock()
    duplicate.headers.return_value = [
        ("correlation_id", b"transport-b"),
        ("outbox_id", b"417"),
    ]
    later_mutation = MagicMock()
    later_mutation.headers.return_value = [("outbox_id", b"418")]

    first_id = _readiness_outbox_id(first)
    duplicate_id = _readiness_outbox_id(duplicate)
    later_id = _readiness_outbox_id(later_mutation)
    assert first_id == duplicate_id == 417
    assert later_id == 418
    assert _readiness_source_mutation_id(first_id) == _readiness_source_mutation_id(duplicate_id)
    assert _readiness_source_mutation_id(first_id) != _readiness_source_mutation_id(later_id)


@pytest.mark.parametrize("raw_value", [b"0", b"-1", b"not-an-id", b""])
async def test_readiness_rejects_nonpositive_or_malformed_outbox_sequence(raw_value: bytes):
    message = MagicMock()
    message.headers.return_value = [("outbox_id", raw_value)]

    with pytest.raises(EventContractValidationError, match="positive integer"):
        _readiness_outbox_id(message)


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [(b"\xff", "UTF-8"), (417, "must be text")],
)
async def test_readiness_rejects_non_text_transport_sequences(
    raw_value: object,
    message: str,
) -> None:
    kafka_message = MagicMock()
    kafka_message.headers.return_value = [("outbox_id", raw_value)]

    with pytest.raises(EventContractValidationError, match=message):
        _readiness_outbox_id(kafka_message)


async def test_readiness_fails_closed_when_transport_headers_are_unreadable() -> None:
    message = MagicMock()
    message.headers.side_effect = RuntimeError("transport unavailable")

    with pytest.raises(EventContractValidationError, match="could not be inspected"):
        _readiness_outbox_id(message)


@pytest.mark.parametrize("raw_value", [b"0", b"-1", b"not-an-id", b""])
async def test_present_invalid_sequence_fails_before_idempotency_claim(
    raw_value: bytes,
    consumer: ValuationReadinessConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
) -> None:
    mock_kafka_message.headers.return_value = [("outbox_id", raw_value)]

    with pytest.raises(EventContractValidationError, match="positive integer"):
        await consumer.process_message(mock_kafka_message)

    mock_dependencies["idempotency_repo"].claim_event_processing.assert_not_awaited()
    mock_dependencies["job_repo"].upsert_job.assert_not_awaited()
    mock_dependencies["job_repo"].upsert_position_readiness_job.assert_not_awaited()
