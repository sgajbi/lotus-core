"""Reject application-clock values used to mint durable lease deadlines."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEADLINE_SUFFIX = "_expires_at"
_APPLICATION_CLOCK_CALLS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("timezone", "now"),
}


@dataclass(frozen=True, slots=True)
class DurableLeaseClockFinding:
    file: str
    line: int
    column: int
    target: str


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return tuple(reversed(parts))


def _contains_application_clock(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            chain = _attribute_chain(child.func)
            if len(chain) >= 2 and tuple(chain[-2:]) in _APPLICATION_CLOCK_CALLS:
                return True
            if chain and chain[-1] in {"timedelta", "make_interval"}:
                # timedelta is an application-side duration when paired with a clock call;
                # make_interval is a database expression and is explicitly safe.
                if chain[-1] == "timedelta":
                    return True
    return False


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return names
    return []


def find_durable_lease_clock_findings(
    *,
    repo_root: Path = REPO_ROOT,
    source_root: Path | None = None,
) -> list[DurableLeaseClockFinding]:
    root = source_root or repo_root / "src"
    findings: list[DurableLeaseClockFinding] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            assignments: list[tuple[list[str], ast.AST]] = []
            if isinstance(node, ast.Assign):
                assignments = [(_target_names(target), node.value) for target in node.targets]
            elif isinstance(node, ast.AnnAssign):
                assignments = [(_target_names(node.target), node.value)] if node.value else []
            elif isinstance(node, ast.Call):
                assignments = [
                    ([keyword.arg], keyword.value)
                    for keyword in node.keywords
                    if keyword.arg and keyword.arg.endswith(_DEADLINE_SUFFIX)
                ]
            for targets, value in assignments:
                for target in targets:
                    if target.endswith(_DEADLINE_SUFFIX) and _contains_application_clock(value):
                        findings.append(
                            DurableLeaseClockFinding(
                                file=path.relative_to(repo_root).as_posix(),
                                line=node.lineno,
                                column=node.col_offset,
                                target=target,
                            )
                        )
    return findings


def main() -> int:
    findings = find_durable_lease_clock_findings()
    if findings:
        print("Durable lease clock guard failed:")
        for finding in findings:
            print(f"{finding.file}:{finding.line}:{finding.column}: {finding.target}")
        return 1
    print("Durable lease clock guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
