from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.reprocessing_replay import (
    ReplayCorrelationMetadata,
    ReprocessingReplayError,
    TransactionReplayMessage,
    ordered_unique_transaction_ids,
    plan_transaction_replay,
    publish_transaction_replay_plan,
)


def _transaction(transaction_id: str, portfolio_id: str = "P1") -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2026, 1, 2, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        currency="USD",
        trade_currency="USD",
        trade_fee=Decimal("0"),
    )


class FakeReplayPublisher:
    def __init__(self, *, fail_at: int | None = None, undelivered_count: int = 0) -> None:
        self.fail_at = fail_at
        self.undelivered_count = undelivered_count
        self.published: list[TransactionReplayMessage] = []

    def publish_replay_message(self, message: TransactionReplayMessage) -> None:
        if self.fail_at is not None and len(self.published) == self.fail_at:
            raise RuntimeError("publisher unavailable")
        self.published.append(message)

    def confirm_replay_delivery(self) -> int:
        return self.undelivered_count


def test_ordered_unique_transaction_ids_preserves_first_seen_order() -> None:
    assert ordered_unique_transaction_ids(["TXN_B", "TXN_A", "TXN_B", "TXN_C"]) == [
        "TXN_B",
        "TXN_A",
        "TXN_C",
    ]


def test_plan_transaction_replay_builds_payloads_and_explicit_headers() -> None:
    plan = plan_transaction_replay(
        transactions=[_transaction("TXN1", portfolio_id="P-1")],
        correlation=ReplayCorrelationMetadata(correlation_id=" corr-001 "),
    )

    assert len(plan.messages) == 1
    message = plan.messages[0]
    assert message.transaction_id == "TXN1"
    assert message.topic == KAFKA_TRANSACTIONS_PERSISTED_TOPIC
    assert message.key == "P-1"
    assert message.payload["transaction_id"] == "TXN1"
    assert message.headers == [("correlation_id", b"corr-001")]


def test_plan_transaction_replay_omits_blank_correlation_header() -> None:
    plan = plan_transaction_replay(
        transactions=[_transaction("TXN1")],
        correlation=ReplayCorrelationMetadata(correlation_id="<not-set>"),
    )

    assert plan.messages[0].headers == []


def test_publish_transaction_replay_plan_reports_partial_failure_without_kafka() -> None:
    plan = plan_transaction_replay(
        transactions=[_transaction("TXN_A"), _transaction("TXN_B"), _transaction("TXN_C")],
        correlation=ReplayCorrelationMetadata(correlation_id="corr-001"),
    )
    publisher = FakeReplayPublisher(fail_at=1)

    with pytest.raises(ReprocessingReplayError) as exc_info:
        publish_transaction_replay_plan(plan=plan, publisher=publisher)

    assert exc_info.value.failed_transaction_ids == ["TXN_B", "TXN_C"]
    assert exc_info.value.published_record_count == 1
    assert [message.transaction_id for message in publisher.published] == ["TXN_A"]


def test_publish_transaction_replay_plan_reports_flush_timeout_without_kafka() -> None:
    plan = plan_transaction_replay(
        transactions=[_transaction("TXN_A"), _transaction("TXN_B")],
        correlation=ReplayCorrelationMetadata(correlation_id="corr-001"),
    )

    with pytest.raises(ReprocessingReplayError) as exc_info:
        publish_transaction_replay_plan(
            plan=plan,
            publisher=FakeReplayPublisher(undelivered_count=1),
        )

    assert exc_info.value.failed_transaction_ids == ["TXN_A", "TXN_B"]
    assert exc_info.value.published_record_count == 0
