"""Prevent magnitude-based bond quote interpretation from re-entering production."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IDENTIFIERS = (
    "resolve_valuation_unit_price",
    "_looks_like_legacy_bond_percent_quote",
    "_bond_percent_quote_multiplier",
    "_bond_price_ratio_multiplier",
)
REQUIRED_CONSUMERS = {
    Path(
        "src/services/calculators/position_valuation_calculator/app/valuation_processor.py"
    ): "requires_bond_quote_authority",
    Path(
        "src/services/financial_reconciliation_service/app/domain/reconciliation_policies.py"
    ): "requires_bond_quote_authority",
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

    for relative, required_identifier in REQUIRED_CONSUMERS.items():
        path = repo_root / relative
        if not path.is_file():
            findings.append(f"{relative.as_posix()}: required production consumer is missing")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _call_name(node) == required_identifier
        ]
        if len(calls) != 1:
            findings.append(f"{relative.as_posix()}: missing explicit bond quote-authority guard")
            continue
        keyword_names = {keyword.arg for keyword in calls[0].keywords}
        if keyword_names != {"product_type", "quantity"}:
            findings.append(
                f"{relative.as_posix()}: bond quote-authority guard must receive "
                "product_type and quantity"
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
