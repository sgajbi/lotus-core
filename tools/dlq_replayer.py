# ruff: noqa: E402
import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import replace
from typing import Optional

# Ensure the script can find the portfolio-common library
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from confluent_kafka import Message
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.logging_utils import normalize_traceparent, setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class DLQReplayConsumer(BaseConsumer):
    """
    A consumer designed to read from a DLQ, extract the original message,
    and attempt to republish it to its original topic.
    """

    def __init__(self, limit: Optional[int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer: KafkaProducer = get_kafka_producer(
            bootstrap_servers=self._consumer_config["bootstrap.servers"]
        )
        self._limit = limit
        self._processed_count = 0
        # Operator limits count attempts; serial admission prevents overshooting them.
        self.execution_profile = replace(self.execution_profile, max_in_flight_messages=1)

    async def process_message(self, msg: Message) -> None:
        """
        Processes a single message from the DLQ.
        """
        try:
            replay = self._decode_replay(msg)
            if replay is None:
                return
            original_topic, original_key, original_value, correlation_id, traceparent = replay

            logger.info(
                f"Replaying message from DLQ. Key: {original_key}, Topic: {original_topic}",
                extra={"correlation_id": correlation_id},
            )

            headers = [("correlation_id", (correlation_id or "").encode("utf-8"))]
            if traceparent:
                headers.append(("traceparent", traceparent.encode("utf-8")))

            def publish_and_confirm() -> None:
                self._producer.publish_message(
                    topic=original_topic,
                    key=original_key,
                    value=original_value,
                    headers=headers,
                )
                if self._producer.flush(timeout=5):
                    raise RuntimeError("Replay delivery confirmation timed out.")

            await self._native_operations.call(publish_and_confirm)
            logger.info(f"Successfully replayed message for key '{original_key}'.")
        except Exception as error:
            logger.error(
                "Unexpected error during replay. Message not committed.",
                extra={"dlq_key": msg.key()},
                exc_info=True,
            )
            # Stop admission before a later offset can acknowledge the failed replay.
            # Retryable classification avoids recursively republishing to another DLQ.
            self.shutdown()
            raise RetryableConsumerError("Replay remains unacknowledged for redelivery.") from error
        finally:
            self._processed_count += 1
            if self._limit and self._processed_count >= self._limit:
                logger.info(f"Reached processing limit of {self._limit}. Shutting down.")
                self.shutdown()

    def _decode_replay(self, msg: Message) -> tuple[str, str, dict, str | None, str | None] | None:
        """Explicitly discard malformed records, preserving malformed-then-valid replay."""
        try:
            value = msg.value()
            dlq_data = json.loads(value.decode("utf-8"))
            if not isinstance(dlq_data, dict):
                raise ValueError("DLQ envelope must be an object")
            topic = self._required_text(dlq_data, "original_topic")
            key = self._required_text(dlq_data, "original_key")
            original = json.loads(dlq_data["original_value"])
            correlation_id = dlq_data.get("correlation_id")
            if not isinstance(original, dict) or not original:
                raise ValueError("Missing original payload object")
            if correlation_id is not None and not isinstance(correlation_id, str):
                raise ValueError("Invalid correlation ID")
            return (
                topic,
                key,
                original,
                correlation_id,
                normalize_traceparent(dlq_data.get("traceparent")),
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            logger.warning(
                "Discarding malformed DLQ record without republishing; acknowledge discard.",
                extra={"dlq_key": msg.key()},
            )
            return None

    @staticmethod
    def _required_text(envelope: dict[str, object], field: str) -> str:
        value = envelope.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Missing replay {field}")
        return value

    async def run(self) -> None:
        """Stop admission after 15 seconds; shared lifecycle drains work before close."""
        deadline = asyncio.get_running_loop().call_later(15, self.shutdown)
        try:
            await super().run()
        finally:
            deadline.cancel()
            if self._processed_count == 0:
                logger.warning("No DLQ records processed before shutdown.")


async def main():
    parser = argparse.ArgumentParser(description="Kafka DLQ Replayer Tool")
    parser.add_argument("--dlq-topic", required=True, help="The DLQ topic to consume from.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of messages to process.",
    )
    args = parser.parse_args()

    logger.info(
        "Starting DLQ Replayer for topic: %s with a limit of %s",
        args.dlq_topic,
        args.limit or "unlimited",
    )
    group_id = f"dlq-replayer-{os.getpid()}"

    consumer = DLQReplayConsumer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093"),
        topic=args.dlq_topic,
        group_id=group_id,
        limit=args.limit,
    )

    await consumer.run()
    logger.info("DLQ Replayer has finished.")


if __name__ == "__main__":
    asyncio.run(main())
