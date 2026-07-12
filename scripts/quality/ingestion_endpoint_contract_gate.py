"""Enforce What/How/When description contract for ingestion router endpoints."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = REPO_ROOT / "src" / "services" / "ingestion_service" / "app" / "routers"
REQUIRED_MARKERS = ("What:", "How:", "When:")
HTTP_DECORATORS = {"get", "post", "put", "delete", "patch"}


def _extract_description_value(decorator: ast.Call) -> str | None:
    for keyword in decorator.keywords:
        if keyword.arg != "description":
            continue
        value_node = keyword.value
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            return value_node.value
        if isinstance(value_node, ast.JoinedStr):
            parts: list[str] = []
            for segment in value_node.values:
                if isinstance(segment, ast.Constant) and isinstance(segment.value, str):
                    parts.append(segment.value)
                else:
                    return None
            return "".join(parts)
        return None
    return None


def _is_router_http_decorator(decorator: ast.AST) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in HTTP_DECORATORS


def _check_file(path: Path) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not _is_router_http_decorator(decorator):
                continue
            assert isinstance(decorator, ast.Call)
            route_path = ""
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                if isinstance(decorator.args[0].value, str):
                    route_path = decorator.args[0].value
            description = _extract_description_value(decorator)
            if not description:
                violations.append(
                    {
                        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "function": node.name,
                        "route": route_path or "<unknown>",
                        "issue": "Missing description or non-literal description expression.",
                    }
                )
                continue
            missing = [marker for marker in REQUIRED_MARKERS if marker not in description]
            if missing:
                violations.append(
                    {
                        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "function": node.name,
                        "route": route_path or "<unknown>",
                        "issue": f"Missing markers: {', '.join(missing)}",
                    }
                )
    return violations


def main() -> int:
    violations: list[dict[str, str]] = []
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        if path.name in {"__init__.py"}:
            continue
        violations.extend(_check_file(path))

    if violations:
        print("Ingestion endpoint What/How/When gate failed:")
        print(json.dumps(violations, indent=2))
        return 1

    print("Ingestion endpoint What/How/When gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
