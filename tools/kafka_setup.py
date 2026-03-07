# tools/kafka_setup.py
import logging
import os
import sys
import time

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS
from portfolio_common.logging_utils import setup_logging

# Setup basic logging for the tool
setup_logging()
logger = logging.getLogger(__name__)

# --- UPDATED: Production-Ready Kafka Topic Configurations ---

# For production, replication_factor should be >= 3. For local dev, 1 is sufficient.
REPLICATION_FACTOR = int(os.getenv("KAFKA_REPLICATION_FACTOR", 1))
NUM_PARTITIONS = int(os.getenv("KAFKA_NUM_PARTITIONS", 1))
# For production, min.insync.replicas should be 2 when replication factor is 3.
MIN_INSYNC_REPLICAS = int(os.getenv("KAFKA_MIN_INSYNC_REPLICAS", 1))

TOPIC_CONFIG = {
    # Guarantees that messages are not lost if a leader fails.
    "min.insync.replicas": MIN_INSYNC_REPLICAS,
    # Prevents an out-of-sync replica from being elected as leader, avoiding data loss.
    "unclean.leader.election.enable": "false",
    # Example retention policy: 7 days
    "retention.ms": "604800000"
}

TOPICS_TO_CREATE = [
    # Raw ingestion topics
    "raw_portfolios",
    "raw_transactions",
    "instruments",
    "market_prices",
    "fx_rates",
    "raw_business_dates",
    # Persistence completion topics
    "raw_transactions_completed",
    "market_price_persisted", # Restored topic
    # Calculation completion topics
    "processed_transactions_completed",
    "transaction_processing_completed",
    "cashflow_calculated",
    "daily_position_snapshot_persisted",
    "position_valued",
    # Timeseries topics
    "position_timeseries_generated",
    "portfolio_aggregation_required",
    # DLQ topics
    "persistence_service.dlq",
    # Valuation Job Topic
    "valuation_required",
    "portfolio_day_ready_for_valuation",
    "valuation_day_completed",
    # Reprocessing Topic
    "transactions_reprocessing_requested", # <-- NEW TOPIC
]

def create_topics(admin_client: AdminClient):
    """Creates topics in Kafka."""

    existing_topics = admin_client.list_topics().topics

    new_topic_list = [
        NewTopic(
            topic,
            num_partitions=NUM_PARTITIONS,
            replication_factor=REPLICATION_FACTOR,
            config=TOPIC_CONFIG
        )
        for topic in TOPICS_TO_CREATE if topic not in existing_topics
    ]

    if not new_topic_list:
        logger.info("All topics already exist. No action taken.")
        return

    logger.info(f"Attempting to create {len(new_topic_list)} new topics...")
    futures = admin_client.create_topics(new_topic_list)

    for topic, future in futures.items():
        try:
            future.result()  # The result itself is None on success
            logger.info(f"Topic '{topic}' created successfully.")
        except KafkaException as e:
            # Check if the error is "TOPIC_ALREADY_EXISTS"
            if e.args[0].code() == KafkaException.TOPIC_ALREADY_EXISTS:
                logger.warning(f"Topic '{topic}' already exists.")
            else:
                logger.error(f"Failed to create topic '{topic}': {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred for topic '{topic}': {e}")

def main():
    """Main function to set up Kafka topics."""
    conf = {'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS}
    admin_client = AdminClient(conf)

    # Retry connecting to Kafka
    max_retries = 10
    retry_delay = 5
    for attempt in range(max_retries):
        try:
            # A simple operation to check connectivity
            admin_client.list_topics(timeout=5)
            logger.info("Successfully connected to Kafka.")
            break
        except KafkaException as e:
            logger.warning(
                "Attempt %s/%s: Failed to connect to Kafka, retrying in %ss... Error: %s",
                attempt + 1,
                max_retries,
                retry_delay,
                e,
            )
            if attempt == max_retries - 1:
                logger.critical("Could not connect to Kafka after multiple retries. Exiting.")
                sys.exit(1)
            time.sleep(retry_delay)

    create_topics(admin_client)
    logger.info("Kafka topic setup complete.")

if __name__ == '__main__':
    main()
