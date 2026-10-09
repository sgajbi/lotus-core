"""Registered signed HTTP to real job/inbox/cut/revisions/outbox/QCP transactions.

The existing publisher transport is captured and fed to the registered consumer;
this proves actual PostgreSQL effects, not Kafka delivery or supplier approval.
"""

import json
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import FxRate, IngestionJob, OutboxEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.event_publisher import (
    EventPublishResult,
    EventPublishStatus,
    get_kafka_event_publisher,
)
from portfolio_common.fx_source_events import FxSourceCutPersistedEvent
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import func, select

from src.services.ingestion_service.app import dependencies
from src.services.ingestion_service.app.main import app
from src.services.ingestion_service.app.services import ingestion_job_service
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService
from src.services.persistence_service.app.consumers import base_consumer
from src.services.persistence_service.app.consumers.fx_rate_consumer import FxRateConsumer
from src.services.query_control_plane_service.app.domain.market_fx import FxSourceSelection
from src.services.query_control_plane_service.app.infrastructure.retained_fx_sources import (
    read_retained_fx_rates,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_source_notification,
)
from tests.test_support import fx_source_database as fx_db_fixtures
from tests.test_support.fx_source_fixtures import (
    OBSERVED,
    configure_synthetic_fx_source,
    signed_event,
    signed_headers,
    submission,
    synthetic_cut,
    synthetic_revision,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
fx_source_schema = fx_db_fixtures.fx_source_schema
fx_source_database = fx_db_fixtures.fx_source_database
acknowledge_retained_fx_cut = fx_source_notification.acknowledge_retained_fx_cut


class CapturedPublisher:
    def __init__(self):
        self.events = []

    def publish(self, request):
        self.events.append(request)
        return EventPublishResult(EventPublishStatus.SUCCESS)

    def confirm_delivery(self, *, timeout_seconds):
        return EventPublishResult(EventPublishStatus.SUCCESS)


def transport_message(payload, *, offset=1, headers=()):
    message = MagicMock()
    message.value.return_value = json.dumps(payload).encode()
    message.topic.return_value = "raw-fx-rates"
    message.partition.return_value = 0
    message.offset.return_value = offset
    message.headers.return_value = list(headers)
    message.key.return_value = payload["authorization"]["claims"]["cut_id"].encode()
    return message


@pytest_asyncio.fixture
async def fx_http(fx_source_database, monkeypatch):
    database = fx_source_database
    configure_synthetic_fx_source(monkeypatch, scope=database.scope)

    async def sessions():
        async with database.sessions() as session:
            yield session

    publisher = CapturedPublisher()
    jobs = IngestionJobService(session_factory=sessions)
    overrides = {
        get_async_db_session: sessions,
        get_kafka_event_publisher: lambda: publisher,
        dependencies.get_ingestion_job_service: lambda: jobs,
    }
    assert not any(key in app.dependency_overrides for key in overrides)
    for key, value in overrides.items():
        monkeypatch.setitem(app.dependency_overrides, key, value)
    # Lifecycle methods use their module's imported factory, independently of
    # the creation store override. Keep real bookkeeping in this owned schema.
    monkeypatch.setattr(ingestion_job_service, "get_async_db_session", sessions)
    monkeypatch.setattr(base_consumer, "get_async_db_session", sessions)
    consumer = FxRateConsumer(
        bootstrap_servers="synthetic-transport",
        topic="raw-fx-rates",
        group_id="synthetic-fx-custody",
        dlq_topic=None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://synthetic-test"
    ) as client:
        yield database, client, publisher, consumer


async def test_registered_http_atomic_retention_semantic_replay_and_qualified_read(fx_http):
    database, client, publisher, consumer = fx_http
    cut = synthetic_cut(synthetic_revision(scope=database.scope))
    body = submission(cut).model_dump(mode="json")
    headers = signed_headers(tenant=database.scope.tenant_id)
    response = await client.post("/ingest/fx-rates", headers=headers, json=body)
    assert response.status_code == 202, response.text
    acknowledgement = response.json()
    assert acknowledgement["entity_type"] == "fx_source_cut"
    assert acknowledgement["accepted_count"] == 1
    assert len(publisher.events) == 1
    captured = publisher.events[0]
    assert captured.key == cut.cut_id and captured.value["event_type"] == "FxSourceCutReceived"
    assert await database.counts() == (0, 0, 0, 0)
    await consumer.process_message(transport_message(captured.value, headers=captured.headers))
    assert await database.counts() == (1, 1, 1, 1)
    # A process-new consumer and a different physical offset still have one effect.
    restarted = FxRateConsumer(
        bootstrap_servers="synthetic-transport",
        topic="raw-fx-rates",
        group_id="synthetic-fx-custody",
        dlq_topic=None,
    )
    await restarted.process_message(transport_message(captured.value, offset=2))
    assert await database.counts() == (1, 1, 1, 1)
    replay = await client.post("/ingest/fx-rates", headers=headers, json=body)
    assert replay.status_code == 202 and replay.json()["job_id"] == acknowledgement["job_id"]
    assert len(publisher.events) == 1
    async with database.sessions() as session:
        job = await session.scalar(select(IngestionJob))
        assert job.tenant_id == cut.scope.tenant_id and job.status == "queued"
        row = await session.scalar(select(OutboxEvent))
        notification = FxSourceCutPersistedEvent.model_validate(row.payload)
        assert notification.cut_id == cut.cut_id and notification.content_hash == cut.content_hash
        assert notification.members[0].revision_id == cut.revisions[0].revision_id
        source_rows = await read_retained_fx_rates(
            session,
            selection=FxSourceSelection(cut.scope, OBSERVED, notification.accepted_at, cut.cut_id),
            from_currency="USD",
            to_currency="SGD",
            start_date=OBSERVED.date(),
            end_date=OBSERVED.date(),
        )
        assert len(source_rows) == 1 and source_rows[0].rate == cut.revisions[0].rate
        assert source_rows[0].source.content_hash == cut.revisions[0].content_hash
        assert await session.scalar(select(func.count()).select_from(FxRate)) == 0
    async with database.sessions.begin() as session:
        assert await acknowledge_retained_fx_cut(session, notification, correlation_id="synthetic")
    async with database.sessions.begin() as session:
        assert not await acknowledge_retained_fx_cut(
            session, notification, correlation_id="synthetic-replay"
        )
    assert await database.counts() == (1, 1, 2, 1)


async def test_failure_after_revision_flush_rolls_back_inbox_cut_and_outbox(fx_http, monkeypatch):
    database, _, _, consumer = fx_http
    event = signed_event(synthetic_cut(synthetic_revision(scope=database.scope)))
    original = OutboxRepository.create_outbox_event

    async def refuse_outbox(repository, **kwargs):
        # These are actual rows in the SAME not-yet-committed PostgreSQL UOW.
        from portfolio_common.fx_source_models import FxRateSourceCut, FxRateSourceRevision

        assert await repository.db.scalar(select(func.count()).select_from(FxRateSourceCut)) == 1
        assert (
            await repository.db.scalar(select(func.count()).select_from(FxRateSourceRevision)) == 1
        )
        raise RuntimeError("SYNTHETIC_FAILURE_AFTER_REVISION_FLUSH")

    with monkeypatch.context() as fault:
        fault.setattr(OutboxRepository, "create_outbox_event", refuse_outbox)
        with pytest.raises(RuntimeError, match="AFTER_REVISION_FLUSH"):
            await consumer.process_message(transport_message(event.bounded_payload()))
    assert await database.counts() == (0, 0, 0, 0)
    assert OutboxRepository.create_outbox_event is original
    await consumer.process_message(transport_message(event.bounded_payload(), offset=2))
    assert await database.counts() == (1, 1, 1, 1)


@pytest.mark.parametrize("fault", ["no-principal", "foreign-tenant", "revoked", "missing-member"])
async def test_registered_refusal_before_job_publish_or_authority(fx_http, monkeypatch, fault):
    database, client, publisher, _ = fx_http
    cut = synthetic_cut(synthetic_revision(scope=database.scope))
    body = submission(cut).model_dump(mode="json")
    headers = signed_headers(tenant=database.scope.tenant_id)
    if fault == "no-principal":
        headers = {"X-Tenant-Id": database.scope.tenant_id}
    elif fault == "foreign-tenant":
        headers = signed_headers(tenant="SYNTHETIC_FOREIGN")
    elif fault == "revoked":
        configure_synthetic_fx_source(monkeypatch, active=False, scope=database.scope)
    else:
        body["declared_member_count"] = 2
    response = await client.post("/ingest/fx-rates", headers=headers, json=body)
    assert response.status_code in (403, 422), response.text
    assert not publisher.events and await database.counts() == (0, 0, 0, 0)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(IngestionJob)) == 0
