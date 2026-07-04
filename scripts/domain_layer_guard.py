from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

DISALLOWED_MODULE_ROOTS = {
    "confluent_kafka",
    "fastapi",
    "httpx",
    "kafka",
    "pydantic",
    "redis",
    "requests",
    "sqlalchemy",
    "starlette",
}

DISALLOWED_IMPORT_PARTS = {
    "DTOs",
    "clients",
    "consumer",
    "consumers",
    "dtos",
    "repositories",
    "repository",
    "settings",
}

DOMAIN_GLOBS = (
    "src/services/**/domain/**/*.py",
    "src/libs/portfolio-common/portfolio_common/transaction_domain/**/*.py",
)

TRANSITIONAL_ALLOWLIST = {
    "src/libs/portfolio-common/portfolio_common/transaction_domain/buy_models.py": {"pydantic"},
    "src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_models.py": {
        "pydantic"
    },
    "src/libs/portfolio-common/portfolio_common/transaction_domain/fx_models.py": {"pydantic"},
    "src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py": {
        "pydantic"
    },
    "src/libs/portfolio-common/portfolio_common/transaction_domain/sell_models.py": {"pydantic"},
}


@dataclass(frozen=True, slots=True)
class DomainImportFinding:
    path: str
    line: int
    imported_module: str
    reason: str

    def as_text(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}: {self.imported_module}"


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _domain_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in DOMAIN_GLOBS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                modules.append((node.lineno, module))
    return modules


def _is_allowed(path: str, module_root: str) -> bool:
    return module_root in TRANSITIONAL_ALLOWLIST.get(path, set())


def _finding_for_import(
    *,
    path: str,
    line: int,
    imported_module: str,
) -> DomainImportFinding | None:
    module_parts = imported_module.split(".")
    module_root = module_parts[0]
    if module_root in DISALLOWED_MODULE_ROOTS and not _is_allowed(path, module_root):
        return DomainImportFinding(
            path=path,
            line=line,
            imported_module=imported_module,
            reason="domain layer imports framework or infrastructure module",
        )
    if any(part in DISALLOWED_IMPORT_PARTS for part in module_parts):
        return DomainImportFinding(
            path=path,
            line=line,
            imported_module=imported_module,
            reason="domain layer imports adapter, repository, DTO, client, or settings module",
        )
    return None


def find_domain_import_findings(root: Path) -> list[DomainImportFinding]:
    root = root.resolve()
    findings: list[DomainImportFinding] = []
    for path in _domain_files(root):
        relative_path = _relative_path(root, path)
        for line, imported_module in _imported_modules(path):
            finding = _finding_for_import(
                path=relative_path,
                line=line,
                imported_module=imported_module,
            )
            if finding is not None:
                findings.append(finding)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guard lotus-core domain packages from framework/infrastructure imports."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    findings = find_domain_import_findings(args.root)
    if findings:
        print("Domain layer import guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Domain layer import guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
