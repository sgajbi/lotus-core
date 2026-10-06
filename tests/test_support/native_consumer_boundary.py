"""Real broker/SQL observers for bounded native consumer boundary tests."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import TypeVar

from confluent_kafka import Consumer, Message, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from portfolio_common.connection_security import build_kafka_connection_config
from portfolio_common.database_models import (
    Cashflow,
    CostBasisProcessingState,
    OutboxEvent,
    PositionHistory,
    PositionLotState,
    ProcessedEvent,
    Transaction,
)
from portfolio_common.kafka_utils import KafkaProducer
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from tests.test_support.docker_stack import resolve_compose_file
from tests.test_support.runtime.compose_fault_recovery import ComposeFaultRecoveryBoundary
from tests.test_support.tenant import TEST_TENANT_ID

T = TypeVar("T")


def wait_for_value(observe: Callable[[], T], accept: Callable[[T], bool], timeout: float = 60) -> T:
    """Return a measured predicate, failing rather than skipping on absent evidence."""
    deadline = time.monotonic() + timeout
    while True:
        value = observe()
        if accept(value):
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Native boundary predicate unavailable; last value={value!r}")
        time.sleep(0.05)


def broker_client(group: str) -> Consumer:
    config = build_kafka_connection_config(
        os.environ["KAFKA_BOOTSTRAP_SERVERS"], service_name="native boundary observer"
    )
    return Consumer(
        {**config, "group.id": group, "enable.auto.commit": False, "auto.offset.reset": "earliest"}
    )


def committed_offset(group: str, topic: str, partition: int = 0) -> int:
    """Query independently without subscribing, storing or joining the target group."""
    reader = broker_client(group)
    try:
        result = reader.committed([TopicPartition(topic, partition)], timeout=10)
        assert len(result) == 1 and result[0].error is None
        return int(result[0].offset)
    finally:
        reader.close()


def initialize_offset(group: str, topic: str, partition: int = 0) -> None:
    """Explicit test-owned initial acknowledgement, only on a unique empty topic."""
    reader = broker_client(group)
    try:
        result = reader.commit(offsets=[TopicPartition(topic, partition, 0)], asynchronous=False)
        assert result[0].error is None and result[0].offset == 0
    finally:
        reader.close()


@contextmanager
def unique_topics(partitions: int = 1) -> Iterator[tuple[str, str]]:
    names = tuple(f"native-boundary-{uuid.uuid4().hex}" for _ in range(2))
    admin = AdminClient(
        build_kafka_connection_config(
            os.environ["KAFKA_BOOTSTRAP_SERVERS"], service_name="native boundary topics"
        )
    )
    created = []
    failures = []
    try:
        for name, future in admin.create_topics(
            [NewTopic(name, partitions, 1) for name in names]
        ).items():
            try:
                future.result(timeout=30)
                created.append(name)
            except Exception as error:
                failures.append(error)
        if failures:
            raise failures[0]
        yield names[0], names[1]
    finally:
        if created:
            for future in admin.delete_topics(created).values():
                future.result(timeout=30)
            wait_for_value(
                lambda: set(admin.list_topics(timeout=10).topics),
                lambda present: not set(created) & present,
            )


def publish(topic: str, value: dict, key: str, partition: int = 0) -> int:
    producer = KafkaProducer(bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"])
    deliveries: list[tuple[object, Message]] = []
    producer.producer.produce(
        topic,
        partition=partition,
        key=key.encode(),
        value=json.dumps(value).encode(),
        on_delivery=lambda error, message: deliveries.append((error, message)),
    )
    assert producer.flush(timeout=10) == 0
    assert len(deliveries) == 1 and deliveries[0][0] is None
    assert deliveries[0][1].topic() == topic and deliveries[0][1].partition() == partition
    return int(deliveries[0][1].offset())


def read_record(topic: str, offset: int = 0, partition: int = 0) -> Message:
    reader = broker_client(f"native-reader-{uuid.uuid4().hex}")
    try:
        reader.assign([TopicPartition(topic, partition, offset)])
        message = wait_for_value(lambda: reader.poll(1), lambda result: result is not None)
        assert message is not None and message.error() is None
        return message
    finally:
        reader.close()


def broker_outage() -> ComposeFaultRecoveryBoundary:
    def ready() -> None:
        admin = AdminClient(
            build_kafka_connection_config(
                os.environ["KAFKA_BOOTSTRAP_SERVERS"], service_name="native outage recovery"
            )
        )
        assert admin.list_topics(timeout=10).brokers

    return ComposeFaultRecoveryBoundary(
        project_name=os.environ["COMPOSE_PROJECT_NAME"],
        faulted_service="kafka",
        recovery_services=(),
        faulted_service_ready=ready,
        recovery_services_ready=lambda: None,
        compose_file=resolve_compose_file(str(Path(__file__).resolve().parents[2])),
    )


def financial_snapshot(
    engine: Engine,
    portfolio: str,
    security: str,
    *,
    event_ids: tuple[str, ...] = (),
) -> dict:
    """Read committed materialized effects using an independent SQL connection."""
    columns = {
        "lots": (
            PositionLotState,
            ("source_transaction_id", "open_quantity", "lot_cost_local", "original_quantity"),
        ),
        "cash": (Cashflow, ("transaction_id", "classification", "amount", "epoch")),
        "positions": (PositionHistory, ("transaction_id", "quantity", "cost_basis", "epoch")),
        "receipts": (
            ProcessedEvent,
            ("event_id", "service_name", "semantic_key", "payload_fingerprint", "tenant_id"),
        ),
        "outbox": (OutboxEvent, ("aggregate_id", "event_type", "payload")),
        "checkpoint": (CostBasisProcessingState, ("latest_transaction_id", "cost_basis_method")),
        "cost": (Transaction, ("transaction_id", "net_cost", "realized_gain_loss")),
    }
    result = {}
    with Session(engine) as session:
        for name, (model, fields) in columns.items():
            predicate = (
                model.aggregate_id == portfolio
                if name == "outbox"
                else model.portfolio_id == portfolio
            )
            statement = select(model).where(predicate)
            if name == "receipts":
                statement = statement.where(
                    model.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                    model.tenant_id == TEST_TENANT_ID,
                )
                observed_ids = set(session.scalars(statement.with_only_columns(model.event_id)))
                assert observed_ids <= set(event_ids), f"Unexpected owning receipt: {observed_ids}"
                statement = statement.where(model.event_id.in_(event_ids))
            if name == "outbox":
                statement = statement.where(
                    model.event_type.in_(["CashflowCalculated", "ProcessedTransactionPersisted"])
                )
            if name in {"lots", "positions", "checkpoint", "cost"}:
                statement = statement.where(model.security_id == security)
            result[name] = sorted(
                [
                    tuple(getattr(row, field) for field in fields)
                    for row in session.scalars(statement)
                ],
                key=repr,
            )
    return result


def assert_financial_oracle(snapshot: dict, buy: str, sell: str | None = None) -> None:
    """Independent zero-fee SGD FIFO arithmetic, not outputs reused as expectations."""
    quantity, basis = (
        (Decimal("10"), Decimal("255")) if sell is None else (Decimal("6"), Decimal("153"))
    )
    assert snapshot["lots"] == [(buy, quantity, basis, Decimal("10"))]
    cash = {row[0]: row[1:3] for row in snapshot["cash"]}
    assert cash[buy] == ("INVESTMENT_OUTFLOW", Decimal("-255"))
    positions = {row[0]: row[1:3] for row in snapshot["positions"]}
    assert positions[buy] == (Decimal("10"), Decimal("255"))
    assert len(snapshot["cash"]) == len(snapshot["positions"]) == (1 if sell is None else 2)
    cost = {row[0]: row[1:] for row in snapshot["cost"]}
    assert cost[buy][0] == Decimal("255")
    if sell is not None:
        assert cash[sell] == ("INVESTMENT_INFLOW", Decimal("120"))
        assert positions[sell] == (Decimal("6"), Decimal("153"))
        assert cost[sell] == (Decimal("-102"), Decimal("18"))
    assert snapshot["checkpoint"] == [(sell or buy, "FIFO")]
    assert len(snapshot["receipts"]) == (1 if sell is None else 2)
    assert all(
        row[1] == TRANSACTION_PROCESSING_SERVICE_NAME
        and row[2]
        and row[3]
        and row[4] == TEST_TENANT_ID
        for row in snapshot["receipts"]
    )
    assert sorted(row[1] for row in snapshot["outbox"]) == sorted(
        ["CashflowCalculated", "ProcessedTransactionPersisted"] * (1 if sell is None else 2)
    )
