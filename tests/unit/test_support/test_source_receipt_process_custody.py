"""Actual local process controls; no Docker, PostgreSQL or HTTP execution."""

import os
import sys

import pytest

from tests.test_support import source_receipt_process_custody as custody

pytestmark = pytest.mark.unit


def test_unsupported_os_refuses_without_process(monkeypatch):
    spawn = []
    monkeypatch.setattr(custody.os, "name", "posix")
    monkeypatch.setattr(custody.subprocess, "Popen", lambda *a, **kw: spawn.append(a))
    with pytest.raises(custody.CustodyRefused, match="WINDOWS_REQUIRED"):
        custody.run_owned([], private_input=b"", environment={}, cwd=".", timeout=1)
    assert spawn == []


def run(code, tmp_path, *, timeout=3, payload=b"", output_limit=65536):
    return custody.run_owned(
        [sys.executable, "-c", code],
        private_input=payload,
        environment=dict(os.environ),
        cwd=tmp_path,
        timeout=timeout,
        output_limit=output_limit,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows is the only supported native profile")
def test_native_success_discards_private_stdout_and_stderr(tmp_path):
    result = run(
        "import sys; print('synthetic-private-dsn'); print('private',file=sys.stderr)", tmp_path
    )
    assert result.exit_code == 0 and not result.timed_out
    assert result.output_bytes > 0 and result.descendants_retired and result.streams_drained
    assert "private" not in repr(result)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only custody")
def test_native_oversized_output_is_finite_and_drained(tmp_path):
    result = run(
        "import sys,time; sys.stdout.write('private'*10000); sys.stdout.flush(); time.sleep(20)",
        tmp_path,
        output_limit=1024,
    )
    assert result.output_limit_exceeded and result.output_bytes <= 2048
    assert result.descendants_retired and result.streams_drained


@pytest.mark.skipif(os.name != "nt", reason="Windows-only custody")
@pytest.mark.parametrize("register", [False, True])
def test_native_child_grandchild_death_retires_exact_inventory(tmp_path, register):
    child = "import time; time.sleep(20)"
    code = (
        "import subprocess,sys,time,pathlib; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        + ("pathlib.Path('registered').write_text('owned'); " if register else "")
        + "time.sleep(20)"
    )
    result = run(code, tmp_path, timeout=0.8)
    assert result.timed_out and result.descendants_retired and result.streams_drained
    assert (tmp_path / "registered").exists() is register


@pytest.mark.skipif(os.name != "nt", reason="Windows-only custody")
def test_native_partial_private_input_failure_preserves_exit(tmp_path):
    result = run(
        "import sys; data=sys.stdin.buffer.read(); sys.exit(4 if data==b'{partial' else 5)",
        tmp_path,
        payload=b"{partial",
    )
    assert result.exit_code == 4 and not result.timed_out
    assert result.descendants_retired and result.streams_drained


@pytest.mark.skipif(os.name != "nt", reason="Windows-only custody")
def test_startup_failure_refuses_and_closes_owned_job(tmp_path):
    with pytest.raises(custody.CustodyRefused, match="PROCESS_FAILED"):
        custody.run_owned(
            [str(tmp_path / "missing.exe")],
            private_input=b"",
            environment=dict(os.environ),
            cwd=tmp_path,
            timeout=1,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only suspended assignment")
def test_assignment_refusal_happens_before_child_executes(monkeypatch, tmp_path):
    def refuse(self, process):
        raise custody.CustodyRefused("SOURCE_RECEIPT_JOB_ASSIGNMENT_REFUSED")

    monkeypatch.setattr(custody.WindowsJob, "assign_and_resume", refuse)
    with pytest.raises(custody.CustodyRefused, match="ASSIGNMENT_REFUSED"):
        run("from pathlib import Path; Path('executed').touch()", tmp_path)
    assert not (tmp_path / "executed").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows-only private descriptor")
def test_private_file_descriptor_and_oversize_refusal(tmp_path):
    path = tmp_path / "private.json"
    path.write_bytes(b'{"database_url":"synthetic-only"}')
    with path.open("rb") as stream:
        assert custody.read_private(stream) == path.read_bytes()
    path.write_bytes(b"x" * 65537)
    with path.open("rb") as stream, pytest.raises(custody.CustodyRefused, match="OVERSIZE"):
        custody.read_private(stream)
