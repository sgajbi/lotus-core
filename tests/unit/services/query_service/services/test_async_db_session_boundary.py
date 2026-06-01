from __future__ import annotations

import ast
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[5] / "src/services/query_service/app/services"


def _asyncio_gather_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "gather"
            and isinstance(func.value, ast.Name)
            and func.value.id == "asyncio"
        ):
            calls.append(node)
    return calls


def test_query_service_layer_does_not_use_asyncio_gather_on_request_session_repos() -> None:
    offenders: dict[str, list[int]] = {}
    for path in SERVICE_DIR.glob("*.py"):
        calls = _asyncio_gather_calls(path)
        if calls:
            offenders[path.relative_to(SERVICE_DIR).as_posix()] = [call.lineno for call in calls]

    assert offenders == {}
