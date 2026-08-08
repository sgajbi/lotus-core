"""Verify correction replay consumes one stable, source-lot ordered anchor."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.event_mapping import EventContractValidationError
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayStatus,
    ReplayBookedTransactionResult,
)
from src.services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    fixed_income_book_cost_disposal_replay_event,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    FixedIncomeBookCostCorrectionReplayConsumer,
    FixedIncomeBookCostCorrectionReplaySourceMissing,
)
from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    AmortizedCostEligibilityReason,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotBookCostAuthorityScope,
)

pytestmark = pytest.mark.asyncio


def _intent() -> FixedIncomeBookCostCorrectionReplayIntent:
    return FixedIncomeBookCostCorrectionReplayIntent(
        scope=LotBookCostAuthorityScope(
            tenant_id="tenant-1",
            legal_book_id="book-1",
            portfolio_id="portfolio-1",
            security_id="security-1",
            lot_id="lot-1",
        ),
        earliest_affected_date=date(2026, 1, 1),
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
        ),
        source_authority_event_content_hash="a" * 64,
        profile_decisions=(
            FixedIncomeBookCostProfileDecisionEvidence(
                effective_date=date(2026, 1, 1),
                profile_id="profile-1",
                profile_version=2,
                authority_content_hash="b" * 64,
                eligibility_reason=AmortizedCostEligibilityReason.ASSIGNMENT_MISSING,
            ),
        ),
    )


def _payload() -> dict[str, object]:
    return fixed_income_book_cost_disposal_replay_event(
        _intent(),
        correlation_id="payload-correlation-001",
        traceparent=None,
    ).model_dump(mode="json")


def _message(*, payload: object | None = None, key: bytes | None = None) -> MagicMock:
    message = MagicMock()
    message.value.return_value = json.dumps(_payload() if payload is None else payload).encode()
    message.key.return_value = (
        key if key is not None else b"tenant-1|book-1|portfolio-1|security-1|lot-1"
    )
    message.topic.return_value = "fixed_income.book_cost.disposal_replay.requested"
    message.partition.return_value = 2
    message.offset.return_value = 41
    message.headers.return_value = [("correlation_id", b"header-correlation-001")]
    return message


def _consumer(use_case: AsyncMock) -> FixedIncomeBookCostCorrectionReplayConsumer:
    return FixedIncomeBookCostCorrectionReplayConsumer(
        bootstrap_servers="mock-server",
        topic="fixed_income.book_cost.disposal_replay.requested",
        group_id="fixed_income_book_cost_correction_replay_group",
        use_case=use_case,
    )


def _dlq_consumer(
    use_case: AsyncMock,
    *,
    retryable_failure_max_attempts: int | None = None,
) -> FixedIncomeBookCostCorrectionReplayConsumer:
    return FixedIncomeBookCostCorrectionReplayConsumer(
        bootstrap_servers="mock-server",
        topic="fixed_income.book_cost.disposal_replay.requested",
        group_id="fixed_income_book_cost_correction_replay_group",
        dlq_topic="dlq.persistence_service",
        use_case=use_case,
        execution_profile=KafkaConsumerExecutionProfile(retryable_failure_backoff_seconds=0.001),
        retryable_failure_max_attempts=retryable_failure_max_attempts,
    )


async def test_valid_command_replays_only_earliest_anchor_with_stable_identity() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="sell-1",
        status=BookedTransactionReplayStatus.REPLAYED,
    )

    await _consumer(use_case).process_message(_message())

    command = use_case.execute.await_args.args[0]
    assert command.transaction_id == "sell-1"
    assert command.correlation_id == "header-correlation-001"
    assert command.repair_delivery_id == _intent().command_id
    use_case.execute.assert_awaited_once()


async def test_partition_key_drift_is_rejected_before_replay() -> None:
    use_case = AsyncMock()

    with pytest.raises(ValueError, match="partition key does not match"):
        await _consumer(use_case).process_message(_message(key=b"wrong-key"))

    use_case.execute.assert_not_awaited()


async def test_forged_command_identity_is_rejected_before_replay() -> None:
    use_case = AsyncMock()
    payload = _payload()
    payload["command_id"] = "c" * 64

    with pytest.raises(ValueError, match="command_id does not match"):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


async def test_unsupported_contract_version_is_rejected_before_replay() -> None:
    use_case = AsyncMock()
    payload = _payload()
    payload["schema_version"] = "2.0.0"

    with pytest.raises(EventContractValidationError, match="not supported"):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


async def test_dependency_failure_is_retryable_for_ordered_redelivery() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = BookedTransactionReplayDependencyUnavailable(
        "broker unavailable"
    )

    with pytest.raises(RetryableConsumerError, match="dependency unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_dependency_retry_exhaustion_publishes_dlq_and_commits_offset() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = BookedTransactionReplayDependencyUnavailable(
        "broker unavailable"
    )
    consumer = _dlq_consumer(use_case, retryable_failure_max_attempts=2)
    consumer._consumer = MagicMock()
    consumer._send_to_dlq_async = AsyncMock(return_value=True)
    message = _message()

    await consumer._process_polled_message(message, asyncio.get_running_loop())

    assert use_case.execute.await_count == 2
    consumer._send_to_dlq_async.assert_awaited_once()
    consumer._consumer.commit.assert_called_once_with(message=message, asynchronous=False)
    assert consumer._running is True


async def test_poison_contract_publishes_dlq_and_commits_offset_without_replay() -> None:
    use_case = AsyncMock()
    consumer = _dlq_consumer(use_case)
    consumer._consumer = MagicMock()
    consumer._send_to_dlq_async = AsyncMock(return_value=True)
    payload = _payload()
    payload["schema_version"] = "2.0.0"
    message = _message(payload=payload)

    await consumer._process_polled_message(message, asyncio.get_running_loop())

    use_case.execute.assert_not_awaited()
    consumer._send_to_dlq_async.assert_awaited_once()
    consumer._consumer.commit.assert_called_once_with(message=message, asynchronous=False)


async def test_missing_canonical_anchor_fails_closed_for_dlq_evidence() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="sell-1",
        status=BookedTransactionReplayStatus.NOT_FOUND,
    )

    with pytest.raises(
        FixedIncomeBookCostCorrectionReplaySourceMissing,
        match="sell-1",
    ):
        await _consumer(use_case).process_message(_message())
