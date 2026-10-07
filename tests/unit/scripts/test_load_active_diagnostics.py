"""Active-boundary timing and owned custody controls; no database/runtime proof."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.operations import performance_load_gate as gate
from scripts.operations import transaction_processing_load_support as support
from scripts.operations.performance import load_completion_diagnostics as collector
from scripts.operations.performance.load_diagnostic_capture import DiagnosticCapture


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
            sender.send_bytes(payload)
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


def test_actual_blocked_child_stopped_without_finish_at_budget():
    capture = actual_capture(budget=2)
    assert capture.done.wait(3)
    result = assert_custody_closed(capture)
    assert result["status"] == "budget_exhausted"
    assert result["capture_timing"]["child_custody_seconds"] < 2.5


def test_actual_oversized_pipe_frame_cannot_leave_live_child():
    capture = actual_capture(payload=b"x" * 200000)
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
