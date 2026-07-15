from pathlib import Path

from scripts.quality.aggregation_scheduler_boundary_guard import (
    find_aggregation_scheduler_boundary_findings,
)

SCHEDULER_PATH = (
    "src/services/portfolio_derived_state_service/app/application/aggregation_jobs/scheduler.py"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_boundary(root: Path) -> None:
    _write(
        root / SCHEDULER_PATH,
        "AggregationSchedulerRepositoryProvider\n"
        "AggregationSchedulerMetricsSink\n"
        "AggregationSchedulerClock\n"
        "AggregationJobBatchProcessor\n"
        "AggregationLeaseTokenGenerator\n"
        "recover_expired_job_leases\n"
        "claim_eligible_jobs\n"
        "def _run_poll_once(): pass\n",
    )
    _write(
        root / "src/services/portfolio_derived_state_service/app/infrastructure/"
        "aggregation_scheduler_adapters.py",
        "class SqlAlchemyAggregationSchedulerRepositoryProvider: pass\n"
        "class PrometheusAggregationSchedulerMetricsSink: pass\n"
        "class SystemAggregationSchedulerClock: pass\n"
        "get_async_db_session\n"
        "PortfolioAggregationRepository\n",
    )
    _write(
        root
        / "src/services/portfolio_derived_state_service/app/ports/aggregation_scheduler_ports.py",
        "class AggregationSchedulerRepository: pass\n"
        "class AggregationSchedulerRepositoryProvider: pass\n"
        "class AggregationSchedulerMetricsSink: pass\n"
        "class AggregationSchedulerClock: pass\n"
        "class AggregationJobBatchProcessor: pass\n"
        "class AggregationLeaseTokenGenerator: pass\n",
    )


def test_aggregation_scheduler_boundary_guard_allows_port_enabled_scheduler(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)

    assert find_aggregation_scheduler_boundary_findings(tmp_path) == []


def test_aggregation_scheduler_boundary_guard_rejects_runtime_coupling_in_scheduler(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path / SCHEDULER_PATH,
        "AggregationSchedulerRepositoryProvider\n"
        "AggregationSchedulerMetricsSink\n"
        "AggregationSchedulerClock\n"
        "AggregationJobBatchProcessor\n"
        "AggregationLeaseTokenGenerator\n"
        "recover_expired_job_leases\n"
        "claim_eligible_jobs\n"
        "def _run_poll_once(): pass\n"
        "get_async_db_session\n"
        "PortfolioAggregationRepository\n"
        "KafkaProducer\n"
        "get_kafka_producer\n"
        "publish_message(\n"
        ".flush(\n"
        "set_control_queue_pending\n"
        "set_control_queue_failed_stored\n"
        "set_control_queue_oldest_pending_age_seconds\n"
        "observe_control_queue_outcome\n",
    )

    findings = find_aggregation_scheduler_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "get_async_db_session",
        "PortfolioAggregationRepository",
        "KafkaProducer",
        "get_kafka_producer",
        "publish_message(",
        ".flush(",
        "set_control_queue_pending",
        "set_control_queue_failed_stored",
        "set_control_queue_oldest_pending_age_seconds",
        "observe_control_queue_outcome",
    ]


def test_aggregation_scheduler_boundary_guard_rejects_concrete_dependencies_in_ports(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path
        / "src/services/portfolio_derived_state_service/app/ports/aggregation_scheduler_ports.py",
        "class AggregationSchedulerRepository: pass\n"
        "class AggregationSchedulerRepositoryProvider: pass\n"
        "class AggregationSchedulerMetricsSink: pass\n"
        "class AggregationSchedulerClock: pass\n"
        "class AggregationJobBatchProcessor: pass\n"
        "class AggregationLeaseTokenGenerator: pass\n"
        "get_async_db_session\n"
        "PortfolioAggregationRepository\n"
        "KafkaProducer\n"
        "get_kafka_producer\n",
    )

    findings = find_aggregation_scheduler_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "get_async_db_session",
        "PortfolioAggregationRepository",
        "KafkaProducer",
        "get_kafka_producer",
    ]
