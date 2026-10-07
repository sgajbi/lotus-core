"""Production emission and private UOW correlation admission controls."""

import json
import os
import stat
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from scripts.operations import performance_load_gate as gate
from scripts.operations.performance import load_completion_diagnostics as support


def response_body(monkeypatch, body):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [body]
    monkeypatch.setattr(support.requests, "get", MagicMock(return_value=response))


def test_actual_composed_consumers_emit_admitted_metrics(monkeypatch):
    from portfolio_common import monitoring

    from src.services.portfolio_transaction_processing_service.app.runtime import (
        consumer_composition,
    )

    registry = CollectorRegistry()
    gauge = Gauge(
        "kafka_consumer_in_flight_messages",
        "in flight",
        ("service", "topic", "group_id"),
        registry=registry,
    )
    monkeypatch.setattr(monitoring, "KAFKA_CONSUMER_IN_FLIGHT_MESSAGES", gauge)
    consumers = consumer_composition.build_transaction_processing_consumers(
        process_transaction=MagicMock(),
        replay_booked_transaction=MagicMock(),
        route_corporate_action_child=MagicMock(),
        tenant_authority=MagicMock(),
        handle_fixed_income_book_cost_authority=MagicMock(),
        handle_corporate_action_manifest=MagicMock(),
        fixed_income_authority_consumer_factory=MagicMock(),
        fixed_income_correction_replay_consumer_factory=MagicMock(),
        corporate_action_manifest_consumer_factory=MagicMock(),
    )
    for consumer in consumers[:2]:
        assert consumer._consumer is None  # No native broker client or runtime start.
        consumer._in_flight_tasks.add(object())
        consumer._set_in_flight_metric()
    response_body(monkeypatch, generate_latest(registry))
    result = support._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == "observed"
    assert {
        tuple(row["labels"][key] for key in ("service", "topic", "group_id"))
        for row in result["samples"]
    } == support._CONSUMER_METRIC_SCOPES
    assert [row["value"] for row in result["samples"]] == [1, 1]


@pytest.mark.parametrize(
    "service,topic,group",
    [
        (
            "portfolio-transaction-processing",
            "transactions.persisted",
            "portfolio_transaction_processing_group",
        ),
        (
            "TXNPROC",
            "transactions.reprocessing.requested",
            "portfolio_transaction_replay_request_group",
        ),
        ("TXNREPLAY", "transactions.persisted", "portfolio_transaction_processing_group"),
    ],
)
def test_wrong_metric_tuple_is_explicit_missing_not_zero(monkeypatch, service, topic, group):
    body = (
        f'kafka_consumer_in_flight_messages{{service="{service}",topic="{topic}",'
        f'group_id="{group}"}} 0\n'
    )
    response_body(monkeypatch, body.encode())
    result = support._load_consumer_metrics("http://isolated/metrics")
    assert result["status"] == "unavailable" and "samples" not in result
    assert result["reason"] == "no_matching_consumer_metric_samples"
    assert result["recognized_samples"] == result["filtered_samples"] == 1


@pytest.fixture
def phase_snapshot(monkeypatch):
    birth = datetime.now(UTC).isoformat()
    scope = {
        "tenant_id": support.LOAD_TENANT_ID,
        "portfolio_id": "PERF_BALANCED_V1",
        "phase_generation": "a" * 32,
        "phase_container_id": "e" * 64,
        "phase_container_started_at": "container-birth",
    }
    backend = {"pid": 41, "backend_start": birth, "database_oid": 7}
    row = {
        "active": True,
        "generation": "b" * 32,
        "worker_pid": 5,
        "backend": backend,
        "phase": "position",
        "phase_started_monotonic": 10,
        "task_identity": "0xabc",
        "delivery_hash": "c" * 64,
        "repair_delivery_hash": "d" * 64,
        "private_transaction": "do-not-export",
    }
    payload = {
        "run_generation": "a" * 32,
        "worker_pid": 5,
        "captured_at": time.time(),
        "captured_monotonic": 211,
        "rows": [row],
        "truncated": False,
    }
    probes = {
        "managed_worker": {
            "status": "observed",
            "container_id": "e" * 64,
            "started_at": "container-birth",
        },
        "database": {"runtime_db_waits": {"rows": [dict(backend)]}},
    }
    run = MagicMock(
        side_effect=lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload).encode())
    )
    monkeypatch.setattr(support.subprocess, "run", run)
    return scope, probes, payload, row, run


def test_phase_correlation_requires_birth_database_generation_and_keeps_await_unknown(
    phase_snapshot,
):
    scope, probes, payload, row, run = phase_snapshot
    result = support._load_processing_phases(scope, probes)
    assert result["status"] == "observed"
    assert result["rows"][0]["phase_elapsed_seconds"] == 201
    assert result["rows"][0]["exact_await"] == "MISSING"
    assert result["rows"][0]["boundary"] == "phase_in_progress_not_python_await"
    assert "do-not-export" not in json.dumps(result)
    assert run.call_args.kwargs["timeout"] == 0.5
    assert "read(16385)" in run.call_args.args[0][-1]


@pytest.mark.parametrize(
    "mutation",
    [
        "birth",
        "database",
        "run",
        "stale",
        "duplicate",
        "completed",
        "nonfinite",
        "task",
        "container",
    ],
)
def test_phase_refuses_stale_ambiguous_or_unqualified_records(phase_snapshot, mutation):
    scope, probes, payload, row, run = phase_snapshot
    if mutation == "birth":
        probes["database"]["runtime_db_waits"]["rows"][0]["backend_start"] = (
            "2020-01-01T00:00:00+00:00"
        )
    elif mutation == "database":
        probes["database"]["runtime_db_waits"]["rows"][0]["database_oid"] = 9
    elif mutation == "run":
        payload["run_generation"] = "f" * 32
    elif mutation == "stale":
        payload["captured_at"] -= 121
    elif mutation == "duplicate":
        payload["rows"].append(dict(row, generation="f" * 32))
    elif mutation == "completed":
        row["active"] = False
    elif mutation == "nonfinite":
        payload["captured_monotonic"] = float("nan")
    elif mutation == "container":
        probes["managed_worker"]["started_at"] = "replacement-birth"
    else:
        row["task_identity"] = "private-task-name"
    result = support._load_processing_phases(scope, probes)
    assert result["status"] == "unavailable"
    assert not result.get("rows")


def test_foreign_phase_scope_cannot_read_container(phase_snapshot):
    scope, probes, payload, row, run = phase_snapshot
    scope["tenant_id"] = "foreign"
    assert (
        support._load_processing_phases(scope, probes)["reason"] == "governed_phase_scope_required"
    )
    run.assert_not_called()


def test_owned_phase_enablement_fixed_path_and_identity(monkeypatch):
    identity = {
        "status": "observed",
        "container_id": "e" * 64,
        "created_at": "birth",
        "started_at": "start",
    }
    monkeypatch.setattr(support, "_load_managed_worker_identity", lambda scope: identity)
    run = MagicMock()
    monkeypatch.setattr(support.subprocess, "run", run)
    scope = {"tenant_id": support.LOAD_TENANT_ID, "portfolio_id": "PERF_BALANCED_V1"}
    result = support.enable_managed_processing_phases(scope)
    assert result["status"] == "enabled" and len(result["generation"]) == 32
    argv = run.call_args.args[0]
    assert argv[:3] == ["docker", "exec", identity["container_id"]]
    assert "os.mkdir(root, 0o700)" in argv[-2]
    assert "os.O_EXCL | os.O_NOFOLLOW" in argv[-2]
    assert "0o600, dir_fd=directory" in argv[-2]
    assert json.loads(argv[-1])["generation"] == result["generation"]
    assert run.call_args.kwargs["timeout"] == 0.5
    run.reset_mock()
    scope["portfolio_id"] = "foreign"
    assert support.enable_managed_processing_phases(scope)["status"] == "unavailable"
    run.assert_not_called()


@pytest.mark.skipif(
    os.name != "posix", reason="Actual remote transport owner/mode/dir_fd proof requires POSIX"
)
def test_native_owned_transport_scripts_create_exclusive_private_files_and_read_snapshot(
    tmp_path, monkeypatch
):
    import tempfile

    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_processing import (  # noqa: E501
        diagnostics,
    )

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["owned-enable", '{"generation":"' + "a" * 32 + '"}'])
    exec(support._processing_transport_script(enable=True), {})
    directory = tmp_path / "lotus-load-uow"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / "enable.json").stat().st_mode) == 0o600
    owner = diagnostics.TransientProcessingDiagnostics(
        directory / "enable.json", directory / "snapshot.json"
    )
    owner.write(b'{"actual":"private"}')
    output = MagicMock()
    monkeypatch.setattr(sys, "stdout", output)
    exec(support._processing_transport_script(enable=False), {})
    output.buffer.write.assert_called_once_with(b'{"actual":"private"}')
    with pytest.raises(FileExistsError):
        exec(support._processing_transport_script(enable=True), {})


@pytest.mark.skipif(
    os.name != "posix", reason="Actual remote transport symlink/mode proof requires POSIX"
)
@pytest.mark.parametrize(
    "damage", ["directory_symlink", "directory_mode", "snapshot_symlink", "snapshot_mode"]
)
def test_native_snapshot_reader_refuses_unsafe_path_without_leaking_target(
    tmp_path, monkeypatch, damage
):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    root = tmp_path / "lotus-load-uow"
    target = tmp_path / "private-target"
    target.mkdir(mode=0o700)
    (target / "snapshot.json").write_bytes(b"must-not-be-read")
    (target / "snapshot.json").chmod(0o600)
    if damage == "directory_symlink":
        root.symlink_to(target, target_is_directory=True)
    else:
        root.mkdir(mode=0o700)
        snapshot = root / "snapshot.json"
        if damage == "snapshot_symlink":
            snapshot.symlink_to(target / "snapshot.json")
        else:
            snapshot.write_bytes(b"owned")
            snapshot.chmod(0o644 if damage == "snapshot_mode" else 0o600)
        if damage == "directory_mode":
            root.chmod(0o755)
    output = MagicMock()
    monkeypatch.setattr(sys, "stdout", output)
    with pytest.raises(OSError):
        exec(support._processing_transport_script(enable=False), {})
    output.buffer.write.assert_not_called()


def test_load_caller_passes_real_container_admission_scope(monkeypatch):
    """Exercise real identity validation, not a mock that hides missing caller fields."""
    endpoints = SimpleNamespace(
        host_database_url="owned-db",
        e2e_transaction_processing_url="http://localhost:26090",
        compose_project_name="owned-load",
    )
    managed = SimpleNamespace(
        runtime=SimpleNamespace(endpoints=endpoints), compose_file="compose.yml"
    )
    args = SimpleNamespace(
        host_database_url="owned-db", transaction_processing_base_url="http://localhost:26090"
    )
    calls = []
    container = "e" * 64

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "ps":
            return SimpleNamespace(stdout=container)
        if argv[1] == "inspect":
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        container,
                        "2026-10-07T00:00:00Z",
                        "2026-10-07T00:00:01Z",
                        123,
                        "owned-load",
                        "portfolio_transaction_processing_service",
                        [{"HostPort": "26090"}],
                    ]
                )
            )
        return SimpleNamespace(stdout=b"")

    monkeypatch.setattr(support.subprocess, "run", run)
    result = gate._enable_owned_processing_phases(args, managed)
    assert result["status"] == "enabled" and [c[1] for c in calls] == ["ps", "inspect", "exec"]
    calls.clear()
    assert (
        support.enable_managed_processing_phases(
            {
                "tenant_id": support.LOAD_TENANT_ID,
                "portfolio_id": "PERF_BALANCED_V1",
                "runtime": "owned-load",
                "metrics_port": 26090,
            }
        )["reason"]
        == "managed_identity_missing"
    )
    assert calls == []
    args.host_database_url = "foreign-db"
    assert gate._enable_owned_processing_phases(args, managed)["status"] == "unavailable"
    assert calls == []
