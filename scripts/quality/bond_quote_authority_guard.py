"""Prevent magnitude-based bond quote interpretation from re-entering production."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IDENTIFIERS = (
    "resolve_valuation_unit_price",
    "_looks_like_legacy_bond_percent_quote",
    "_bond_percent_quote_multiplier",
    "_bond_price_ratio_multiplier",
)


@dataclass(frozen=True)
class RequiredConsumer:
    function_name: str
    keyword_expressions: dict[str, str]


REQUIRED_CONSUMERS = {
    Path(
        "src/services/calculators/position_valuation_calculator/app/valuation_processor.py"
    ): RequiredConsumer(
        function_name="_value_legacy_snapshot",
        keyword_expressions={
            "product_type": "instrument.product_type",
            "quantity": "snapshot.quantity",
            "cost_basis_reporting": "snapshot.cost_basis",
            "cost_basis_local": "snapshot.cost_basis_local",
        },
    ),
    Path(
        "src/services/financial_reconciliation_service/app/domain/reconciliation_policies.py"
    ): RequiredConsumer(
        function_name="position_valuation_reconciliation_findings",
        keyword_expressions={
            "product_type": "evidence.product_type",
            "quantity": "quantity",
            "cost_basis_reporting": "cost_basis_reporting",
            "cost_basis_local": "cost_basis_local",
        },
    ),
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def evaluate(repo_root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    source_root = repo_root / "src"
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for identifier in FORBIDDEN_IDENTIFIERS:
            if any(
                (isinstance(node, ast.Name) and node.id == identifier)
                or (isinstance(node, ast.Attribute) and node.attr == identifier)
                or (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == identifier
                )
                for node in ast.walk(tree)
            ):
                findings.append(f"{relative}: forbidden bond quote heuristic: {identifier}")

    for relative, required_consumer in REQUIRED_CONSUMERS.items():
        path = repo_root / relative
        if not path.is_file():
            findings.append(f"{relative.as_posix()}: required production consumer is missing")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        owning_functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == required_consumer.function_name
        ]
        if len(owning_functions) != 1:
            findings.append(
                f"{relative.as_posix()}: required function "
                f"{required_consumer.function_name} is missing or ambiguous"
            )
            continue
        guarded_calls = [
            node.test
            for node in ast.walk(owning_functions[0])
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Call)
            and _call_name(node.test) == "requires_bond_quote_authority"
        ]
        if len(guarded_calls) != 1:
            findings.append(
                f"{relative.as_posix()}: {required_consumer.function_name} must have exactly "
                "one direct bond quote-authority fail-closed branch"
            )
            continue
        actual_expressions = {
            keyword.arg: ast.unparse(keyword.value)
            for keyword in guarded_calls[0].keywords
            if keyword.arg is not None
        }
        if actual_expressions != required_consumer.keyword_expressions:
            findings.append(
                f"{relative.as_posix()}: {required_consumer.function_name} bond quote-authority "
                "branch must use the governed product, quantity, and cost evidence"
            )
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = evaluate(args.repo_root.resolve())
    if findings:
        print("Bond quote authority guard failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Bond quote authority guard passed: no production magnitude inference remains.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
