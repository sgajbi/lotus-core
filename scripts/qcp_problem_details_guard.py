"""Guard query-control-plane routers against raw error payload regressions."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QCP_ROUTER_ROOT = REPO_ROOT / "src" / "services" / "query_control_plane_service" / "app" / "routers"

HTTP_EXCEPTION_IMPORT_MODULES = {
    "fastapi",
    "starlette.exceptions",
}


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_str_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func) == "str"


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _detail_dict_uses_raw_string(node: ast.Dict) -> bool:
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant):
            continue
        if key.value == "detail" and _is_str_call(value):
            return True
    return False


def evaluate_router_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    source = _relative_path(path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in HTTP_EXCEPTION_IMPORT_MODULES:
            if any(alias.name == "HTTPException" for alias in node.names):
                violations.append(
                    f"{source}:{node.lineno} imports HTTPException; "
                    "raise QueryControlPlaneProblem through response_helpers instead"
                )
        if isinstance(node, ast.Call) and _call_name(node.func) == "HTTPException":
            violations.append(
                f"{source}:{node.lineno} calls HTTPException; "
                "use a bounded QueryControlPlaneProblem contract"
            )
        if isinstance(node, ast.keyword) and node.arg == "detail" and _is_str_call(node.value):
            violations.append(
                f"{source}:{node.lineno} uses detail=str(...); "
                "map exceptions to stable QCP error codes and bounded details"
            )
        if isinstance(node, ast.Dict) and _detail_dict_uses_raw_string(node):
            violations.append(
                f"{source}:{node.lineno} builds {{'detail': str(...)}}; "
                "map exceptions to stable QCP error codes and bounded details"
            )

    return violations


def discover_qcp_router_files(root: Path = QCP_ROUTER_ROOT) -> list[Path]:
    return sorted(path for path in root.glob("*.py") if path.name != "__init__.py")


def evaluate_qcp_routers(paths: list[Path] | None = None) -> list[str]:
    router_files = discover_qcp_router_files() if paths is None else paths
    violations: list[str] = []
    for path in router_files:
        violations.extend(evaluate_router_file(path))
    return violations


def main() -> int:
    violations = evaluate_qcp_routers()
    if violations:
        print("QCP problem-details guard failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("QCP problem-details guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
