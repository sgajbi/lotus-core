from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SERVICES_ROOT = Path("src/services")
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
    services_root = root / SERVICES_ROOT
    if not services_root.exists():
        return [
            CashInstrumentAuthorityFinding(
                path=SERVICES_ROOT.as_posix(),
                line_no=0,
                expression="<missing-directory>",
                reason="production service source boundary is missing",
            )
        ]
    for path in sorted(services_root.rglob("*.py")):
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
