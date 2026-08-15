"""Prevent magnitude-based bond quote interpretation from re-entering production."""

from __future__ import annotations

import argparse
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


def evaluate(repo_root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    source_root = repo_root / "src"
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8")
        for identifier in FORBIDDEN_IDENTIFIERS:
            if identifier in source:
                findings.append(f"{relative}: forbidden bond quote heuristic: {identifier}")

    for relative, required_identifier in REQUIRED_CONSUMERS.items():
        path = repo_root / relative
        if not path.is_file():
            findings.append(f"{relative.as_posix()}: required production consumer is missing")
            continue
        if required_identifier not in path.read_text(encoding="utf-8"):
            findings.append(f"{relative.as_posix()}: missing explicit bond quote-authority guard")
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
