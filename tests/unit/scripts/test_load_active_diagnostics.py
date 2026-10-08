"""Active-boundary timing and owned custody controls; no database/runtime proof."""

from __future__ import annotations

import json
import multiprocessing
import struct
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.operations import performance_load_gate as gate
from scripts.operations import transaction_processing_load_support as support
from scripts.operations.performance import load_completion_diagnostics as collector
from scripts.operations.performance import load_phase_evidence as phase_evidence
from scripts.operations.performance.load_diagnostic_capture import (
    SCOPE_INPUT_MAX_BYTES,
    DiagnosticCapture,
    DiagnosticScopeSlot,
    read_diagnostic_scope,
)


def observation(count=0, **changes):
    return {
        "status": "observed",
        "count": count,
        "labels": {"stage": "transaction", "outcome": "processed"},
        "producer_birth": 10,
        "counter_created_at": 11,
        "continuity": "observed",
        **changes,
    }


@pytest.fixture
def report(tmp_path, monkeypatch):
    args = SimpleNamespace(
        profile_tier="full",
        enforce=True,
        repo_root=str(tmp_path),
        output_dir="evidence",
        drain_timeout_seconds=240,
    )
    value = gate._LoadEvidenceReport(args, "bounded-test", MagicMock(), None)
    value.replay_completion["target"] = 360
    value.boundary_capture = MagicMock()
    value.boundary_capture.request.return_value = True
    monkeypatch.setattr(gate._LoadEvidenceReport, "_diagnostic_arguments", lambda *a: {})
    return value


class Clock:
    now = 0.0

    def sleep(self, seconds):
        self.now += seconds


def wait(monkeypatch, callback=None, *, completed_at=213, changes=None):
    clock = Clock()
    monkeypatch.setattr(support.time, "time", lambda: clock.now)
    monkeypatch.setattr(support.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        support,
        "transaction_processing_operation_observation",
        lambda **k: observation(360 if clock.now >= completed_at else 200, **(changes or {})),
    )
    result = support.wait_for_transaction_processing_operation_count(
        transaction_processing_base_url="http://unused",
        stage="transaction",
        outcome="processed",
        expected_minimum=360,
        timeout_seconds=240,
        baseline=observation(),
        on_pending_observation=callback,
    )
    return result, clock.now


def test_finite_late_completion_keeps_first_active_boundary_and_original_elapsed(
    report, monkeypatch
):
    capture = MagicMock()
    start = MagicMock(return_value=capture)
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", start)
    assert wait(monkeypatch, report.replay_pending) == (213, 213)
    boundary = report.replay_completion["slo_boundary_capture"]
    assert boundary["observed_elapsed_seconds"] == 180
    assert boundary["observation"]["count"] == 200
    assert boundary["late_request_seconds"] == 0
    start.assert_not_called()
    report.boundary_capture.request.assert_called_once()
    report.replay_timeout()
    assert report.replay_completion["slo_boundary_capture"] is boundary
    assert "diagnostics" not in report.replay_completion


@pytest.mark.parametrize("completed_at", [179, 180, 181])
def test_target_observed_at_or_after_boundary_never_captures_drained_state(
    report, monkeypatch, completed_at
):
    start = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", start)
    assert wait(monkeypatch, report.replay_pending, completed_at=completed_at)[0] == completed_at
    start.assert_not_called()
    assert report.boundary_capture.request.call_count == (1 if completed_at == 181 else 0)
    if report.boundary_capture.request.called:
        assert report.replay_completion["slo_boundary_capture"]["observation"]["count"] == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "missing"},
        {"producer_birth": "MISSING"},
        {"producer_birth": 12},
        {"counter_created_at": 12},
        {"labels": {"stage": "other", "outcome": "processed"}},
    ],
)
def test_unqualified_continuity_never_launches_capture(report, monkeypatch, changes):
    start = MagicMock()
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", start)
    assert wait(monkeypatch, report.replay_pending, changes=changes) == (None, 240)
    start.assert_not_called()
    report.boundary_capture.request.assert_not_called()


def test_callback_failure_preserves_completion_and_original_timeout(monkeypatch):
    def fail(*a):
        raise RuntimeError("private database endpoint")

    assert wait(monkeypatch, fail) == (213, 213)
    assert wait(monkeypatch, fail, completed_at=300) == (None, 240)


def test_late_request_projection_once_and_unavailable_metadata(report, monkeypatch):
    report.boundary_capture.request.side_effect = OSError("secret connection string")
    start = MagicMock()
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", start)
    report.replay_pending(observation(payload="private", counter_created_at="secret"), 179.9996)
    start.assert_not_called()
    report.replay_pending(observation(payload="private", counter_created_at="secret"), 187.25)
    report.replay_pending(observation(), 200)
    boundary = report.replay_completion["slo_boundary_capture"]
    assert boundary["late_request_seconds"] == 7.25
    assert boundary["reason"] == "OSError"
    assert boundary["observation"]["counter_created_at"] == "MISSING"
    assert "private" not in json.dumps(boundary) and "secret" not in json.dumps(boundary)
    start.assert_not_called()
    report.boundary_capture.request.assert_called_once()


@pytest.mark.parametrize("elapsed", [float("nan"), float("inf"), -1])
def test_nonfinite_or_negative_elapsed_cannot_request_capture(report, monkeypatch, elapsed):
    start = MagicMock()
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", start)
    report.replay_pending(observation(), elapsed)
    start.assert_not_called()


def test_report_preserves_original_exception_when_finalization_fails(report, monkeypatch):
    report.replay_completion["slo_boundary_capture"] = {}
    report.boundary_capture = MagicMock()
    report.boundary_capture.finish.side_effect = OSError("private")
    written = []
    monkeypatch.setattr(gate, "_write_report", lambda **kwargs: written.append(kwargs))
    with pytest.raises(RuntimeError, match="original enforcing failure"):
        with report:
            raise RuntimeError("original enforcing failure")
    evidence = written[0]["evidence"]
    assert evidence["failure_type"] == "RuntimeError"
    diagnostic = evidence["replay_completion"]["slo_boundary_capture"]["diagnostics"]
    assert diagnostic == {
        "status": "unavailable",
        "reason": "OSError",
        "child_cleanup": {"status": "unconfirmed"},
    }


def hold_pipe(sender):
    """Retain the actual child-side pipe while simulating a blocked probe."""
    try:
        time.sleep(30)
    finally:
        sender.close()


def idle_test_worker(sender, request, cancel, ready, payload, idle_seconds):
    ready.set()
    try:
        if not request.wait(idle_seconds) or cancel.is_set():
            return
        if payload is None:
            hold_pipe(sender)
        else:
            sender.send_bytes(b"x" * 200000 if payload == "oversized" else payload)
    finally:
        sender.close()


class DelayedProcess:
    """Delay the caller without adding an unpickleable function to the spawned process."""

    def __init__(self, process, delay):
        self.process, self.delay = process, delay

    def start(self):
        time.sleep(self.delay)
        self.process.start()

    def __getattr__(self, name):
        return getattr(self.process, name)


def actual_capture(
    *,
    payload=None,
    budget=2,
    max_bytes=32768,
    stop=None,
    request=True,
    idle_seconds=10,
    start_delay=0,
    preparation_budget=6,
    scope_slot=None,
):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    request_event, cancel_event, ready_event = (context.Event() for _ in range(3))
    process = context.Process(
        target=idle_test_worker,
        args=(sender, request_event, cancel_event, ready_event, payload, idle_seconds),
        daemon=True,
    )
    process = DelayedProcess(process, start_delay)
    capture = DiagnosticCapture(
        process=process,
        receiver=receiver,
        sender=sender,
        public_scope={"stage": "replay_storm"},
        stop_process=stop or collector._stop_diagnostic_process,
        budget_seconds=budget,
        max_bytes=max_bytes,
        request_event=request_event,
        cancel_event=cancel_event,
        ready_event=ready_event,
        idle_seconds=idle_seconds,
        preparation_budget_seconds=preparation_budget,
        scope_slot=scope_slot,
    )
    if request:
        capture.request()
    return capture


def assert_custody_closed(capture):
    result = capture.finish()
    assert result["child_cleanup"]["status"] in {"stopped", "not_started"}
    assert result["custody_threads_cleanup"] == "stopped"
    assert capture.reader is None or not capture.reader.is_alive()
    assert capture.timer is None or not capture.timer.is_alive()
    assert capture.receiver.closed and capture.sender.closed
    assert capture.finish() is result
    return result


def test_actual_pipe_backpressure_received_before_late_finish():
    payload = json.dumps({"status": "observed", "probes": {"padding": "x" * 24000}}).encode()
    capture = actual_capture(payload=payload)
    assert capture.done.wait(2)
    # No finish() call was needed to drain a frame larger than a Windows pipe buffer.
    result = assert_custody_closed(capture)
    assert result["status"] == "observed"
    assert result["probes"]["padding"] == "x" * 24000
    assert result["capture_timing"]["child_custody_seconds"] < 2


def test_delayed_actual_spawn_is_preparation_only_and_request_keeps_polling(report, monkeypatch):
    payload = json.dumps({"status": "observed"}).encode()
    before = time.monotonic()
    capture = actual_capture(payload=payload, request=False, start_delay=0.3)
    assert time.monotonic() - before >= 0.3
    assert capture.preparation_status == "ready", capture.finish()
    assert capture.started is None and not capture.done.is_set()
    report.boundary_capture = capture
    # The waiter starts AFTER preparation; no spawn, receipt wait or join on this path.
    monkeypatch.setattr(capture.process, "start", lambda: pytest.fail("second startup"))
    assert wait(monkeypatch, report.replay_pending) == (213, 213)
    assert capture.done.wait(3)
    result = assert_custody_closed(capture)
    timing = result["capture_timing"]
    assert timing["preparation_seconds"] >= 0.3
    assert timing["preparation_status"] == "ready"
    assert timing["requested_at"] is not None
    assert capture.request() is False


def test_unused_prearmed_child_retired_without_boundary_or_probes(report, monkeypatch):
    capture = actual_capture(payload=b"must_not_send", request=False)
    report.boundary_capture = capture
    assert wait(monkeypatch, report.replay_pending, completed_at=180) == (180, 180)
    assert "slo_boundary_capture" not in report.replay_completion
    result = assert_custody_closed(capture)
    assert result["status"] == "unused"
    assert result["capture_timing"]["requested_at"] is None
    assert result["capture_timing"]["child_custody_seconds"] is None


def test_late_native_start_is_retired_without_probe_or_request():
    capture = actual_capture(
        payload=b"must_not_send", request=False, preparation_budget=0.1, start_delay=0.2
    )
    result = assert_custody_closed(capture)
    assert result["reason"] == "preparation_expired"
    assert result["capture_timing"]["preparation_status"] == "expired"
    assert result["capture_timing"]["requested_at"] is None
    assert capture.request() is False


def test_idle_scope_expiry_refuses_late_request():
    capture = actual_capture(payload=b"must_not_send", request=False, idle_seconds=0.05)
    assert capture.done.wait(2)
    result = assert_custody_closed(capture)
    assert result["status"] == "idle_expired"
    assert capture.request() is False


def test_requested_capture_does_not_delay_original_timeout(report, monkeypatch):
    capture = actual_capture(request=False)
    report.boundary_capture = capture
    assert wait(monkeypatch, report.replay_pending, completed_at=300) == (None, 240)
    assert_custody_closed(capture)


@pytest.mark.parametrize("worker_name", ["_supervise", "_receive"])
def test_partial_worker_start_failure_retires_actual_idle_child_and_workers(
    monkeypatch, worker_name
):
    original_start = threading.Thread.start

    def fail_start(worker):
        if getattr(worker._target, "__name__", None) == worker_name:
            raise RuntimeError("private worker-start adapter")
        original_start(worker)

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    capture = actual_capture(payload=b"must_not_send", request=False)
    result = assert_custody_closed(capture)
    assert result["status"] == "unavailable" and result["reason"] == "RuntimeError"
    assert result["capture_timing"]["preparation_status"] == "failed"
    assert result["capture_timing"]["requested_at"] is None
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("failed", [False, True])
def test_total_setup_receipt_includes_delayed_factory_success_and_refusal(
    report, monkeypatch, failed
):
    # Delay precedes construction of a capture; its internal launch timer cannot cover this cost.
    monkeypatch.setattr(gate._LoadEvidenceReport, "_diagnostic_arguments", lambda *a: {"scope": {}})
    capture = MagicMock()
    capture.preparation_status = "ready"
    capture.finish.return_value = {"status": "unused", "capture_timing": {"requested_at": None}}

    def factory(**kwargs):
        time.sleep(0.05)
        if failed:
            raise OSError("private factory path")
        return capture

    monkeypatch.setattr(gate, "start_load_completion_diagnostics", factory)
    report.boundary_capture = None
    report.prepare_replay_capture([])
    setup = dict(report.replay_preparation)
    assert setup["setup_elapsed_seconds"] >= 0.05
    assert setup["status"] == ("unavailable" if failed else "ready")
    written = []
    monkeypatch.setattr(gate, "_write_report", lambda **kwargs: written.append(kwargs))
    with report:
        pass
    retained = written[0]["evidence"]["replay_diagnostic_preparation"]
    assert retained["setup_elapsed_seconds"] == setup["setup_elapsed_seconds"]
    assert "slo_boundary_capture" not in written[0]["evidence"]["replay_completion"]
    if failed:
        assert retained["reason"] == "OSError"
        assert "private" not in json.dumps(retained)
    else:
        assert retained["setup_status"] == "ready" and retained["status"] == "unused"
        assert retained["custody"]["capture_timing"]["requested_at"] is None
        capture.request.assert_not_called()


def test_idle_worker_canceled_before_ready_request_never_calls_probes(monkeypatch):
    probe = MagicMock()
    monkeypatch.setattr(collector, "_diagnostic_worker", probe)
    request, cancel, ready, sender = (MagicMock() for _ in range(4))
    request.wait.return_value = True
    cancel.is_set.return_value = True
    collector._idle_diagnostic_worker(
        sender, "private", "private", "private", {}, request, cancel, ready, 1
    )
    ready.set.assert_called_once()
    probe.assert_not_called()
    sender.close.assert_called_once()


def bound_scope(**changes):
    return {
        "run_id": "run",
        "tenant_id": "tenant",
        "portfolio_id": "portfolio",
        "stage": "replay_storm",
        "submitted_count": 2,
        "submitted_ids": ["actual-source-1", "actual-source-2"],
        "ingestion_job_ids": ["present-ack-job"],
        **changes,
    }


def scope_test_worker(sender, request, cancel, ready, descriptor, identity, expected, delay):
    """Actual spawn/attachment proof, not database or financial execution."""
    ready.set()
    try:
        if request.wait(10) and not cancel.is_set():
            time.sleep(delay)
            try:
                scope, deadline = read_diagnostic_scope(descriptor, identity)
                evidence = {
                    "status": "observed",
                    "exact_private_scope": scope == expected,
                    "parent_deadline": deadline,
                    "job_count": len(scope["ingestion_job_ids"]),
                }
            except (ValueError, OSError) as exc:
                evidence = {"status": "unavailable", "reason": type(exc).__name__}
            sender.send_bytes(json.dumps(evidence).encode())
    finally:
        sender.close()


def scope_capture(scope, *, request=True, delay=0, budget=2):
    context = multiprocessing.get_context("spawn")
    request_event, cancel, ready = (context.Event() for _ in range(3))
    slot = DiagnosticScopeSlot(bound_scope())
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=scope_test_worker,
        args=(sender, request_event, cancel, ready, slot.descriptor, bound_scope(), scope, delay),
    )
    capture = DiagnosticCapture(
        process=process,
        receiver=receiver,
        sender=sender,
        public_scope={"run_id": "run"},
        stop_process=collector._stop_diagnostic_process,
        budget_seconds=budget,
        max_bytes=32768,
        request_event=request_event,
        cancel_event=cancel,
        ready_event=ready,
        idle_seconds=10,
        scope_slot=slot,
    )
    assert capture.preparation_status == "ready"
    assert capture.bind_scope(scope)
    if request:
        assert capture.request()
    return capture, slot.descriptor


@pytest.mark.parametrize("jobs", [[], ["present-ack-job"]])
def test_actual_spawn_private_scope_after_submissions_is_exact_and_retired(jobs):
    capture, descriptor = scope_capture(bound_scope(ingestion_job_ids=jobs))
    result = assert_custody_closed(capture)
    assert result["status"] == "observed" and result["exact_private_scope"]
    assert result["parent_deadline"] == capture.started + capture.budget_seconds - 1
    assert result["job_count"] == len(jobs)
    assert result["child_cleanup"]["scope_slot"] == "retired"
    assert result["capture_timing"]["scope_binding_status"] == "bound"
    assert result["capture_timing"]["boundary_header_seconds"] >= 0
    assert all(
        value not in json.dumps(result)
        for value in [descriptor["name"], "actual-source-1", "present-ack-job", "submitted_ids"]
    )
    with pytest.raises(FileNotFoundError):
        read_diagnostic_scope(descriptor, bound_scope())


def test_actual_spawn_late_attachment_never_restarts_parent_deadline():
    capture, descriptor = scope_capture(bound_scope(), delay=0.3, budget=1.2)
    result = assert_custody_closed(capture)
    assert result["status"] == "unavailable" and result["reason"] == "ValueError"
    assert result["child_cleanup"]["scope_slot"] == "retired"


def test_actual_spawn_unused_scope_is_unlinked_without_active_record():
    capture, descriptor = scope_capture(bound_scope(), request=False)
    result = assert_custody_closed(capture)
    assert result["status"] == "unused"
    assert result["capture_timing"]["requested_at"] is None
    with pytest.raises(FileNotFoundError):
        read_diagnostic_scope(descriptor, bound_scope())


@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "other"},
        {"tenant_id": "other"},
        {"portfolio_id": "other"},
        {"stage": "other"},
        {"submitted_ids": []},
        {"submitted_ids": "MISSING"},
        {"ingestion_job_ids": "MISSING"},
        {"submitted_count": 3},
        {"submitted_ids": ["", "actual-source-2"]},
        {"extra": "x" * SCOPE_INPUT_MAX_BYTES},
    ],
)
def test_scope_slot_refuses_foreign_missing_malformed_or_oversized_input(changes):
    slot = DiagnosticScopeSlot(bound_scope())
    try:
        with pytest.raises(ValueError):
            slot.bind(bound_scope(**changes))
        assert not slot.request(time.monotonic() + 1)
    finally:
        slot.close()


@pytest.mark.parametrize(
    "corruption", ["version", "length", "truncated", "expired", "identity", "descriptor"]
)
def test_scope_attachment_refuses_invalid_header_payload_or_fixed_identity(corruption):
    slot = DiagnosticScopeSlot(bound_scope())
    try:
        slot.bind(bound_scope())
        slot.request(time.monotonic() + 2)
        identity, descriptor = bound_scope(), slot.descriptor
        if corruption == "version":
            struct.pack_into("!I", slot.mapping.buf, 0, 9)
        elif corruption == "length":
            struct.pack_into("!I", slot.mapping.buf, 4, SCOPE_INPUT_MAX_BYTES + 1)
        elif corruption == "truncated":
            struct.pack_into("!I", slot.mapping.buf, 4, 1)
        elif corruption == "expired":
            struct.pack_into("!d", slot.mapping.buf, 8, time.monotonic() - 1)
        elif corruption == "identity":
            identity["tenant_id"] = "foreign"
        else:
            descriptor["max_bytes"] += 1
        with pytest.raises(ValueError):
            read_diagnostic_scope(descriptor, identity)
    finally:
        slot.close()


@pytest.mark.parametrize("tier,bursts,size", [("fast", 4, 15), ("full", 12, 30)])
def test_governed_replay_shape_fits_or_is_explicitly_unavailable(tier, bursts, size):
    # Actual generated IDs, repeated submissions and one present acknowledgement per burst.
    sources = gate._build_transaction_batch(
        portfolio_id=gate.GOVERNED_LOAD_PORTFOLIO_ID,
        batch_size=120,
        seed="PERF-20261008T000000Z-replay-source",
        transaction_date="2026-10-08T00:00:00Z",
        security_prefix=gate.GOVERNED_LOAD_SECURITY_PREFIX,
        sequence_offset=0,
    )
    ids = [row["transaction_id"] for row in sources[:size]] * bursts
    scope = bound_scope(
        submitted_ids=ids,
        submitted_count=len(ids),
        ingestion_job_ids=[f"job-{index}" for index in range(bursts)],
    )
    slot = DiagnosticScopeSlot(bound_scope())
    try:
        slot.bind(scope)
        assert slot.request(time.monotonic() + 2)
        assert read_diagnostic_scope(slot.descriptor, bound_scope())[0] == scope
        with pytest.raises(ValueError, match="already_bound"):
            slot.bind(scope)
    finally:
        slot.close()


def test_scope_factory_failure_retires_mapping(monkeypatch):
    slots = []

    def factory(scope):
        slot = DiagnosticScopeSlot(scope)
        slots.append(slot)
        return slot

    monkeypatch.setattr(collector, "DiagnosticScopeSlot", factory)
    monkeypatch.setattr(
        collector, "_new_diagnostic_child", MagicMock(side_effect=RuntimeError("failed"))
    )
    with pytest.raises(RuntimeError):
        collector.start_load_completion_diagnostics(
            database_url="unused",
            metrics_url="unused",
            kafka_bootstrap_servers="unused",
            scope=bound_scope(),
            isolated_runtime=True,
            idle_seconds=10,
        )
    assert slots[0].closed


@pytest.mark.parametrize("failure", ["_supervise", "_receive", "start", "idle"])
def test_partial_spawn_or_worker_failure_and_idle_expiry_retire_private_slot(monkeypatch, failure):
    slot = DiagnosticScopeSlot(bound_scope())
    descriptor = slot.descriptor
    original_start = threading.Thread.start

    def start(worker):
        if getattr(worker._target, "__name__", None) == failure:
            raise RuntimeError("private worker adapter")
        original_start(worker)

    monkeypatch.setattr(threading.Thread, "start", start)
    if failure == "start":
        monkeypatch.setattr(DelayedProcess, "start", MagicMock(side_effect=RuntimeError("private")))
    capture = actual_capture(
        request=False, scope_slot=slot, idle_seconds=0.05 if failure == "idle" else 10
    )
    if failure == "idle":
        assert capture.done.wait(2)
    result = assert_custody_closed(capture)
    assert result["child_cleanup"]["scope_slot"] == "retired"
    assert not capture.bind_scope(bound_scope()) and not capture.request()
    with pytest.raises(FileNotFoundError):
        read_diagnostic_scope(descriptor, bound_scope())


def test_request_header_is_constant_work_without_json_serialization_or_ack_wait(monkeypatch):
    slot = DiagnosticScopeSlot(bound_scope())
    capture = actual_capture(request=False, scope_slot=slot)
    try:
        assert not capture.request()  # Unbound is unavailable, not authority for empty-ID probes.
        assert capture.bind_scope(bound_scope())
        with monkeypatch.context() as patched:
            patched.setattr(
                json, "dumps", MagicMock(side_effect=AssertionError("serialization at poll"))
            )
            assert capture.request()
            assert not capture.request()
        assert_custody_closed(capture)
    finally:
        capture.finish()


def test_expired_parent_request_never_calls_any_probe(monkeypatch):
    probes = [
        "_load_managed_worker_identity",
        "_load_database_diagnostics",
        "_load_consumer_metrics",
        "_load_processing_phases",
        "_load_consumer_offsets",
    ]
    for name in probes:
        monkeypatch.setattr(collector, name, MagicMock(side_effect=AssertionError("late probe")))
    sender = MagicMock()
    collector._diagnostic_worker(
        sender, "unused", "unused", "unused", bound_scope(), request_deadline=time.monotonic() - 1
    )
    result = json.loads(sender.send_bytes.call_args.args[0])
    assert all(value["status"] == "budget_exhausted" for value in result["probes"].values())


@pytest.mark.parametrize("timeout", [20, 31])
def test_health_nominal_allowance_tracks_same_configured_requests_without_changing_wait(
    report, monkeypatch, timeout
):
    monkeypatch.setattr(gate, "HEALTH_REQUEST_TIMEOUT_SECONDS", timeout)
    monkeypatch.setattr(gate._LoadEvidenceReport, "_diagnostic_arguments", lambda *a: {"scope": {}})
    prepare = MagicMock(return_value=report.boundary_capture)
    monkeypatch.setattr(gate, "start_load_completion_diagnostics", prepare)
    profiles = [{"batches": 2, "sleep_seconds": 1}, {"batches": 3, "sleep_seconds": 2}]
    report.prepare_replay_capture(profiles)
    assert (
        prepare.call_args.kwargs["idle_seconds"]
        == 4 * 240 + 30 * (12 + 1 + 5) + 8 + 5 * 3 * timeout
    )
    responses = MagicMock(return_value=SimpleNamespace(status_code=200, json=lambda: {}))
    monkeypatch.setattr(gate.requests, "get", responses)
    gate._get_health_snapshot(event_replay_base_url="unused", ops_token="private")
    assert responses.call_count == gate.HEALTH_SNAPSHOT_REQUESTS
    assert all(call.kwargs["timeout"] == timeout for call in responses.call_args_list)
    assert report.args.drain_timeout_seconds == 240
    assert gate.GOVERNED_MAX_DRAIN_SECONDS["full"]["replay_storm"] == 180


def test_report_binds_only_after_ack_scope_and_keeps_missing_accepted_ids(report, monkeypatch):
    monkeypatch.undo()
    report.stage = "replay_storm"
    report.args.transaction_processing_base_url = "http://unused:8090"
    report.batches[report.stage] = [
        {"submitted_ids": ["source-a"], "accepted_ids": "MISSING", "acknowledgement": {}},
        {
            "submitted_ids": ["source-b"],
            "accepted_ids": "MISSING",
            "acknowledgement": {"job_id": "present-job"},
        },
    ]
    report.bind_replay_scope()
    scope = report.boundary_capture.bind_scope.call_args.args[0]
    assert scope["submitted_ids"] == ["source-a", "source-b"]
    assert scope["ingestion_job_ids"] == ["present-job"]
    assert all(batch["accepted_ids"] == "MISSING" for batch in report.batches[report.stage])
    report.boundary_capture.request.assert_not_called()


def test_spawn_scope_lifecycle_subprocess_emits_no_resource_tracker_warnings():
    code = (
        "from tests.unit.scripts import test_load_active_diagnostics as t; import pytest; "
        "t.test_actual_spawn_private_scope_after_submissions_is_exact_and_retired([]); "
        "t.test_actual_spawn_unused_scope_is_unlinked_without_active_record(); "
        "t.test_actual_spawn_late_attachment_never_restarts_parent_deadline(); "
        "m=pytest.MonkeyPatch(); t.test_scope_factory_failure_retires_mapping(m); m.undo(); "
        "m=pytest.MonkeyPatch(); "
        "t.test_partial_spawn_or_worker_failure_and_idle_expiry_retire_private_slot"
        "(m, '_receive'); "
        "m.undo()"
    )
    result = subprocess.run(
        [sys.executable, "-Werror", "-c", code],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr, result.stderr


def test_actual_blocked_child_stopped_without_finish_at_budget():
    capture = actual_capture(budget=2)
    assert capture.done.wait(3)
    result = assert_custody_closed(capture)
    assert result["status"] == "budget_exhausted"
    assert result["capture_timing"]["child_custody_seconds"] < 2.5


def test_actual_oversized_pipe_frame_cannot_leave_live_child():
    # Generate the oversized frame after READY, not in the spawn constructor input.
    capture = actual_capture(payload="oversized")
    assert capture.preparation_status == "ready", capture.finish()
    assert capture.done.wait(1.5)
    result = assert_custody_closed(capture)
    assert result["status"] == "unavailable" and result["reason"] == "OSError"


def test_actual_cleanup_adapter_exception_does_not_escape_or_leave_child():
    def fail(process):
        raise RuntimeError("private cleanup details")

    capture = actual_capture(stop=fail)
    assert capture.done.wait(3)
    result = assert_custody_closed(capture)
    assert result["child_cleanup"]["errors"] == ["RuntimeError"]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("payload", [b"[]", b"broken json"])
def test_actual_malformed_child_receipt_refused_and_cleaned(payload):
    capture = actual_capture(payload=payload)
    assert capture.done.wait(2)
    result = assert_custody_closed(capture)
    assert result["status"] == "unavailable"
    assert result["reason"] in {"ValueError", "JSONDecodeError"}


def test_factory_construction_failure_closes_both_pipes(monkeypatch):
    sender, receiver = MagicMock(), MagicMock()
    context = MagicMock()
    context.Pipe.return_value = (receiver, sender)
    context.Process.side_effect = OSError("private")
    monkeypatch.setattr(collector.multiprocessing, "get_context", lambda *a: context)
    with pytest.raises(OSError):
        collector._new_diagnostic_child("private", "private", "private", {})
    sender.close.assert_called_once()
    receiver.close.assert_called_once()


def test_nonmanaged_async_capture_refused_before_any_io(monkeypatch):
    create = MagicMock()
    monkeypatch.setattr(collector, "_new_diagnostic_child", create)
    assert (
        collector.start_load_completion_diagnostics(
            database_url="private",
            metrics_url="private",
            kafka_bootstrap_servers="private",
            scope={},
            isolated_runtime=False,
            idle_seconds=10,
        )
        is None
    )
    create.assert_not_called()


def test_failed_process_start_closes_owners_and_exports_only_failure_type():
    process, receiver, sender = MagicMock(), MagicMock(), MagicMock()
    process.start.side_effect = PermissionError("private path and password")
    capture = DiagnosticCapture(
        process=process,
        receiver=receiver,
        sender=sender,
        public_scope={"stage": "replay_storm"},
        stop_process=lambda p: {"status": "not_started", "errors": []},
        budget_seconds=6,
        max_bytes=32768,
        request_event=MagicMock(),
        cancel_event=MagicMock(),
        ready_event=MagicMock(),
        idle_seconds=10,
    )
    result = capture.finish()
    assert result["status"] == "unavailable" and result["reason"] == "PermissionError"
    assert result["child_cleanup"]["status"] == "not_started"
    assert result["capture_timing"]["request_to_child_observation_seconds"] is None
    assert "private" not in json.dumps(result) and "password" not in json.dumps(result)
    receiver.close.assert_called_once()
    sender.close.assert_called_once()
    receiver.poll.assert_not_called()


def test_projected_output_plus_metadata_retains_byte_budget():
    payload = json.dumps({"status": "observed", "probes": {"padding": "x" * 3100}}).encode()
    capture = actual_capture(payload=payload, max_bytes=3300)
    assert capture.done.wait(2)
    result = assert_custody_closed(capture)
    assert result["status"] == "byte_budget_exhausted"
    assert len(json.dumps(result).encode()) <= 3300
    assert "probes" not in result


def bound_diagnostic_evidence(evidence, max_bytes):
    # Defer the new API import: baseline behavior tests must collect on original source.
    from scripts.operations.performance.load_diagnostic_capture import (
        bound_diagnostic_evidence as bound,
    )

    return bound(evidence, max_bytes)


def public_diagnostic_payload():
    """Supported projected shapes; no raw SQL, private metric labels or runtime I/O."""
    waits = [
        {
            "pid": 200 + n,
            "backend_start": "2026-10-08T01:15:39Z",
            "database_oid": 1,
            "backend_identity_status": "observed",
            "wait_event_type": "Lock",
            "wait_event": "transactionid",
            "blocking_pids": [100],
            "exact_await": "MISSING",
            "statement": {
                "status": "observed",
                "structure": ("select transactions where portfolio_id = ? " * 24)[:1024],
                "policy": "whitelisted_schema_and_grammar_all_other_tokens_redacted",
            },
        }
        for n in range(20)
    ]
    return {
        "status": "observed",
        "scope": {
            "run_id": "burst-run",
            "tenant_id": "tenant_performance_load",
            "portfolio_id": "PERF_BALANCED_V1",
            "stage": "burst",
            "submitted_count": 640,
            "portfolio_claim_minimum": 840,
            "phase_generation": "a" * 32,
            "phase_container_id": "b" * 64,
            "phase_container_started_at": "2026-10-08T01:15:39Z",
        },
        "observed_at": "2026-10-08T01:20:44Z",
        "probes": {
            "managed_worker": {"status": "observed", "started_at": "2026-10-08T01:15:39Z"},
            "database": {
                "exact_prefix_counts": {
                    "status": "observed",
                    "scope": "submitted_ids",
                    "row_limit": 20,
                    "truncated": False,
                    "rows": [
                        {
                            "transaction_count": 640,
                            "cost_count": 629,
                            "cashflow_count": 629,
                            "portfolio_aggregate_claims": 829,
                        }
                    ],
                },
                "runtime_db_waits": {
                    "status": "observed",
                    "scope": "isolated_runtime",
                    "row_limit": 20,
                    "truncated": True,
                    "observed_total_rows": None,
                    "rows": waits,
                },
                "runtime_db_locks": {
                    "status": "observed",
                    "scope": "isolated_runtime",
                    "row_limit": 20,
                    "observed_total_rows": 30,
                    "truncated": True,
                    "rows": [
                        {
                            "pid": 200 + n,
                            "backend_start": "2026-10-08T01:15:39Z",
                            "database_oid": 1,
                            "backend_identity_status": "observed",
                            "waiter_pid": 200 + n,
                            "waiter_backend_start": "2026-10-08T01:15:39Z",
                            "blocker_pid": 100,
                            "blocker_backend_start": "2026-10-08T01:15:38Z",
                            "locktype": "transactionid",
                            "mode": "ShareLock",
                            "granted": False,
                            "blocking_role": "waiting_edge",
                            "edge_identity_status": "observed",
                        }
                        for n in range(20)
                    ],
                },
                "consumer_rejections": {
                    "status": "unavailable",
                    "reason": "PermissionError",
                },
            },
            "ptp_metrics": {"status": "unavailable", "reason": "private_or_unknown_metric_labels"},
            "processing_phases": {
                "status": "unavailable",
                "reason": "no_birth_qualified_active_phase",
                "rows": [],
                "truncated": True,
                "row_limit": 20,
                "admission": {
                    "candidate_count": 20,
                    "admitted_count": 0,
                    "rejected_by_reason": {"backend_not_in_observed_sample": 20},
                },
            },
            "consumer_offsets": {
                "status": "partial",
                "group_joined": False,
                "groups": [{"status": "budget_exhausted"}],
                "partitions": [],
                "truncated": True,
                "row_limit": 20,
            },
        },
    }


def test_supported_oversized_capture_keeps_probes_counts_and_refusals():
    original = public_diagnostic_payload()
    before = json.dumps(original)
    assert len(before.encode()) > 32768
    result = bound_diagnostic_evidence(original, 32768 - 2048)
    assert len(json.dumps(result).encode()) <= 32768 - 2048
    assert json.dumps(original) == before  # Do not mutate the retained original snapshot.
    assert result["scope"] == original["scope"]
    assert result["observed_at"] == original["observed_at"]
    assert result["probes"].keys() == original["probes"].keys()
    for name in ("ptp_metrics", "processing_phases", "consumer_offsets"):
        assert result["probes"][name] == original["probes"][name]
    database = result["probes"]["database"]
    assert database["exact_prefix_counts"] == original["probes"]["database"]["exact_prefix_counts"]
    assert database["consumer_rejections"]["reason"] == "PermissionError"
    row = database["runtime_db_waits"]["rows"][0]
    assert row["pid"] == 200 and row["backend_start"] == "2026-10-08T01:15:39Z"
    assert row["exact_await"] == "MISSING" and row["statement"]["structure_truncated"]


def test_child_send_compacts_supported_capture_before_pipe_limit(monkeypatch):
    original = public_diagnostic_payload()
    for function, probe in (
        ("_load_managed_worker_identity", "managed_worker"),
        ("_load_database_diagnostics", "database"),
        ("_load_consumer_metrics", "ptp_metrics"),
        ("_load_processing_phases", "processing_phases"),
        ("_load_consumer_offsets", "consumer_offsets"),
    ):
        monkeypatch.setattr(collector, function, lambda *a, probe=probe: original["probes"][probe])
    scope = {
        **original["scope"],
        "submitted_ids": ["private-source"],
        "ingestion_job_ids": ["private-job"],
        "compose_file": "private-path",
    }
    sender = MagicMock()
    collector._diagnostic_worker(sender, "unused", "unused", "unused", scope)
    encoded = sender.send_bytes.call_args.args[0]
    assert len(encoded) <= collector.DIAGNOSTIC_MAX_BYTES - 2048
    result = json.loads(encoded)
    assert "probes" in result, "original child discarded supported probe evidence"
    assert result["scope"] == original["scope"]
    assert result["probes"]["database"]["exact_prefix_counts"]["rows"][0]["cost_count"] == 629
    assert result["probes"]["ptp_metrics"]["reason"] == "private_or_unknown_metric_labels"
    assert "private-source" not in encoded.decode() and "private-job" not in encoded.decode()
    assert "private-path" not in encoded.decode()
    sender.close.assert_called_once()


def test_parent_actual_metadata_independently_bounds_supported_capture():
    original = public_diagnostic_payload()
    # Baseline-only APIs: the red parent proof must not depend on the new compactor.
    child = public_diagnostic_payload()
    waits = child["probes"]["database"]["runtime_db_waits"]
    waits["rows"] = waits["rows"][:3]
    locks = child["probes"]["database"]["runtime_db_locks"]
    locks["rows"] = locks["rows"][:1]
    for row in waits["rows"]:
        row["statement"]["structure"] = "select ?"
    # Fill only already-supported redacted previews, each still <= the collector's
    # existing 1024-character projection limit. No unknown padding probe.
    gap = 5968 - len(json.dumps(child).encode())
    for row in child["probes"]["database"]["runtime_db_waits"]["rows"]:
        preview = row["statement"]["structure"]
        added = min(gap, 1024 - len(preview))
        row["statement"]["structure"] += (" select ?" * 128)[:added]
        gap -= added
    assert gap == 0
    encoded = json.dumps(child).encode()
    assert len(encoded) == 5968 < 6000
    capture = actual_capture(payload=encoded, max_bytes=6000, request=False)
    capture.public_scope = original["scope"]
    assert capture.request()
    assert capture.done.wait(2)
    result = assert_custody_closed(capture)
    assert "probes" in result, "original parent discarded supported probe evidence"
    raw_parent = {
        **child,
        "scope": capture.public_scope,
        "child_cleanup": result["child_cleanup"],
        "capture_timing": result["capture_timing"],
    }
    assert len(json.dumps(raw_parent).encode()) > 6000 - 128
    assert len(json.dumps(result).encode()) <= 6000
    assert result["scope"] == capture.public_scope
    assert result["child_cleanup"]["status"] == "stopped"
    assert result["capture_timing"]["budget_seconds"] == 2
    assert result["capture_timing"]["requested_at"] is not None
    assert result["capture_timing"]["child_observed_at"] == original["observed_at"]
    assert result["capture_timing"]["request_to_child_observation_seconds"] is None
    assert result["custody_threads_cleanup"] == "stopped"
    assert (
        result["probes"]["processing_phases"]["admission"]
        == original["probes"]["processing_phases"]["admission"]
    )


def test_row_reduction_records_coverage_and_unknown_refusal_controls():
    original = public_diagnostic_payload()
    rows = original["probes"]["database"]["runtime_db_waits"]["rows"]
    rows[-1].update(status="unknown_future_status", reason="unknown_future_refusal")
    rows[-1]["statement"] = {"status": "unavailable", "reason": "unknown_statement_refusal"}
    result = bound_diagnostic_evidence(original, 6000)
    assert len(json.dumps(result).encode()) <= 6000
    waits = result["probes"]["database"]["runtime_db_waits"]
    coverage = waits["byte_budget_coverage"]["rows"]
    assert waits["truncated"] is True
    assert coverage["original_rows"] == 20
    assert coverage["retained_rows"] + coverage["omitted_rows"] == 20
    assert (
        sum(row["omitted_rows_with_controls"] for row in coverage["omitted_row_controls"])
        == coverage["omitted_rows"]
    )
    assert any(
        row.get("status") == "unknown_future_status"
        and row.get("reason") == "unknown_future_refusal"
        for row in coverage["omitted_row_controls"]
    )
    assert any(
        row.get("statement", {}).get("reason") == "unknown_statement_refusal"
        for row in coverage["omitted_row_controls"]
    )
    assert waits["rows"][0]["pid"] == 200


def test_ordinary_public_payload_unchanged_and_irreducible_envelope_refused():
    original = {"status": "unavailable", "reason": "scope_identity_mismatch"}
    assert bound_diagnostic_evidence(original, 32768) is original
    oversized = public_diagnostic_payload()
    oversized["scope"]["run_id"] = "r" * 40000
    result = bound_diagnostic_evidence(oversized, 32768)
    assert result["status"] == "byte_budget_exhausted"
    assert result["reason"] == "irreducible_diagnostic_envelope"
    assert result["scope_timing_cleanup"] == "unavailable_due_to_byte_budget"
    assert "probes" not in result and "scope" not in result
    assert len(json.dumps(result).encode()) <= 32768
    with pytest.raises(ValueError, match="diagnostic_envelope_cannot_fit"):
        bound_diagnostic_evidence(oversized, 8)


def test_original_wait_identity_vector_is_safe_and_measures_existing_query_interval(monkeypatch):
    backend = {"pid": 41, "backend_start": "2026-10-08T00:00:00Z", "database_oid": 7}
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchmany.return_value = [dict(backend, private_statement="SELECT 'private-business'")]
    connection = MagicMock()
    connection.cursor.return_value = cursor
    wall = iter(range(100, 140))
    ticks = iter(range(1000, 1040))
    monkeypatch.setattr(collector.time, "time", lambda: next(wall))
    monkeypatch.setattr(collector.time, "monotonic", lambda: next(ticks))
    result = collector._load_database_probes(
        connection,
        {"portfolio_id": "PERF_BALANCED_V1", "submitted_ids": [], "ingestion_job_ids": []},
        object,
    )
    waits = result["runtime_db_waits"]
    vector = waits["original_sample"]
    assert vector["rows"][0]["backend"] == {
        "status": "observed",
        "value": {**backend, "backend_start": "2026-10-08T00:00:00+00:00"},
    }
    assert vector["rows"][0]["sample_index"] == 0
    assert vector["original_rows"] == 1 and vector["row_limit"] == 20
    assert vector["overflow"] == "unknown_beyond_sql_limit"
    assert waits["sampling_interval"]["elapsed_seconds"]["value"] == 1
    assert "private-business" not in json.dumps(vector)
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    # No extra measurement SQL: the same two no-source probes, one waits query.
    assert len(queries) == 2
    assert sum("FROM pg_stat_activity" in query and "LIMIT 20" in query for query in queries) == 1
    connection.rollback.assert_not_called()


@pytest.mark.parametrize("limit", [30720, 6500])
def test_join_details_compact_with_explicit_omissions_and_unchanged_admission(limit):
    original = public_diagnostic_payload()
    waits = original["probes"]["database"]["runtime_db_waits"]
    waits["original_sample"] = {
        "rows": [
            {"sample_index": index, "backend": phase_evidence.backend_measurement(row)}
            for index, row in enumerate(waits["rows"])
        ],
        "detail_status": "retained",
        "original_rows": 20,
        "row_limit": 20,
        "scope": "pre_compaction_identity_only_not_whole_database",
    }
    rows = [
        {
            "active": True,
            "generation": f"{index:032x}",
            "worker_pid": 5,
            "task_identity": "0xabc",
            "phase": "position",
            "backend": {
                "pid": 500 + index,
                "backend_start": "2026-10-08T01:15:39Z",
                "database_oid": 1,
            },
            "phase_started_monotonic": 10,
            "updated_monotonic": 11,
            "delivery_hash": "c" * 64,
            "repair_delivery_hash": None,
        }
        for index in range(20)
    ]
    admitted, summary = phase_evidence.processing_phase_admission(
        rows, {"run_generation": "a" * 32, "worker_pid": 5}, waits["rows"]
    )
    assert admitted == []
    original["probes"]["processing_phases"]["admission"] = summary
    before = json.dumps(original)
    result = bound_diagnostic_evidence(original, limit)
    assert json.dumps(original) == before
    assert len(json.dumps(result).encode()) <= limit
    assert "probes" in result
    admission = result["probes"]["processing_phases"]["admission"]
    assert admission["admitted_count"] == 0 and admission["active_count"] == 20
    assert admission["rejected_by_reason"] == {"backend_not_in_observed_sample": 20}
    sample = result["probes"]["database"]["runtime_db_waits"]["original_sample"]
    for owner in (admission["rejected_active"], sample):
        assert owner["original_rows"] == 20
        if coverage := owner.get("byte_budget_coverage", {}).get("rows"):
            assert coverage["omitted_rows"] + len(owner["rows"]) == 20
            assert coverage["retained_rows"] == len(owner["rows"])
            assert owner["detail_status"] == "partial_due_to_byte_budget"
    if limit == 6500:
        rejected = admission["rejected_active"]
        assert rejected["detail_status"] == "partial_due_to_byte_budget"
        controls = rejected["byte_budget_coverage"]["rows"]["omitted_row_controls"]
        assert all(record["authority"] == "not_admitted_not_causal" for record in controls)
        assert sum(record["omitted_rows_with_controls"] for record in controls) == (
            20 - len(rejected["rows"])
        )
        assert sample["detail_status"] == "partial_due_to_byte_budget"


@pytest.mark.parametrize(
    "bad", [None, True, "private-time", float("nan"), float("inf"), -1, 10**400]
)
def test_measurement_refuses_invalid_or_missing_clock_without_echoing(bad):
    result = phase_evidence.measurement(bad, phase_evidence.finite_nonnegative(bad))
    assert result == {"status": "missing" if bad is None else "invalid", "value": None}
    assert "private" not in json.dumps(result, allow_nan=False)


def test_unconfirmed_receiver_finalization_is_explicit_and_cached():
    capture = DiagnosticCapture.__new__(DiagnosticCapture)
    capture.final_result = None
    capture.result = None
    capture.public_scope = {"stage": "replay_storm"}
    capture.started = time.monotonic()
    capture.cancel_event = MagicMock()
    capture.budget_seconds = 0
    capture.cleanup_reserve = 0
    capture.done = MagicMock()
    capture.done.is_set.return_value = False
    capture._expire = MagicMock()
    capture._stop = MagicMock(return_value={"status": "unconfirmed", "errors": ["OSError"]})
    capture._join_receipt_workers = MagicMock(return_value="unconfirmed")
    result = capture.finish()
    assert result["status"] == "unavailable"
    assert result["reason"] == "receiver_cleanup_unconfirmed"
    assert result["child_cleanup"]["status"] == "unconfirmed"
    assert result["custody_threads_cleanup"] == "unconfirmed"
    assert capture.finish() is result
    capture._expire.assert_called_once()
