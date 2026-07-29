"""Validate the complete calculated financial-output policy inventory."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = Path("docs/standards/financial-calculated-output-policies.v1.json")
POLICY_KEYS = {
    "declaration_path",
    "owner",
    "output_family",
    "name",
    "version",
    "precision",
    "scale",
    "working_precision",
    "rounding",
    "lineage_binding",
    "lineage_gap_callsites",
}
LINEAGE_BINDINGS = {"required", "partial", "not-exposed"}
EXECUTION_METHODS = {
    "add",
    "arithmetic_context",
    "divide",
    "multiply",
    "normalize",
    "subtract",
}


@dataclass(frozen=True, slots=True)
class PolicyDeclaration:
    constant: str
    declaration_path: str
    name: str
    version: str
    precision: int
    scale: int
    working_precision: int
    rounding: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("contract root must be an object")
    return payload


def _literal(call: ast.Call, keyword: str, default: object = None) -> object:
    for item in call.keywords:
        if item.arg == keyword:
            try:
                return ast.literal_eval(item.value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{keyword} must be a literal") from exc
    return default


def _declarations(repo_root: Path) -> dict[str, PolicyDeclaration]:
    declarations: dict[str, PolicyDeclaration] = {}
    for path in sorted((repo_root / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for statement in tree.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            value = statement.value
            if (
                value is None
                or not isinstance(value, ast.Call)
                or not isinstance(value.func, (ast.Name, ast.Attribute))
            ):
                continue
            constructor = value.func.id if isinstance(value.func, ast.Name) else value.func.attr
            if constructor != "CalculatedDecimalPolicy":
                continue
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                raise ValueError(f"{path}: calculated policy must use one named assignment")
            constant = targets[0].id
            if constant in declarations:
                raise ValueError(f"duplicate calculated policy constant: {constant}")
            declaration = PolicyDeclaration(
                constant=constant,
                declaration_path=path.relative_to(repo_root).as_posix(),
                name=str(_literal(value, "name")),
                version=str(_literal(value, "version")),
                precision=int(_literal(value, "precision")),
                scale=int(_literal(value, "scale")),
                working_precision=int(_literal(value, "working_precision", 64)),
                rounding=str(_literal(value, "rounding", ROUND_HALF_EVEN)),
            )
            declarations[constant] = declaration
    return declarations


def _usage(
    repo_root: Path,
    constants: set[str],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    execution = {constant: set() for constant in constants}
    lineage = {constant: set() for constant in constants}
    for path in sorted((repo_root / "src").rglob("*.py")):
        relative_path = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _policy_aliases(tree, constants)
        _UsageVisitor(
            relative_path=relative_path,
            constants=constants,
            aliases=aliases,
            execution=execution,
            lineage=lineage,
        ).visit(tree)
    return execution, lineage


def _policy_aliases(tree: ast.Module, constants: set[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for imported in node.names:
                if imported.name in constants:
                    aliases[imported.asname or imported.name] = imported.name
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if isinstance(value, ast.Name) and (value.id in constants or value.id in aliases):
            aliases[target.id] = aliases.get(value.id, value.id)
        elif isinstance(value, ast.Attribute) and value.attr in constants:
            aliases[target.id] = value.attr
    return aliases


class _UsageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        constants: set[str],
        aliases: dict[str, str],
        execution: dict[str, set[str]],
        lineage: dict[str, set[str]],
    ) -> None:
        self._relative_path = relative_path
        self._constants = constants
        self._aliases = aliases
        self._execution = execution
        self._lineage = lineage
        self._scope: list[str] = []

    @property
    def _callsite(self) -> str:
        scope = ".".join(self._scope) if self._scope else "<module>"
        return f"{self._relative_path}::{scope}"

    def _visit_scope(self, node: ast.AST, name: str) -> None:
        self._scope.append(name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node, node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_scope(node, f"<lambda>@{node.lineno}")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            constant = self._resolve_policy(node.func.value)
            if constant is not None:
                if node.func.attr in EXECUTION_METHODS:
                    self._execution[constant].add(self._callsite)
                if node.func.attr == "lineage_identity":
                    self._lineage[constant].add(self._callsite)
        self.generic_visit(node)

    def _resolve_policy(self, receiver: ast.expr) -> str | None:
        if isinstance(receiver, ast.Name):
            return receiver.id if receiver.id in self._constants else self._aliases.get(receiver.id)
        if isinstance(receiver, ast.Attribute) and receiver.attr in self._constants:
            return receiver.attr
        return None


def evaluate(repo_root: Path, contract_path: Path) -> tuple[str, ...]:
    payload = _load_contract(contract_path)
    findings: list[str] = []
    if set(payload) != {"schema_version", "expected_inventory", "policies"}:
        findings.append("contract root must contain schema_version, expected_inventory, policies")
        return tuple(findings)
    if payload["schema_version"] != "1.0.0":
        findings.append("schema_version must be 1.0.0")
    policies = payload["policies"]
    if not isinstance(policies, dict):
        return (*findings, "policies must be an object")
    declarations = _declarations(repo_root)
    expected_inventory = payload["expected_inventory"]
    if not isinstance(expected_inventory, int) or isinstance(expected_inventory, bool):
        findings.append("expected_inventory must be an integer")
        return tuple(findings)
    if expected_inventory != len(policies):
        findings.append(
            f"expected_inventory={expected_inventory} does not match contract count={len(policies)}"
        )
    missing = sorted(set(declarations) - set(policies))
    stale = sorted(set(policies) - set(declarations))
    findings.extend(f"{constant}: missing contract classification" for constant in missing)
    findings.extend(f"{constant}: stale contract classification" for constant in stale)
    execution, lineage = _usage(repo_root, set(declarations))
    for constant in sorted(set(declarations) & set(policies)):
        declaration = declarations[constant]
        policy = policies[constant]
        if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
            findings.append(f"{constant}: policy keys must be {sorted(POLICY_KEYS)}")
            continue
        expected = {
            "declaration_path": declaration.declaration_path,
            "name": declaration.name,
            "version": declaration.version,
            "precision": declaration.precision,
            "scale": declaration.scale,
            "working_precision": declaration.working_precision,
            "rounding": declaration.rounding,
        }
        for field_name, actual in expected.items():
            if policy[field_name] != actual:
                findings.append(
                    f"{constant}.{field_name}: contract={policy[field_name]!r}, source={actual!r}"
                )
        for field_name in ("owner", "output_family"):
            if not isinstance(policy[field_name], str) or not policy[field_name].strip():
                findings.append(f"{constant}.{field_name}: must be nonblank")
        binding = policy["lineage_binding"]
        if binding not in LINEAGE_BINDINGS:
            findings.append(
                f"{constant}.lineage_binding: must be one of {sorted(LINEAGE_BINDINGS)}"
            )
        gap_callsites = policy["lineage_gap_callsites"]
        valid_gap_callsites = (
            isinstance(gap_callsites, list)
            and all(
                isinstance(callsite, str) and callsite.strip() and "::" in callsite
                for callsite in gap_callsites
            )
            and gap_callsites == sorted(set(gap_callsites))
        )
        if not valid_gap_callsites:
            findings.append(
                f"{constant}.lineage_gap_callsites: must be a sorted list of unique "
                "path::callable values"
            )
            continue
        execution_callsites = execution[constant]
        lineage_callsites = lineage[constant]
        computed_gaps = execution_callsites - lineage_callsites
        contract_gaps = set(gap_callsites)
        for callsite in sorted(computed_gaps - contract_gaps):
            findings.append(f"{constant}: unclassified lineage gap at {callsite}")
        for callsite in sorted(contract_gaps - computed_gaps):
            findings.append(f"{constant}: stale lineage gap at {callsite}")
        if not execution_callsites:
            findings.append(f"{constant}: no execution consumer found")
        if binding == "required" and (not lineage_callsites or computed_gaps):
            findings.append(f"{constant}: required lineage binding is incomplete")
        if binding == "partial" and (not lineage_callsites or not computed_gaps):
            findings.append(
                f"{constant}: partial lineage binding requires bound and unbound consumers"
            )
        if binding == "not-exposed" and lineage_callsites:
            findings.append(f"{constant}: not-exposed policy has a lineage binding")
    if len(declarations) != expected_inventory:
        findings.append(
            f"source inventory={len(declarations)} does not match expected={expected_inventory}"
        )
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    contract_path = (
        args.contract if args.contract.is_absolute() else repo_root / args.contract
    ).resolve()
    findings = evaluate(repo_root, contract_path)
    if findings:
        print("Calculated output policy guard failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    policy_count = _load_contract(contract_path)["expected_inventory"]
    print(f"Calculated output policy guard passed: {policy_count} policies classified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
