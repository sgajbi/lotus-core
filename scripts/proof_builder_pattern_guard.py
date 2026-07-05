from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

STANDARD_PATH = Path("docs/standards/proof-builder-pattern-standard.md")
MODULE_PATH = Path("src/libs/portfolio-common/portfolio_common/proof_builders.py")
TEST_PATH = Path("tests/unit/libs/portfolio-common/test_proof_builders.py")
FORBIDDEN_DELIVERY_OR_PERSISTENCE_GLOBS = (
    "src/services/**/app/routers/**/*.py",
    "src/services/**/app/repositories/**/*.py",
    "src/services/**/app/persistence/**/*.py",
)
REQUIRED_SYMBOLS = {
    "ProofArtifact",
    "ProofObservation",
    "SourceDataSupportabilityProofInput",
    "IngestionReplayEvidenceProofInput",
    "ReconciliationEvidenceProofInput",
    "AppValidationEvidenceProofInput",
    "build_source_data_supportability_proof",
    "build_ingestion_replay_evidence_proof",
    "build_reconciliation_evidence_proof",
    "build_app_validation_evidence_proof",
}


@dataclass(frozen=True, slots=True)
class ProofBuilderPatternFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_proof_builder_pattern_findings(root: Path) -> list[ProofBuilderPatternFinding]:
    root = root.resolve()
    findings: list[ProofBuilderPatternFinding] = []
    findings.extend(_validate_required_paths(root))
    if (root / MODULE_PATH).exists():
        findings.extend(_validate_required_symbols(root / MODULE_PATH))
    findings.extend(_scan_forbidden_imports(root))
    return findings


def _validate_required_paths(root: Path) -> list[ProofBuilderPatternFinding]:
    findings: list[ProofBuilderPatternFinding] = []
    for path, rule in (
        (STANDARD_PATH, "missing-proof-builder-standard"),
        (MODULE_PATH, "missing-proof-builder-contract-module"),
        (TEST_PATH, "missing-proof-builder-tests"),
    ):
        if not (root / path).exists():
            findings.append(
                ProofBuilderPatternFinding(
                    path=path.as_posix(),
                    rule=rule,
                    detail="required proof-builder artifact is missing",
                )
            )
    return findings


def _validate_required_symbols(module_path: Path) -> list[ProofBuilderPatternFinding]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    symbols = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    missing_symbols = sorted(REQUIRED_SYMBOLS - symbols)
    if not missing_symbols:
        return []
    return [
        ProofBuilderPatternFinding(
            path=MODULE_PATH.as_posix(),
            rule="missing-proof-builder-symbol",
            detail=f"missing required symbols: {', '.join(missing_symbols)}",
        )
    ]


def _scan_forbidden_imports(root: Path) -> list[ProofBuilderPatternFinding]:
    findings: list[ProofBuilderPatternFinding] = []
    for pattern in FORBIDDEN_DELIVERY_OR_PERSISTENCE_GLOBS:
        for path in (root / ".").glob(pattern):
            if _imports_proof_builders(path):
                findings.append(
                    ProofBuilderPatternFinding(
                        path=path.relative_to(root).as_posix(),
                        rule="proof-builder-import-in-delivery-or-persistence",
                        detail=(
                            "routers and repositories must not import shared "
                            "proof-builder contracts directly"
                        ),
                    )
                )
    return findings


def _imports_proof_builders(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "portfolio_common.proof_builders" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "portfolio_common.proof_builders":
                return True
    return False


def main() -> int:
    findings = find_proof_builder_pattern_findings(Path.cwd())
    if findings:
        print("Proof builder pattern guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Proof builder pattern guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
