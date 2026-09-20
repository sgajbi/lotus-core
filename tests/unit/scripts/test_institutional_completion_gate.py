import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation.institutional_completion_gate import (
    ScenarioArtifactMetadata,
    _latest_new_scenario_artifact,
    _load_scenario_metadata,
    _reconciliation_args,
    _reported_scenario_artifact_path,
    _scenario_args,
    main,
)
from tests.test_support.runtime_env import RuntimeEndpoints


def _fake_endpoints() -> RuntimeEndpoints:
    return RuntimeEndpoints(
        profile="e2e",
        compose_project_name="institutional-test",
        host_database_url="postgresql://user:password@localhost:15000/portfolio_db",
        host_query_database_url="postgresql://user:password@localhost:15000/portfolio_db",
        kafka_bootstrap_servers="localhost:15001",
        e2e_ingestion_url="http://localhost:15002",
        e2e_query_url="http://localhost:15003",
        e2e_query_control_plane_url="http://localhost:15004",
        e2e_event_replay_url="http://localhost:15005",
        e2e_transaction_processing_url="http://localhost:15006",
        e2e_position_valuation_url="http://localhost:15007",
        e2e_portfolio_derived_state_url="http://localhost:15008",
        e2e_valuation_orchestrator_url="http://localhost:15009",
        e2e_financial_reconciliation_url="http://localhost:15010",
    )


class _FakeManagedRun:
    def __init__(self, calls: list[tuple[str, list[str]]]) -> None:
        self.calls = calls
        self.runtime = SimpleNamespace(
            values={"COMPOSE_PROJECT_NAME": "institutional-test"},
            endpoints=_fake_endpoints(),
        )

    def __enter__(self) -> "_FakeManagedRun":
        self.calls.append(("managed_start", []))
        return self

    def __exit__(self, *args: object) -> bool:
        self.calls.append(("managed_finish", []))
        return False


def test_load_scenario_metadata_reads_required_fields(tmp_path: Path) -> None:
    artifact = tmp_path / "20260419T120000Z-bank-day-load.json"
    artifact.write_text(
        json.dumps(
            {
                "run_id": "20260419T120000Z",
                "config": {
                    "trade_date": "2026-04-17",
                    "portfolio_count": 1000,
                    "transactions_per_portfolio": 100,
                },
            }
        ),
        encoding="utf-8",
    )

    metadata = _load_scenario_metadata(artifact)

    assert metadata == ScenarioArtifactMetadata(
        run_id="20260419T120000Z",
        business_date="2026-04-17",
        portfolio_count=1000,
        transactions_per_portfolio=100,
        artifact_path=artifact,
    )


def test_load_scenario_metadata_rejects_missing_required_values(tmp_path: Path) -> None:
    artifact = tmp_path / "bad-bank-day-load.json"
    artifact.write_text(json.dumps({"run_id": "", "config": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing run_id"):
        _load_scenario_metadata(artifact)


def test_latest_new_scenario_artifact_selects_latest_unseen_file(tmp_path: Path) -> None:
    known = tmp_path / "20260419T110000Z-bank-day-load.json"
    older = tmp_path / "20260419T120000Z-bank-day-load.json"
    newer = tmp_path / "20260419T130000Z-bank-day-load.json"
    for path in (known, older, newer):
        path.write_text("{}", encoding="utf-8")

    selected = _latest_new_scenario_artifact(output_dir=tmp_path, known_paths={known})

    assert selected == newer


def test_reported_scenario_artifact_path_resolves_reported_json_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    reported = _reported_scenario_artifact_path(
        stdout="\n".join(
            [
                "diagnostic output",
                "Wrote JSON report: output/task-runs/20260419T130000Z-bank-day-load.json",
            ]
        ),
        repo_root=repo_root,
    )

    assert reported == repo_root / "output" / "task-runs" / "20260419T130000Z-bank-day-load.json"


def test_scenario_and_reconciliation_args_use_governed_run_values() -> None:
    class Args:
        compose_file = "docker-compose.yml"
        portfolio_count = 1000
        transactions_per_portfolio = 100
        transaction_batch_size = 2000
        sample_size = 5
        drain_timeout_seconds = 7200
        output_dir = "output/task-runs"
        trade_date = "2026-04-17"

    scenario = ScenarioArtifactMetadata(
        run_id="20260419T120000Z",
        business_date="2026-04-17",
        portfolio_count=1000,
        transactions_per_portfolio=100,
        artifact_path=Path("output/task-runs/20260419T120000Z-bank-day-load.json"),
    )

    assert _scenario_args(Args, endpoints=_fake_endpoints())[:18] == [
        "--compose-file",
        "docker-compose.yml",
        "--compose-project-name",
        "institutional-test",
        "--portfolio-count",
        "1000",
        "--transactions-per-portfolio",
        "100",
        "--transaction-batch-size",
        "2000",
        "--sample-size",
        "5",
        "--drain-timeout-seconds",
        "7200",
        "--output-dir",
        "output/task-runs",
        "--trade-date",
        "2026-04-17",
    ]
    assert _reconciliation_args(
        parsed_args=Args, scenario=scenario, endpoints=_fake_endpoints()
    ) == [
        "--run-id",
        "20260419T120000Z",
        "--business-date",
        "2026-04-17",
        "--transactions-per-portfolio",
        "100",
        "--portfolio-limit",
        "1000",
        "--output-dir",
        "output/task-runs",
        "--query-base-url",
        _fake_endpoints().e2e_query_url,
        "--query-control-base-url",
        _fake_endpoints().e2e_query_control_plane_url,
        "--reconciliation-base-url",
        _fake_endpoints().e2e_financial_reconciliation_url,
    ]


def test_scenario_args_bind_the_allocated_compose_endpoints() -> None:
    class Args:
        compose_file = "docker-compose.yml"
        portfolio_count = 1000
        transactions_per_portfolio = 100
        transaction_batch_size = 2000
        sample_size = 5
        drain_timeout_seconds = 7200
        output_dir = "output/task-runs"
        trade_date = "2026-04-17"

    endpoints = _fake_endpoints()

    command = _scenario_args(Args, endpoints=endpoints)

    assert command[:4] == [
        "--compose-file",
        "docker-compose.yml",
        "--compose-project-name",
        endpoints.compose_project_name,
    ]
    assert "--host-database-url" not in command
    assert dict(zip(command[::2], command[1::2], strict=True)) == {
        "--compose-file": "docker-compose.yml",
        "--compose-project-name": endpoints.compose_project_name,
        "--portfolio-count": "1000",
        "--transactions-per-portfolio": "100",
        "--transaction-batch-size": "2000",
        "--sample-size": "5",
        "--drain-timeout-seconds": "7200",
        "--output-dir": "output/task-runs",
        "--trade-date": "2026-04-17",
        "--ingestion-base-url": endpoints.e2e_ingestion_url,
        "--query-base-url": endpoints.e2e_query_url,
        "--query-control-base-url": endpoints.e2e_query_control_plane_url,
        "--event-replay-base-url": endpoints.e2e_event_replay_url,
        "--reconciliation-base-url": endpoints.e2e_financial_reconciliation_url,
        "--transaction-processing-base-url": endpoints.e2e_transaction_processing_url,
        "--position-valuation-base-url": endpoints.e2e_position_valuation_url,
        "--portfolio-derived-state-base-url": endpoints.e2e_portfolio_derived_state_url,
        "--valuation-orchestrator-base-url": endpoints.e2e_valuation_orchestrator_url,
    }


def test_main_runs_scenario_then_exhaustive_reconciliation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path
    output_dir = repo_root / "output" / "task-runs"
    output_dir.mkdir(parents=True)
    calls: list[tuple[str, list[str]]] = []

    def _fake_run_python_script(
        *,
        repo_root: Path,
        script_relative_path: str,
        args: list[str],
        environment: dict[str, str] | None = None,
    ) -> str:
        assert environment == {"COMPOSE_PROJECT_NAME": "institutional-test"}
        calls.append((script_relative_path, args))
        if script_relative_path == "scripts/operations/bank_day_load_scenario.py":
            scenario_artifact = output_dir / "20260419T120000Z-bank-day-load.json"
            scenario_artifact.write_text(
                json.dumps(
                    {
                        "run_id": "20260419T120000Z",
                        "config": {
                            "trade_date": "2026-04-17",
                            "portfolio_count": 1000,
                            "transactions_per_portfolio": 100,
                        },
                    }
                ),
                encoding="utf-8",
            )
            return "Wrote JSON report: output/task-runs/20260419T120000Z-bank-day-load.json\n"
        return ""

    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate._run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.prepare_managed_compose_run",
        lambda **_kwargs: _FakeManagedRun(calls),
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.Path.resolve",
        lambda self: repo_root / "scripts" / "validation" / "institutional_completion_gate.py",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "institutional_completion_gate.py",
            "--output-dir",
            "output/task-runs",
        ],
    )

    assert main() == 0
    assert [name for name, _ in calls] == [
        "managed_start",
        "scripts/operations/bank_day_load_scenario.py",
        "scripts/operations/bank_day_load_reconciliation_report.py",
        "managed_finish",
    ]
    scenario_options = dict(zip(calls[1][1][::2], calls[1][1][1::2], strict=True))
    assert scenario_options["--compose-project-name"] == _fake_endpoints().compose_project_name
    assert scenario_options["--ingestion-base-url"] == _fake_endpoints().e2e_ingestion_url
    assert scenario_options["--valuation-orchestrator-base-url"] == (
        _fake_endpoints().e2e_valuation_orchestrator_url
    )
    assert scenario_options["--drain-timeout-seconds"] == "7200"
    assert calls[2][1] == [
        "--run-id",
        "20260419T120000Z",
        "--business-date",
        "2026-04-17",
        "--transactions-per-portfolio",
        "100",
        "--portfolio-limit",
        "1000",
        "--output-dir",
        "output/task-runs",
        "--query-base-url",
        _fake_endpoints().e2e_query_url,
        "--query-control-base-url",
        _fake_endpoints().e2e_query_control_plane_url,
        "--reconciliation-base-url",
        _fake_endpoints().e2e_financial_reconciliation_url,
    ]
    assert "--host-database-url" not in calls[2][1]


def test_main_falls_back_to_latest_new_artifact_when_stdout_has_no_report_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path
    output_dir = repo_root / "output" / "task-runs"
    output_dir.mkdir(parents=True)
    known_artifact = output_dir / "20260419T110000Z-bank-day-load.json"
    known_artifact.write_text("{}", encoding="utf-8")

    calls: list[tuple[str, list[str]]] = []

    def _fake_run_python_script(
        *,
        repo_root: Path,
        script_relative_path: str,
        args: list[str],
        environment: dict[str, str] | None = None,
    ) -> str:
        assert environment == {"COMPOSE_PROJECT_NAME": "institutional-test"}
        calls.append((script_relative_path, args))
        if script_relative_path == "scripts/operations/bank_day_load_scenario.py":
            scenario_artifact = output_dir / "20260419T120000Z-bank-day-load.json"
            scenario_artifact.write_text(
                json.dumps(
                    {
                        "run_id": "20260419T120000Z",
                        "config": {
                            "trade_date": "2026-04-17",
                            "portfolio_count": 1000,
                            "transactions_per_portfolio": 100,
                        },
                    }
                ),
                encoding="utf-8",
            )
        return ""

    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate._run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.prepare_managed_compose_run",
        lambda **_kwargs: _FakeManagedRun(calls),
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.Path.resolve",
        lambda self: repo_root / "scripts" / "validation" / "institutional_completion_gate.py",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "institutional_completion_gate.py",
            "--output-dir",
            "output/task-runs",
        ],
    )

    assert main() == 0
    assert calls[-2][0] == "scripts/operations/bank_day_load_reconciliation_report.py"


def test_main_propagates_reconciliation_failure_through_managed_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path
    output_dir = repo_root / "output" / "task-runs"
    output_dir.mkdir(parents=True)
    scenario_artifact = output_dir / "20260419T120000Z-bank-day-load.json"
    scenario_artifact.write_text(
        json.dumps(
            {
                "run_id": "20260419T120000Z",
                "config": {
                    "trade_date": "2026-04-17",
                    "portfolio_count": 1000,
                    "transactions_per_portfolio": 100,
                },
            }
        ),
        encoding="utf-8",
    )

    def _fake_run_python_script(
        *,
        repo_root: Path,
        script_relative_path: str,
        args: list[str],
        environment: dict[str, str] | None = None,
    ) -> str:
        assert environment == {"COMPOSE_PROJECT_NAME": "institutional-test"}
        if script_relative_path == "scripts/operations/bank_day_load_scenario.py":
            return "Wrote JSON report: output/task-runs/20260419T120000Z-bank-day-load.json\n"
        raise RuntimeError("reconciliation failed")

    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate._run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.prepare_managed_compose_run",
        lambda **_kwargs: _FakeManagedRun([]),
    )
    monkeypatch.setattr(
        "scripts.validation.institutional_completion_gate.Path.resolve",
        lambda self: repo_root / "scripts" / "validation" / "institutional_completion_gate.py",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "institutional_completion_gate.py",
            "--output-dir",
            "output/task-runs",
        ],
    )

    with pytest.raises(RuntimeError, match="reconciliation failed"):
        main()
