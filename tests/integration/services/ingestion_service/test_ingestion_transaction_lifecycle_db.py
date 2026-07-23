from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from portfolio_common.database_models import IngestionJob, OutboxEvent, ProcessedEvent, Transaction
from portfolio_common.domain.eventing import transaction_partition_key
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
    get_job_response,
    mark_job_queued,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
)
from src.services.persistence_service.app.consumers import base_consumer as base_consumer_module
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from tests.integration.services.persistence_service.consumers import (
    test_transaction_consumer_boundary as transaction_boundary,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.lifecycle]

JOB_ID = "JOB_LIFECYCLE_DB_001"
IDEMPOTENCY_KEY = "IDEMPOTENCY_LIFECYCLE_DB_001"
CORRELATION_ID = "CID-BOUNDARY-01"
REQUEST_ID = "REQ_LIFECYCLE_DB_001"
TRACE_ID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _session_provider(
    factory: async_sessionmaker[AsyncSession],
):
    async def provide() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    return provide


def _successful_producer(publications: list[dict[str, object]]) -> MagicMock:
    producer = MagicMock(spec=KafkaProducer)

    def publish_message(**kwargs: object) -> None:
        publications.append(kwargs)

    def flush(timeout: int = 10) -> None:  # noqa: ARG001
        for publication in publications:
            callback = publication.get("on_delivery")
            outbox_id = publication.get("outbox_id")
            if callable(callback) and isinstance(outbox_id, str):
                callback(outbox_id, True, None)

    producer.publish_message.side_effect = publish_message
    producer.flush.side_effect = flush
    return producer


async def test_transaction_ingestion_dispatches_once_and_retains_support_lineage(
    clean_db,
    async_db_session: AsyncSession,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"transactions": [transaction_boundary._transaction_payload()]}
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    session_provider = _session_provider(async_factory)
    monkeypatch.setattr(
        base_consumer_module,
        "get_async_db_session",
        session_provider,
    )

    created = await create_or_get_job_result(
        job_id=JOB_ID,
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key=IDEMPOTENCY_KEY,
        correlation_id=CORRELATION_ID,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
        request_payload=payload,
        session_factory=session_provider,
    )
    assert created.created is True
    assert created.job.status == "accepted"
    persisted_job = await async_db_session.scalar(
        select(IngestionJob).where(IngestionJob.job_id == JOB_ID)
    )
    assert persisted_job is not None
    assert persisted_job.request_payload_fingerprint == ingestion_payload_fingerprint(payload)
    assert await mark_job_queued(job_id=JOB_ID, session_factory=session_provider) is True

    await transaction_boundary._seed_portfolio(async_db_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="unused-in-db-direct-proof:9092",
        topic="raw-transactions",
        group_id="ingestion-transaction-lifecycle-db",
        dlq_topic=None,
    )
    await consumer.process_message(
        transaction_boundary._FakeMessage(transaction_boundary._transaction_payload())
    )

    outbox = (
        await async_db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == "PORT_BOUNDARY_01",
                OutboxEvent.event_type == "RawTransactionPersisted",
            )
        )
    ).scalar_one()
    assert outbox.status == "PENDING"
    assert outbox.correlation_id == CORRELATION_ID
    expected_partition_key = transaction_partition_key(
        portfolio_id="PORT_BOUNDARY_01",
        security_id="SEC_BOUNDARY_01",
        linked_transaction_group_id="LTG-BOUNDARY-01",
    ).value
    assert outbox.partition_key == expected_partition_key

    publications: list[dict[str, object]] = []
    dispatcher = OutboxDispatcher(
        kafka_producer=_successful_producer(publications),
        poll_interval=1,
        batch_size=10,
        db_session_factory=sessionmaker(bind=db_engine, expire_on_commit=False),
    )
    dispatcher._process_batch_sync()

    await async_db_session.refresh(outbox)
    assert outbox.status == "PROCESSED"
    assert outbox.processed_at is not None
    assert outbox.claim_token is None
    assert outbox.claim_expires_at is None
    assert len(publications) == 1
    assert publications[0]["key"] == expected_partition_key
    assert dict(publications[0]["headers"])["correlation_id"] == CORRELATION_ID.encode()

    durable_job = await get_job_response(job_id=JOB_ID, session_factory=session_provider)
    assert durable_job is not None
    assert durable_job.status == "queued"
    assert durable_job.correlation_id == CORRELATION_ID
    assert durable_job.request_id == REQUEST_ID
    assert durable_job.trace_id == TRACE_ID
    assert durable_job.accepted_count == 1
    assert durable_job.idempotency_key == IDEMPOTENCY_KEY
    assert durable_job.completed_at is not None

    await consumer.process_message(
        transaction_boundary._FakeMessage(
            transaction_boundary._transaction_payload(),
            offset=2,
        )
    )
    dispatcher._process_batch_sync()

    counts = {
        "jobs": await async_db_session.scalar(
            select(func.count()).select_from(IngestionJob).where(IngestionJob.job_id == JOB_ID)
        ),
        "transactions": await async_db_session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.transaction_id == "TXN_BOUNDARY_01")
        ),
        "processed_events": await async_db_session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(
                ProcessedEvent.event_id == "TXN_BOUNDARY_01",
                ProcessedEvent.service_name == "persistence-transactions",
            )
        ),
        "outbox": await async_db_session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == "PORT_BOUNDARY_01",
                OutboxEvent.event_type == "RawTransactionPersisted",
            )
        ),
    }
    assert counts == {"jobs": 1, "transactions": 1, "processed_events": 1, "outbox": 1}
    assert len(publications) == 1
