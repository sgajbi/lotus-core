"""Active-boundary timing and owned custody controls; no database/runtime proof."""

from __future__ import annotations

import json
import multiprocessing
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
        profile_tier="full", enforce=True, repo_root=str(tmp_path), output_dir="evidence"
    )
    value = gate._LoadEvidenceReport(args, "bounded-test", MagicMock(), None)
    value.replay_completion["target"] = 360
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
    start.assert_called_once()
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
    assert start.call_count == (1 if completed_at == 181 else 0)
    if start.called:
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


def test_callback_failure_preserves_completion_and_original_timeout(monkeypatch):
    def fail(*a):
        raise RuntimeError("private database endpoint")

    assert wait(monkeypatch, fail) == (213, 213)
    assert wait(monkeypatch, fail, completed_at=300) == (None, 240)


def test_late_request_projection_once_and_unavailable_metadata(report, monkeypatch):
    start = MagicMock(side_effect=OSError("secret connection string"))
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
    start.assert_called_once()


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


def actual_capture(*, payload=None, budget=1.5, max_bytes=32768, stop=None):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = (
        context.Process(target=hold_pipe, args=(sender,), daemon=True)
        if payload is None
        else context.Process(target=sender.send_bytes, args=(payload,), daemon=True)
    )
    capture = DiagnosticCapture(
        process=process,
        receiver=receiver,
        sender=sender,
        public_scope={"stage": "replay_storm"},
        stop_process=stop or collector._stop_diagnostic_process,
        budget_seconds=budget,
        max_bytes=max_bytes,
    )
    return capture


def assert_custody_closed(capture):
    result = capture.finish()
    assert result["child_cleanup"]["status"] == "stopped"
    assert result["custody_threads_cleanup"] == "stopped"
    assert not capture.reader.is_alive() and not capture.timer.is_alive()
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
    assert result["capture_timing"]["child_custody_seconds"] < 1.5


def test_actual_blocked_child_stopped_without_finish_at_budget():
    capture = actual_capture(budget=0.2)
    assert capture.done.wait(1)
    result = assert_custody_closed(capture)
    assert result["status"] == "budget_exhausted"
    assert result["capture_timing"]["child_custody_seconds"] < 1


def test_actual_oversized_pipe_frame_cannot_leave_live_child():
    capture = actual_capture(payload=b"x" * 200000, budget=0.5)
    assert capture.done.wait(1.5)
    result = assert_custody_closed(capture)
    assert result["status"] == "unavailable" and result["reason"] == "OSError"


def test_actual_cleanup_adapter_exception_does_not_escape_or_leave_child():
    def fail(process):
        raise RuntimeError("private cleanup details")

    capture = actual_capture(budget=0.2, stop=fail)
    assert capture.done.wait(1)
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
