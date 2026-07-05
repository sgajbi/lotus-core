from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts import certify_lotus_core_app as validator


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "output_dir": tmp_path,
        "json_output": tmp_path / "evidence.json",
        "skip_static_contracts": False,
        "skip_runtime_smoke": False,
        "runtime_build": False,
        "runtime_skip_compose": False,
        "runtime_reset_volumes": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_lotus_core_validation_writes_app_wide_evidence(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    evidence = validator.run_validation(_args(tmp_path))

    assert evidence["status"] == "passed"
    assert evidence["failed"] == 0
    assert "ingestion" in evidence["runtime_surface_families"]
    assert "simulation" in evidence["runtime_surface_families"]
    assert any("docker_endpoint_smoke.py" in command for command in commands[-1])
    check_names = {check["name"] for check in evidence["checks"]}
    assert {
        "openapi_contract",
        "api_vocabulary_contract",
        "route_family_contract",
        "source_data_product_contract",
        "domain_product_contract",
        "supported_feature_truth",
        "runtime_app_surface_smoke",
    } <= check_names


def test_lotus_core_validation_fails_on_runtime_smoke_failure(tmp_path: Path, monkeypatch) -> None:
    class Completed:
        stdout = ""
        stderr = "runtime failed"

        def __init__(self, returncode: int):
            self.returncode = returncode

    calls = 0

    def fake_run(_command, **_kwargs):
        nonlocal calls
        calls += 1
        return Completed(1 if calls == 7 else 0)

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    evidence = validator.run_validation(_args(tmp_path))

    assert evidence["status"] == "failed"
    assert evidence["failed"] == 1
    assert evidence["failures"][0]["name"] == "runtime_app_surface_smoke"
    assert evidence["failures"][0]["details"]["stderr_tail"] == "runtime failed"


def test_lotus_core_validation_skip_modes_are_explicit(tmp_path: Path, monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = "supported features ok"
        stderr = ""

    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *_args, **_kwargs: Completed(),
    )

    evidence = validator.run_validation(
        _args(tmp_path, skip_static_contracts=True, skip_runtime_smoke=True)
    )

    assert evidence["status"] == "passed"
    skipped = {
        check["name"]: check["details"]["skipped"]
        for check in evidence["checks"]
        if "skipped" in check["details"]
    }
    assert skipped["openapi_contract"] is True
    assert skipped["runtime_app_surface_smoke"] is True
    supported_feature_check = next(
        check for check in evidence["checks"] if check["name"] == "supported_feature_truth"
    )
    assert supported_feature_check["details"]["command"] == [
        sys.executable,
        "scripts/supported_features_guard.py",
    ]


def test_lotus_core_validation_cli_writes_json(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        validator,
        "run_validation",
        lambda _args: {"app": "lotus-core", "status": "passed", "failed": 0},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "certify_lotus_core_app.py",
            "--skip-static-contracts",
            "--skip-runtime-smoke",
            "--json-output",
            str(output),
        ],
    )

    assert validator.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"
    assert "Wrote:" in capsys.readouterr().out
