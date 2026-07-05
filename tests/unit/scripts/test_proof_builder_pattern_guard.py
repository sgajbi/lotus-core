from pathlib import Path

from scripts.proof_builder_pattern_guard import find_proof_builder_pattern_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_artifacts(root: Path) -> None:
    _write(root / "docs/standards/proof-builder-pattern-standard.md", "standard")
    _write(root / "tests/unit/libs/portfolio-common/test_proof_builders.py", "def test_x(): pass\n")
    _write(
        root / "src/libs/portfolio-common/portfolio_common/proof_builders.py",
        "\n".join(
            [
                "class ProofArtifact: pass",
                "class ProofObservation: pass",
                "class SourceDataSupportabilityProofInput: pass",
                "class IngestionReplayEvidenceProofInput: pass",
                "class ReconciliationEvidenceProofInput: pass",
                "class AppValidationEvidenceProofInput: pass",
                "def build_source_data_supportability_proof(): pass",
                "def build_ingestion_replay_evidence_proof(): pass",
                "def build_reconciliation_evidence_proof(): pass",
                "def build_app_validation_evidence_proof(): pass",
            ]
        ),
    )


def test_proof_builder_pattern_guard_accepts_required_artifacts(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)

    assert find_proof_builder_pattern_findings(tmp_path) == []


def test_proof_builder_pattern_guard_rejects_missing_symbol(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/libs/portfolio-common/portfolio_common/proof_builders.py",
        "class ProofArtifact: pass\n",
    )

    findings = find_proof_builder_pattern_findings(tmp_path)

    assert any(finding.rule == "missing-proof-builder-symbol" for finding in findings)


def test_proof_builder_pattern_guard_rejects_router_import(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)
    _write(
        tmp_path / "src/services/example_service/app/routers/proof.py",
        "from portfolio_common.proof_builders import ProofArtifact\n",
    )

    findings = find_proof_builder_pattern_findings(tmp_path)

    assert any(
        finding.rule == "proof-builder-import-in-delivery-or-persistence" for finding in findings
    )
