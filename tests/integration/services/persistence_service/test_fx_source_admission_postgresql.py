"""Admission-only PG proof; captured broker is explicit, no historical QCP upgrade."""

import json
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import IngestionJob, OutboxEvent, ProcessedEvent
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.db import get_async_db_session
from portfolio_common.domain.transaction.fx_source_admission import IncompleteFxSourceError
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_legacy_fingerprint,
    transaction_payload_pre_upstream_fingerprint,
)
from portfolio_common.event_publisher import KafkaEventPublisher, get_kafka_event_publisher
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.kafka_utils import KafkaProducer
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.ingestion_service.app import main as ingestion_main
from src.services.ingestion_service.app.DTOs.transaction_dto import (
    Transaction as IngestionTransaction,
)
from src.services.persistence_service.app.adapters.event_record_mapper import (
    transaction_event_to_record_values,
)
from src.services.persistence_service.app.consumers import base_consumer as persistence_base
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from tests.test_support.tenant import TEST_TENANT_HEADERS
from tests.test_support.transaction_processing import portfolio_record

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


def _source() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="FX-PRESENCE-CLOSE-001",
        portfolio_id="PORT-FX-PRESENCE-001",
        tenant_id="tenant-test",
        instrument_id="FXC-EURUSD-PRESENCE",
        security_id="FXC-EURUSD-PRESENCE",
        transaction_type="FX_FORWARD",
        transaction_date=datetime(2026, 4, 1, tzinfo=UTC),
        settlement_date=datetime(2026, 4, 3, tzinfo=UTC),
        component_type="FX_CONTRACT_CLOSE",
        component_id="FX-PRESENCE-COMPONENT",
        economic_event_id="FX-PRESENCE-EVENT",
        linked_transaction_group_id="FX-PRESENCE-GROUP",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="BOOKING_LEDGER",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1100"),
        sell_amount=Decimal("1000"),
        contract_rate=Decimal("1.1"),
        fx_contract_id="FXC-EURUSD-PRESENCE",
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
    )


async def _durable_row(session: AsyncSession):
    await session.commit()
    return (
        (
            await session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == _source().transaction_id,
                )
            )
        )
        .mappings()
        .one()
    )


class _CapturedBrokerMessage:
    """Explicit broker substitute; consumer and PostgreSQL behavior are real."""

    def __init__(self, publication):
        event = TransactionEvent.model_validate(publication["value"])
        self._payload = event.model_dump(mode="json")
        self._headers = publication["headers"]

    def value(self):
        return json.dumps(self._payload).encode()

    def key(self):
        return self._payload["transaction_id"].encode()

    def topic(self):
        return "raw-transactions"

    def partition(self):
        return 0

    def offset(self):
        return 1

    def headers(self):
        return self._headers


@pytest_asyncio.fixture
async def fresh_fx_ingress(clean_db, async_db_session, monkeypatch):
    """Real registered HTTP/consumer/DB boundaries, explicit captured broker substitute."""
    async_db_session.add(portfolio_record(_source().portfolio_id))
    await async_db_session.commit()
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def database_session():
        async with factory() as session:
            yield session

    publications = []
    producer = MagicMock(spec=KafkaProducer)
    producer.publish_message.side_effect = lambda **kwargs: publications.append(kwargs)
    producer.flush.return_value = 0
    monkeypatch.setattr(ingestion_main, "get_kafka_producer", lambda: producer)
    monkeypatch.setitem(ingestion_main.app_state, "kafka_producer", producer)
    monkeypatch.setitem(
        ingestion_main.app.dependency_overrides, get_async_db_session, database_session
    )
    monkeypatch.setitem(
        ingestion_main.app.dependency_overrides,
        get_kafka_event_publisher,
        lambda: KafkaEventPublisher(producer),
    )
    monkeypatch.setattr(persistence_base, "get_async_db_session", database_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="unused-broker-substitute:9092",
        topic="raw-transactions",
        group_id="fx-fresh-admission-db-proof",
        dlq_topic=None,
    )
    transport = httpx.ASGITransport(app=ingestion_main.app)
    async with ingestion_main.app.router.lifespan_context(ingestion_main.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, consumer, publications


def _fresh_wire_payload(local="0", base="0"):
    source_values = {
        field.name: getattr(_source(), field.name)
        for field in fields(_source())
        if field.name in IngestionTransaction.model_fields
    }
    source_values.update(
        gross_transaction_amount=Decimal("1100"),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        realized_fx_pnl_local=Decimal(0),
        realized_fx_pnl_base=Decimal(0),
    )
    payload = IngestionTransaction.model_validate(source_values).model_dump(mode="json")
    payload.update(realized_fx_pnl_local=local, realized_fx_pnl_base=base)
    return payload


async def _assert_no_fresh_financial_writes(session):
    await session.rollback()  # Force a fresh independent read after the consumer UOW ended.
    assert await session.scalar(select(func.count()).select_from(IngestionJob)) == 0
    assert (
        await session.scalar(
            select(func.count())
            .select_from(DBTransaction)
            .where(DBTransaction.portfolio_id == _source().portfolio_id)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(ProcessedEvent.portfolio_id == _source().portfolio_id)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == _source().portfolio_id)
        )
        == 0
    )


@pytest.mark.parametrize("local,base", [(None, None), ("0", None), (None, "0")])
@pytest.mark.parametrize("batch", [False, True])
async def test_fresh_incomplete_fx_http_and_broker_refuse_without_durable_fence(
    async_db_session, fresh_fx_ingress, local, base, batch
) -> None:
    client, consumer, publications = fresh_fx_ingress
    payload = _fresh_wire_payload(local, base)
    payload.update(realized_total_pnl_local="0", realized_total_pnl_base="0")
    endpoint = "/ingest/transactions" if batch else "/ingest/transaction"
    body = {"transactions": [_fresh_wire_payload(), payload]} if batch else payload
    response = await client.post(endpoint, headers=TEST_TENANT_HEADERS, json=body)
    assert response.status_code == 422, response.text
    assert "FX_UPSTREAM_SOURCE_INCOMPLETE" in response.text
    assert publications == []
    await _assert_no_fresh_financial_writes(async_db_session)
    # Bypass public DTO validation to exercise actual consumer claim rollback.
    publication = {"value": {**payload, "tenant_id": "tenant-test"}, "headers": []}
    with pytest.raises(IncompleteFxSourceError):
        await consumer.process_message(_CapturedBrokerMessage(publication))
    await _assert_no_fresh_financial_writes(async_db_session)
    # This is the FIRST booking after refusal, not a correction of a durable row.
    zero = await client.post(
        "/ingest/transaction", headers=TEST_TENANT_HEADERS, json=_fresh_wire_payload()
    )
    assert zero.status_code == 202, zero.text
    await consumer.process_message(_CapturedBrokerMessage(publications[-1]))
    assert (await _durable_row(async_db_session))["realized_fx_pnl_base"] == Decimal(0)


async def test_existing_incomplete_v3_replay_survives_fence_expiry_without_ledger_write(
    async_db_session, fresh_fx_ingress
) -> None:
    client, consumer, publications = fresh_fx_ingress
    historical_payload = _fresh_wire_payload(None, None)
    event = TransactionEvent.model_validate({**historical_payload, "tenant_id": "tenant-test"})
    # Synthetic already-durable v3 raw source: this is not a pre-v3 backfill,
    # source receipt or caller-controlled public legacy bypass.
    outcome = await TransactionDBRepository(async_db_session).create_or_update_transaction(event)
    assert outcome.inserted
    before = dict(await _durable_row(async_db_session))
    publication = {"value": event.model_dump(mode="json"), "headers": []}
    for _ in range(2):
        await consumer.process_message(_CapturedBrokerMessage(publication))
    assert dict(await _durable_row(async_db_session)) == before
    await async_db_session.execute(delete(ProcessedEvent))
    await async_db_session.commit()
    await consumer.process_message(_CapturedBrokerMessage(publication))
    assert dict(await _durable_row(async_db_session)) == before
    assert await async_db_session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
    public_retry = await client.post(
        "/ingest/transaction", headers=TEST_TENANT_HEADERS, json=historical_payload
    )
    assert public_retry.status_code == 422, public_retry.text
    assert publications == []
    changed = {
        "value": {
            **publication["value"],
            "realized_fx_pnl_local": "0",
            "realized_fx_pnl_base": "0",
        },
        "headers": [],
    }
    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(_CapturedBrokerMessage(changed))
    assert dict(await _durable_row(async_db_session)) == before


async def _control_snapshot(session):
    await session.rollback()
    tables = (DBTransaction, ProcessedEvent, OutboxEvent)
    return [
        [dict(row) for row in (await session.execute(select(*table.__table__.columns))).mappings()]
        for table in tables
    ]


@pytest.mark.parametrize("amount", ["0", "12", "-12"])
async def test_complete_source_zero_signed_reload_and_exact_retry(
    async_db_session, fresh_fx_ingress, amount
):
    client, consumer, publications = fresh_fx_ingress
    payload = _fresh_wire_payload(amount, amount)
    accepted = await client.post("/ingest/transaction", headers=TEST_TENANT_HEADERS, json=payload)
    assert accepted.status_code == 202, accepted.text
    await consumer.process_message(_CapturedBrokerMessage(publications[-1]))
    before = await _control_snapshot(async_db_session)
    assert len(before[0]) == len(before[1]) == len(before[2]) == 1
    assert before[0][0]["realized_fx_pnl_local"] == Decimal(amount)
    assert before[0][0]["realized_fx_pnl_base"] == Decimal(amount)
    assert before[1][0]["semantic_key"].startswith("transaction-persistence:v3:")
    # A separately owned DB session proves reload, not an ORM-cached predecessor.
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with factory() as reloaded:
        assert await _control_snapshot(reloaded) == before
    accepted = await client.post("/ingest/transaction", headers=TEST_TENANT_HEADERS, json=payload)
    assert accepted.status_code == 202, accepted.text
    await consumer.process_message(_CapturedBrokerMessage(publications[-1]))
    assert await _control_snapshot(async_db_session) == before


@pytest.mark.parametrize("component", ["capital", "fx", "total"])
@pytest.mark.parametrize("basis", ["local", "base"])
async def test_changed_raw_upstream_source_refuses_without_row_fence_outbox_mutation(
    async_db_session, fresh_fx_ingress, component, basis
):
    client, consumer, publications = fresh_fx_ingress
    response = await client.post(
        "/ingest/transaction", headers=TEST_TENANT_HEADERS, json=_fresh_wire_payload()
    )
    assert response.status_code == 202, response.text
    await consumer.process_message(_CapturedBrokerMessage(publications[-1]))
    before = await _control_snapshot(async_db_session)
    changed = {
        "value": {**publications[-1]["value"], f"realized_{component}_pnl_{basis}": "12"},
        "headers": [],
    }
    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(_CapturedBrokerMessage(changed))
    assert await _control_snapshot(async_db_session) == before
    # The durable ledger protects the same change after transient fence expiry.
    await async_db_session.execute(delete(ProcessedEvent))
    await async_db_session.commit()
    expired = await _control_snapshot(async_db_session)
    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(_CapturedBrokerMessage(changed))
    assert await _control_snapshot(async_db_session) == expired


async def test_foreign_tenant_raw_source_refuses_before_fence_or_financial_write(
    async_db_session, fresh_fx_ingress
):
    _, consumer, _ = fresh_fx_ingress
    foreign = {"value": {**_fresh_wire_payload(), "tenant_id": "foreign-tenant"}, "headers": []}
    with pytest.raises(ValueError, match="tenant does not own"):
        await consumer.process_message(_CapturedBrokerMessage(foreign))
    await _assert_no_fresh_financial_writes(async_db_session)


@pytest.mark.parametrize("legacy_version", ["v1", "v2"])
async def test_ambiguous_pre_v3_upstream_fence_and_ledger_remain_unchanged(
    async_db_session, fresh_fx_ingress, legacy_version
):
    _, consumer, _ = fresh_fx_ingress
    event = TransactionEvent.model_validate(
        {
            **_fresh_wire_payload(),
            "tenant_id": "tenant-test",
            "transaction_fx_rate": "1.1",
            "transaction_fx_rate_origin": "SOURCE_BOOKED",
        }
    )
    historical_hash = (
        transaction_payload_legacy_fingerprint(event.model_dump(mode="python"))
        if legacy_version == "v1"
        else transaction_payload_pre_upstream_fingerprint(event.model_dump(mode="python"))
    )
    record = transaction_event_to_record_values(event)
    record.update(
        payload_fingerprint=historical_hash,
        transaction_fx_rate_origin="LEGACY_UNKNOWN" if legacy_version == "v1" else "SOURCE_BOOKED",
    )
    async_db_session.add(DBTransaction(**record))
    async_db_session.add(
        ProcessedEvent(
            event_id=event.transaction_id,
            portfolio_id=event.portfolio_id,
            tenant_id=event.tenant_id,
            service_name="persistence-transactions",
            semantic_key=f"transaction-persistence:{legacy_version}:{event.tenant_id}:{event.transaction_id}",
            payload_fingerprint=historical_hash,
            correlation_id="legacy-fx-proof",
        )
    )
    await async_db_session.commit()
    before = await _control_snapshot(async_db_session)
    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(
            _CapturedBrokerMessage({"value": event.model_dump(mode="json"), "headers": []})
        )
    assert await _control_snapshot(async_db_session) == before
