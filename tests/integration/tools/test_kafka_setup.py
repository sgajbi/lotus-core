# tests/integration/tools/test_kafka_setup.py
import pytest
from confluent_kafka.admin import AdminClient

# Import the main function and topic list from the script we are testing
import tools.kafka_setup as kafka_setup
from tools.kafka_setup import main as create_all_topics
from tools.kafka_setup import TOPICS_TO_CREATE

# Mark all tests in this file as async since some Kafka operations can be slow
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
def kafka_admin_client(docker_services):
    """Provides a Kafka AdminClient connected to the test container."""
    # The test runs on the host, so we connect to localhost
    bootstrap_servers = "localhost:9092" 
    client = AdminClient({"bootstrap.servers": bootstrap_servers})
    return client

async def test_kafka_setup_ensures_topics_exist_and_is_idempotent(kafka_admin_client, clean_db):
    """
    GIVEN a running docker-compose environment where topics are already created at startup
    WHEN the kafka_setup.py script is run again
    THEN it should complete without errors and all required topics should still be present.
    """
    # ARRANGE
    # In our test environment, the 'kafka-topic-creator' service has already run.
    # So, we first verify that the startup process worked as expected.
    topics_after_startup = kafka_admin_client.list_topics(timeout=5).topics
    
    missing_at_start = [
        topic for topic in TOPICS_TO_CREATE if topic not in topics_after_startup
    ]
    assert not missing_at_start, f"Topics that should have been created at startup are missing: {missing_at_start}"


    # ACT
    # Run the topic creation logic again to test for idempotency.
    # If the script is not idempotent, this call might raise an exception.
    kafka_setup.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    create_all_topics()


    # ASSERT
    # Fetch the topics again and verify the list is unchanged.
    topics_after_second_run = kafka_admin_client.list_topics(timeout=5).topics
    
    missing_at_end = [
        topic for topic in TOPICS_TO_CREATE if topic not in topics_after_second_run
    ]
    assert not missing_at_end, f"Topics disappeared after the second run: {missing_at_end}"

    # Check that no topics were unexpectedly removed.
    assert topics_after_second_run.keys() >= topics_after_startup.keys()
