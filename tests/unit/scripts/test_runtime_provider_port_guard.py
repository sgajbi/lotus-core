from pathlib import Path

from scripts.runtime_provider_port_guard import find_runtime_provider_port_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_artifacts(root: Path) -> None:
    _write(root / "docs/standards/runtime-provider-port-standard.md", "standard")
    _write(
        root / "src/libs/portfolio-common/portfolio_common/runtime_providers.py",
        "class Clock: pass\n"
        "class MonotonicTimer: pass\n"
        "class IdGenerator: pass\n"
        "class SystemClock: pass\n"
        "class SystemMonotonicTimer: pass\n"
        "class UuidIdGenerator: pass\n",
    )
    _write(
        root
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        "from portfolio_common.runtime_providers import Clock\n"
        "started = self._monotonic_timer.seconds()\n"
        "finding = self._id_generator.new_hex()\n",
    )
    _write(
        root / "src/services/query_service/app/services/core_snapshot_service.py",
        "from portfolio_common.runtime_providers import Clock, SystemClock\n"
        "generated_at = self._clock.utc_now()\n",
    )
    _write(
        root / "src/services/query_service/app/services/simulation_service.py",
        "from portfolio_common.runtime_providers import Clock, IdGenerator, "
        "SystemClock, UuidIdGenerator\n"
        "now = self._clock.utc_now()\n"
        "session_id = self._id_generator.new_id()\n",
    )


def test_runtime_provider_port_guard_accepts_required_artifacts(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)

    assert find_runtime_provider_port_findings(tmp_path) == []


def test_runtime_provider_port_guard_rejects_direct_datetime_call(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/query_service/app/services/core_snapshot_service.py",
        "from portfolio_common.runtime_providers import Clock, SystemClock\n"
        "generated_at = self._clock.utc_now()\n"
        "fallback = datetime.now(UTC)\n",
    )

    findings = find_runtime_provider_port_findings(tmp_path)

    assert any(finding.rule == "direct-runtime-capability-call" for finding in findings)


def test_runtime_provider_port_guard_rejects_direct_uuid_call(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/query_service/app/services/simulation_service.py",
        "from portfolio_common.runtime_providers import Clock, IdGenerator, "
        "SystemClock, UuidIdGenerator\n"
        "now = self._clock.utc_now()\n"
        "session_id = self._id_generator.new_id()\n"
        "fallback = uuid4()\n",
    )

    findings = find_runtime_provider_port_findings(tmp_path)

    assert any(finding.rule == "direct-runtime-capability-call" for finding in findings)


def test_runtime_provider_port_guard_rejects_missing_provider_usage(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/query_service/app/services/simulation_service.py",
        "from portfolio_common.runtime_providers import Clock, IdGenerator, "
        "SystemClock, UuidIdGenerator\n"
        "now = self._clock.utc_now()\n",
    )

    findings = find_runtime_provider_port_findings(tmp_path)

    assert any(finding.rule == "missing-runtime-provider-usage" for finding in findings)
