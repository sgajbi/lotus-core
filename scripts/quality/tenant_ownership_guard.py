"""Measure tenant ownership coverage and prohibit synthetic production tenants."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
GuardMode = Literal["report", "enforce-defaults", "enforce"]


@dataclass(frozen=True, slots=True)
class TenantOwnershipFinding:
    path: str
    line: int | None
    rule: str
    detail: str

    def as_text(self) -> str:
        location = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{location}: {self.rule}: {self.detail}"


def find_orm_tenant_findings(base: Any) -> list[TenantOwnershipFinding]:
    """Return every mapped table that is not yet explicitly tenant-owned."""

    findings: list[TenantOwnershipFinding] = []
    mappers = sorted(base.registry.mappers, key=lambda mapper: mapper.local_table.name)
    for mapper in mappers:
        table = mapper.local_table
        if "tenant_id" not in table.c:
            findings.append(
                TenantOwnershipFinding(
                    path="src/libs/portfolio-common/portfolio_common/database_models.py",
                    line=None,
                    rule="missing-tenant-column",
                    detail=f"{table.name} ({mapper.class_.__name__})",
                )
            )
    return findings


def find_synthetic_default_findings(root: Path) -> list[TenantOwnershipFinding]:
    """Find production tenant defaults that silently fabricate ownership."""

    findings: list[TenantOwnershipFinding] = []
    source_root = root / "src"
    for path in sorted(source_root.rglob("*.py")):
        if "build" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _is_synthetic_tenant_default(node):
                findings.append(
                    TenantOwnershipFinding(
                        path=path.relative_to(root).as_posix(),
                        line=node.lineno,
                        rule="synthetic-default-tenant",
                        detail="production tenant ownership cannot use the literal 'default'",
                    )
                )
    return findings


def _is_synthetic_tenant_default(node: ast.AST) -> bool:
    if isinstance(node, ast.keyword):
        return node.arg == "tenant_id" and _is_default_literal(node.value)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        value = node.value
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return _is_default_literal(value) and any(
            "tenant_id" in _target_names(item) for item in targets
        )
    if isinstance(node, ast.Dict):
        return any(
            _is_tenant_id_literal(key) and _is_default_literal(value)
            for key, value in zip(node.keys, node.values)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            node.func.attr == "get"
            and len(node.args) >= 2
            and _is_tenant_header_literal(node.args[0])
            and _is_default_literal(node.args[1])
        )
    return False


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for child in node.elts for name in _target_names(child)}
    return set()


def _is_default_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "default"


def _is_tenant_id_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "tenant_id"


def _is_tenant_header_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and str(node.value).lower() == "x-tenant-id"


def evaluate_tenant_ownership(root: Path = REPO_ROOT) -> list[TenantOwnershipFinding]:
    from portfolio_common.database_models import Base

    return [*find_orm_tenant_findings(Base), *find_synthetic_default_findings(root)]


def _is_blocking(finding: TenantOwnershipFinding, mode: GuardMode) -> bool:
    if mode == "report":
        return False
    if mode == "enforce-defaults":
        return finding.rule == "synthetic-default-tenant"
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure source-owned tenant coverage and reject synthetic defaults."
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--mode",
        choices=("report", "enforce-defaults", "enforce"),
        default="report",
    )
    args = parser.parse_args()

    findings = evaluate_tenant_ownership(args.root.resolve())
    for finding in findings:
        print(f"  - {finding.as_text()}")
    blocking = [finding for finding in findings if _is_blocking(finding, args.mode)]
    print(
        "Tenant ownership guard: "
        f"{len(findings)} finding(s), {len(blocking)} blocking in {args.mode} mode."
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
