"""Portable launch controls and explicit resource-free Windows capability cases."""

import base64
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_support import source_receipt_process_custody as custody

pytestmark = pytest.mark.unit
PRIVATE = b"dummy-private-bytes\x00\n"


@pytest.mark.parametrize("bad", ["empty_cli", "mutable", "extra", "private_zero", "total_cap"])
def test_source_prefix_rejects_bad_shape_and_total_budget(bad):
    snapshots, size = (b"cli", b"api"), 1
    if bad == "empty_cli":
        snapshots = (b"", b"api")
    elif bad == "mutable":
        snapshots = (bytearray(b"cli"), b"api")
    elif bad == "extra":
        snapshots = (b"cli", b"api", b"extra")
    elif bad == "private_zero":
        size = 0
    else:
        size = 65536 - 12 - 6 + 1
    with pytest.raises(custody.CustodyRefused):
        custody.source_prefix(snapshots, size)


def test_source_prefix_accepts_exact_original_total_cap():
    snapshots = (b"cli", b"api")
    private = b"x" * (65536 - 12 - 6)
    wire = custody.source_prefix(snapshots, len(private)) + private
    assert len(wire) == 65536
    assert [int.from_bytes(wire[offset : offset + 4], "big") for offset in (0, 4, 8)] == [
        3,
        3,
        len(private),
    ]
    assert wire[12:] == b"cliapi" + private


def test_combined_source_envelope_cap_refuses_before_resume(monkeypatch):
    events, sent = install_fake_owned(monkeypatch)
    with pytest.raises(custody.CustodyRefused):
        custody.run_owned(
            ["dummy"],
            private_input=PRIVATE,
            environment={},
            cwd=".",
            timeout=1,
            bind_launch=True,
            source_snapshots=(b"x" * 65530, b""),
        )
    assert "resume" not in events and "send" not in events and not sent


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows process identity envelope measurement")
@pytest.mark.parametrize("mode", ["child", "cleanup", "api"])
def test_native_complete_source_envelope_measurement(mode):
    """Measure current complete wire with real held-process identities and dummy input."""
    root = Path(__file__).resolve().parents[3]
    snapshots = (
        (root / "scripts/validation/qualify_source_receipts.py").read_bytes(),
        (root / "tests/test_support/portfolio_source_http_process.py").read_bytes()
        if mode == "api"
        else b"",
    )
    payload = b'{"database_url":"postgresql://synthetic:dummy@127.0.0.1:5432/owned"}'
    job, process = custody.WindowsJob(), None
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", "pass"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x4 | 0x08000000,
        )
        wire = custody.bind_source_process(process, job, payload, snapshots, time.monotonic() + 5)
        sizes = [int.from_bytes(wire[offset : offset + 4], "big") for offset in (0, 4, 8)]
        assert sum(sizes) + 12 == len(wire) <= 65536
        assert (
            base64.b64decode(json.loads(wire[12 + sizes[0] + sizes[1] :])["payload_b64"]) == payload
        )
        print(
            "SOURCE_WIRE="
            + json.dumps(
                dict(
                    mode=mode,
                    cli_bytes=sizes[0],
                    api_bytes=sizes[1],
                    private_envelope_bytes=sizes[2],
                    total_bytes=len(wire),
                    budget=65536,
                )
            )
        )
        process.wait(timeout=5)
        assert process.returncode == 0
    finally:
        try:
            assert job.retire()
            if process is not None:
                process.wait(timeout=5)
        finally:
            job.close()
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()


@pytest.mark.parametrize("bad", ["truncated", "oversize", "wrong_mode", "zero_private"])
def test_seed_prefix_refuses_before_bootstrap_or_private_reader(tmp_path, bad):
    from scripts.validation.qualify_source_receipts import SOURCE_SEED

    marker = tmp_path / "private-reader"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n".encode()
    pin = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    sizes = [len(source), 0, 1]
    if bad == "oversize":
        sizes[2] = 65536
    if bad == "wrong_mode":
        sizes[1] = 1
    if bad == "zero_private":
        sizes[2] = 0
    wire = b"".join(size.to_bytes(4, "big") for size in sizes) + source
    if bad == "truncated":
        wire = wire[:-1]
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", SOURCE_SEED, str(tmp_path), pin, "child"],
        input=wire,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2 and not result.stdout and not result.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual owned Windows pipe/Job contract")
@pytest.mark.parametrize("mode", ["child", "cleanup", "api", "timeout"])
def test_native_seed_pipe_binding_stop_and_timeout(tmp_path, mode):
    """Resource-free seed/custody proof; no database or financial qualification."""
    from scripts.validation.qualify_source_receipts import SOURCE_SEED

    root = Path(__file__).resolve().parents[3]
    source = (
        f"import sys,os,json\nsys.path.insert(0,{str(root)!r})\n"
        "from tests.test_support.source_receipt_process_custody import read_launch_bound_private\n"
        "def main():\n"
        " value=read_launch_bound_private(sys.stdin.buffer,size=_SOURCE_RECEIPT_PRIVATE_SIZE)\n"
        f" assert value=={PRIVATE!r}\n"
        " print('BOUND',flush=True)\n return 0\n"
        "def api_entry(snapshot,size):\n"
        " value=read_launch_bound_private(sys.stdin.buffer,size=size)\n"
        f" assert value=={PRIVATE!r}\n"
        " print(json.dumps({'pid':os.getpid(),'parent':os.getppid()}),flush=True)\n"
        " assert sys.stdin.readline()=='stop\\n'\n"
        " print('API_STOP',flush=True)\n"
    ).encode()
    pin = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        SOURCE_SEED,
        str(tmp_path),
        pin,
        "api" if mode == "api" else "child",
    ]
    snapshots = (source, b"captured-api" if mode == "api" else b"")
    if mode in ("child", "cleanup"):
        command[-1] = mode
        capture = bytearray()
        receipt = custody.run_owned(
            command,
            private_input=PRIVATE,
            environment=dict(os.environ),
            cwd=root,
            timeout=10,
            output_limit=4096,
            stdout_capture=capture,
            bind_launch=True,
            source_snapshots=snapshots,
        )
        assert receipt.exit_code == 0 and bytes(capture).strip() == b"BOUND"
        assert receipt.descendants_retired and receipt.streams_drained and not receipt.timed_out
        return
    job = custody.WindowsJob()
    process, ready_thread = None, None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x4 | 0x08000000,
        )
        started = time.monotonic()
        if mode == "api":
            wire = custody.bind_source_process(process, job, PRIVATE, snapshots, started + 5)
            assert len(wire) <= 65536
            process.stdin.write(wire)
            process.stdin.flush()
            lines = []
            ready_thread = threading.Thread(
                target=lambda: lines.append(process.stdout.readline()), daemon=True
            )
            ready_thread.start()
            ready_thread.join(timeout=5)
            assert not ready_thread.is_alive() and lines
            reported = json.loads(lines[0])
            worker = custody.require_owned_api_worker(
                process, job, reported["pid"], time.monotonic() + 5
            )
            assert worker["pid"] == reported["pid"]
            assert reported["parent"] == (
                process.pid if worker["pid"] != process.pid else os.getpid()
            )
            print(
                "API_READY="
                + json.dumps(dict(created=process.pid, worker=worker["pid"], exact_job=True))
            )
            process.stdin.write(b"stop\n")
            process.stdin.flush()
        else:
            job.assign_and_resume(process)
            process.stdin.write(b"\0")
            process.stdin.flush()  # Leave the truncated prefix pipe open deliberately.
        process.wait(timeout=9)
        assert process.returncode == (0 if mode == "api" else 2)
        if mode == "timeout":
            assert 4.5 <= time.monotonic() - started < 9
        else:
            assert process.stdout.read().strip() == b"API_STOP"
        assert not process.stderr.read()
    finally:
        try:
            assert job.retire()
            if process is not None:
                process.wait(timeout=5)
        finally:
            job.close()
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            if ready_thread is not None:
                ready_thread.join(timeout=1)
                assert not ready_thread.is_alive()


@pytest.mark.parametrize("pid", [True, None, "123", -1, 0, 2**32])
def test_api_readiness_rejects_invalid_pid_before_native_observation(monkeypatch, pid):
    observed = []
    monkeypatch.setattr(custody, "_observe_identity", lambda *args, **kwargs: observed.append(args))
    with pytest.raises(custody.CustodyRefused):
        custody.require_owned_api_worker(
            SimpleNamespace(_handle=99), SimpleNamespace(handle=77), pid, float("inf")
        )
    assert not observed


@pytest.mark.parametrize("deadline", [-1, float("inf"), float("nan"), "deadline", True])
def test_api_readiness_requires_finite_current_deadline_before_observation(monkeypatch, deadline):
    observed = []
    monkeypatch.setattr(custody, "_observe_identity", lambda *args, **kwargs: observed.append(args))
    with pytest.raises(custody.CustodyRefused):
        custody.require_owned_api_worker(
            SimpleNamespace(_handle=99), SimpleNamespace(handle=77), 123, deadline
        )
    assert not observed


@pytest.mark.skipif(os.name != "nt", reason="Exact held Windows Job membership")
def test_native_api_readiness_refuses_live_worker_in_another_owned_job():
    jobs, processes = [custody.WindowsJob(), custody.WindowsJob()], []
    try:
        for job in jobs:
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", "-c", "import time; time.sleep(10)"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=0x4 | 0x08000000,
            )
            processes.append(process)
            job.assign_and_resume(process)
        assert custody._in_job(int(processes[1]._handle), jobs[1].handle)
        with pytest.raises(custody.CustodyRefused):
            custody.require_owned_api_worker(
                processes[0], jobs[0], processes[1].pid, time.monotonic() + 5
            )
    finally:
        for job, process in zip(jobs, processes):
            try:
                assert job.retire()
                process.wait(timeout=5)
                assert not process.stdout.read() and not process.stderr.read()
            finally:
                job.close()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()


def identity(pid, birth, image="b"):
    return {"pid": pid, "birth_ticks": birth, "image_sha256": image * 64}


def frame(direct=False):
    return {
        "schema": "source-receipt.launch-bound-private/v1",
        "controller": identity(10, 100),
        "created": identity(30, 300) if direct else identity(20, 200, "a"),
        "payload_b64": base64.b64encode(PRIVATE).decode(),
    }


@pytest.mark.parametrize("direct", [False, True])
def test_exact_direct_or_created_parent_returns_original_payload(direct):
    envelope = frame(direct)
    parent = envelope["controller"] if direct else envelope["created"]
    assert (
        custody._validate_launch(envelope, identity(10, 100), identity(30, 300), parent) == PRIVATE
    )


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "extra",
        "controller_pid",
        "controller_birth",
        "controller_hash",
        "controller_extra",
        "created_pid",
        "created_birth",
        "created_hash",
        "created_is_controller",
        "created_bool_pid",
        "parent_pid",
        "parent_birth",
        "worker_hash",
        "worker_birth",
        "worker_is_controller",
        "payload_type",
    ],
)
def test_unbound_or_reused_identity_refuses(change):
    envelope = frame()
    controller, worker, parent = identity(10, 100), identity(30, 300), identity(20, 200, "a")
    if change == "schema":
        envelope["schema"] = "unknown"
    if change == "extra":
        envelope["private"] = "must-not-pass"
    if change == "controller_extra":
        envelope["controller"]["path"] = "must-not-pass"
    if change == "controller_pid":
        controller["pid"] = 11
    if change == "controller_birth":
        controller["birth_ticks"] = 101
    if change == "controller_hash":
        controller["image_sha256"] = "c" * 64
    if change == "created_pid":
        envelope["created"]["pid"] = 99
    if change == "created_birth":
        envelope["created"]["birth_ticks"] = 301
    if change == "created_hash":
        envelope["created"]["image_sha256"] = "c" * 64
    if change == "created_is_controller":
        envelope["created"] = copy.deepcopy(controller)
    if change == "created_bool_pid":
        envelope["created"]["pid"] = True
    if change == "parent_pid":
        parent["pid"] = 99
    if change == "parent_birth":
        parent["birth_ticks"] = 201
    if change == "worker_hash":
        worker["image_sha256"] = "c" * 64
    if change == "worker_birth":
        worker["birth_ticks"] = 199
    if change == "worker_is_controller":
        worker = copy.deepcopy(controller)
    if change == "payload_type":
        envelope["payload_b64"] = ["not-text"]
    with pytest.raises(custody.CustodyRefused, match="LAUNCH_BINDING_REFUSED"):
        custody._validate_launch(envelope, controller, worker, parent)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 0),
        ("pid", 2**32),
        ("birth_ticks", True),
        ("birth_ticks", 0),
        ("birth_ticks", 2**64),
        ("image_sha256", "not-a-hash"),
    ],
)
def test_identity_has_closed_native_bounds(field, value):
    record = identity(10, 100)
    record[field] = value
    with pytest.raises(custody.CustodyRefused):
        custody._identity(record)


def test_duplicate_binding_fields_refuse():
    with pytest.raises(custody.CustodyRefused):
        json.loads('{"controller":1,"controller":2}', object_pairs_hook=custody._unique_launch)


@pytest.fixture
def pipe_reader(monkeypatch):
    envelope = frame()
    monkeypatch.setattr(custody, "require_supported_os", lambda: None)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda fd: 88))
    api = SimpleNamespace(GetFileType=lambda handle: 3)
    monkeypatch.setattr(custody.ctypes, "WinDLL", lambda *a, **kw: api, raising=False)
    monkeypatch.setattr(custody, "require_current_job", lambda: None)
    monkeypatch.setattr(custody, "read_private", lambda *a, **kw: json.dumps(envelope).encode())
    monkeypatch.setattr(custody.os, "getpid", lambda: 30)
    monkeypatch.setattr(custody.os, "getppid", lambda: 20)
    monkeypatch.setattr(custody, "_process_identity", lambda *a: identity(30, 300))
    calls = []

    def observe(pid, deadline, **kwargs):
        calls.append((pid, kwargs))
        return identity(10, 100) if pid == 10 else identity(20, 200, "a")

    monkeypatch.setattr(custody, "_observe_identity", observe)
    return envelope, api, calls, SimpleNamespace(fileno=lambda: 0)


def test_reader_requires_pipe_and_expected_parent_job(pipe_reader):
    envelope, api, calls, stream = pipe_reader
    assert custody.read_launch_bound_private(stream) == PRIVATE
    assert calls == [(20, {"require_job": True}), (10, {})]


def test_subcap_nested_frame_has_closed_refusal_without_private_text(monkeypatch, pipe_reader):
    envelope, api, calls, stream = pipe_reader
    raw = b"[" * 2000 + b'"dummy-private-frame"' + b"]" * 2000
    assert len(raw) < 65536
    with pytest.raises(RecursionError):
        json.loads(raw)
    monkeypatch.setattr(custody, "read_private", lambda *a, **kw: raw)
    with pytest.raises(custody.CustodyRefused) as caught:
        custody.read_launch_bound_private(stream)
    assert str(caught.value) == "SOURCE_RECEIPT_LAUNCH_BINDING_REFUSED"
    assert "dummy-private-frame" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert calls == []


@pytest.mark.parametrize("timeout", [0, -1, 6, True, None, "5"])
def test_reader_rejects_invalid_timeout_before_input(pipe_reader, timeout):
    envelope, api, calls, stream = pipe_reader
    with pytest.raises(custody.CustodyRefused):
        custody.read_launch_bound_private(stream, timeout=timeout)
    assert calls == []


def test_unsupported_reader_refuses_before_windows_import(monkeypatch):
    monkeypatch.setattr(custody.os, "name", "posix")
    with pytest.raises(custody.CustodyRefused, match="WINDOWS_REQUIRED"):
        custody.read_launch_bound_private(None)


@pytest.mark.parametrize(
    "failure", ["file", "unknown_job", "parent_changed", "invalid_json", "bad_base64", "expired"]
)
def test_reader_refusals_are_closed_without_private_text(monkeypatch, pipe_reader, failure):
    envelope, api, calls, stream = pipe_reader
    if failure == "file":
        api.GetFileType = lambda handle: 1
    if failure == "unknown_job":

        def refuse():
            raise custody.CustodyRefused("SOURCE_RECEIPT_UNSUPERVISED_CHILD")

        monkeypatch.setattr(custody, "require_current_job", refuse)
    if failure == "parent_changed":
        parents = iter([20, 99])
        monkeypatch.setattr(custody.os, "getppid", lambda: next(parents))
    if failure == "invalid_json":
        monkeypatch.setattr(custody, "read_private", lambda *a, **kw: PRIVATE)
    if failure == "bad_base64":
        envelope["payload_b64"] = "PRIVATE!"
    if failure == "expired":
        ticks = iter([0, 6])
        monkeypatch.setattr(custody.time, "monotonic", lambda: next(ticks))
    with pytest.raises(custody.CustodyRefused) as caught:
        custody.read_launch_bound_private(stream)
    assert "PRIVATE" not in str(caught.value) and "dummy-private" not in str(caught.value)


def install_fake_owned(monkeypatch):
    events, sent = [], []

    class Pipe:
        def write(self, data):
            sent.append(data)

        def flush(self):
            pass

        def close(self):
            pass

    process = SimpleNamespace(
        pid=20, _handle=99, stdin=Pipe(), stdout=Pipe(), stderr=Pipe(), returncode=0
    )
    resumed = [False]
    process.poll = lambda: 0 if resumed[0] else None
    process.wait = lambda **kw: None
    process.kill = lambda: events.append("kill")

    class Job:
        handle = 77

        def assign(self, child):
            events.append("assign")

        def resume(self, child):
            events.append("resume")
            resumed[0] = True

        def assign_and_resume(self, child):
            events.append("raw")
            self.assign(child)
            self.resume(child)

        def retire(self):
            events.append("retire")
            return True

        def close(self):
            events.append("close")

    class Thread:
        def __init__(self, target, **kw):
            self.target = target

        def start(self):
            if self.target.__name__ == "send":
                events.append("send")
                self.target()

        def join(self, **kw):
            pass

        def is_alive(self):
            return False

    monkeypatch.setattr(custody, "require_supported_os", lambda: None)
    monkeypatch.setattr(custody, "WindowsJob", Job)
    monkeypatch.setattr(custody.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(custody.threading, "Thread", Thread)
    monkeypatch.setattr(custody.os, "getpid", lambda: 10)
    monkeypatch.setattr(
        custody, "_in_job", lambda handle, job: events.append((handle, job)) or True
    )
    monkeypatch.setattr(
        custody, "_process_identity", lambda handle, pid, deadline: identity(pid, pid * 10)
    )
    return events, sent


@pytest.mark.parametrize("bound", [False, True])
def test_owned_pipe_delivery_follows_binding_or_preserves_raw_default(monkeypatch, bound):
    events, sent = install_fake_owned(monkeypatch)
    receipt = custody.run_owned(
        ["dummy"], private_input=PRIVATE, environment={}, cwd=".", timeout=1, bind_launch=bound
    )
    assert receipt.exit_code == 0 and receipt.descendants_retired and receipt.streams_drained
    assert events[-2:] == ["retire", "close"]
    if bound:
        assert events[:4] == ["assign", (99, 77), "resume", "send"]
        assert base64.b64decode(json.loads(sent[0])["payload_b64"]) == PRIVATE
    else:
        assert events[:4] == ["raw", "assign", "resume", "send"] and sent == [PRIVATE]


@pytest.mark.parametrize(
    "failure", ["wrong_job", "final_cap", "late_binding", "invalid_mode", "mutable_payload"]
)
def test_binding_failure_never_resumes_or_delivers(monkeypatch, failure):
    events, sent = install_fake_owned(monkeypatch)
    payload, mode = PRIVATE, True
    if failure == "wrong_job":
        monkeypatch.setattr(custody, "_in_job", lambda *a: False)
    if failure == "final_cap":
        payload = b"x" * 65536
    if failure == "late_binding":
        ticks = iter([0, 2])
        monkeypatch.setattr(custody.time, "monotonic", lambda: next(ticks))
    if failure == "invalid_mode":
        mode = 1
    if failure == "mutable_payload":
        payload = bytearray(PRIVATE)
    with pytest.raises(custody.CustodyRefused):
        custody.run_owned(
            ["dummy"], private_input=payload, environment={}, cwd=".", timeout=1, bind_launch=mode
        )
    assert "resume" not in events and "send" not in events and sent == []
    if failure not in ("invalid_mode", "mutable_payload"):
        assert events[-2:] == ["kill", "close"]


@pytest.mark.parametrize("failure", [None, "times", "pid", "image", "exit"])
def test_identity_is_observed_from_exact_handle(monkeypatch, failure):
    api = SimpleNamespace()
    api.GetProcessId = lambda handle: 31 if failure == "pid" else 30

    def times(handle, birth, *rest):
        birth._obj.dwLowDateTime = 300
        return failure != "times"

    def image(handle, flags, path, count):
        path.value = "private-image-path"
        return failure != "image"

    def exit_code(handle, code):
        code._obj.value = 0 if failure == "exit" else 259
        return True

    api.GetProcessTimes, api.QueryFullProcessImageNameW, api.GetExitCodeProcess = (
        times,
        image,
        exit_code,
    )
    monkeypatch.setattr(custody.ctypes, "WinDLL", lambda *a, **kw: api, raising=False)
    monkeypatch.setattr(custody, "_image_fingerprint", lambda path, deadline: "b" * 64)
    if failure:
        with pytest.raises(custody.CustodyRefused):
            custody._process_identity(99, 30, float("inf"))
    else:
        assert custody._process_identity(99, 30, float("inf")) == identity(30, 300)


def test_image_fingerprint_is_bounded_and_expires(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **kw: io.BytesIO(b"image"))
    assert len(custody._image_fingerprint("not-output", float("inf"))) == 64
    with pytest.raises(custody.CustodyRefused):
        custody._image_fingerprint("not-output", 0)


@pytest.mark.parametrize("failure", [None, "open", "job", "identity"])
def test_parent_handle_closes_after_metadata_or_job_refusal(monkeypatch, failure):
    closed = []
    api = SimpleNamespace(
        OpenProcess=lambda *args: 0 if failure == "open" else 99,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(custody.ctypes, "WinDLL", lambda *a, **kw: api, raising=False)
    monkeypatch.setattr(custody, "_in_job", lambda handle, job_handle=None: failure != "job")

    def observe(handle, pid, deadline):
        assert handle == 99 and pid == 20
        if failure == "identity":
            raise custody.CustodyRefused("SOURCE_RECEIPT_LAUNCH_BINDING_REFUSED")
        return identity(20, 200)

    monkeypatch.setattr(custody, "_process_identity", observe)
    if failure:
        with pytest.raises(custody.CustodyRefused):
            custody._observe_identity(20, float("inf"), require_job=True)
    else:
        assert custody._observe_identity(20, float("inf"), require_job=True) == identity(20, 200)
    assert closed == ([] if failure == "open" else [99])


def test_oversized_or_empty_executable_refuses(monkeypatch):
    class Oversized:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return b"x" * size

    monkeypatch.setattr("builtins.open", lambda *a, **kw: Oversized())
    with pytest.raises(custody.CustodyRefused):
        custody._image_fingerprint("not-output", float("inf"))
    monkeypatch.setattr("builtins.open", lambda *a, **kw: io.BytesIO(b""))
    with pytest.raises(custody.CustodyRefused):
        custody._image_fingerprint("not-output", float("inf"))


@pytest.mark.parametrize("mode", ["--child", "--cleanup-child"])
@pytest.mark.parametrize("refused", [False, True])
def test_profile_caller_authenticates_before_private_json_and_dispatch(monkeypatch, mode, refused):
    from scripts.validation import qualify_source_receipts as runner

    events = []
    monkeypatch.setattr(runner, "_SOURCE_RECEIPT_VERIFIED_ENTRY", True, raising=False)
    # This mocked caller test starts after the independently tested native bootstrap.
    flags = {name: getattr(sys.flags, name) for name in dir(sys.flags) if not name.startswith("_")}
    flags.update(isolated=1, no_user_site=1, ignore_environment=1)
    monkeypatch.setattr(sys, "flags", SimpleNamespace(**flags))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(runner, "validate_environment", lambda *args: None)
    monkeypatch.setattr(runner, "read_admission", lambda *args: {})
    monkeypatch.setattr(runner, "bootstrap", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "load_runtime", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            mode,
            "--admission",
            "unused",
            "--admission-sha256",
            "a" * 64,
            "--workspace-root",
            "unused",
        ],
    )
    monkeypatch.setattr(runner, "require_supported_os", lambda: None)
    monkeypatch.setattr(runner.profile, "load_admission", lambda *args: {})
    monkeypatch.setattr(runner.profile, "validate_admission", lambda *args, **kwargs: None)

    def bound(stream, **kwargs):
        events.append("authenticated")
        if refused:
            raise custody.CustodyRefused("SOURCE_RECEIPT_LAUNCH_BINDING_REFUSED")
        return b'{"database_url":"dummy"}'

    monkeypatch.setattr(runner, "read_launch_bound_private", bound)
    monkeypatch.setattr(runner, "read_private", lambda *args: pytest.fail("raw reader reached"))
    decode = runner.json.loads

    def decoded(*args, **kwargs):
        events.append("json")
        return decode(*args, **kwargs)

    monkeypatch.setattr(runner.json, "loads", decoded)

    def dispatched(*args):
        events.append(mode)
        assert args[1] == "dummy"
        return 0

    monkeypatch.setattr(runner, "child" if mode == "--child" else "cleanup_child", dispatched)
    assert runner.main() == (2 if refused else 0)
    assert events == (["authenticated"] if refused else ["authenticated", "json", mode])


def test_profile_top_level_retains_raw_private_reader(monkeypatch):
    from scripts.validation import qualify_source_receipts as runner

    monkeypatch.setattr(runner, "read_private", lambda stream: b'{"database_url":"dummy"}')
    monkeypatch.setattr(
        runner,
        "read_launch_bound_private",
        lambda *args: pytest.fail("top-level input is not a nested launch"),
    )
    assert runner.private_input() == "dummy"


@pytest.mark.parametrize("refused", [False, True])
def test_profile_normal_and_recovery_launches_bind_with_original_bounds(
    monkeypatch, tmp_path, refused
):
    from dataclasses import dataclass

    from scripts.development import repository_python
    from scripts.validation import qualify_source_receipts as runner

    @dataclass
    class Receipt:
        exit_code: int = 0
        timed_out: bool = False
        output_limit_exceeded: bool = False
        descendants_retired: bool = True
        streams_drained: bool = True
        pid: int = 123

    admission = {
        "cases": [{"schema": "dummy", "node": "dummy"}],
        "source_sha": "a" * 40,
        "run_deadline": 150,
        "cleanup_deadline": 180,
    }
    args = SimpleNamespace(
        admission=str(tmp_path / "unused"), admission_sha256="b" * 64, workspace_root=str(tmp_path)
    )
    monkeypatch.setattr(repository_python, "repository_environment", lambda: {})
    for name in ("OperatorSourceSession", "qualify_source", "qualify_container", "qualify_parent"):
        monkeypatch.setattr(runner.profile, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(runner.profile, "instant", lambda value: value)
    monkeypatch.setattr(
        runner,
        "_active_provenance",
        SimpleNamespace(source=lambda path: b"qualified-cli", object=lambda path: "a" * 40),
    )
    monkeypatch.setattr(runner.time, "time", lambda: 100)
    calls = []

    def owned(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs["bind_launch"] is True
        assert kwargs["source_snapshots"] == (b"qualified-cli", b"")
        assert kwargs["private_input"] == b'{"database_url": "dummy"}'
        assert kwargs["cwd"] == runner.ROOT
        assert "output_limit" not in kwargs  # original default65536, never widened
        assert "LOTUS_SOURCE_RECEIPT_PARENT_PID" not in kwargs["environment"]
        run_dir = runner.Path(kwargs["environment"]["LOTUS_SOURCE_RECEIPT_RUN_DIR"])
        if "--child" in argv:
            assert kwargs["timeout"] == 30
            if refused:
                return Receipt(exit_code=2)
            (run_dir / "dummy.json").write_text(
                " "
                + json.dumps(
                    {"http_calls": 14, "processes": 4, "pids": [1, 2, 3, 4], "ports": [1, 2, 3, 4]}
                )
            )
        else:
            assert "--cleanup-child" in argv and kwargs["timeout"] == 60
            if refused:
                return Receipt(exit_code=2)
            (run_dir / "cleanup.json").write_text('[{"schema":"dummy","outcome":"absent"}]')
        return Receipt()

    monkeypatch.setattr(runner, "run_owned", owned)
    assert runner.execute(admission, "dummy", args) == (1 if refused else 0)
    assert len(calls) == 2
