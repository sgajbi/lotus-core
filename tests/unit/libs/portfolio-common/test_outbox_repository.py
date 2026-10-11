# tests/unit/libs/portfolio-common/test_outbox_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import OutboxEvent
from portfolio_common.domain.eventing import portfolio_security_partition_key
from portfolio_common.events import CashflowCalculatedEvent
from portfolio_common.ingestion_lineage import ingestion_job_scope
from portfolio_common.logging_utils import traceparent_var
from portfolio_common.outbox_repository import (
    EVENT_SCHEMA_VERSION,
    OutboxRepository,
    build_outbox_payload,
)

TRACEPARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    # FIX: Configure .add() as a synchronous MagicMock
    session.add = MagicMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> OutboxRepository:
    """Provides an instance of the OutboxRepository with a mock session."""
    return OutboxRepository(mock_db_session)


async def test_create_outbox_event_success(
    repository: OutboxRepository, mock_db_session: AsyncMock
):
    """
    GIVEN valid event details
    WHEN create_outbox_event is called
    THEN it should stage a correctly formed OutboxEvent without an eager database flush.
    """
    # Arrange
    event_details = {
        "aggregate_type": "Test",
        "aggregate_id": "agg-123",
        "event_type": "TestEvent",
        "payload": {"data": "value"},
        "topic": "test.topic",
        "correlation_id": "corr-123",
    }

    # Act
    await repository.create_outbox_event(**event_details)

    # Assert
    mock_db_session.add.assert_called_once()
    mock_db_session.flush.assert_not_awaited()

    added_object = mock_db_session.add.call_args[0][0]
    assert isinstance(added_object, OutboxEvent)
    assert added_object.aggregate_id == event_details["aggregate_id"]
    assert added_object.partition_key == event_details["aggregate_id"]
    assert added_object.topic == event_details["topic"]
    assert added_object.payload == {
        "data": "value",
        "event_type": "TestEvent",
        "schema_version": EVENT_SCHEMA_VERSION,
        "correlation_id": "corr-123",
        "traceparent": None,
    }
    assert added_object.status == "PENDING"
    assert event_details["payload"] == {"data": "value"}


async def test_create_outbox_event_separates_aggregate_and_partition_identity(
    repository: OutboxRepository,
) -> None:
    event = await repository.create_outbox_event(
        aggregate_type="DailyPositionSnapshot",
        aggregate_id="snapshot-101",
        partition_key=portfolio_security_partition_key("PORT_001", "SEC_A"),
        event_type="DailyPositionSnapshotPersisted",
        payload={"snapshot_id": 101},
        topic="valuation.snapshot.persisted",
    )

    assert event.aggregate_id == "snapshot-101"
    assert event.partition_key == "PORT_001|SEC_A"


async def test_create_outbox_event_rejects_blank_partition_key(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="partition_key is required"):
        await repository.create_outbox_event(
            aggregate_type="DailyPositionSnapshot",
            aggregate_id="snapshot-101",
            partition_key="   ",
            event_type="DailyPositionSnapshotPersisted",
            payload={"snapshot_id": 101},
            topic="valuation.snapshot.persisted",
        )


async def test_create_outbox_event_raises_type_error_for_bad_payload(repository: OutboxRepository):
    """
    GIVEN a payload that is not a dictionary
    WHEN create_outbox_event is called
    THEN it should raise a TypeError.
    """
    # Arrange
    event_details = {
        "aggregate_type": "Test",
        "aggregate_id": "agg-123",
        "event_type": "TestEvent",
        "payload": "just a string",  # Invalid payload type
        "topic": "test.topic",
    }

    # Act & Assert
    with pytest.raises(TypeError, match="payload must be a dict"):
        await repository.create_outbox_event(**event_details)


async def test_create_outbox_event_normalizes_sentinel_correlation(
    repository: OutboxRepository, mock_db_session: AsyncMock
):
    event = await repository.create_outbox_event(
        aggregate_type="portfolio",
        aggregate_id="P1",
        event_type="evt",
        payload={"x": 1},
        topic="topic-1",
        correlation_id="<not-set>",
    )

    assert event.correlation_id is None
    assert event.correlation_missing_reason == "correlation_id_not_supplied"
    assert (
        event.alternate_lookup_key
        == "outbox_event|aggregate_id=P1|aggregate_type=portfolio|event_type=evt|topic=topic-1"
    )
    assert event.payload["correlation_id"] is None
    assert event.payload["traceparent"] is None


async def test_create_outbox_event_captures_traceparent_context(
    repository: OutboxRepository,
) -> None:
    token = traceparent_var.set(TRACEPARENT)
    try:
        event = await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="evt",
            payload={"x": 1},
            topic="topic-1",
            correlation_id="corr-123",
        )
    finally:
        traceparent_var.reset(token)

    assert event.payload["traceparent"] == TRACEPARENT


async def test_create_outbox_event_captures_durable_ingestion_job_owner(
    repository: OutboxRepository,
) -> None:
    with ingestion_job_scope("job-001"):
        event = await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="evt",
            payload={"x": 1},
            topic="topic-1",
            correlation_id="corr-123",
        )

    assert event.ingestion_job_id == "job-001"


async def test_create_outbox_event_rejects_conflicting_payload_traceparent(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="payload traceparent"):
        await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="ExpectedEvent",
            payload={"traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"},
            topic="topic-1",
            traceparent=TRACEPARENT,
        )


async def test_create_outbox_event_rejects_conflicting_payload_event_type(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="payload event_type 'OtherEvent'"):
        await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="ExpectedEvent",
            payload={"event_type": "OtherEvent"},
            topic="topic-1",
        )


async def test_create_outbox_event_rejects_conflicting_payload_correlation_id(
    repository: OutboxRepository,
) -> None:
    with pytest.raises(ValueError, match="payload correlation_id 'payload-corr'"):
        await repository.create_outbox_event(
            aggregate_type="portfolio",
            aggregate_id="P1",
            event_type="ExpectedEvent",
            payload={"correlation_id": "payload-corr"},
            topic="topic-1",
            correlation_id="outbox-corr",
        )


async def test_enriched_payload_remains_compatible_with_event_models(
    repository: OutboxRepository,
) -> None:
    event = await repository.create_outbox_event(
        aggregate_type="Cashflow",
        aggregate_id="P1",
        event_type="CashflowCalculated",
        payload={
            "cashflow_id": 101,
            "transaction_id": "T1",
            "portfolio_id": "P1",
            "security_id": "S1",
            "cashflow_date": "2026-04-10",
            "amount": "12.34",
            "currency": "USD",
            "classification": "DIVIDEND",
            "timing": "eod",
            "is_position_flow": True,
            "is_portfolio_flow": False,
            "calculation_type": "standard",
        },
        topic="cashflows.calculated",
        correlation_id="corr-123",
    )

    parsed = CashflowCalculatedEvent.model_validate(event.payload)

    assert parsed.transaction_id == "T1"
    assert event.payload["event_type"] == "CashflowCalculated"
    assert event.payload["schema_version"] == EVENT_SCHEMA_VERSION


@pytest.mark.parametrize("payload", [None, [], "not-a-domain-object"])
async def test_payload_builder_refuses_non_object_payload_before_enrichment(payload) -> None:
    with pytest.raises(TypeError, match="payload must be a dict"):
        build_outbox_payload(
            payload=payload,
            event_type="TransactionIngested",
            correlation_id="corr-source",
        )


@pytest.mark.parametrize(
    "event_type",
    ["TransactionIngested", "RawTransactionPersisted", "ProcessedTransactionPersisted"],
)
async def test_transaction_outbox_refuses_unsupported_schema_without_staging(
    repository: OutboxRepository, mock_db_session: AsyncMock, event_type: str
) -> None:
    payload = {"transaction_id": "TXN-SOURCE-1", "schema_version": "2.0.0"}
    original = dict(payload)

    with pytest.raises(ValueError, match="Unsupported transaction schema_version"):
        await repository.create_outbox_event(
            aggregate_type="Transaction",
            aggregate_id="TXN-SOURCE-1",
            event_type=event_type,
            payload=payload,
            topic="transactions.source",
            correlation_id="corr-source",
        )

    assert payload == original
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "event_type",
    ["TransactionIngested", "RawTransactionPersisted", "ProcessedTransactionPersisted"],
)
@pytest.mark.parametrize("schema_version", ["1.0.0", "1.1.0"])
async def test_transaction_outbox_accepts_supported_schema_and_preserves_source_payload(
    repository: OutboxRepository, event_type: str, schema_version: str
) -> None:
    payload = {
        "transaction_id": "TXN-SOURCE-1",
        "schema_version": schema_version,
        "event_type": event_type,
    }
    if schema_version == "1.1.0":
        payload.update(source_record_id="REC-1", source_batch_id="BATCH-1")
    original = dict(payload)

    event = await repository.create_outbox_event(
        aggregate_type="Transaction",
        aggregate_id="TXN-SOURCE-1",
        event_type=event_type,
        payload=payload,
        topic="transactions.source",
        correlation_id="corr-source",
        traceparent=TRACEPARENT,
    )

    assert event.payload == {
        **original,
        "correlation_id": "corr-source",
        "traceparent": TRACEPARENT,
    }
    assert event.status == "PENDING"
    assert event.aggregate_id == event.partition_key == "TXN-SOURCE-1"
    assert payload == original
