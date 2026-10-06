"""Named real Kafka ownership/offset boundaries around production PG economics."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from confluent_kafka import KafkaException
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from portfolio_common.kafka_consumer_native import (
    ConsumerNativeOperations,
    OffsetAcknowledgementFailed,
    PartitionOwnershipLost,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.delivery.kafka.transaction_processing_consumer import (  # noqa: E501
    TransactionProcessingConsumer,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_tenant_authority import (  # noqa: E501
    SqlAlchemyTransactionTenantAuthority,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_corporate_action_child_arrival_use_case,
    build_process_transaction_use_case,
)
from tests.test_support.native_consumer_boundary import (
    assert_financial_oracle,
    broker_client,
    broker_outage,
    committed_offset,
    financial_snapshot,
    initialize_offset,
    publish,
    unique_topics,
    wait_for_value,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


class _ObservedNative(ConsumerNativeOperations):
    """Observe real callbacks/results; never replace a broker result."""

    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.revoked = asyncio.Event()
        self.refused = asyncio.Event()
        self.failure = None
        self.revoked_partitions = set()

    def on_revocation(self, consumer, partitions):
        super().on_revocation(consumer, partitions)
        self.revoked_partitions.update((item.topic, item.partition) for item in partitions)
        self.loop.call_soon_threadsafe(self.revoked.set)

    async def commit(self, consumer, message, generation):
        try:
            await super().commit(consumer, message, generation)
        except Exception as error:
            self.failure = error
            self.refused.set()
            raise


class _BoundaryConsumer(TransactionProcessingConsumer):
    """A test-owned barrier surrounds, rather than substitutes, production processing."""

    def __init__(self, topic, group, session_factory, *, hold_after_durable=False):
        super().__init__(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            topic=topic,
            group_id=group,
            use_case=build_process_transaction_use_case(session_factory=session_factory),
            route_corporate_action_child=build_corporate_action_child_arrival_use_case(
                session_factory=session_factory
            ),
            tenant_authority=SqlAlchemyTransactionTenantAuthority(session_factory),
            execution_profile=KafkaConsumerExecutionProfile(max_in_flight_messages=2),
        )
        self._native_operations.finish()
        self._native_operations = _ObservedNative(asyncio.get_running_loop())
        self.durable = asyncio.Event()
        self.release = asyncio.Event()
        self.hold_after_durable = hold_after_durable

    async def process_message(self, message):
        await super().process_message(message)
        self.durable.set()
        if self.hold_after_durable:
            await self.release.wait()


async def _seed(session):
    suffix = uuid.uuid4().hex[:12]
    portfolio, security = f"NB-{suffix}", f"NB-EQ-{suffix}"
    session.add_all(
        [
            portfolio_record(portfolio, base_currency="SGD"),
            instrument_record(
                security, name="Native boundary equity", isin="SG0000000001", currency="SGD"
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=f"NB-BUY-{suffix}",
        portfolio_id=portfolio,
        security_id=security,
        transaction_date=datetime(2026, 1, 10, 10, tzinfo=UTC),
        transaction_type="BUY",
        quantity="10",
        price="25.50",
        gross_amount="255",
        trade_currency="SGD",
    )
    session.add(canonical_transaction_record(event))
    await session.commit()
    return event


async def _ack(group, topic, expected):
    await asyncio.to_thread(
        wait_for_value, lambda: committed_offset(group, topic), lambda value: value == expected
    )


async def _retire(consumer, task):
    consumer.release.set()
    consumer.shutdown()
    await asyncio.wait_for(asyncio.shield(task), 120)
    assert consumer._shutdown_finalized


async def test_broker_offsets_follow_named_buy_sell_financial_effects(
    docker_services,
    clean_db,
    async_db_session,
    db_engine,
):
    event = await _seed(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    with unique_topics() as (topic, _):
        group = f"native-financial-{uuid.uuid4().hex}"
        initialize_offset(group, topic)
        buy_offset = publish(topic, event.model_dump(mode="json"), event.portfolio_id)
        consumer = _BoundaryConsumer(topic, group, factory, hold_after_durable=True)
        task = asyncio.create_task(consumer.run())
        try:
            await asyncio.wait_for(consumer.durable.wait(), 60)
            buy_snapshot = financial_snapshot(
                db_engine,
                event.portfolio_id,
                event.security_id,
                event_ids=(f"{topic}-0-{buy_offset}",),
            )
            assert_financial_oracle(buy_snapshot, event.transaction_id)
            assert committed_offset(group, topic) == buy_offset
            consumer.hold_after_durable = False
            consumer.release.set()
            await _ack(group, topic, buy_offset + 1)
            sell = booked_transaction_event(
                transaction_id=f"{event.transaction_id}-SELL",
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
                transaction_date=datetime(2026, 2, 10, 10, tzinfo=UTC),
                transaction_type="SELL",
                quantity="4",
                price="30",
                gross_amount="120",
                trade_currency="SGD",
            )
            async_db_session.add(canonical_transaction_record(sell))
            await async_db_session.commit()
            sell_offset = publish(topic, sell.model_dump(mode="json"), event.portfolio_id)
            assert sell_offset == buy_offset + 1
            await _ack(group, topic, sell_offset + 1)
            ids = (f"{topic}-0-{buy_offset}", f"{topic}-0-{sell_offset}")
            final = financial_snapshot(
                db_engine,
                event.portfolio_id,
                event.security_id,
                event_ids=ids,
            )
            assert_financial_oracle(final, event.transaction_id, sell.transaction_id)
            assert {row[0] for row in final["receipts"]} == {
                f"{topic}-0-{buy_offset}",
                f"{topic}-0-{sell_offset}",
            }
            duplicate = publish(topic, sell.model_dump(mode="json"), event.portfolio_id)
            await _ack(group, topic, duplicate + 1)
            assert (
                financial_snapshot(
                    db_engine,
                    event.portfolio_id,
                    event.security_id,
                    event_ids=ids,
                )
                == final
            )
        finally:
            await _retire(consumer, task)


async def test_real_revoke_refuses_stale_ack_and_redelivery_preserves_financial_once(
    docker_services,
    clean_db,
    async_db_session,
    db_engine,
):
    event = await _seed(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    with unique_topics(partitions=2) as (topic, _):
        group = f"native-revoke-{uuid.uuid4().hex}"
        initialize_offset(group, topic)
        offset = publish(topic, event.model_dump(mode="json"), event.portfolio_id)
        old = _BoundaryConsumer(topic, group, factory, hold_after_durable=True)
        task = asyncio.create_task(old.run())
        rival = broker_client(group)
        try:
            await asyncio.wait_for(old.durable.wait(), 60)
            expected = financial_snapshot(
                db_engine,
                event.portfolio_id,
                event.security_id,
                event_ids=(f"{topic}-0-{offset}",),
            )
            assert_financial_oracle(expected, event.transaction_id)
            rival.subscribe([topic])
            await asyncio.to_thread(
                wait_for_value,
                lambda: (rival.poll(0.1), old._native_operations.revoked.is_set())[1],
                bool,
                60,
            )
            assert (topic, 0) in old._native_operations.revoked_partitions
            old.release.set()
            await asyncio.wait_for(old._native_operations.refused.wait(), 60)
            assert isinstance(old._native_operations.failure, PartitionOwnershipLost)
            assert committed_offset(group, topic) == offset
        finally:
            rival.close()
            await _retire(old, task)
        successor = _BoundaryConsumer(topic, group, factory)
        successor_task = asyncio.create_task(successor.run())
        try:
            await _ack(group, topic, offset + 1)
            assert (
                financial_snapshot(
                    db_engine,
                    event.portfolio_id,
                    event.security_id,
                    event_ids=(f"{topic}-0-{offset}",),
                )
                == expected
            )
        finally:
            await _retire(successor, successor_task)


async def test_real_commit_refusal_after_pg_durability_redelivers_financial_once(
    docker_services,
    clean_db,
    async_db_session,
    db_engine,
):
    event = await _seed(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    with unique_topics() as (topic, _):
        group = f"native-refusal-{uuid.uuid4().hex}"
        initialize_offset(group, topic)
        offset = publish(topic, event.model_dump(mode="json"), event.portfolio_id)
        old = _BoundaryConsumer(topic, group, factory, hold_after_durable=True)
        task = asyncio.create_task(old.run())
        outage = broker_outage()
        try:
            await asyncio.wait_for(old.durable.wait(), 60)
            expected = financial_snapshot(
                db_engine,
                event.portfolio_id,
                event.security_id,
                event_ids=(f"{topic}-0-{offset}",),
            )
            assert_financial_oracle(expected, event.transaction_id)
            await asyncio.to_thread(outage.__enter__)
            old.release.set()
            await asyncio.wait_for(old._native_operations.refused.wait(), 120)
            failure = old._native_operations.failure
            assert isinstance(failure, (KafkaException, OffsetAcknowledgementFailed)), repr(failure)
            native_error = failure.args[0] if isinstance(failure, KafkaException) else None
            print(
                json.dumps(
                    {
                        "commit_refusal_type": type(failure).__name__,
                        "commit_refusal": str(failure),
                        "native_error_code": native_error.code() if native_error else None,
                        "native_error_name": native_error.name() if native_error else None,
                        "topic": topic,
                        "partition": 0,
                        "unacknowledged_offset": offset,
                    }
                )
            )
        finally:
            await asyncio.to_thread(outage.restore)
            await _retire(old, task)
        assert outage.recovery_evidence is not None
        assert committed_offset(group, topic) == offset
        successor = _BoundaryConsumer(topic, group, factory)
        successor_task = asyncio.create_task(successor.run())
        try:
            await _ack(group, topic, offset + 1)
            assert (
                financial_snapshot(
                    db_engine,
                    event.portfolio_id,
                    event.security_id,
                    event_ids=(f"{topic}-0-{offset}",),
                )
                == expected
            )
        finally:
            await _retire(successor, successor_task)
