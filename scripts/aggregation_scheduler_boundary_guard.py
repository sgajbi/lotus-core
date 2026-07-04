from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEDULER_MODULE = Path(
    "src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py"
)
PUBLISHER_MODULE = Path(
    "src/services/portfolio_aggregation_service/app/core/aggregation_job_publisher.py"
)
ADAPTER_MODULE = Path(
    "src/services/portfolio_aggregation_service/app/infrastructure/"
    "aggregation_scheduler_adapters.py"
)
PORT_MODULE = Path(
    "src/services/portfolio_aggregation_service/app/ports/aggregation_scheduler_ports.py"
)

REQUIRED_SCHEDULER_SNIPPETS = (
    "AggregationSchedulerRepositoryProvider",
    "AggregationSchedulerMetricsSink",
    "AggregationSchedulerClock",
    "AggregationJobPublisher",
    "plan_aggregation_job_dispatch",
    "publish_aggregation_dispatch_plan",
    "def _run_poll_once",
)
FORBIDDEN_SCHEDULER_SNIPPETS = {
    "get_async_db_session": (
        "database session factories belong in scheduler infrastructure adapters"
    ),
    "TimeseriesRepository": "concrete repositories belong behind the scheduler repository port",
    "KafkaProducer": "scheduler orchestration must use the aggregation job publisher port",
    "get_kafka_producer": "Kafka producer creation belongs in runtime composition",
    "publish_message(": "direct Kafka publication belongs in publisher adapters",
    ".flush(": "delivery confirmation belongs in publisher adapters",
    "set_control_queue_pending": "metric functions belong behind the scheduler metrics sink",
    "set_control_queue_failed_stored": "metric functions belong behind the scheduler metrics sink",
    "set_control_queue_oldest_pending_age_seconds": (
        "metric functions belong behind the scheduler metrics sink"
    ),
}
REQUIRED_PUBLISHER_SNIPPETS = (
    "class AggregationJobPublisher",
    "class AggregationJobDispatchMessage",
    "def plan_aggregation_job_dispatch",
    "def publish_aggregation_dispatch_plan",
)
FORBIDDEN_PUBLISHER_SNIPPETS = {
    "get_async_db_session": "publisher planning must not depend on database sessions",
    "TimeseriesRepository": "publisher planning must not depend on repositories",
    "KafkaProducer": "publisher adapters should use portfolio_common.event_publisher",
    "get_kafka_producer": "publisher adapters should use portfolio_common.event_publisher",
}
REQUIRED_ADAPTER_SNIPPETS = (
    "class SqlAlchemyAggregationSchedulerRepositoryProvider",
    "class PrometheusAggregationSchedulerMetricsSink",
    "class SystemAggregationSchedulerClock",
    "get_async_db_session",
    "TimeseriesRepository",
)
REQUIRED_PORT_SNIPPETS = (
    "class AggregationSchedulerRepository",
    "class AggregationSchedulerRepositoryProvider",
    "class AggregationSchedulerMetricsSink",
    "class AggregationSchedulerClock",
)
FORBIDDEN_PORT_SNIPPETS = {
    "get_async_db_session": "scheduler ports must not depend on database session factories",
    "TimeseriesRepository": "scheduler ports must not depend on concrete repositories",
    "KafkaProducer": "scheduler ports must not depend on concrete Kafka producers",
    "get_kafka_producer": "scheduler ports must not create concrete Kafka producers",
}


@dataclass(frozen=True, slots=True)
class AggregationSchedulerBoundaryFinding:
    path: str
    snippet: str
    reason: str


def find_aggregation_scheduler_boundary_findings(
    root: Path,
) -> list[AggregationSchedulerBoundaryFinding]:
    findings: list[AggregationSchedulerBoundaryFinding] = []
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=SCHEDULER_MODULE,
            snippets=REQUIRED_SCHEDULER_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=SCHEDULER_MODULE,
            snippets=FORBIDDEN_SCHEDULER_SNIPPETS,
        )
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=PUBLISHER_MODULE,
            snippets=REQUIRED_PUBLISHER_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=PUBLISHER_MODULE,
            snippets=FORBIDDEN_PUBLISHER_SNIPPETS,
        )
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=ADAPTER_MODULE,
            snippets=REQUIRED_ADAPTER_SNIPPETS,
        )
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=PORT_MODULE,
            snippets=REQUIRED_PORT_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=PORT_MODULE,
            snippets=FORBIDDEN_PORT_SNIPPETS,
        )
    )
    return findings


def _required_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: tuple[str, ...],
) -> list[AggregationSchedulerBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return [
            AggregationSchedulerBoundaryFinding(
                path=relative_path.as_posix(),
                snippet="<missing-file>",
                reason="required aggregation scheduler boundary file is missing",
            )
        ]
    source = path.read_text(encoding="utf-8")
    return [
        AggregationSchedulerBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason="required aggregation scheduler boundary snippet is missing",
        )
        for snippet in snippets
        if snippet not in source
    ]


def _forbidden_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: dict[str, str],
) -> list[AggregationSchedulerBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    return [
        AggregationSchedulerBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason=reason,
        )
        for snippet, reason in snippets.items()
        if snippet in source
    ]


def main() -> int:
    findings = find_aggregation_scheduler_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Aggregation scheduler boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
