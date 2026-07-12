from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_PATH = Path("docs/standards/testability-architecture-contract.json")


@dataclass(frozen=True, slots=True)
class TestabilityArchitectureContract:
    protected_path_globs: tuple[str, ...]
    forbidden_import_prefixes: tuple[str, ...]
    forbidden_import_parts: tuple[str, ...]
    forbidden_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TestabilityArchitectureFinding:
    path: str
    line: int
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def find_testability_architecture_findings(
    root: Path,
) -> list[TestabilityArchitectureFinding]:
    root = root.resolve()
    contract = _load_contract(root)
    findings: list[TestabilityArchitectureFinding] = []
    for path in _protected_files(root, contract):
        relative_path = path.relative_to(root).as_posix()
        findings.extend(
            _find_file_testability_violations(
                path=path,
                relative_path=relative_path,
                contract=contract,
            )
        )
    return findings


def _load_contract(root: Path) -> TestabilityArchitectureContract:
    payload = json.loads((root / CONTRACT_PATH).read_text(encoding="utf-8"))
    _require_contract_list(payload, "protectedPathGlobs")
    _require_contract_list(payload, "forbiddenImportPrefixes")
    _require_contract_list(payload, "forbiddenImportParts")
    _require_contract_list(payload, "forbiddenSymbols")
    return TestabilityArchitectureContract(
        protected_path_globs=tuple(payload["protectedPathGlobs"]),
        forbidden_import_prefixes=tuple(payload["forbiddenImportPrefixes"]),
        forbidden_import_parts=tuple(payload["forbiddenImportParts"]),
        forbidden_symbols=tuple(payload["forbiddenSymbols"]),
    )


def _require_contract_list(payload: dict[str, Any], field_name: str) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{CONTRACT_PATH.as_posix()}: {field_name} must be a string list")


def _protected_files(
    root: Path,
    contract: TestabilityArchitectureContract,
) -> list[Path]:
    files: set[Path] = set()
    for pattern in contract.protected_path_globs:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def _find_file_testability_violations(
    *,
    path: Path,
    relative_path: str,
    contract: TestabilityArchitectureContract,
) -> list[TestabilityArchitectureFinding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            TestabilityArchitectureFinding(
                path=relative_path,
                line=exc.lineno or 1,
                rule="syntax-error",
                detail=str(exc),
            )
        ]

    findings: list[TestabilityArchitectureFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                findings.extend(
                    _find_import_violations(
                        relative_path=relative_path,
                        line=node.lineno,
                        imported_module=alias.name,
                        imported_symbols=(alias.asname or alias.name.split(".")[0],),
                        contract=contract,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            imported_module = "." * node.level + (node.module or "")
            findings.extend(
                _find_import_violations(
                    relative_path=relative_path,
                    line=node.lineno,
                    imported_module=imported_module,
                    imported_symbols=tuple(alias.asname or alias.name for alias in node.names),
                    contract=contract,
                )
            )
        elif isinstance(node, ast.Call):
            call_name = _call_root_name(node)
            if call_name in contract.forbidden_symbols:
                findings.append(
                    TestabilityArchitectureFinding(
                        path=relative_path,
                        line=node.lineno,
                        rule="forbidden-runtime-call",
                        detail=f"calls runtime symbol '{call_name}'",
                    )
                )
    return findings


def _find_import_violations(
    *,
    relative_path: str,
    line: int,
    imported_module: str,
    imported_symbols: tuple[str, ...],
    contract: TestabilityArchitectureContract,
) -> list[TestabilityArchitectureFinding]:
    findings: list[TestabilityArchitectureFinding] = []
    normalized_module = imported_module.lstrip(".")
    for forbidden_prefix in contract.forbidden_import_prefixes:
        if _module_matches(normalized_module, forbidden_prefix):
            findings.append(
                TestabilityArchitectureFinding(
                    path=relative_path,
                    line=line,
                    rule="forbidden-runtime-import",
                    detail=f"imports '{imported_module}'",
                )
            )
    module_parts = tuple(part for part in normalized_module.split(".") if part)
    for forbidden_part in contract.forbidden_import_parts:
        if forbidden_part in module_parts:
            findings.append(
                TestabilityArchitectureFinding(
                    path=relative_path,
                    line=line,
                    rule="forbidden-layer-import",
                    detail=f"imports '{imported_module}' through layer '{forbidden_part}'",
                )
            )
    for symbol in imported_symbols:
        if symbol in contract.forbidden_symbols:
            findings.append(
                TestabilityArchitectureFinding(
                    path=relative_path,
                    line=line,
                    rule="forbidden-runtime-symbol",
                    detail=f"imports runtime symbol '{symbol}' from '{imported_module}'",
                )
            )
    return findings


def _module_matches(import_name: str, forbidden_prefix: str) -> bool:
    return import_name == forbidden_prefix or import_name.startswith(f"{forbidden_prefix}.")


def _call_root_name(node: ast.Call) -> str | None:
    current = node.func
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def main() -> int:
    findings = find_testability_architecture_findings(Path.cwd())
    if findings:
        print("Testability architecture guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Testability architecture guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
