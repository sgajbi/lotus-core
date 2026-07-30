"""Guard production outbox dispatchers against shared producer recovery boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
EXPECTED_RUNTIME_COMPOSITIONS = 5


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_production_outbox_dispatchers_use_exclusive_producer_factory() -> None:
    compositions: list[tuple[Path, ast.Call]] = []
    for source_path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "OutboxDispatcher":
                compositions.append((source_path, node))

    assert len(compositions) == EXPECTED_RUNTIME_COMPOSITIONS
    for source_path, composition in compositions:
        producer_arguments = [
            keyword.value for keyword in composition.keywords if keyword.arg == "kafka_producer"
        ]
        assert len(producer_arguments) == 1, source_path.relative_to(REPOSITORY_ROOT)
        producer_argument = producer_arguments[0]
        assert isinstance(producer_argument, ast.Call), source_path.relative_to(REPOSITORY_ROOT)
        assert _call_name(producer_argument) == "create_kafka_producer", source_path.relative_to(
            REPOSITORY_ROOT
        )
