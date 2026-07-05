# libs/portfolio-common/portfolio_common/kafka_admin.py
import logging
from typing import List

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient
from tenacity import before_log, retry, stop_after_attempt, stop_after_delay, wait_fixed

from .config import KAFKA_BOOTSTRAP_SERVERS
from .downstream_access import DownstreamAccessPolicy, load_downstream_access_policy

logger = logging.getLogger(__name__)
KAFKA_ADMIN_ACCESS_POLICY = load_downstream_access_policy()


class KafkaTopicVerificationError(RuntimeError):
    """Raised when required Kafka topics cannot be verified safely."""


@retry(
    stop=stop_after_attempt(KAFKA_ADMIN_ACCESS_POLICY.retry_max_attempts)
    | stop_after_delay(KAFKA_ADMIN_ACCESS_POLICY.retry_max_elapsed_seconds),
    wait=wait_fixed(KAFKA_ADMIN_ACCESS_POLICY.retry_backoff_seconds),
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

    try:
        _verify_required_topics(
            _build_admin_client(),
            required_topics,
            policy=KAFKA_ADMIN_ACCESS_POLICY,
        )
        logger.info("All required Kafka topics found.")

    except KafkaException as e:
        logger.warning(f"Kafka error while verifying topics: {e}. Retrying...")
        raise  # Re-raise to allow tenacity to handle the retry
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred while verifying Kafka topics: {e}", exc_info=True
        )
        raise KafkaTopicVerificationError("Unexpected error while verifying Kafka topics.") from e


def _build_admin_client() -> AdminClient:
    return AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})


def _verify_required_topics(
    admin_client: AdminClient,
    required_topics: List[str],
    *,
    policy: DownstreamAccessPolicy | None = None,
) -> None:
    existing_topics = _existing_topic_names(admin_client, policy=policy)
    missing_topics = _missing_required_topics(required_topics, existing_topics)
    if missing_topics:
        raise KafkaException(f"Required topics are not yet available: {missing_topics}")


def _existing_topic_names(
    admin_client: AdminClient,
    *,
    policy: DownstreamAccessPolicy | None = None,
):
    resolved_policy = policy or KAFKA_ADMIN_ACCESS_POLICY
    cluster_metadata = admin_client.list_topics(timeout=resolved_policy.request_timeout_seconds)
    return cluster_metadata.topics.keys()


def _missing_required_topics(required_topics: List[str], existing_topics) -> list[str]:
    return [topic for topic in required_topics if topic not in existing_topics]
