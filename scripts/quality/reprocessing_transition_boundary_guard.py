from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path("src")
REQUIRED_OWNED_REQUEUE_CALLERS = (
    Path("src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py"),
    Path("src/services/valuation_orchestrator_service/app/core/fx_revaluation_job_processor.py"),
)


@dataclass(frozen=True, slots=True)
class ReprocessingTransitionBoundaryFinding:
    path: str
    line: int
    reason: str


def find_reprocessing_transition_boundary_findings(
    root: Path,
) -> list[ReprocessingTransitionBoundaryFinding]:
    findings: list[ReprocessingTransitionBoundaryFinding] = []
    source_root = root / SOURCE_ROOT
    if source_root.exists():
        for path in sorted(source_root.rglob("*.py")):
            findings.extend(_direct_pending_transition_findings(root=root, path=path))
    for relative_path in REQUIRED_OWNED_REQUEUE_CALLERS:
        path = root / relative_path
        if not path.exists() or "requeue_owned_effective_dated_job(" not in path.read_text(
            encoding="utf-8"
        ):
            findings.append(
                ReprocessingTransitionBoundaryFinding(
                    path=relative_path.as_posix(),
                    line=0,
                    reason=(
                        "effective-dated replay retries must use the repository-owned "
                        "requeue/coalescing operation"
                    ),
                )
            )
    return findings


def _direct_pending_transition_findings(
    *,
    root: Path,
    path: Path,
) -> list[ReprocessingTransitionBoundaryFinding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        ReprocessingTransitionBoundaryFinding(
            path=path.relative_to(root).as_posix(),
            line=node.lineno,
            reason=(
                "direct update_job_status(..., PENDING) bypasses lease-fenced replay "
                "sibling coalescing"
            ),
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update_job_status"
        and _requested_status(node) == "PENDING"
    ]


def _requested_status(call: ast.Call) -> str | None:
    if len(call.args) >= 2:
        return _string_literal(call.args[1])
    for keyword in call.keywords:
        if keyword.arg == "status":
            return _string_literal(keyword.value)
    return None


def _string_literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def main() -> int:
    findings = find_reprocessing_transition_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.reason}")
        return 1
    print("Reprocessing transition boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
