from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GOVERNED_APPLICATION_PUBLISHER_PATHS = (
    Path("src/services/ingestion_service/app/services/ingestion_service.py"),
    Path("src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py"),
    Path("src/services/valuation_orchestrator_service/app/core/valuation_job_publisher.py"),
)
FORBIDDEN_TOKENS = (
    "portfolio_common.kafka_utils",
    "KafkaProducer",
    "get_kafka_producer",
)


@dataclass(frozen=True, slots=True)
class EventPublisherPortFinding:
    path: str
    token: str


def find_event_publisher_port_findings(root: Path) -> list[EventPublisherPortFinding]:
    findings: list[EventPublisherPortFinding] = []
    for relative_path in GOVERNED_APPLICATION_PUBLISHER_PATHS:
        path = root / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in source:
                findings.append(
                    EventPublisherPortFinding(
                        path=relative_path.as_posix(),
                        token=token,
                    )
                )
    return findings


def main() -> int:
    findings = find_event_publisher_port_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(
                f"{finding.path}: {finding.token}: application publisher paths must use "
                "portfolio_common.event_publisher ports"
            )
        return 1
    print("Event publisher port guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
