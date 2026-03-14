# ruff: noqa: E402, I001
import os
import sys
import time
import json
import logging
import asyncio
import argparse
from typing import Optional

# Ensure the script can find the portfolio-common library
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from portfolio_common.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class DLQReplayConsumer(BaseConsumer):
    """
    A consumer designed to read from a DLQ, extract the original message,
    and attempt to republish it to its original topic.
    """
    def __init__(self, limit: Optional[int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer: KafkaProducer = get_kafka_producer()
        self._limit = limit
        self._processed_count = 0

    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single message from the DLQ.
        """
        try:
            dlq_data = json.loads(msg.value().decode("utf-8"))

            original_topic = dlq_data.get("original_topic")
            original_key = dlq_data.get("original_key")
            original_value_str = dlq_data.get("original_value")
            original_value = json.loads(original_value_str)
            correlation_id = dlq_data.get("correlation_id")

            if not all([original_topic, original_key, original_value]):
                logger.error(
                    "DLQ message is missing required fields. Skipping.",
                    extra={"dlq_key": msg.key()},
                )
                return

            logger.info(
                f"Replaying message from DLQ. Key: {original_key}, Topic: {original_topic}",
                extra={"correlation_id": correlation_id},
            )

            headers = [("correlation_id", (correlation_id or "").encode("utf-8"))]

            self._producer.publish_message(
                topic=original_topic,
                key=original_key,
                value=original_value,
                headers=headers,
            )
            undelivered_count = self._producer.flush(timeout=5)
            if undelivered_count:
                raise RuntimeError(
                    "Replay delivery confirmation timed out before Kafka acknowledged the message."
                )
            logger.info(f"Successfully replayed message for key '{original_key}'.")

            self._consumer.commit(message=msg, asynchronous=False)

        except json.JSONDecodeError:
            logger.error(
                "Failed to parse DLQ message value. Skipping.",
                extra={"dlq_key": msg.key()},
                exc_info=True,
            )
        except Exception:
            logger.error(
                "Unexpected error during replay. Message not committed.",
                extra={"dlq_key": msg.key()},
                exc_info=True,
            )
        finally:
            self._processed_count += 1
            if self._limit and self._processed_count >= self._limit:
                logger.info(f"Reached processing limit of {self._limit}. Shutting down.")
                self.shutdown()

    async def run(self):
        """
        Overrides the base consumer's run loop to include a timeout, making
        it suitable for a script that should not run indefinitely.
        """
        self._initialize_consumer()
        loop = asyncio.get_running_loop()

        timeout = 15  # seconds
        start_time = time.time()

        logger.info(f"Polling topic '{self.topic}' with a {timeout}s timeout...")

        while self._running and (time.time() - start_time) < timeout:
            msg = await loop.run_in_executor(None, self._consumer.poll, 1.0)

            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka consumer error: {msg.error()}")
                continue

            # This is a synchronous call within the executor
            await loop.run_in_executor(None, self.process_message, msg, loop)

        if self._processed_count == 0:
            logger.warning(f"No messages found on topic '{self.topic}' within the timeout period.")

        self.shutdown()


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
