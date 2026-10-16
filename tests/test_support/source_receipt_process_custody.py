"""Windows-only custody for the pinned, cooperative source-receipt test processes."""

from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass


class CustodyRefused(RuntimeError):
    pass


def _require_launch(value):
    if not value:
        raise CustodyRefused("SOURCE_RECEIPT_LAUNCH_BINDING_REFUSED")


def _before(deadline):
    _require_launch(time.monotonic() < deadline)


def _image_fingerprint(path, deadline):
    digest, size = hashlib.sha256(), 0
    with open(path, "rb") as stream:
        while True:
            _before(deadline)
            chunk = stream.read(65536)
            if not chunk:
                break
            size += len(chunk)
            _require_launch(size <= 32 * 1024 * 1024)
            digest.update(chunk)
    _require_launch(size > 0)
    return digest.hexdigest()


def _process_identity(handle, pid, deadline):
    """Observe a held process handle; never return its image path or command line."""
    _before(deadline)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    api.GetProcessId.argtypes, api.GetProcessId.restype = [wintypes.HANDLE], wintypes.DWORD
    _require_launch(api.GetProcessId(handle) == pid)
    api.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    birth, exit_time, kernel, user = [wintypes.FILETIME() for _ in range(4)]
    _require_launch(
        api.GetProcessTimes(
            handle,
            ctypes.byref(birth),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
    )
    path, count = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
    _require_launch(api.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(count)))
    fingerprint = _image_fingerprint(path.value, deadline)
    code = wintypes.DWORD()
    _require_launch(api.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
    _before(deadline)
    return {
        "pid": pid,
        "birth_ticks": (birth.dwHighDateTime << 32) | birth.dwLowDateTime,
        "image_sha256": fingerprint,
    }


def _in_job(handle, job_handle=None):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    admitted = wintypes.BOOL()
    _require_launch(api.IsProcessInJob(handle, job_handle, ctypes.byref(admitted)))
    return bool(admitted.value)


def _observe_identity(pid, deadline, *, require_job=False, job_handle=None):
    _before(deadline)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes, api.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    handle = api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION only.
    _require_launch(handle)
    try:
        if require_job:
            _require_launch(_in_job(handle, job_handle))
        return _process_identity(handle, pid, deadline)
    finally:
        api.CloseHandle(handle)


def _identity(record):
    _require_launch(type(record) is dict and set(record) == {"pid", "birth_ticks", "image_sha256"})
    _require_launch(type(record["pid"]) is int and 0 < record["pid"] < 2**32)
    _require_launch(type(record["birth_ticks"]) is int and 0 < record["birth_ticks"] < 2**64)
    _require_launch(
        type(record["image_sha256"]) is str and re.fullmatch("[0-9a-f]{64}", record["image_sha256"])
    )
    return record


def _launch_envelope(payload, process, job, deadline):
    """Only custody can bind the newly assigned, still-suspended Popen identity."""
    _require_launch(_in_job(int(process._handle), job.handle))
    controller = _identity(_process_identity(wintypes.HANDLE(-1), os.getpid(), deadline))
    created = _identity(_process_identity(int(process._handle), process.pid, deadline))
    _require_launch(
        controller["pid"] != created["pid"] and controller["birth_ticks"] <= created["birth_ticks"]
    )
    raw = json.dumps(
        {
            "schema": "source-receipt.launch-bound-private/v1",
            "controller": controller,
            "created": created,
            "payload_b64": base64.b64encode(payload).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    _require_launch(len(raw) <= 65536)
    _before(deadline)
    return raw


def _unique_launch(pairs):
    result = {}
    for key, value in pairs:
        _require_launch(key not in result)
        result[key] = value
    return result


def _validate_launch(envelope, controller, worker, parent):
    _require_launch(
        type(envelope) is dict
        and set(envelope) == {"schema", "controller", "created", "payload_b64"}
    )
    _require_launch(envelope["schema"] == "source-receipt.launch-bound-private/v1")
    expected_controller, created = _identity(envelope["controller"]), _identity(envelope["created"])
    controller, worker, parent = (_identity(row) for row in (controller, worker, parent))
    _require_launch(
        controller == expected_controller
        and controller["pid"] != created["pid"]
        and worker["pid"] not in (controller["pid"], parent["pid"])
        and controller["birth_ticks"] <= created["birth_ticks"] <= worker["birth_ticks"]
        and worker["image_sha256"] == controller["image_sha256"]
    )
    if worker["pid"] == created["pid"]:
        _require_launch(worker == created and parent == controller)
    else:
        _require_launch(parent == created)
    _require_launch(type(envelope["payload_b64"]) is str)
    return base64.b64decode(envelope["payload_b64"], validate=True)


def source_prefix(snapshots, private_size):
    """Closed raw source framing shares the original total stdin budget."""
    _require_launch(
        type(snapshots) is tuple
        and len(snapshots) == 2
        and all(type(value) is bytes for value in snapshots)
        and bool(snapshots[0])
        and type(private_size) is int
        and private_size > 0
    )
    sizes = [len(value) for value in snapshots] + [private_size]
    _require_launch(sum(sizes) + 12 <= 65536)
    return b"".join(size.to_bytes(4, "big") for size in sizes) + b"".join(snapshots)


def _read_private_size(stream, size, deadline):
    """Finite API envelope read leaves the subsequent stop line on the same pipe."""
    import msvcrt

    _require_launch(type(size) is int and 0 < size <= 65536)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.PeekNamedPipe.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    api.PeekNamedPipe.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())
    available, raw = wintypes.DWORD(), bytearray()
    while len(raw) < size:
        _before(deadline)
        _require_launch(api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None))
        if available.value:
            chunk = os.read(stream.fileno(), min(available.value, size - len(raw)))
            _require_launch(chunk)
            raw.extend(chunk)
        else:
            time.sleep(0.01)
    return bytes(raw)


def bind_source_process(process, job, payload, snapshots, deadline):
    """Assign suspended process and check the complete wire before resume or send."""
    job.assign(process)
    envelope = _launch_envelope(payload, process, job, deadline)
    wire = source_prefix(snapshots, len(envelope)) + envelope
    _before(deadline)
    job.resume(process)
    return wire


def require_owned_api_worker(process, job, pid, deadline):
    """Accept the created interpreter or its worker only inside this exact held Job."""
    _require_launch(type(pid) is int and 0 < pid < 2**32 and bool(job.handle))
    _require_launch(type(deadline) in (int, float) and 0 < deadline - time.monotonic() <= 5)
    _before(deadline)
    _require_launch(_in_job(int(process._handle), job.handle))
    created = _identity(_process_identity(int(process._handle), process.pid, deadline))
    worker = _identity(_observe_identity(pid, deadline, require_job=True, job_handle=job.handle))
    controller = _identity(_process_identity(wintypes.HANDLE(-1), os.getpid(), deadline))
    _require_launch(
        controller["birth_ticks"] <= created["birth_ticks"] <= worker["birth_ticks"]
        and worker["image_sha256"] == controller["image_sha256"]
        and (pid != created["pid"] or worker == created)
    )
    _before(deadline)
    return worker


def read_launch_bound_private(stream, *, timeout=5, size=None):
    """Return payload only after pipe, current Job and expected launch identities qualify.

    The controller remains the authority even when the pinned interpreter introduces
    its own child. This is a cooperative owned-process contract, not a signature or
    protection from a malicious process running as the same Windows user.
    """
    require_supported_os()
    import msvcrt

    try:
        _require_launch(type(timeout) in (int, float) and 0 < timeout <= 5)
        deadline = time.monotonic() + timeout
        require_current_job()
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetFileType.argtypes, api.GetFileType.restype = [wintypes.HANDLE], wintypes.DWORD
        _require_launch(api.GetFileType(msvcrt.get_osfhandle(stream.fileno())) == 3)
        remaining = deadline - time.monotonic()
        _require_launch(remaining > 0)
        raw = (
            read_private(stream, timeout=remaining)
            if size is None
            else _read_private_size(stream, size, deadline)
        )
        envelope = json.loads(raw, object_pairs_hook=_unique_launch)
        _require_launch(
            type(envelope) is dict
            and set(envelope) == {"schema", "controller", "created", "payload_b64"}
            and envelope["schema"] == "source-receipt.launch-bound-private/v1"
        )
        expected_controller = _identity(envelope["controller"])
        _identity(envelope["created"])
        parent_pid = os.getppid()
        worker = _process_identity(wintypes.HANDLE(-1), os.getpid(), deadline)
        parent = _observe_identity(
            parent_pid, deadline, require_job=parent_pid != expected_controller["pid"]
        )
        controller = (
            parent
            if parent_pid == expected_controller["pid"]
            else _observe_identity(expected_controller["pid"], deadline)
        )
        payload = _validate_launch(envelope, controller, worker, parent)
        _require_launch(os.getppid() == parent_pid)
        _before(deadline)
        return payload
    except (OSError, ValueError, TypeError, KeyError, binascii.Error, RecursionError):
        raise CustodyRefused("SOURCE_RECEIPT_LAUNCH_BINDING_REFUSED") from None


def require_supported_os():
    if os.name != "nt":
        raise CustodyRefused("SOURCE_RECEIPT_WINDOWS_REQUIRED")


def require_current_job():
    require_supported_os()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    admitted = wintypes.BOOL()
    if (
        not api.IsProcessInJob(wintypes.HANDLE(-1), None, ctypes.byref(admitted))
        or not admitted.value
    ):
        raise CustodyRefused("SOURCE_RECEIPT_UNSUPERVISED_CHILD")


def read_private(stream, *, timeout=5):
    """Finite private stdin descriptor, accepting only a file or pipe on Windows."""
    import msvcrt

    require_supported_os()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
    api.GetFileType.argtypes, api.GetFileType.restype = [wintypes.HANDLE], wintypes.DWORD
    kind = api.GetFileType(handle)
    if kind == 1:
        raw = os.read(stream.fileno(), 65537)
    elif kind == 3:
        api.PeekNamedPipe.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        api.PeekNamedPipe.restype = wintypes.BOOL
        raw, available = bytearray(), wintypes.DWORD()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                if ctypes.get_last_error() not in (109, 232):
                    raise CustodyRefused("SOURCE_RECEIPT_PRIVATE_PIPE_FAILED")
                break
            if available.value:
                raw.extend(os.read(stream.fileno(), min(available.value, 65537 - len(raw))))
                if len(raw) > 65536:
                    break
            else:
                time.sleep(0.01)
        else:
            raise CustodyRefused("SOURCE_RECEIPT_PRIVATE_INPUT_TIMEOUT")
        raw = bytes(raw)
    else:
        raise CustodyRefused("SOURCE_RECEIPT_PRIVATE_INPUT_REQUIRED")
    if len(raw) > 65536:
        raise CustodyRefused("SOURCE_RECEIPT_PRIVATE_INPUT_OVERSIZE")
    return raw


class _Limits(ctypes.Structure):
    _fields_ = [
        ("per_process", ctypes.c_int64),
        ("per_job", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("minimum", ctypes.c_size_t),
        ("maximum", ctypes.c_size_t),
        ("active_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _Limits),
        ("io", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("times", ctypes.c_int64 * 4),
        ("faults", wintypes.DWORD),
        ("total", wintypes.DWORD),
        ("active", wintypes.DWORD),
        ("terminated", wintypes.DWORD),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("usage", wintypes.DWORD),
        ("thread_id", wintypes.DWORD),
        ("process_id", wintypes.DWORD),
        ("base_priority", wintypes.LONG),
        ("delta_priority", wintypes.LONG),
        ("flags", wintypes.DWORD),
    ]


class WindowsJob:
    def __init__(self):
        require_supported_os()
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
                wintypes.BOOL,
            ),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Thread32First": ([wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.api.CreateJobObjectW(None, None)
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.handle or not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise CustodyRefused("SOURCE_RECEIPT_JOB_UNAVAILABLE")

    def assign_and_resume(self, process):
        self.assign(process)
        self.resume(process)

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise CustodyRefused("SOURCE_RECEIPT_JOB_ASSIGNMENT_REFUSED")

    def resume(self, process):
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise CustodyRefused("SOURCE_RECEIPT_THREAD_UNAVAILABLE")
        entry = _ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        try:
            found = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.process_id == process.pid:
                    handle = self.api.OpenThread(2, False, entry.thread_id)
                    if not handle:
                        raise CustodyRefused("SOURCE_RECEIPT_THREAD_UNAVAILABLE")
                    try:
                        if self.api.ResumeThread(handle) == 0xFFFFFFFF:
                            raise CustodyRefused("SOURCE_RECEIPT_RESUME_REFUSED")
                        return
                    finally:
                        self.api.CloseHandle(handle)
                found = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            raise CustodyRefused("SOURCE_RECEIPT_THREAD_UNAVAILABLE")
        finally:
            self.api.CloseHandle(snapshot)

    def active(self):
        accounting = _Accounting()
        if not self.api.QueryInformationJobObject(
            self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
        ):
            raise CustodyRefused("SOURCE_RECEIPT_CUSTODY_UNKNOWN")
        return accounting.active

    def retire(self):
        if not self.api.TerminateJobObject(self.handle, 124):
            raise CustodyRefused("SOURCE_RECEIPT_RETIREMENT_REFUSED")
        deadline = time.monotonic() + 5
        while self.active() and time.monotonic() < deadline:
            time.sleep(0.02)
        return self.active() == 0

    def close(self):
        if getattr(self, "handle", None):
            self.api.CloseHandle(self.handle)
            self.handle = None


@dataclass(frozen=True)
class ProcessReceipt:
    exit_code: int
    timed_out: bool
    output_limit_exceeded: bool
    output_bytes: int
    descendants_retired: bool
    streams_drained: bool
    pid: int


def run_owned(
    command,
    *,
    private_input,
    environment,
    cwd,
    timeout,
    output_limit=65536,
    stdout_capture=None,
    bind_launch=False,
    source_snapshots=None,
):
    """Discard all child text; return only finite, credential-free lifecycle facts."""
    require_supported_os()
    if not 0 < timeout <= 600 or not 1 <= output_limit <= 65536 or len(private_input) > 65536:
        raise CustodyRefused("SOURCE_RECEIPT_PROCESS_BOUNDS_INVALID")
    _require_launch(type(bind_launch) is bool and (not bind_launch or type(private_input) is bytes))
    _require_launch(source_snapshots is None or bind_launch)
    job, process, threads = WindowsJob(), None, []
    size, oversized = [0], threading.Event()
    retired_output = threading.Event()
    drain_failed = threading.Event()
    output_lock = threading.Lock()
    timed_out = False
    deadline = time.monotonic() + timeout

    def drain(stream):
        import msvcrt

        available = wintypes.DWORD()
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.PeekNamedPipe.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        api.PeekNamedPipe.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(stream.fileno())
        while True:
            if not api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                if ctypes.get_last_error() not in (109, 232):
                    drain_failed.set()
                return
            if available.value:
                chunk = os.read(stream.fileno(), min(4096, available.value))
                with output_lock:
                    if stdout_capture is not None and stream is process.stdout:
                        stdout_capture.extend(chunk[: max(0, output_limit - len(stdout_capture))])
                    size[0] = min(2 * output_limit, size[0] + len(chunk))
                    if size[0] > output_limit:
                        oversized.set()
            elif retired_output.is_set():
                return  # Job active count is zero; no owned producer can write again.
            else:
                time.sleep(0.01)

    def send():
        try:
            process.stdin.write(private_input)
            process.stdin.flush()
        except (OSError, ValueError):
            pass
        finally:
            process.stdin.close()

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x4 | 0x08000000,  # suspended, no console
        )
        if bind_launch:
            if source_snapshots is not None:
                private_input = bind_source_process(
                    process, job, private_input, source_snapshots, deadline
                )
            else:
                job.assign(process)
                private_input = _launch_envelope(private_input, process, job, deadline)
                _before(deadline)
                job.resume(process)
        else:
            job.assign_and_resume(process)
        threads = [
            threading.Thread(target=drain, args=(stream,), daemon=True)
            for stream in (process.stdout, process.stderr)
        ]
        threads.append(threading.Thread(target=send, daemon=True))
        for thread in threads:
            thread.start()
        while process.poll() is None and not oversized.is_set():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)
        retired = job.retire()  # Also retires descendants after ordinary parent exit.
        process.wait(timeout=5)
        if retired:
            retired_output.set()
        for thread in threads:
            thread.join(timeout=1)
        return ProcessReceipt(
            process.returncode,
            timed_out,
            oversized.is_set(),
            size[0],
            retired,
            all(not thread.is_alive() for thread in threads) and not drain_failed.is_set(),
            process.pid,
        )
    except (OSError, subprocess.SubprocessError):
        raise CustodyRefused("SOURCE_RECEIPT_PROCESS_FAILED") from None
    finally:
        if process is not None and process.poll() is None:
            process.kill()  # Exact owned suspended parent if assignment failed.
            process.wait(timeout=5)
        job.close()
        retired_output.set()
        for thread in threads:
            thread.join(timeout=1)
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
