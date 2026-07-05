from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts import generate_documentation_evidence_pack as pack


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "output_dir": tmp_path,
        "json_output": tmp_path / "documentation-evidence-pack.json",
        "runtime_profile": "unit-docs",
        "invocation_command": "python scripts/generate_documentation_evidence_pack.py",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_documentation_evidence_pack_records_required_metadata(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(pack.subprocess, "run", fake_run)

    evidence = pack.run_documentation_evidence(_args(tmp_path))

    assert evidence["app"] == "lotus-core"
    assert evidence["evidence_scope"] == "documentation-release-evidence"
    assert evidence["runtime_profile"] == "unit-docs"
    assert evidence["status"] == "passed"
    assert evidence["failed"] == 0
    assert "README.md" in evidence["affected_documentation_surfaces"]
    assert "wiki/Supported-Features.md" in evidence["affected_documentation_surfaces"]
    assert any(
        path.endswith("api-vocabulary-inventory.json") for path in evidence["artifact_paths"]
    )
    rendered_commands = [" ".join(command) for command in commands]
    assert any("api_vocabulary_inventory.py" in command for command in rendered_commands)
    assert any("wiki_validation_guard.py" in command for command in rendered_commands)
    assert any("rfc0083_closure_guard.py" in command for command in rendered_commands)
    assert any("rfc_status_ledger_guard.py" in command for command in rendered_commands)
    check_names = {check["name"] for check in evidence["checks"]}
    assert {
        "readme_link_validation",
        "wiki_link_validation",
        "api_catalog_generation",
        "rfc_ledger_check",
        "rfc_status_ledger_check",
        "supported_features_manifest",
        "runbook_validation",
    } <= check_names


def test_documentation_evidence_pack_fails_when_command_fails(tmp_path: Path, monkeypatch) -> None:
    class Completed:
        stdout = ""
        stderr = "api failed"

        def __init__(self, returncode: int):
            self.returncode = returncode

    calls = 0

    def fake_run(command, **_kwargs):
        nonlocal calls
        calls += 1
        if command[:2] == ["git", "rev-parse"]:
            return Completed(0)
        return Completed(1 if calls == 2 else 0)

    monkeypatch.setattr(pack.subprocess, "run", fake_run)

    evidence = pack.run_documentation_evidence(_args(tmp_path))

    assert evidence["status"] == "failed"
    assert evidence["failed"] == 1
    assert evidence["failures"][0]["name"] == "api_catalog_generation"
    assert evidence["failures"][0]["details"]["stderr_tail"] == "api failed"


def test_documentation_evidence_pack_cli_writes_json(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        pack,
        "run_documentation_evidence",
        lambda _args: {"app": "lotus-core", "status": "passed", "failed": 0},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_documentation_evidence_pack.py",
            "--json-output",
            str(output),
            "--runtime-profile",
            "unit-docs",
        ],
    )

    assert pack.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"
    assert "Wrote:" in capsys.readouterr().out
