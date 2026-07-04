from pathlib import Path

from scripts.aggregation_scheduler_boundary_guard import (
    find_aggregation_scheduler_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_boundary(root: Path) -> None:
    _write(
        root / "src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py",
        "AggregationSchedulerRepositoryProvider\n"
        "AggregationSchedulerMetricsSink\n"
        "AggregationSchedulerClock\n"
        "AggregationJobPublisher\n"
        "plan_aggregation_job_dispatch\n"
        "publish_aggregation_dispatch_plan\n"
        "def _run_poll_once(): pass\n",
    )
    _write(
        root / "src/services/portfolio_aggregation_service/app/core/aggregation_job_publisher.py",
        "class AggregationJobPublisher: pass\n"
        "class AggregationJobDispatchMessage: pass\n"
        "def plan_aggregation_job_dispatch(): pass\n"
        "def publish_aggregation_dispatch_plan(): pass\n",
    )
    _write(
        root / "src/services/portfolio_aggregation_service/app/infrastructure/"
        "aggregation_scheduler_adapters.py",
        "class SqlAlchemyAggregationSchedulerRepositoryProvider: pass\n"
        "class PrometheusAggregationSchedulerMetricsSink: pass\n"
        "class SystemAggregationSchedulerClock: pass\n"
        "get_async_db_session\n"
        "TimeseriesRepository\n",
    )
    _write(
        root
        / "src/services/portfolio_aggregation_service/app/ports/aggregation_scheduler_ports.py",
        "class AggregationSchedulerRepository: pass\n"
        "class AggregationSchedulerRepositoryProvider: pass\n"
        "class AggregationSchedulerMetricsSink: pass\n"
        "class AggregationSchedulerClock: pass\n",
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
        tmp_path / "src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py",
        "AggregationSchedulerRepositoryProvider\n"
        "AggregationSchedulerMetricsSink\n"
        "AggregationSchedulerClock\n"
        "AggregationJobPublisher\n"
        "plan_aggregation_job_dispatch\n"
        "publish_aggregation_dispatch_plan\n"
        "def _run_poll_once(): pass\n"
        "get_async_db_session\n"
        "TimeseriesRepository\n"
        "KafkaProducer\n"
        "get_kafka_producer\n"
        "publish_message(\n"
        ".flush(\n"
        "set_control_queue_pending\n"
        "set_control_queue_failed_stored\n"
        "set_control_queue_oldest_pending_age_seconds\n",
    )

    findings = find_aggregation_scheduler_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "get_async_db_session",
        "TimeseriesRepository",
        "KafkaProducer",
        "get_kafka_producer",
        "publish_message(",
        ".flush(",
        "set_control_queue_pending",
        "set_control_queue_failed_stored",
        "set_control_queue_oldest_pending_age_seconds",
    ]


def test_aggregation_scheduler_boundary_guard_rejects_database_coupled_publisher(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path
        / "src/services/portfolio_aggregation_service/app/core/aggregation_job_publisher.py",
        "class AggregationJobPublisher: pass\n"
        "class AggregationJobDispatchMessage: pass\n"
        "def plan_aggregation_job_dispatch(): pass\n"
        "def publish_aggregation_dispatch_plan(): pass\n"
        "get_async_db_session\n"
        "TimeseriesRepository\n"
        "KafkaProducer\n"
        "get_kafka_producer\n",
    )

    findings = find_aggregation_scheduler_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "get_async_db_session",
        "TimeseriesRepository",
        "KafkaProducer",
        "get_kafka_producer",
    ]


def test_aggregation_scheduler_boundary_guard_rejects_concrete_dependencies_in_ports(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path
        / "src/services/portfolio_aggregation_service/app/ports/aggregation_scheduler_ports.py",
        "class AggregationSchedulerRepository: pass\n"
        "class AggregationSchedulerRepositoryProvider: pass\n"
        "class AggregationSchedulerMetricsSink: pass\n"
        "class AggregationSchedulerClock: pass\n"
        "get_async_db_session\n"
        "TimeseriesRepository\n"
        "KafkaProducer\n"
        "get_kafka_producer\n",
    )

    findings = find_aggregation_scheduler_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "get_async_db_session",
        "TimeseriesRepository",
        "KafkaProducer",
        "get_kafka_producer",
    ]
