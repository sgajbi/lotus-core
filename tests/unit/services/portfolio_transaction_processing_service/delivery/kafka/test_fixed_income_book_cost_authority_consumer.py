"""Verify fixed-income book-cost Kafka delivery remains ordered and fail closed."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.exceptions import RetryableConsumerError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from services.portfolio_transaction_processing_service.app.delivery.kafka import (
    FixedIncomeBookCostAuthorityConsumer,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs

pytestmark = pytest.mark.asyncio


def _payload() -> dict[str, object]:
    assignment = resolved_fixed_income_book_cost_inputs().assignment
    return {
        "event_type": "fixed_income.book_cost.authority.received",
        "schema_version": "1.0.0",
        "authority": {
            "authority_type": "POLICY_ASSIGNMENT",
            "header": {
                "scope": {
                    "tenant_id": assignment.scope.tenant_id,
                    "legal_book_id": assignment.scope.legal_book_id,
                    "portfolio_id": assignment.scope.portfolio_id,
                    "security_id": assignment.scope.security_id,
                    "lot_id": assignment.scope.lot_id,
                },
                "source": {
                    "source_system": assignment.source_system,
                    "source_record_id": assignment.source_record_id,
                    "source_revision": assignment.source_revision,
                    "source_version": assignment.assignment_version,
                    "observed_at": assignment.observed_at.isoformat(),
                },
                "status": assignment.assignment_status.value,
                "valid_from": assignment.valid_from.isoformat(),
                "valid_to": None,
            },
            "policy_id": assignment.policy_id,
            "policy_version": assignment.policy_version,
            "assignment_reason": assignment.assignment_reason,
        },
    }


def _message(*, payload: object | None = None, key: bytes | None = None) -> MagicMock:
    message = MagicMock()
    message.value.return_value = json.dumps(_payload() if payload is None else payload).encode()
    message.key.return_value = (
        key
        if key is not None
        else b"TENANT_SG|BOOK_SG_PB|AMORT_PORTFOLIO|AMORT_BOND_001|AMORT_LOT_001"
    )
    message.headers.return_value = [("correlation_id", b"corr-book-cost-001")]
    return message


def _consumer(use_case: AsyncMock) -> FixedIncomeBookCostAuthorityConsumer:
    return FixedIncomeBookCostAuthorityConsumer(
        bootstrap_servers="mock-server",
        topic="fixed_income.book_cost.authority.received",
        group_id="fixed_income_book_cost_authority_group",
        use_case=use_case,
    )


async def test_valid_event_and_exact_partition_key_invoke_atomic_handler() -> None:
    use_case = AsyncMock()

    await _consumer(use_case).process_message(_message())

    event = use_case.execute.await_args.args[0]
    assert event.authority.authority_type == "POLICY_ASSIGNMENT"
    assert event.authority.header.source.source_version == 1
    use_case.execute.assert_awaited_once()


async def test_partition_key_drift_is_rejected_before_database_work() -> None:
    use_case = AsyncMock()

    with pytest.raises(ValueError, match="partition key does not match"):
        await _consumer(use_case).process_message(_message(key=b"wrong-key"))

    use_case.execute.assert_not_awaited()


async def test_invalid_contract_is_rejected_before_database_work() -> None:
    use_case = AsyncMock()
    payload = _payload()
    payload["schema_version"] = "2.0.0"

    with pytest.raises(ValidationError):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


async def test_missing_payload_is_rejected() -> None:
    use_case = AsyncMock()
    broker_message = MagicMock()
    broker_message.value.return_value = None
    broker_message.key.return_value = b"key"

    with pytest.raises(ValueError, match="payload is missing"):
        await _consumer(use_case).process_message(broker_message)

    use_case.execute.assert_not_awaited()


async def test_missing_partition_key_is_rejected() -> None:
    use_case = AsyncMock()
    broker_message = _message()
    broker_message.key.return_value = None

    with pytest.raises(ValueError, match="partition key is missing"):
        await _consumer(use_case).process_message(broker_message)

    use_case.execute.assert_not_awaited()


async def test_database_failure_is_retryable_for_ordered_redelivery() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = IntegrityError("INSERT", {}, RuntimeError("db unavailable"))

    with pytest.raises(RetryableConsumerError, match="database dependency unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_source_conflict_remains_terminal_for_dlq_evidence() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = ValueError("source version conflict")

    with pytest.raises(ValueError, match="source version conflict"):
        await _consumer(use_case).process_message(_message())
