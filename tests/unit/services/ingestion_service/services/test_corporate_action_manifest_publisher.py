"""Direct producer contract for corporate-action manifest authority."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from portfolio_common.config import KAFKA_CORPORATE_ACTION_MANIFEST_RECEIVED_TOPIC
from portfolio_common.event_publisher import KafkaEventPublisher
from portfolio_common.ingestion_lineage import ingestion_job_scope
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import correlation_id_var
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.corporate_action_manifest_dto import (
    CorporateActionManifestIngestionRequest,
)
from src.services.ingestion_service.app.services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
)

pytestmark = pytest.mark.asyncio

PARTITION_KEY = "PORTFOLIO_001|transaction-group|GROUP_001"


def _manifest(*, version: int = 1, revision: str | None = None) -> dict[str, object]:
    return {
        "corporate_action_event_id": "EVENT_001",
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "portfolio_id": "PORTFOLIO_001",
        "linked_transaction_group_id": "GROUP_001",
        "parent_event_reference": "PARENT_001",
        "corporate_action_type": "SPIN_OFF",
        "version": version,
        "completion_declared": True,
        "expected_children": [],
        "source": {
            "source_system": "corporate-actions-master",
            "source_record_id": "EVENT_001",
            "source_revision": revision or f"revision-{version}",
            "source_content_hash": f"{version:064x}",
            "observed_at": "2026-08-11T02:15:00Z",
        },
    }


def _request(
    manifests: list[dict[str, object]] | None = None,
) -> CorporateActionManifestIngestionRequest:
    return CorporateActionManifestIngestionRequest.model_validate(
        {"manifests": manifests or [_manifest()]}
    )


@pytest.fixture
def kafka_producer() -> MagicMock:
    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 0
    return producer


@pytest.fixture
def service(kafka_producer: MagicMock) -> IngestionService:
    return IngestionService(KafkaEventPublisher(kafka_producer))


async def test_publish_uses_exact_group_key_payload_and_lineage_headers(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    request = _request()
    correlation_token = correlation_id_var.set("corr-manifest-001")
    try:
        with ingestion_job_scope("job-manifest-001"):
            await service.publish_corporate_action_manifests(
                request,
                idempotency_key="manifest-request-001",
            )
    finally:
        correlation_id_var.reset(correlation_token)

    call = kafka_producer.publish_message.call_args
    assert call.kwargs["topic"] == KAFKA_CORPORATE_ACTION_MANIFEST_RECEIVED_TOPIC
    assert call.kwargs["key"] == PARTITION_KEY
    assert call.kwargs["value"] == request.manifests[0].model_dump(mode="json")
    assert dict(call.kwargs["headers"]) == {
        "correlation_id": b"corr-manifest-001",
        "ingestion_job_id": b"job-manifest-001",
        "idempotency_key": b"manifest-request-001",
    }
    kafka_producer.flush.assert_called_once_with(timeout=5)


async def test_parent_versions_publish_monotonically_per_stream(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    await service.publish_corporate_action_manifests(
        _request([_manifest(version=2), _manifest(version=1)])
    )

    assert [
        call.kwargs["value"]["version"] for call in kafka_producer.publish_message.call_args_list
    ] == [1, 2]


async def test_duplicate_parent_version_is_rejected_before_publication(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    duplicate = deepcopy(_manifest())
    source = duplicate["source"]
    assert isinstance(source, dict)
    source["source_revision"] = "conflicting-revision"

    with pytest.raises(ValidationError, match="duplicate parent-event versions"):
        _request([_manifest(), duplicate])

    kafka_producer.publish_message.assert_not_called()


async def test_publish_failure_reports_only_unpublished_versions(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    kafka_producer.publish_message.side_effect = [None, RuntimeError("broker unavailable")]

    with pytest.raises(IngestionPublishError) as exc_info:
        await service.publish_corporate_action_manifests(
            _request([_manifest(version=1), _manifest(version=2)])
        )

    assert exc_info.value.published_record_count == 1
    assert exc_info.value.failed_record_keys == [
        f"{PARTITION_KEY}|EVENT_001|v2|corporate-actions-master|EVENT_001|revision-2"
    ]
    kafka_producer.flush.assert_not_called()


async def test_delivery_timeout_reports_whole_batch_as_uncertain(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    kafka_producer.flush.return_value = 1

    with pytest.raises(IngestionPublishError) as exc_info:
        await service.publish_corporate_action_manifests(_request())

    assert exc_info.value.published_record_count == 0
    assert exc_info.value.failed_record_keys == [
        f"{PARTITION_KEY}|EVENT_001|v1|corporate-actions-master|EVENT_001|revision-1"
    ]


async def test_publish_rejects_untyped_request(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    with pytest.raises(TypeError, match="CorporateActionManifestIngestionRequest"):
        await service.publish_corporate_action_manifests(  # type: ignore[arg-type]
            {"manifests": [_manifest()]}
        )

    kafka_producer.publish_message.assert_not_called()
