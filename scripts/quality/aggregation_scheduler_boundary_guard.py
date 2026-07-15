from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEDULER_MODULE = Path(
    "src/services/portfolio_derived_state_service/app/application/aggregation_jobs/scheduler.py"
)
ADAPTER_MODULE = Path(
    "src/services/portfolio_derived_state_service/app/infrastructure/"
    "aggregation_scheduler_adapters.py"
)
PORT_MODULE = Path(
    "src/services/portfolio_derived_state_service/app/ports/aggregation_scheduler_ports.py"
)

REQUIRED_SCHEDULER_SNIPPETS = (
    "AggregationSchedulerRepositoryProvider",
    "AggregationSchedulerMetricsSink",
    "AggregationSchedulerClock",
    "AggregationJobBatchProcessor",
    "AggregationLeaseTokenGenerator",
    "recover_expired_job_leases",
    "claim_eligible_jobs",
    "def _run_poll_once",
)
FORBIDDEN_SCHEDULER_SNIPPETS = {
    "get_async_db_session": (
        "database session factories belong in scheduler infrastructure adapters"
    ),
    "TimeseriesRepository": "concrete repositories belong behind the scheduler repository port",
    "PortfolioAggregationRepository": (
        "concrete repositories belong behind the scheduler repository port"
    ),
    "KafkaProducer": "application scheduling must not depend on Kafka",
    "get_kafka_producer": "application scheduling must not create Kafka producers",
    "publish_message(": "application scheduling must not publish transport messages",
    ".flush(": "application scheduling must not manage broker delivery",
    "set_control_queue_pending": "metric functions belong behind the scheduler metrics sink",
    "set_control_queue_failed_stored": "metric functions belong behind the scheduler metrics sink",
    "set_control_queue_oldest_pending_age_seconds": (
        "metric functions belong behind the scheduler metrics sink"
    ),
    "observe_control_queue_outcome": (
        "metric functions belong behind the scheduler metrics sink"
    ),
}
REQUIRED_ADAPTER_SNIPPETS = (
    "class SqlAlchemyAggregationSchedulerRepositoryProvider",
    "class PrometheusAggregationSchedulerMetricsSink",
    "class SystemAggregationSchedulerClock",
    "get_async_db_session",
    "PortfolioAggregationRepository",
)
REQUIRED_PORT_SNIPPETS = (
    "class AggregationSchedulerRepository",
    "class AggregationSchedulerRepositoryProvider",
    "class AggregationSchedulerMetricsSink",
    "class AggregationSchedulerClock",
    "class AggregationJobBatchProcessor",
    "class AggregationLeaseTokenGenerator",
)
FORBIDDEN_PORT_SNIPPETS = {
    "get_async_db_session": "scheduler ports must not depend on database session factories",
    "TimeseriesRepository": "scheduler ports must not depend on concrete repositories",
    "PortfolioAggregationRepository": "scheduler ports must not depend on concrete repositories",
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
