from pathlib import Path

from scripts import rfc0083_closure_guard as guard


def _ledger() -> dict[str, object]:
    return {
        "specVersion": "1.0.0",
        "application": "lotus-core",
        "governingRfcs": ["RFC-0082", "RFC-0083"],
        "closureStatus": "target-model-and-guarded-artifact-closure",
        "runtimeProductionStatus": "not-production-closed",
        "remainingRuntimeProof": ["full PR Merge Gate"],
        "slices": [
            {
                "slice": slice_number,
                "title": f"Slice {slice_number}",
                "status": "completed",
                "validationLane": "unit",
                "artifacts": [f"slice-{slice_number}.md"],
            }
            for slice_number in range(12)
        ],
    }


def _write_artifacts(repo_root: Path) -> None:
    for slice_number in range(12):
        (repo_root / f"slice-{slice_number}.md").write_text("ok\n", encoding="utf-8")


def test_evaluate_ledger_accepts_complete_ledger(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)

    assert guard.evaluate_ledger(_ledger(), repo_root=tmp_path) == []


def test_evaluate_ledger_rejects_missing_slice(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    ledger["slices"] = ledger["slices"][:-1]  # type: ignore[index]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert "ledger is missing slice(s): 11" in errors


def test_evaluate_ledger_rejects_missing_artifact(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    (tmp_path / "slice-3.md").unlink()

    errors = guard.evaluate_ledger(_ledger(), repo_root=tmp_path)

    assert "slice 3 artifact does not exist: slice-3.md" in errors


def test_evaluate_ledger_rejects_runtime_production_claim(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    ledger["runtimeProductionStatus"] = "production-closed"

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert "ledger must not claim runtime production closure without full proof" in errors


def test_evaluate_ledger_rejects_absolute_artifact_path(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    slices = ledger["slices"]  # type: ignore[assignment]
    slices[0]["artifacts"] = [str((tmp_path / "slice-0.md").resolve())]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any("artifact must be repo-relative" in error for error in errors)
