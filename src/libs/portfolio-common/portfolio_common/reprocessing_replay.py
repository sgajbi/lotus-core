from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from .events import TransactionEvent
from .logging_utils import normalize_lineage_value


class ReprocessingReplayError(RuntimeError):
    def __init__(
        self,
        message: str,
        failed_transaction_ids: list[str],
        published_record_count: int = 0,
    ):
        super().__init__(message)
        self.failed_transaction_ids = failed_transaction_ids
        self.published_record_count = published_record_count


class TransactionReplayReader(Protocol):
    async def list_transactions_to_replay(
        self,
        ordered_transaction_ids: list[str],
    ) -> list[Any]: ...


class TransactionReplayPublisher(Protocol):
    def publish_replay_message(self, message: TransactionReplayMessage) -> None: ...

    def confirm_replay_delivery(self) -> int: ...


@dataclass(frozen=True, slots=True)
class ReplayCorrelationMetadata:
    correlation_id: str | None = None

    @property
    def headers(self) -> list[tuple[str, bytes]]:
        correlation_id = normalize_lineage_value(self.correlation_id)
        if not correlation_id:
            return []
        return [("correlation_id", correlation_id.encode("utf-8"))]


@dataclass(frozen=True, slots=True)
class TransactionReplayMessage:
    transaction_id: str
    portfolio_id: str
    topic: str
    key: str
    payload: dict[str, Any]
    headers: Sequence[tuple[str, bytes]]


@dataclass(frozen=True, slots=True)
class TransactionReplayPlan:
    messages: list[TransactionReplayMessage]

    @property
    def transaction_ids(self) -> list[str]:
        return [message.transaction_id for message in self.messages]


def ordered_unique_transaction_ids(transaction_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(transaction_ids))


def plan_transaction_replay(
    *,
    transactions: list[Any],
    correlation: ReplayCorrelationMetadata,
) -> TransactionReplayPlan:
    headers = correlation.headers
    messages = [
        _transaction_replay_message(transaction=transaction, headers=headers)
        for transaction in transactions
    ]
    return TransactionReplayPlan(messages=messages)


def publish_transaction_replay_plan(
    *,
    plan: TransactionReplayPlan,
    publisher: TransactionReplayPublisher,
) -> int:
    transaction_ids = plan.transaction_ids
    for index, message in enumerate(plan.messages):
        try:
            publisher.publish_replay_message(message)
        except Exception as exc:
            raise_partial_replay_error_from_publish_failure(
                failed_transaction_id=message.transaction_id,
                ordered_transaction_ids=transaction_ids,
                failure_index=index,
                cause=exc,
            )

    undelivered_count = publisher.confirm_replay_delivery()
    if undelivered_count:
        raise_flush_timeout_error(ordered_transaction_ids=transaction_ids)
    return len(plan.messages)


def raise_partial_replay_error(
    *,
    failed_transaction_id: str,
    ordered_transaction_ids: list[str],
    failure_index: int,
) -> None:
    unpublished_transaction_ids = ordered_transaction_ids[failure_index:]
    published_record_count = failure_index
    earlier_records = (
        f"{published_record_count} earlier transaction(s) were already republished"
        if published_record_count
        else "no earlier transactions were republished"
    )
    remaining_ids = ", ".join(unpublished_transaction_ids)
    raise ReprocessingReplayError(
        (
            f"Failed to republish transaction '{failed_transaction_id}' after "
            f"{earlier_records}. Remaining transaction ids: {remaining_ids}."
        ),
        failed_transaction_ids=unpublished_transaction_ids,
        published_record_count=published_record_count,
    )


def raise_partial_replay_error_from_publish_failure(
    *,
    failed_transaction_id: str,
    ordered_transaction_ids: list[str],
    failure_index: int,
    cause: Exception,
) -> None:
    try:
        raise_partial_replay_error(
            failed_transaction_id=failed_transaction_id,
            ordered_transaction_ids=ordered_transaction_ids,
            failure_index=failure_index,
        )
    except ReprocessingReplayError as replay_exc:
        raise replay_exc from cause


def raise_flush_timeout_error(*, ordered_transaction_ids: list[str]) -> None:
    remaining_ids = ", ".join(ordered_transaction_ids)
    raise ReprocessingReplayError(
        (
            "Delivery confirmation timed out while republishing transactions. "
            f"Affected transaction ids: {remaining_ids}."
        ),
        failed_transaction_ids=ordered_transaction_ids,
        published_record_count=0,
    )


def _transaction_replay_message(
    *,
    transaction: Any,
    headers: Sequence[tuple[str, bytes]],
) -> TransactionReplayMessage:
    event_to_publish = TransactionEvent.model_validate(transaction)
    transaction_id = str(getattr(transaction, "transaction_id"))
    portfolio_id = str(getattr(transaction, "portfolio_id"))
    return TransactionReplayMessage(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
        key=portfolio_id,
        payload=event_to_publish.model_dump(mode="json"),
        headers=list(headers),
    )
