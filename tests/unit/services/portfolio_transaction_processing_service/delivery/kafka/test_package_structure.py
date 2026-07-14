"""Protect Kafka delivery test ownership and retired root paths."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
SERVICE_TEST_ROOT = REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service"


def test_kafka_delivery_tests_use_the_mirrored_package() -> None:
    """Keep Kafka adapter tests beside their delivery capability."""

    kafka_test_root = SERVICE_TEST_ROOT / "delivery/kafka"

    assert (kafka_test_root / "test_replay_request_consumer.py").is_file()
    assert (kafka_test_root / "test_transaction_consumer.py").is_file()
    assert (kafka_test_root / "test_transaction_event_mapper.py").is_file()
    assert not (SERVICE_TEST_ROOT / "test_booked_transaction_replay_request_consumer.py").exists()
    assert not (SERVICE_TEST_ROOT / "test_transaction_processing_consumer.py").exists()
    assert not (SERVICE_TEST_ROOT / "test_transaction_event_mapper.py").exists()
