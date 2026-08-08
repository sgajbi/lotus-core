"""Reject duplicate service-package identities in governed Python test sources."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = (REPO_ROOT / "tests", REPO_ROOT / "src" / "services")
LEGACY_SERVICE_ROOT = "services"


@dataclass(frozen=True, slots=True)
class LegacyTestImport:
    path: Path
    line_number: int
    module: str

    def render(self, *, root: Path) -> str:
        return (
            f"{self.path.relative_to(root).as_posix()}:{self.line_number}: "
            f"legacy test module reference '{self.module}'; use 'src.services.*'"
        )


def find_legacy_test_imports(*, root: Path = REPO_ROOT) -> tuple[LegacyTestImport, ...]:
    """Return imports and patch targets that can execute one service package twice."""

    findings: list[LegacyTestImport] = []
    for path in _test_python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = (*_imported_modules(node), *_patched_modules(node))
            findings.extend(
                LegacyTestImport(path=path, line_number=node.lineno, module=module)
                for module in modules
                if module == LEGACY_SERVICE_ROOT or module.startswith(f"{LEGACY_SERVICE_ROOT}.")
            )
    return tuple(sorted(findings, key=lambda item: (str(item.path), item.line_number, item.module)))


def _test_python_files(root: Path) -> tuple[Path, ...]:
    candidates = set((root / "tests").rglob("*.py"))
    candidates.update((root / "src" / "services").glob("*/tests/**/*.py"))
    return tuple(sorted(path for path in candidates if path.is_file()))


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    return ()


def _patched_modules(node: ast.AST) -> tuple[str, ...]:
    if not isinstance(node, ast.Call) or not node.args or not _is_patch_call(node.func):
        return ()
    target = node.args[0]
    if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
        return ()
    return (target.value.rpartition(".")[0],)


def _is_patch_call(function: ast.AST) -> bool:
    return (isinstance(function, ast.Name) and function.id == "patch") or (
        isinstance(function, ast.Attribute) and function.attr == "patch"
    )


def main() -> int:
    findings = find_legacy_test_imports()
    if findings:
        print("Test import-root guard failed:")
        for finding in findings:
            print(f"- {finding.render(root=REPO_ROOT)}")
        return 1
    print("Test import-root guard passed: canonical src.services package identity only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
