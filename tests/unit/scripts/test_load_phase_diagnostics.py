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
from scripts.operations.performance import load_phase_evidence as phase_evidence


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
        "database": {"runtime_db_waits": {"status": "observed", "rows": [dict(backend)]}},
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


def test_phase_admission_valid_counters_and_counts_preserve_identity(phase_snapshot):
    scope, probes, payload, row, run = phase_snapshot
    payload.update(capture_errors=2, callback_failures=3)
    result = support._load_processing_phases(scope, probes)
    counts = result["admission"]
    assert (
        counts["candidate_count"],
        counts["active_count"],
        counts["admitted_count"],
    ) == (1, 1, 1)
    assert counts["rejected_count"] == 0 and counts["rejected_by_reason"] == {}
    assert counts["worker_counters"]["capture_errors"] == {
        "status": "observed",
        "value": 2,
    }
    assert counts["worker_counters"]["callback_failures"]["value"] == 3
    assert result["rows"][0]["exact_await"] == "MISSING"
    assert "do-not-export" not in json.dumps(result)
    assert len(json.dumps(result).encode()) < support.DIAGNOSTIC_MAX_BYTES


@pytest.mark.parametrize(
    "bad", [True, False, -1, 1.0, float("nan"), float("inf"), 2**31, "private"]
)
def test_phase_admission_invalid_counters_never_coerce_or_export(phase_snapshot, bad):
    scope, probes, payload, row, run = phase_snapshot
    payload.update(capture_errors=bad, callback_failures=bad)
    result = support._load_processing_phases(scope, probes)
    assert result["status"] == "observed"  # Supporting counters cannot alter row admission.
    assert all(
        counter == {"status": "invalid", "value": None}
        for counter in result["admission"]["worker_counters"].values()
    )
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("value", [0, 2**31 - 1, None])
def test_phase_admission_counter_boundaries_and_absence(value):
    expected = "missing" if value is None else "observed"
    assert phase_evidence.phase_counter(value) == {"status": expected, "value": value}


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("inactive", "inactive"),
        ("missing", "backend_missing"),
        ("invalid", "backend_identity_invalid"),
        ("birth", "backend_not_in_observed_sample"),
        ("database", "backend_not_in_observed_sample"),
        ("backend_duplicate", "backend_identity_ambiguous"),
        ("pid_duplicate", "duplicate_pid"),
        ("metadata", "invalid_phase_metadata"),
        ("nondict", "invalid_row"),
    ],
)
def test_phase_admission_closed_rejections_do_not_qualify_rows(phase_snapshot, mutation, reason):
    scope, probes, payload, row, run = phase_snapshot
    payload.update(capture_errors=0, callback_failures=0)
    if mutation == "inactive":
        row["active"] = False
    elif mutation == "missing":
        row["backend"] = None
    elif mutation == "invalid":
        row["backend"]["pid"] = True
    elif mutation in {"birth", "database"}:
        observed = probes["database"]["runtime_db_waits"]["rows"][0]
        observed["backend_start" if mutation == "birth" else "database_oid"] = (
            "2020-01-01T00:00:00+00:00" if mutation == "birth" else 999
        )
    elif mutation == "backend_duplicate":
        probes["database"]["runtime_db_waits"]["rows"].append(dict(row["backend"]))
    elif mutation == "pid_duplicate":
        payload["rows"].append(dict(row, generation="f" * 32))
    elif mutation == "metadata":
        row["task_identity"] = "private-invalid-task"
    else:
        payload["rows"] = ["private-invalid-row"]
    result = support._load_processing_phases(scope, probes)
    count = 2 if mutation == "pid_duplicate" else 1
    assert result["status"] == "unavailable" and result["rows"] == []
    assert result["admission"]["admitted_count"] == 0
    assert result["admission"]["rejected_count"] == count
    assert result["admission"]["rejected_by_reason"] == {reason: count}
    assert "private-invalid" not in json.dumps(result)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("run", "phase_run_generation_mismatch"),
        ("stale", "phase_snapshot_stale"),
        ("overflow", "phase_row_budget"),
        ("bytes", "phase_snapshot_byte_budget"),
    ],
)
def test_phase_admission_outer_fences_remain_closed(phase_snapshot, mutation, reason):
    scope, probes, payload, row, run = phase_snapshot
    if mutation == "run":
        payload["run_generation"] = "f" * 32
    elif mutation == "stale":
        payload["captured_at"] -= 121
    elif mutation == "overflow":
        payload["rows"] = [dict(row)] * 21
    else:
        payload["private"] = "x" * 16385
    result = support._load_processing_phases(scope, probes)
    assert result == {"status": "unavailable", "reason": reason}


def test_phase_admission_truncation_and_missing_counters_do_not_claim_worker_total(
    phase_snapshot,
):
    scope, probes, payload, row, run = phase_snapshot
    payload["truncated"] = True
    payload["rows"] = []
    result = support._load_processing_phases(scope, probes)
    assert result["truncated"] and result["status"] == "unavailable"
    assert result["admission"]["candidate_count"] == 0
    assert result["admission"]["scope"] == "bounded_snapshot_rows_not_whole_worker"
    assert all(
        counter["status"] == "missing"
        for counter in result["admission"]["worker_counters"].values()
    )


@pytest.mark.parametrize(
    "candidate,active,admitted,reasons",
    [
        (1, 1, 0, {"unknown": 1}),
        (True, 1, 0, {"inactive": 1}),
        (21, 1, 0, {"inactive": 21}),
        (1, 1, 0, {"inactive": float("nan")}),
        (1, 1, 0, {"inactive": -1}),
        (1, 1, 0, {"inactive": True}),
        (1, 0, 1, {}),
        (1, 1, 0, {}),
    ],
)
def test_phase_admission_contract_counts_reject_unknown_or_inconsistent_categories(
    candidate, active, admitted, reasons
):
    with pytest.raises(ValueError):
        phase_evidence.phase_admission_counts(candidate, active, admitted, reasons)


def test_phase_admission_mixed_snapshot_counts_partition_all_candidates(phase_snapshot):
    scope, probes, payload, row, run = phase_snapshot
    payload["rows"] = [row, dict(row, active=False), dict(row, backend=None), "private-row"]
    result = support._load_processing_phases(scope, probes)
    counts = result["admission"]
    assert (counts["candidate_count"], counts["active_count"], counts["admitted_count"]) == (
        4,
        2,
        1,
    )
    assert counts["rejected_count"] == 3
    assert counts["rejected_by_reason"] == {"inactive": 1, "backend_missing": 1, "invalid_row": 1}
    assert "private-row" not in json.dumps(result)
    assert result["rows"][0]["exact_await"] == "MISSING"


def test_phase_admission_active_count_cannot_disagree_with_rejection_partition():
    with pytest.raises(ValueError, match="phase_admission_active_count_mismatch"):
        phase_evidence.phase_admission_counts(1, 1, 0, {"inactive": 1})


def test_rejected_active_birth_key_and_snapshot_time_survive_without_admission(phase_snapshot):
    scope, probes, payload, row, run = phase_snapshot
    probes["database"]["runtime_db_waits"]["rows"][0]["backend_start"] = "2020-01-01T00:00:00Z"
    result = support._load_processing_phases(scope, probes)
    assert result["rows"] == [] and result["admission"]["admitted_count"] == 0
    assert result["admission"]["rejected_by_reason"] == {"backend_not_in_observed_sample": 1}
    rejected = result["admission"]["rejected_active"]["rows"][0]
    assert rejected["backend"]["value"] == row["backend"]
    assert rejected["generation"]["value"] == row["generation"] != payload["run_generation"]
    assert rejected["match_diagnostics"]["same_pid_birth_mismatch_count"] == 1
    assert rejected["authority"] == "not_admitted_not_causal"
    timing = result["snapshot_timing"]
    assert timing["captured_at"]["value"] == payload["captured_at"]
    assert timing["captured_monotonic"]["value"] == payload["captured_monotonic"]
    assert timing["clock_relation"] == "worker_monotonic_not_collector_clock"
    assert result["snapshot_identity"]["worker_pid"]["value"] == payload["worker_pid"]
    assert result["snapshot_identity"]["run_generation"]["value"] == scope["phase_generation"]
    assert "do-not-export" not in json.dumps(result)


@pytest.mark.parametrize("worker", [None, True, "private-worker", -1, 2**31])
def test_snapshot_worker_identity_missing_or_invalid_is_safe_not_admission(phase_snapshot, worker):
    scope, probes, payload, row, run = phase_snapshot
    payload["worker_pid"] = worker
    result = support._load_processing_phases(scope, probes)
    assert result["snapshot_identity"]["worker_pid"] == {
        "status": "missing" if worker is None else "invalid",
        "value": None,
    }
    assert result["rows"] == [] and "private-worker" not in json.dumps(result)


@pytest.mark.parametrize(
    "mutation,reason,full,birth,database",
    [
        ("valid", None, None, None, None),
        ("outside", "backend_not_in_observed_sample", 0, 0, 0),
        ("reuse", "backend_not_in_observed_sample", 0, 1, 0),
        ("database", "backend_not_in_observed_sample", 0, 0, 1),
        ("ambiguous", "backend_identity_ambiguous", 2, 0, 0),
        ("duplicate", "duplicate_pid", 1, 0, 0),
        ("inactive", "inactive", None, None, None),
    ],
)
def test_join_measurement_does_not_change_first_refusal_or_admission(
    phase_snapshot, mutation, reason, full, birth, database
):
    scope, probes, payload, row, run = phase_snapshot
    waits = probes["database"]["runtime_db_waits"]["rows"]
    if mutation == "outside":
        waits.clear()
    elif mutation == "reuse":
        waits[0]["backend_start"] = "2020-01-01T00:00:00Z"
    elif mutation == "database":
        waits[0]["database_oid"] = 9
    elif mutation == "ambiguous":
        waits.append(dict(waits[0]))
    elif mutation == "duplicate":
        payload["rows"].append(dict(row, generation="f" * 32))
    elif mutation == "inactive":
        row["active"] = False
    result = support._load_processing_phases(scope, probes)
    count = 2 if mutation == "duplicate" else 1
    assert result["admission"]["rejected_by_reason"] == ({reason: count} if reason else {})
    assert result["admission"]["admitted_count"] == (1 if reason is None else 0)
    detail = result["admission"]["rejected_active"]
    if mutation in {"valid", "inactive"}:
        assert detail["rows"] == []
    else:
        assert len(detail["rows"]) == count
        for record in detail["rows"]:
            match = record["match_diagnostics"]
            assert match["full_key_match_count"] == full
            assert match["same_pid_birth_mismatch_count"] == birth
            assert match["same_pid_database_mismatch_count"] == database
            assert record["reason"] == reason and record["authority"] == "not_admitted_not_causal"


@pytest.mark.parametrize(
    "key,bad",
    [
        ("generation", "private-generation"),
        ("delivery_hash", "private-business-id"),
        ("repair_delivery_hash", "private-repair-id"),
        ("worker_pid", "private-worker"),
        ("task_identity", "private-task"),
        ("phase", "private-phase"),
        ("phase_started_monotonic", float("inf")),
        ("updated_monotonic", float("nan")),
        ("updated_monotonic", -1),
        ("updated_monotonic", True),
        ("backend", {"pid": True, "backend_start": "private-birth", "database_oid": 7}),
    ],
)
def test_rejected_candidate_projection_refuses_sensitive_or_invalid_fields(
    phase_snapshot, key, bad
):
    scope, probes, payload, row, run = phase_snapshot
    probes["database"]["runtime_db_waits"]["rows"] = []
    row[key] = bad
    row["request_body"] = "private-body"
    result = support._load_processing_phases(scope, probes)
    projected = result["admission"]["rejected_active"]["rows"][0]
    assert projected[key] == {"status": "invalid", "value": None}
    assert "private-" not in json.dumps(result, allow_nan=False)
    assert result["rows"] == []
    assert result["admission"]["admitted_count"] == 0


def test_rejected_metadata_missing_and_clock_domains_remain_unqualified(phase_snapshot):
    scope, probes, payload, row, run = phase_snapshot
    probes["database"]["runtime_db_waits"]["rows"] = []
    for key in ("backend", "task_identity", "updated_monotonic"):
        row.pop(key, None)
    payload["captured_monotonic"] = 10**12  # Not the collector's monotonic epoch.
    result = support._load_processing_phases(scope, probes)
    record = result["admission"]["rejected_active"]["rows"][0]
    assert all(
        record[key] == {"status": "missing", "value": None}
        for key in ("backend", "task_identity", "updated_monotonic")
    )
    assert record["match_diagnostics"]["full_key_match_count"] is None
    assert result["snapshot_timing"]["captured_monotonic"]["value"] == 10**12
    assert result["rows"] == [] and result["sample_status"] == "observed"


def test_delayed_snapshot_and_collector_clock_regression_do_not_rewrite_admission(
    phase_snapshot, monkeypatch
):
    scope, probes, payload, row, run = phase_snapshot
    payload["captured_at"] = 100
    wall = iter([110, 109, 110])
    ticks = iter([1000, 1001])
    monkeypatch.setattr(support.time, "time", lambda: next(wall))
    monkeypatch.setattr(support.time, "monotonic", lambda: next(ticks))
    result = support._load_processing_phases(scope, probes)
    assert result["rows"][0]["backend"]["pid"] == 41
    assert result["transport_interval"]["wall_order"] == "clock_regression"
    assert result["transport_interval"]["elapsed_seconds"]["value"] == 1
    assert result["snapshot_timing"]["captured_at"]["value"] == 100
    assert result["snapshot_timing"]["clock_relation"] == "worker_monotonic_not_collector_clock"


@pytest.mark.parametrize("outcome", ["valid", "rejected", "duplicate"])
def test_pure_phase_evidence_preserves_raw_inputs_and_detaches_public_outputs(
    phase_snapshot, outcome
):
    scope, probes, payload, row, run = phase_snapshot
    waits = probes["database"]["runtime_db_waits"]["rows"]
    if outcome == "rejected":
        waits[0]["database_oid"] = 9
    elif outcome == "duplicate":
        payload["rows"].append(dict(row))
    before = json.dumps([payload, waits], sort_keys=True)
    admitted, admission = phase_evidence.processing_phase_admission(payload["rows"], payload, waits)
    sample = phase_evidence.original_wait_sample(waits)
    snapshot = phase_evidence.snapshot_measurements(payload, scope["phase_generation"], "observed")
    assert admission["admitted_count"] == (1 if outcome == "valid" else 0)
    assert admission["rejected_by_reason"] == (
        {}
        if outcome == "valid"
        else {"backend_not_in_observed_sample": 1}
        if outcome == "rejected"
        else {"duplicate_pid": 2}
    )
    if admitted:
        admitted[0]["backend"]["pid"] = -1
    else:
        rejected = admission["rejected_active"]["rows"][0]
        assert rejected["authority"] == "not_admitted_not_causal"
        rejected["backend"]["value"]["pid"] = -1
    sample["rows"][0]["backend"]["value"]["pid"] = -1
    snapshot["snapshot_identity"]["worker_pid"]["value"] = -1
    assert json.dumps([payload, waits], sort_keys=True) == before
