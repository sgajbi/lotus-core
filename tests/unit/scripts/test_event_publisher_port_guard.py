from pathlib import Path

from scripts.event_publisher_port_guard import find_event_publisher_port_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_event_publisher_port_guard_allows_shared_event_publisher_port(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "from portfolio_common.event_publisher import EventPublisher\n",
    )

    assert find_event_publisher_port_findings(tmp_path) == []


def test_event_publisher_port_guard_rejects_concrete_kafka_imports(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_service.py",
        "from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer\n",
    )

    findings = find_event_publisher_port_findings(tmp_path)

    assert [finding.token for finding in findings] == [
        "portfolio_common.kafka_utils",
        "KafkaProducer",
        "get_kafka_producer",
    ]
