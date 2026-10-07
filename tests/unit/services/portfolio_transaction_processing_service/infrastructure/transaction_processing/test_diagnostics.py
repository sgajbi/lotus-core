"""Transient capture refuses stale ownership without changing financial outcomes."""

import asyncio
import json
import os
import stat
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_processing import (  # noqa: E501
    diagnostics as sink,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    processing_diagnostics as port,
)

TENANT = "tenant_performance_load"
PORTFOLIO = "PERF_BALANCED_V1"


@pytest.fixture
def owner(tmp_path, monkeypatch):
    enabled = tmp_path / "enabled.json"
    enabled.write_text(
        json.dumps(
            {
                "tenant_id": TENANT,
                "portfolio_id": PORTFOLIO,
                "generation": "a" * 32,
                "created_at": time.time(),
            }
        )
    )
    enabled.chmod(0o600)
    result = sink.TransientProcessingDiagnostics(enabled, tmp_path / "snapshot.json")
    if os.name != "posix":
        # Windows exercises capture lifecycle with a mocked reader, not POSIX file security.
        monkeypatch.setattr(result, "_read_configuration", lambda: enabled.read_bytes()[:1025])
    return result


async def stop_writer(owner):
    if owner.writer is not None:
        owner.writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner.writer


@pytest.mark.asyncio
async def test_active_holder_survives_long_window_and_capacity_pressure(owner):
    first = owner.capture(TENANT, PORTFOLIO, "private-first", None)
    first.row()["updated_monotonic"] -= 400
    for i in range(19):
        owner.capture(TENANT, PORTFOLIO, str(i), None)
    assert owner.capture(TENANT, PORTFOLIO, "overflow", None) is None
    assert first.row() is not None and owner.truncated and len(owner.rows) == 20
    assert "private-first" not in owner.snapshot().decode()
    await stop_writer(owner)


@pytest.mark.asyncio
async def test_completed_retention_never_displaces_active_holder(owner):
    holder = owner.capture(TENANT, PORTFOLIO, "holder", None)
    for i in range(19):
        completed = owner.capture(TENANT, PORTFOLIO, str(i), None)
        completed.close()
    fresh = owner.capture(TENANT, PORTFOLIO, "fresh", "repair-private")
    assert holder.row() is not None and fresh.row() is not None
    assert len(owner.rows) == 20 and owner.truncated
    assert len(owner.snapshot()) <= 16384
    fresh.close()
    owner.rows[fresh.key]["updated_monotonic"] -= 121
    owner.capture(TENANT, PORTFOLIO, "next", None)
    assert fresh.key not in owner.rows and holder.row() is not None
    await stop_writer(owner)


@pytest.mark.asyncio
async def test_backend_birth_task_and_generation_affinity(owner):
    capture = owner.capture(TENANT, PORTFOLIO, "private", "private-repair")
    birth = datetime.now(UTC)
    capture.backend(port.ProcessingBackendIdentity(41, birth, 7))
    assert capture.row()["backend"] == {
        "pid": 41,
        "backend_start": birth.isoformat(),
        "database_oid": 7,
    }
    original = capture.row()["phase"]

    async def child():
        capture.phase("cost")
        capture.close()

    await asyncio.create_task(child())
    assert capture.row()["phase"] == original and capture.row()["active"]
    capture.phase("cost")
    assert capture.row()["phase"] == "cost" and capture.row()["exact_await"] == "MISSING"
    owner.run_generation = "b" * 32
    capture.phase("position")
    capture.close()
    assert capture.row() is None and owner.rows[capture.key]["phase"] == "cost"
    await stop_writer(owner)


@pytest.mark.asyncio
async def test_naive_backend_birth_is_not_qualified(owner):
    capture = owner.capture(TENANT, PORTFOLIO, "tx", None)
    capture.backend(port.ProcessingBackendIdentity(4, datetime(2026, 1, 1), 1))
    assert capture.row()["backend"] is None
    await stop_writer(owner)


@pytest.mark.parametrize(
    "change",
    [
        {"created_at": float("nan")},
        {"created_at": time.time() + 100},
        {"generation": "bad"},
        {"tenant_id": "foreign"},
        {"created_at": time.time() - 3601},
    ],
)
def test_invalid_enablement_is_refused_without_writer(owner, change):
    config = json.loads(owner.enable_path.read_text())
    config.update(change)
    owner.enable_path.write_text(json.dumps(config))
    assert owner.capture(TENANT, PORTFOLIO, "tx", None) is None
    assert owner.writer is None and not owner.rows


def test_missing_enablement_is_cached_and_foreign_scope_never_reads(tmp_path, monkeypatch):
    owner = sink.TransientProcessingDiagnostics(tmp_path / "missing", tmp_path / "snapshot")
    opening = MagicMock(side_effect=FileNotFoundError)
    monkeypatch.setattr(owner, "_read_configuration", opening)
    assert owner.capture("foreign", PORTFOLIO, "tx", None) is None
    opening.assert_not_called()
    for _ in range(3):
        assert owner.capture(TENANT, PORTFOLIO, "tx", None) is None
    assert opening.call_count == 1


def test_enable_input_read_is_bounded(owner, monkeypatch):
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.read.return_value = b"x" * 1025
    monkeypatch.setattr(sink, "_private_directory_fd", lambda path: 10)
    monkeypatch.setattr(os, "open", MagicMock(return_value=11))
    monkeypatch.setattr(
        os, "fstat", lambda descriptor: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=123)
    )
    monkeypatch.setattr(os, "geteuid", lambda: 123, raising=False)
    monkeypatch.setattr(os, "O_NOFOLLOW", 131072, raising=False)
    monkeypatch.setattr(os, "fdopen", MagicMock(return_value=stream))
    closing = MagicMock()
    monkeypatch.setattr(os, "close", closing)
    monkeypatch.setattr(
        owner,
        "_read_configuration",
        sink.TransientProcessingDiagnostics._read_configuration.__get__(owner),
    )
    assert owner.capture(TENANT, PORTFOLIO, "tx", None) is None
    stream.read.assert_called_once_with(1025)
    closing.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_phases_are_memory_only_and_one_periodic_writer_survives_capture_failure(
    owner, monkeypatch
):
    writes = []

    def fail_write(encoded):
        writes.append(encoded)
        raise OSError("diagnostic disk unavailable")

    monkeypatch.setattr(owner, "write", fail_write)
    capture = owner.capture(TENANT, PORTFOLIO, "tx", None)
    writer = owner.writer
    for phase in ("cost", "position", "cashflow", "durable_commit"):
        capture.phase(phase)
    assert not writes and owner.writer is writer
    capture.close()
    await asyncio.wait_for(writer, 2)
    assert len(writes) == 1 and owner.capture_errors == 1
    assert not owner.rows[capture.key]["active"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("financial failure"), asyncio.CancelledError()])
async def test_capture_errors_preserve_business_exception_and_context_cleanup(monkeypatch, error):
    monkeypatch.setattr(port, "_callback_failures", 0)
    capture = MagicMock()
    capture.phase.side_effect = OSError("snapshot failed")
    capture.close.side_effect = OSError("cleanup failed")
    monkeypatch.setattr(port, "_factory", lambda *args: capture)
    with pytest.raises(type(error)) as raised:
        with port.diagnostic_delivery(TENANT, PORTFOLIO, "tx", None):
            port.diagnostic_phase("cost")
            raise error
    assert raised.value is error and port.current_processing_diagnostic() is None
    capture.close.assert_called_once()
    assert port.processing_diagnostic_failures() == 2


def test_factory_fault_is_counted_without_replacing_business_exception(monkeypatch):
    monkeypatch.setattr(port, "_callback_failures", 0)
    factory = MagicMock(side_effect=OSError("configuration fault"))
    monkeypatch.setattr(port, "_factory", factory)
    error = RuntimeError("original business error")
    with pytest.raises(RuntimeError) as raised:
        with port.diagnostic_delivery(TENANT, PORTFOLIO, "tx", None):
            assert port.current_processing_diagnostic() is None
            raise error
    assert raised.value is error and port.current_processing_diagnostic() is None
    assert port.processing_diagnostic_failures() == 1


def test_callback_fault_accounting_saturates_without_cardinality(monkeypatch):
    monkeypatch.setattr(port, "_callback_failures", 65534)
    for _ in range(4):
        port.record_processing_diagnostic_failure()
    assert port.processing_diagnostic_failures() == 65535


@pytest.mark.parametrize(
    "directory,mode,uid",
    [
        (True, stat.S_IFLNK | 0o700, 123),
        (True, stat.S_IFDIR | 0o755, 123),
        (True, stat.S_IFDIR | 0o700, 456),
        (False, stat.S_IFREG | 0o644, 123),
        (False, stat.S_IFLNK | 0o600, 123),
        (False, stat.S_IFDIR | 0o600, 123),
        (False, stat.S_IFREG | 0o600, 456),
    ],
)
def test_private_transport_metadata_refuses_bad_owner_mode_and_kind(directory, mode, uid):
    with pytest.raises(PermissionError):
        sink._require_private_owner(
            SimpleNamespace(st_mode=mode, st_uid=uid), directory=directory, uid=123
        )


@pytest.mark.parametrize(
    "directory,mode", [(True, stat.S_IFDIR | 0o700), (False, stat.S_IFREG | 0o600)]
)
def test_private_transport_metadata_accepts_only_valid_owner_mode_and_kind(directory, mode):
    sink._require_private_owner(
        SimpleNamespace(st_mode=mode, st_uid=123), directory=directory, uid=123
    )


@pytest.mark.parametrize("value", [None, 0, -1, True, "131072"])
def test_posix_required_flag_refuses_missing_or_invalid_capability(monkeypatch, value):
    monkeypatch.setattr(os, "O_NOFOLLOW", value, raising=False)
    with pytest.raises(OSError):
        sink._posix_flag("O_NOFOLLOW")


def test_posix_required_flag_accepts_present_capability_and_refuses_other_names(monkeypatch):
    monkeypatch.setattr(os, "O_NOFOLLOW", 131072, raising=False)
    assert sink._posix_flag("O_NOFOLLOW") == 131072
    with pytest.raises(OSError):
        sink._posix_flag("O_RDONLY")


@pytest.mark.parametrize("value", [None, -1, True, "123"])
def test_effective_owner_refuses_invalid_identity(monkeypatch, value):
    monkeypatch.setattr(os, "geteuid", lambda: value, raising=False)
    with pytest.raises(OSError):
        sink._effective_uid()


def test_effective_owner_requires_callable_and_accepts_valid_identity(monkeypatch):
    monkeypatch.setattr(os, "geteuid", None, raising=False)
    with pytest.raises(OSError):
        sink._effective_uid()
    monkeypatch.setattr(os, "geteuid", lambda: 123, raising=False)
    assert sink._effective_uid() == 123


@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX file security requires actual ownership; Windows config reader is mocked",
)
def test_native_private_transport_valid_read_and_exclusive_snapshot_replacement(owner, monkeypatch):
    assert json.loads(owner._read_configuration())["tenant_id"] == TENANT
    owner.write(b'{"observed":true}')
    assert owner.snapshot_path.read_bytes() == b'{"observed":true}'
    assert stat.S_IMODE(owner.snapshot_path.stat().st_mode) == 0o600
    assert not list(owner.snapshot_path.parent.glob(".snapshot-*"))
    reading = MagicMock(wraps=os.fdopen)
    monkeypatch.setattr(os, "fdopen", reading)
    owner.enable_path.write_bytes(b"x" * 2048)
    assert len(owner._read_configuration()) == 1025
    reading.assert_called_once()


@pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX file security is separate from Windows mocks"
)
@pytest.mark.parametrize(
    "damage",
    ["directory_mode", "enable_mode", "enable_symlink", "snapshot_symlink", "snapshot_mode"],
)
def test_native_private_transport_refuses_unsafe_files_without_following_targets(
    owner, tmp_path, damage
):
    target = tmp_path / "untouched-target"
    target.write_bytes(b"private-original")
    if damage == "directory_mode":
        tmp_path.chmod(0o755)
    elif damage == "enable_mode":
        owner.enable_path.chmod(0o644)
    elif damage == "enable_symlink":
        owner.enable_path.unlink()
        owner.enable_path.symlink_to(target)
    elif damage == "snapshot_symlink":
        owner.snapshot_path.symlink_to(target)
    else:
        owner.snapshot_path.write_bytes(b"existing")
        owner.snapshot_path.chmod(0o644)
    with pytest.raises(OSError):
        if damage.startswith("snapshot"):
            owner.write(b"replacement")
        else:
            owner._read_configuration()
    assert target.read_bytes() == b"private-original"


@pytest.mark.skipif(os.name != "posix", reason="Actual POSIX exclusive writer cleanup")
def test_native_private_writer_fault_preserves_existing_snapshot_and_removes_owned_temp(
    owner, monkeypatch
):
    owner.write(b"prior")
    original = OSError("replacement refused")
    monkeypatch.setattr(os, "replace", MagicMock(side_effect=original))
    with pytest.raises(OSError) as raised:
        owner.write(b"new")
    assert raised.value is original
    assert owner.snapshot_path.read_bytes() == b"prior"
    assert not list(owner.snapshot_path.parent.glob(".snapshot-*"))
