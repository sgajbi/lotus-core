# libs/portfolio-common/portfolio_common/kafka_admin.py
import logging
import sys
from typing import List

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient
from tenacity import before_log, retry, stop_after_attempt, wait_fixed

from .config import KAFKA_BOOTSTRAP_SERVERS

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(15),  # Total wait time: 15 attempts * 4s = 60s
    wait=wait_fixed(4),
    before=before_log(logger, logging.INFO),
)
def ensure_topics_exist(required_topics: List[str]):
    """
    Connects to Kafka and verifies that a list of required topics exists.

    This function uses a retry mechanism to wait for topics to be created,
    which is crucial in orchestrated environments like Docker Compose where a
    topic-creator service may still be running.

    If the topics are not found after the timeout, it logs a critical error
    and exits the application.

    Args:
        required_topics: A list of topic names that must exist.
    """
    logger.info(f"Verifying existence of Kafka topics: {required_topics}...")

    conf = {"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS}
    admin_client = AdminClient(conf)

    try:
        # Get the cluster metadata, which includes the list of topics
        cluster_metadata = admin_client.list_topics(timeout=5)
        existing_topics = cluster_metadata.topics.keys()

        # Find any topics that are required but do not yet exist
        missing_topics = [topic for topic in required_topics if topic not in existing_topics]

        if missing_topics:
            # If topics are missing, raise an exception to trigger a retry
            raise KafkaException(f"Required topics are not yet available: {missing_topics}")

        logger.info("All required Kafka topics found.")

    except KafkaException as e:
        logger.warning(f"Kafka error while verifying topics: {e}. Retrying...")
        raise  # Re-raise to allow tenacity to handle the retry
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred while verifying Kafka topics: {e}", exc_info=True
        )
        sys.exit(1)  # Exit on unexpected errors
