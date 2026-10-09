"""Registered ASGI HTTP -> native consumer/UOW -> PostgreSQL -> registered reads.

The broker is an explicit recording substitute; this is not a Kafka/runtime claim.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from portfolio_common.database_models import IngestionJob, Transaction
from portfolio_common.event_publisher import KafkaEventPublisher
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.kafka_utils import KafkaProducer
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.event_replay_service.app.main import app as evidence_app
from src.services.ingestion_service.app import dependencies
from src.services.ingestion_service.app.main import app as ingress_app
from src.services.ingestion_service.app.routers.transactions import (
    TRANSACTION_LINEAGE_SOURCE_SYSTEM_REQUIRED_EXAMPLE,
)
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    get_ingestion_job_service,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionService
from src.services.persistence_service.app.consumers import base_consumer
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.query_service.app.main import app as query_app
from tests.integration.services.persistence_service.consumers import (
    test_transaction_consumer_boundary as boundary,
)
from tests.test_support.tenant import TEST_TENANT_HEADERS
from tests.test_support.transaction_processing import portfolio_record

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.asyncio]

PORTFOLIO = "PORT-SUPPLIER-LINEAGE"
_FakeMessage = boundary._FakeMessage


def _record(identifier, batch):
    record = {
        "transaction_id": identifier,
        "portfolio_id": PORTFOLIO,
        "instrument_id": "SEC-SUPPLIER-LINEAGE",
        "security_id": "SEC-SUPPLIER-LINEAGE",
        "transaction_date": "2026-10-09T09:00:00Z",
        "transaction_type": "BUY",
        "quantity": "2",
        "price": "10",
        "gross_transaction_amount": "20",
        "trade_currency": "USD",
        "currency": "USD",
        "source_system": "CUSTODY",
    }
    if batch is not None:
        record.update(
            source_record_id=f"SUPPLIER-{identifier}",
            source_batch_id=batch,
            observed_at="2026-10-09T09:30:00Z",
        )
    return record


@pytest.mark.parametrize(
    ("batches", "reason"),
    [
        (("BATCH-1", "BATCH-1"), "PROVEN"),
        (("BATCH-1", "BATCH-2"), "MIXED_BATCHES"),
        ((None, None), "LEGACY_UNKNOWN"),
    ],
)
async def test_registered_supplier_lineage_persists_without_changing_booking_fence(
    clean_db,
    async_db_session,
    monkeypatch,
    batches,
    reason,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def sessions():
        async with factory() as session:
            yield session

    async with factory() as session, session.begin():
        assert (
            await session.scalar(text("SELECT version_num FROM alembic_version"))
            == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        )
        session.add(portfolio_record(PORTFOLIO))
    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 0
    publications = []
    producer.publish_message.side_effect = lambda **kwargs: publications.append(kwargs)
    service = IngestionService(KafkaEventPublisher(producer))
    jobs = IngestionJobService(session_factory=sessions)
    overrides = {
        dependencies.get_async_db_session: sessions,
        dependencies.get_ingestion_service: lambda: service,
        get_ingestion_job_service: lambda: jobs,
    }
    apps = (ingress_app, query_app, evidence_app)
    assert all(not set(overrides).intersection(app.dependency_overrides) for app in apps)
    for app in apps:
        app.dependency_overrides.update(overrides)
    monkeypatch.setattr(base_consumer, "get_async_db_session", sessions)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="unused-broker-substitute:9092",
        topic="raw-transactions",
        group_id="supplier-lineage-proof",
        dlq_topic=None,
    )
    try:
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=ingress_app),
                base_url="http://ingress",
                headers=TEST_TENANT_HEADERS,
            ) as ingress,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=query_app),
                base_url="http://query",
                headers=TEST_TENANT_HEADERS,
            ) as query,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=evidence_app),
                base_url="http://evidence",
                headers={**TEST_TENANT_HEADERS, "X-Lotus-Ops-Token": "lotus-core-ops-local"},
            ) as evidence,
        ):
            records = [_record(f"TX-SUPPLIER-{i}", batch) for i, batch in enumerate(batches)]
            invalid = {
                **records[0],
                "source_record_id": "RECORD-WITHOUT-SYSTEM",
                "source_system": None,
            }
            refused = await ingress.post("/ingest/transactions", json={"transactions": [invalid]})
            assert refused.status_code == 400, refused.text
            assert refused.json() == TRANSACTION_LINEAGE_SOURCE_SYSTEM_REQUIRED_EXAMPLE
            assert refused.json()["detail"]["code"] == "TRANSACTION_LINEAGE_SOURCE_SYSTEM_REQUIRED"
            typo = {**records[0], "source_batch_identifer": "BATCH-TYPO"}
            refused = await ingress.post("/ingest/transactions", json={"transactions": [typo]})
            assert refused.status_code == 400, refused.text
            assert refused.json()["detail"]["code"] == "TRANSACTION_LINEAGE_UNKNOWN_FIELD"
            assert publications == []
            response = await ingress.post("/ingest/transactions", json={"transactions": records})
            assert response.status_code == 202, response.text
            assert response.json()["accepted_count"] == 2
            job_id = response.json()["job_id"]
            assert len(publications) == 2
            payloads = [json.loads(json.dumps(item["value"], default=str)) for item in publications]
            for payload in payloads:
                if payload.get("source_batch_id") is not None:
                    assert payload["schema_version"] == "1.1.0"
                else:
                    assert "source_batch_id" not in payload
                    assert "schema_version" not in payload
                await consumer.process_message(_FakeMessage(payload))
            async with factory() as session:
                job = await session.scalar(
                    select(IngestionJob).where(IngestionJob.job_id == job_id)
                )
                assert job.request_payload is None
                assert job.request_payload_replay_eligible is False
                assert job.transaction_batch_lineage["reason"] == reason
            # Fresh connections read durable state after the consumer UOW has committed.
            ledger = await query.get(
                f"/portfolios/{PORTFOLIO}/transactions",
                params={"include_projected": "true", "limit": 1},
            )
            assert ledger.status_code == 200, ledger.text
            body = ledger.json()
            assert body["total"] == 2
            assert body["source_lineage"]["batch_lineage_reason"] == reason
            assert bool(body["source_batch_fingerprint"]) == (reason == "PROVEN")
            # Batch proof covers the complete window, not just this one-row page.
            assert len(body["transactions"]) == 1
            if batches[0] is not None:
                filtered = await query.get(
                    f"/portfolios/{PORTFOLIO}/transactions",
                    params={
                        "include_projected": "true",
                        "source_system": "CUSTODY",
                        "source_batch_id": "BATCH-1",
                    },
                )
                assert filtered.status_code == 200, filtered.text
                assert {row["transaction_id"] for row in filtered.json()["transactions"]} == {
                    record["transaction_id"]
                    for record in records
                    if record.get("source_batch_id") == "BATCH-1"
                }
            bundle = await evidence.get(f"/ingestion/jobs/{job_id}/evidence")
            assert bundle.status_code == 200, bundle.text
            assert bundle.json()["source_lineage"]["batch_lineage_reason"] == reason
            assert bundle.json()["source_batch_fingerprint"] == body["source_batch_fingerprint"]
            original = payloads[0]
            # Metadata-only replay is a no-op; first accepted lineage remains immutable.
            replay = {
                **original,
                "source_record_id": "REPLAY-RECORD",
                "source_batch_id": "REPLAY-BATCH",
            }
            await consumer.process_message(_FakeMessage(replay, offset=20))
            with pytest.raises(TransactionSemanticConflictError):
                await consumer.process_message(_FakeMessage({**replay, "quantity": "3"}, offset=21))
            async with factory() as session:
                persisted = await session.scalar(
                    select(Transaction).where(
                        Transaction.transaction_id == original["transaction_id"]
                    )
                )
                assert persisted.source_batch_id == batches[0]
                assert persisted.source_record_id == records[0].get("source_record_id")
                assert persisted.quantity == 2
            async with factory() as session:
                for mutation in (
                    {"source_batch_id": "FORGED-BATCH"},
                    {"source_record_id": "FORGED-RECORD"},
                    {"observed_at": datetime.fromisoformat("2026-10-10T09:30:00+00:00")},
                    {"source_system": "FORGED-SYSTEM"},
                    *(({"source_batch_id": None},) if batches[0] is not None else ()),
                ):
                    with pytest.raises(DBAPIError, match="supplier lineage is immutable"):
                        await session.execute(
                            update(Transaction)
                            .where(Transaction.transaction_id == original["transaction_id"])
                            .values(**mutation)
                        )
                    await session.rollback()
                # A valid processor update retaining the same lineage is allowed.
                await session.execute(
                    update(Transaction)
                    .where(Transaction.transaction_id == original["transaction_id"])
                    .values(source_batch_id=batches[0])
                )
                await session.commit()
            foreign = await query.get(
                f"/portfolios/{PORTFOLIO}/transactions", headers={"X-Tenant-Id": "tenant-foreign"}
            )
            assert foreign.status_code == 404
    finally:
        for app in apps:
            for key in overrides:
                app.dependency_overrides.pop(key, None)
