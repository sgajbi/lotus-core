import json
from pathlib import Path

import pytest

from scripts.institutional_completion_gate import (
    ScenarioArtifactMetadata,
    _compose_down,
    _compose_up,
    _latest_new_scenario_artifact,
    _load_scenario_metadata,
    _reconciliation_args,
    _scenario_args,
    main,
)


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


def test_scenario_and_reconciliation_args_use_governed_run_values() -> None:
    class Args:
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

    assert _scenario_args(Args) == [
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
    assert _reconciliation_args(parsed_args=Args, scenario=scenario) == [
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
    ]


def test_compose_up_starts_governed_completion_services(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(cmd: list[str], cwd: Path) -> None:
        calls.append((cmd, cwd))

    monkeypatch.setattr("scripts.institutional_completion_gate._run", _fake_run)

    repo_root = Path("/tmp/repo")
    _compose_up(repo_root=repo_root, compose_file="docker-compose.yml", build=False)

    assert calls == [
        (
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.yml",
                "up",
                "-d",
                "ingestion_service",
                "event_replay_service",
                "query_service",
                "query_control_plane_service",
                "persistence_service",
                "cost_calculator_service",
                "cashflow_calculator_service",
                "position_calculator_service",
                "pipeline_orchestrator_service",
                "position_valuation_calculator",
                "timeseries_generator_service",
                "valuation_orchestrator_service",
                "portfolio_aggregation_service",
                "financial_reconciliation_service",
            ],
            repo_root,
        )
    ]


def test_compose_down_uses_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(cmd: list[str], cwd: Path) -> None:
        calls.append((cmd, cwd))

    monkeypatch.setattr("scripts.institutional_completion_gate._run", _fake_run)

    repo_root = Path("/tmp/repo")
    _compose_down(repo_root=repo_root, compose_file="docker-compose.yml")

    assert calls == [
        (["docker", "compose", "-f", "docker-compose.yml", "down"], repo_root)
    ]


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
    ) -> None:
        calls.append((script_relative_path, args))
        if script_relative_path == "scripts/bank_day_load_scenario.py":
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

    monkeypatch.setattr(
        "scripts.institutional_completion_gate._run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "scripts.institutional_completion_gate._compose_up",
        lambda **_kwargs: calls.append(("compose_up", [])),
    )
    monkeypatch.setattr(
        "scripts.institutional_completion_gate._compose_down",
        lambda **_kwargs: calls.append(("compose_down", [])),
    )
    monkeypatch.setattr(
        "scripts.institutional_completion_gate.Path.resolve",
        lambda self: repo_root / "scripts" / "institutional_completion_gate.py",
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
    assert calls == [
        ("compose_up", []),
        (
            "scripts/bank_day_load_scenario.py",
            [
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
            ],
        ),
        (
            "scripts/bank_day_load_reconciliation_report.py",
            [
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
            ],
        ),
        ("compose_down", []),
    ]
