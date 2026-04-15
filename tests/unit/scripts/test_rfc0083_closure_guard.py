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
                "artifacts": sorted(guard.EXPECTED_SLICE_ARTIFACTS[slice_number]),
            }
            for slice_number in range(12)
        ],
    }


def _write_artifacts(repo_root: Path) -> None:
    for artifacts in guard.EXPECTED_SLICE_ARTIFACTS.values():
        for artifact in artifacts:
            path = repo_root / artifact
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("ok\n", encoding="utf-8")


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
    (tmp_path / "src/libs/portfolio-common/portfolio_common/reconstruction_identity.py").unlink()

    errors = guard.evaluate_ledger(_ledger(), repo_root=tmp_path)

    assert (
        "slice 3 artifact does not exist: "
        "src/libs/portfolio-common/portfolio_common/reconstruction_identity.py"
    ) in errors


def test_evaluate_ledger_rejects_missing_required_artifact_entry(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    slices = ledger["slices"]  # type: ignore[assignment]
    slices[6]["artifacts"] = [
        "docs/architecture/RFC-0083-source-data-product-catalog.md",
        "src/libs/portfolio-common/portfolio_common/source_data_products.py",
    ]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert (
        "slice 6 is missing required artifact(s): "
        "scripts/source_data_product_contract_guard.py, "
        "tests/unit/libs/portfolio-common/test_source_data_products.py, "
        "tests/unit/scripts/test_source_data_product_contract_guard.py"
    ) in errors


def test_evaluate_ledger_rejects_runtime_production_claim(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    ledger["runtimeProductionStatus"] = "production-closed"

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert "ledger must not claim runtime production closure without full proof" in errors


def test_evaluate_ledger_rejects_incomplete_slice_status(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    slices = ledger["slices"]  # type: ignore[assignment]
    slices[4]["status"] = "blocked"

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert "slice 4 status must be completed for closure" in errors


def test_evaluate_ledger_rejects_invalid_remaining_runtime_proof(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    ledger["remainingRuntimeProof"] = [""]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert "ledger has invalid remaining runtime proof: ''" in errors


def test_evaluate_ledger_rejects_absolute_artifact_path(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    ledger = _ledger()
    slices = ledger["slices"]  # type: ignore[assignment]
    slices[0]["artifacts"] = [str((tmp_path / "REPOSITORY-ENGINEERING-CONTEXT.md").resolve())]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any("artifact must be repo-relative" in error for error in errors)
