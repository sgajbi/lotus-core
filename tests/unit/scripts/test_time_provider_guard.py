from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_reconciliation_service_uses_provider_ports_for_time_and_ids() -> None:
    service_text = (
        REPO_ROOT
        / "src/services/financial_reconciliation_service/app/services/reconciliation_service.py"
    ).read_text(encoding="utf-8")

    assert "uuid4" not in service_text
    assert "perf_counter" not in service_text


def test_core_snapshot_service_keeps_system_time_behind_clock_provider() -> None:
    service_text = (
        REPO_ROOT / "src/services/query_service/app/services/core_snapshot_service.py"
    ).read_text(encoding="utf-8")
    direct_time_lines = [
        line.strip() for line in service_text.splitlines() if "datetime.now(UTC)" in line
    ]

    assert direct_time_lines == ["self._clock = clock or (lambda: datetime.now(UTC))"]
