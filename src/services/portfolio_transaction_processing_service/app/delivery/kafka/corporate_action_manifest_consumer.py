"""Kafka delivery for source-owned corporate-action manifests."""

from __future__ import annotations

import json
import logging
from typing import cast

from confluent_kafka import Message
from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent
from portfolio_common.event_mapping import (
    DecodedKafkaEventPayload,
    kafka_event_id,
    validate_kafka_event_payload,
)
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from sqlalchemy.exc import DBAPIError, IntegrityError

from ...application.corporate_action_manifest_ingestion import (
    HandleCorporateActionManifestEventUseCase,
)

logger = logging.getLogger(__name__)

_EVENT_TYPE = "corporate_action.manifest.received"
_ACCEPTED_SCHEMA_VERSIONS = ("1.0.0",)


class CorporateActionManifestConsumer(BaseConsumer):
    """Validate and register each manifest on its exact group-ordered stream."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: str | None = None,
        service_prefix: str = "CAMANIFEST",
        metrics: dict[str, object] | None = None,
        execution_profile: KafkaConsumerExecutionProfile | None = None,
        retryable_failure_max_attempts: int | None = None,
        retryable_failure_max_elapsed_seconds: int | None = None,
        *,
        use_case: HandleCorporateActionManifestEventUseCase,
    ) -> None:
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic=topic,
            group_id=group_id,
            dlq_topic=dlq_topic,
            service_prefix=service_prefix,
            metrics=metrics,
            execution_profile=execution_profile,
            retryable_failure_max_attempts=retryable_failure_max_attempts,
            retryable_failure_max_elapsed_seconds=retryable_failure_max_elapsed_seconds,
        )
        self._use_case = use_case

    async def process_message(self, msg: Message) -> None:
        event = validate_kafka_event_payload(
            _message_payload(msg),
            CorporateActionManifestReceivedEvent,
            expected_event_type=_EVENT_TYPE,
            accepted_schema_versions=_ACCEPTED_SCHEMA_VERSIONS,
        )
        if _message_key(msg) != event.partition_key:
            raise ValueError("corporate-action manifest partition key does not match event scope")
        try:
            outcome = await self._use_case.execute(event)
        except (DBAPIError, IntegrityError) as exc:
            raise RetryableConsumerError(
                "Corporate-action manifest database dependency unavailable"
            ) from exc
        logger.debug(
            "Corporate-action manifest processed.",
            extra={
                "corporate_action_event_id": event.corporate_action_event_id,
                "linked_transaction_group_id": event.linked_transaction_group_id,
                "manifest_outcome": outcome.value,
                "portfolio_id": event.portfolio_id,
                "source_revision": event.source.source_revision,
                "version": event.version,
            },
        )


def _message_payload(msg: Message) -> DecodedKafkaEventPayload:
    value = msg.value()
    if value is None:
        raise ValueError("corporate-action manifest payload is missing")
    try:
        data = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("corporate-action manifest payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("corporate-action manifest payload must be a JSON object")
    return DecodedKafkaEventPayload(event_id=kafka_event_id(msg), data=data)


def _message_key(msg: Message) -> str:
    key = msg.key()
    if key is None:
        raise ValueError("corporate-action manifest partition key is missing")
    try:
        return cast(str, key.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("corporate-action manifest partition key is not UTF-8") from exc
