"""Verify corporate-action manifest delivery is ordered and fail closed."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.event_mapping import EventContractValidationError
from portfolio_common.exceptions import RetryableConsumerError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    CorporateActionManifestConsumer,
)
from src.services.portfolio_transaction_processing_service.app.ports.corporate_action_event_graph import (  # noqa: E501
    CorporateActionManifestAppendOutcome,
)

pytestmark = pytest.mark.asyncio


def _payload() -> dict[str, object]:
    return {
        "event_type": "corporate_action.manifest.received",
        "schema_version": "1.0.0",
        "corporate_action_event_id": "EVENT_001",
        "portfolio_id": "PORTFOLIO_001",
        "linked_transaction_group_id": "GROUP_001",
        "parent_event_reference": "PARENT_001",
        "corporate_action_type": "SPIN_OFF",
        "version": 1,
        "completion_declared": True,
        "expected_children": [],
        "source": {
            "source_system": "corporate-actions-master",
            "source_record_id": "EVENT_001",
            "source_revision": "revision-1",
            "source_content_hash": "a" * 64,
            "observed_at": "2026-08-11T02:15:00Z",
        },
    }


def _message(*, payload: object | None = None, key: bytes | None = None) -> MagicMock:
    message = MagicMock()
    message.value.return_value = json.dumps(_payload() if payload is None else payload).encode()
    message.key.return_value = (
        key
        if key is not None
        else b"PORTFOLIO_001|transaction-group|GROUP_001"
    )
    message.headers.return_value = [("correlation_id", b"corr-manifest-001")]
    return message


def _consumer(use_case: AsyncMock) -> CorporateActionManifestConsumer:
    return CorporateActionManifestConsumer(
        bootstrap_servers="mock-server",
        topic="corporate_action.manifest.received",
        group_id="corporate_action_manifest_group",
        use_case=use_case,
    )


async def test_valid_manifest_and_exact_group_key_invoke_handler() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = CorporateActionManifestAppendOutcome.APPENDED

    await _consumer(use_case).process_message(_message())

    event = use_case.execute.await_args.args[0]
    assert event.corporate_action_event_id == "EVENT_001"
    assert event.source.source_revision == "revision-1"
    use_case.execute.assert_awaited_once()


async def test_partition_key_drift_is_rejected_before_database_work() -> None:
    use_case = AsyncMock()

    with pytest.raises(ValueError, match="partition key does not match"):
        await _consumer(use_case).process_message(_message(key=b"wrong-key"))

    use_case.execute.assert_not_awaited()


async def test_unsupported_schema_is_rejected_before_database_work() -> None:
    use_case = AsyncMock()
    payload = _payload()
    payload["schema_version"] = "2.0.0"

    with pytest.raises(EventContractValidationError, match="not supported"):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


async def test_missing_source_authority_is_rejected_before_database_work() -> None:
    use_case = AsyncMock()
    payload = _payload()
    del payload["source"]

    with pytest.raises(ValidationError):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


@pytest.mark.parametrize("payload", ([], "not-an-object"))
async def test_non_object_payload_is_rejected(payload: object) -> None:
    use_case = AsyncMock()

    with pytest.raises(ValueError, match="must be a JSON object"):
        await _consumer(use_case).process_message(_message(payload=payload))

    use_case.execute.assert_not_awaited()


async def test_database_failure_is_retryable_for_ordered_redelivery() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = IntegrityError("INSERT", {}, RuntimeError("db unavailable"))

    with pytest.raises(RetryableConsumerError, match="database dependency unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_source_conflict_remains_terminal_for_dlq_evidence() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = ValueError("source revision conflict")

    with pytest.raises(ValueError, match="source revision conflict"):
        await _consumer(use_case).process_message(_message())
