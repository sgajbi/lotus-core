"""Finite owned diagnostic receipt and child custody, outside completion polling."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class DiagnosticCapture:
    """One bounded receiver and deadline timer; no dependency on later finalization."""

    def __init__(
        self,
        *,
        process: Any,
        receiver: Any,
        sender: Any,
        public_scope: dict[str, Any],
        stop_process: Callable[[Any], dict[str, Any]],
        budget_seconds: float,
        max_bytes: int,
    ) -> None:
        self.process, self.receiver, self.sender = process, receiver, sender
        self.public_scope, self.stop_process = public_scope, stop_process
        self.budget_seconds, self.max_bytes = budget_seconds, max_bytes
        self.requested_at = datetime.now(UTC).isoformat()
        self.started = time.monotonic()
        self.done = threading.Event()
        self.expired = threading.Event()
        self.cleanup_lock = threading.Lock()
        self.cleanup: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.final_result: dict[str, Any] | None = None
        self.reader: threading.Thread | None = None
        self.timer: threading.Timer | None = None
        # Reserve the existing two bounded cleanup joins within the six-second policy.
        self.cleanup_reserve = min(0.5, budget_seconds / 2)
        try:
            process.start()
            sender.close()
            self.launch_seconds = round(time.monotonic() - self.started, 6)
            remaining = max(0.0, budget_seconds - self.launch_seconds - self.cleanup_reserve)
            self.timer = threading.Timer(remaining, self._expire)
            self.timer.daemon = True
            self.reader = threading.Thread(target=self._receive, daemon=True)
            self.timer.start()
            self.reader.start()
        except Exception as exc:
            self.launch_seconds = round(time.monotonic() - self.started, 6)
            if self.timer is not None:
                self.timer.cancel()
            self._complete(self._unavailable(type(exc).__name__))

    def _unavailable(self, reason: str) -> dict[str, Any]:
        return {"status": "unavailable", "reason": reason, "scope": self.public_scope}

    def _stop(self) -> dict[str, Any]:
        with self.cleanup_lock:
            if self.cleanup is None:
                try:
                    self.cleanup = self.stop_process(self.process)
                except Exception as exc:
                    self.cleanup = {"status": "unconfirmed", "errors": [type(exc).__name__]}
                    try:
                        self.process.kill()
                        self.process.join(timeout=0.2)
                        if not self.process.is_alive():
                            self.cleanup["status"] = "stopped"
                            self.process.close()
                    except Exception as fallback_error:
                        self.cleanup["errors"].append(type(fallback_error).__name__)
            return self.cleanup

    def _expire(self) -> None:
        self.expired.set()
        # Killing the sole sender also releases a receiver blocked on a partial pipe frame.
        self._stop()

    def _receive(self) -> None:
        try:
            remaining = max(0.0, self.budget_seconds - (time.monotonic() - self.started))
            if self.receiver.poll(remaining):
                decoded = json.loads(self.receiver.recv_bytes(self.max_bytes))
                if not isinstance(decoded, dict):
                    raise ValueError("non_object_diagnostic")
                result = decoded
                result["scope"] = self.public_scope
            else:
                result = {"status": "budget_exhausted", "scope": self.public_scope}
        except Exception as exc:
            result = self._unavailable(type(exc).__name__)
        if self.expired.is_set():
            result = {"status": "budget_exhausted", "scope": self.public_scope}
        self._complete(result)

    def _complete(self, result: dict[str, Any]) -> None:
        if self.timer is not None:
            self.timer.cancel()
        cleanup = self._stop()
        for pipe in (self.sender, self.receiver):
            try:
                pipe.close()
            except Exception as exc:
                cleanup.setdefault("errors", []).append(type(exc).__name__)
        timing = {
            "requested_at": self.requested_at,
            "child_observed_at": result.get("observed_at"),
            "custody_completed_at": datetime.now(UTC).isoformat(),
            "launch_seconds": self.launch_seconds,
            "child_custody_seconds": round(time.monotonic() - self.started, 6),
            "budget_seconds": self.budget_seconds,
            "claim": "requested_boundary_not_exact_capture_time_or_zero_overhead",
        }
        timing["request_to_child_observation_seconds"] = None
        try:
            observed = datetime.fromisoformat(result["observed_at"])
            delay = (observed - datetime.fromisoformat(self.requested_at)).total_seconds()
            if delay >= 0:
                timing["request_to_child_observation_seconds"] = delay
        except (KeyError, TypeError, ValueError):
            pass  # Missing/invalid wall-clock capture timing is not measured zero.
        result.update(child_cleanup=cleanup, capture_timing=timing)
        if len(json.dumps(result, default=str).encode()) > self.max_bytes - 128:
            result = {
                "status": "byte_budget_exhausted",
                "scope": self.public_scope,
                "child_cleanup": cleanup,
                "capture_timing": timing,
            }
        self.result = result
        self.done.set()

    def _join_receipt_workers(self) -> str:
        """Bounded joins confirm both owned threads, without waiting on shared resources."""
        status = "stopped"
        for worker in (self.reader, self.timer):
            if worker is not None and worker.ident is not None:
                worker.join(timeout=0.2)
                if worker.is_alive():
                    status = "unconfirmed"
        return status

    def finish(self) -> dict[str, Any]:
        """Join only owned finite custody before teardown; cache the original snapshot."""
        if self.final_result is not None:
            return self.final_result
        remaining = max(0.0, self.budget_seconds - (time.monotonic() - self.started))
        self.done.wait(remaining + self.cleanup_reserve)
        if not self.done.is_set():
            self._expire()
        custody_status = self._join_receipt_workers()
        if not self.done.is_set():
            result = {
                **self._unavailable("receiver_cleanup_unconfirmed"),
                "child_cleanup": self._stop(),
                "receiver_cleanup": "unconfirmed",
            }
        else:
            result = (
                self.result if self.result is not None else self._unavailable("receipt_missing")
            )
        result["custody_threads_cleanup"] = custody_status
        self.final_result = result
        return result
