from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

DOMAIN_ROOT = Path("src/services/portfolio_transaction_processing_service/app/domain")
IDENTIFIER_FIELDS = ("instrument_id", "security_id")


@dataclass(frozen=True, slots=True)
class CashInstrumentAuthorityFinding:
    path: str
    line_no: int
    expression: str
    reason: str


def find_cash_instrument_authority_findings(
    root: Path,
) -> list[CashInstrumentAuthorityFinding]:
    findings: list[CashInstrumentAuthorityFinding] = []
    domain_root = root / DOMAIN_ROOT
    if not domain_root.exists():
        return [
            CashInstrumentAuthorityFinding(
                path=DOMAIN_ROOT.as_posix(),
                line_no=0,
                expression="<missing-directory>",
                reason="transaction-processing domain boundary is missing",
            )
        ]
    for path in sorted(domain_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if _is_cash_identifier_prefix_inference(node):
                findings.append(
                    CashInstrumentAuthorityFinding(
                        path=path.relative_to(root).as_posix(),
                        line_no=node.lineno,
                        expression=ast.unparse(node),
                        reason=(
                            "cash classification must use server-owned product metadata, "
                            "not instrument or security identifier prefixes"
                        ),
                    )
                )
    return findings


def _is_cash_identifier_prefix_inference(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "startswith" or not node.args:
        return False
    prefix = node.args[0]
    if not isinstance(prefix, ast.Constant) or not isinstance(prefix.value, str):
        return False
    if not prefix.value.strip().upper().startswith("CASH"):
        return False
    receiver = ast.unparse(node.func.value).lower()
    return any(field in receiver for field in IDENTIFIER_FIELDS)


def main() -> int:
    findings = find_cash_instrument_authority_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line_no}: {finding.expression}: {finding.reason}")
        return 1
    print("Cash instrument authority guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
