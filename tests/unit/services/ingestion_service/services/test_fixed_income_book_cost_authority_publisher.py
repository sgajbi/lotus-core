"""Direct producer contract for fixed-income book-cost source authority."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from portfolio_common.config import KAFKA_FIXED_INCOME_BOOK_COST_AUTHORITY_RECEIVED_TOPIC
from portfolio_common.event_publisher import KafkaEventPublisher
from portfolio_common.ingestion_lineage import ingestion_job_scope
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import correlation_id_var, traceparent_var
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.fixed_income_book_cost_authority_dto import (
    FixedIncomeBookCostAuthorityIngestionRequest,
)
from src.services.ingestion_service.app.services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
)

pytestmark = pytest.mark.asyncio

TRACEPARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
PARTITION_KEY = "TENANT_001|BOOK_001|PORTFOLIO_001|SECURITY_001|LOT_001"


def _header(*, source_record_id: str, source_version: int = 1) -> dict[str, object]:
    return {
        "scope": {
            "tenant_id": "TENANT_001",
            "legal_book_id": "BOOK_001",
            "portfolio_id": "PORTFOLIO_001",
            "security_id": "SECURITY_001",
            "lot_id": "LOT_001",
        },
        "source": {
            "source_system": "fixed-income-master",
            "source_record_id": source_record_id,
            "source_revision": f"revision-{source_version}",
            "source_version": source_version,
            "observed_at": "2026-08-02T10:15:00+08:00",
        },
        "status": "ACTIVE",
        "valid_from": "2026-08-01",
        "valid_to": None,
    }


def _authorities() -> list[dict[str, object]]:
    return [
        {
            "authority_type": "POLICY_ASSIGNMENT",
            "header": _header(source_record_id="LOT_001-POLICY"),
            "policy_id": "EFFECTIVE_YIELD_BOOK_COST",
            "policy_version": 1,
            "assignment_reason": "Governed effective-yield accounting policy.",
        },
        {
            "authority_type": "CLEAN_COST_BASIS",
            "header": _header(source_record_id="LOT_001-BASIS"),
            "currency": "USD",
            "initial_clean_cost_local": "980000",
            "fees_in_basis_local": "1000",
            "redemption_value_local": "1000000",
            "discount_origin": "MARKET_DISCOUNT",
        },
        {
            "authority_type": "EFFECTIVE_YIELD",
            "header": _header(source_record_id="LOT_001-YIELD"),
            "annual_yield": "0.045",
            "yield_application": "ANNUAL_EFFECTIVE",
        },
    ]


def _request(
    authorities: list[dict[str, object]] | None = None,
) -> FixedIncomeBookCostAuthorityIngestionRequest:
    return FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
        {"authorities": authorities or _authorities()}
    )


@pytest.fixture
def kafka_producer() -> MagicMock:
    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 0
    return producer


@pytest.fixture
def service(kafka_producer: MagicMock) -> IngestionService:
    return IngestionService(KafkaEventPublisher(kafka_producer))


async def test_publish_uses_domain_partition_key_canonical_payload_and_lineage_headers(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    request = _request()
    correlation_token = correlation_id_var.set("corr-fixed-income-001")
    traceparent_token = traceparent_var.set(TRACEPARENT)
    try:
        with ingestion_job_scope("job-fixed-income-001"):
            await service.publish_fixed_income_book_cost_authorities(
                request,
                idempotency_key="fixed-income-request-001",
            )
    finally:
        traceparent_var.reset(traceparent_token)
        correlation_id_var.reset(correlation_token)

    assert kafka_producer.publish_message.call_count == 3
    expected_payloads = [event.model_dump(mode="json") for event in request.events()]
    for call, expected_payload in zip(
        kafka_producer.publish_message.call_args_list,
        expected_payloads,
        strict=True,
    ):
        assert call.kwargs["topic"] == KAFKA_FIXED_INCOME_BOOK_COST_AUTHORITY_RECEIVED_TOPIC
        assert call.kwargs["key"] == PARTITION_KEY
        assert call.kwargs["value"] == expected_payload
        assert call.kwargs["value"]["event_type"] == ("fixed_income.book_cost.authority.received")
        assert isinstance(call.kwargs["value"]["authority"]["header"]["valid_from"], str)
        headers = dict(call.kwargs["headers"])
        assert headers == {
            "correlation_id": b"corr-fixed-income-001",
            "traceparent": TRACEPARENT.encode("utf-8"),
            "ingestion_job_id": b"job-fixed-income-001",
            "idempotency_key": b"fixed-income-request-001",
        }
    kafka_producer.flush.assert_called_once_with(timeout=5)


async def test_duplicate_source_version_is_rejected_before_publication(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    authority = _authorities()[1]

    with pytest.raises(ValidationError, match="duplicate source-version identities"):
        request = _request([authority, deepcopy(authority)])
        await service.publish_fixed_income_book_cost_authorities(request)

    kafka_producer.publish_message.assert_not_called()
    kafka_producer.flush.assert_not_called()


async def test_source_versions_are_published_in_monotonic_stream_order(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    version_two = _authorities()[0]
    version_two["header"] = _header(
        source_record_id="LOT_001-POLICY",
        source_version=2,
    )
    version_two["policy_version"] = 2
    version_one = _authorities()[0]

    await service.publish_fixed_income_book_cost_authorities(_request([version_two, version_one]))

    published_versions = [
        call.kwargs["value"]["authority"]["header"]["source"]["source_version"]
        for call in kafka_producer.publish_message.call_args_list
    ]
    assert published_versions == [1, 2]


async def test_publish_rejects_untyped_request_before_publication(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    with pytest.raises(
        TypeError,
        match="request must be a FixedIncomeBookCostAuthorityIngestionRequest",
    ):
        await service.publish_fixed_income_book_cost_authorities(  # type: ignore[arg-type]
            {"authorities": _authorities()}
        )

    kafka_producer.publish_message.assert_not_called()
    kafka_producer.flush.assert_not_called()


async def test_publish_failure_reports_only_failed_and_unpublished_source_versions(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    kafka_producer.publish_message.side_effect = [None, RuntimeError("broker unavailable")]

    with pytest.raises(IngestionPublishError) as exc_info:
        await service.publish_fixed_income_book_cost_authorities(_request())

    expected_failed = [
        f"{PARTITION_KEY}|CLEAN_COST_BASIS|fixed-income-master|LOT_001-BASIS|v1",
        f"{PARTITION_KEY}|EFFECTIVE_YIELD|fixed-income-master|LOT_001-YIELD|v1",
    ]
    assert exc_info.value.failed_record_keys == expected_failed
    assert exc_info.value.published_record_count == 1
    assert "1 earlier record(s) were already published" in str(exc_info.value)
    assert "Remaining unpublished record keys" in str(exc_info.value)
    kafka_producer.flush.assert_not_called()


async def test_delivery_confirmation_failure_reports_whole_batch_as_uncertain(
    service: IngestionService,
    kafka_producer: MagicMock,
) -> None:
    kafka_producer.flush.return_value = 2

    with pytest.raises(IngestionPublishError) as exc_info:
        await service.publish_fixed_income_book_cost_authorities(_request())

    assert exc_info.value.failed_record_keys == [
        f"{PARTITION_KEY}|POLICY_ASSIGNMENT|fixed-income-master|LOT_001-POLICY|v1",
        f"{PARTITION_KEY}|CLEAN_COST_BASIS|fixed-income-master|LOT_001-BASIS|v1",
        f"{PARTITION_KEY}|EFFECTIVE_YIELD|fixed-income-master|LOT_001-YIELD|v1",
    ]
    assert exc_info.value.published_record_count == 0
    assert (
        "Delivery confirmation timed out for fixed-income book-cost authority delivery "
        "confirmation."
    ) in str(exc_info.value)
    kafka_producer.flush.assert_called_once_with(timeout=5)
