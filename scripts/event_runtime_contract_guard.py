"""Validate RFC-0083 event catalog coverage for runtime outbox emissions."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portfolio_common import config, events
from portfolio_common.event_supportability import (
    EVENT_FAMILY_DEFINITIONS,
    EventFamilyDefinition,
    validate_event_supportability_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"


@dataclass(frozen=True)
class OutboxEventEmission:
    source: str
    function_name: str
    event_type: str
    topic: str

    @property
    def diagnostic_key(self) -> str:
        return f"{self.source}:{self.function_name}: {self.event_type}"


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_topic(node: ast.AST) -> str | None:
    topic = _literal_string(node)
    if topic is not None:
        return topic
    if isinstance(node, ast.Name):
        value = getattr(config, node.id, None)
        return value if isinstance(value, str) else None
    return None


def _call_keyword_value(node: ast.Call, keyword_name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _dict_value(node: ast.Dict, key_name: str) -> ast.AST | None:
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            continue
        if _literal_string(key) == key_name:
            return value
    return None


def _emission_from_values(
    *,
    source: str,
    function_name: str,
    event_type_node: ast.AST | None,
    topic_node: ast.AST | None,
) -> OutboxEventEmission | None:
    if event_type_node is None or topic_node is None:
        return None
    event_type = _literal_string(event_type_node)
    topic = _resolve_topic(topic_node)
    if event_type is None or topic is None:
        return None
    return OutboxEventEmission(
        source=source,
        function_name=function_name,
        event_type=event_type,
        topic=topic,
    )


def _is_create_outbox_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "create_outbox_event"
    return False


class _OutboxEmissionVisitor(ast.NodeVisitor):
    def __init__(self, source: str) -> None:
        self.source = source
        self.function_name = "<module>"
        self.emissions: list[OutboxEventEmission] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if _is_create_outbox_call(node):
            emission = _emission_from_values(
                source=self.source,
                function_name=self.function_name,
                event_type_node=_call_keyword_value(node, "event_type"),
                topic_node=_call_keyword_value(node, "topic"),
            )
            if emission is not None:
                self.emissions.append(emission)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> Any:
        if _is_outbox_details_dict(node):
            emission = _emission_from_values(
                source=self.source,
                function_name=self.function_name,
                event_type_node=_dict_value(node, "event_type"),
                topic_node=_dict_value(node, "topic"),
            )
            if emission is not None:
                self.emissions.append(emission)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        previous_function_name = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous_function_name


def _is_outbox_details_dict(node: ast.Dict) -> bool:
    return _dict_value(node, "event_type") is not None and _dict_value(node, "topic") is not None


def discover_outbox_event_emissions(
    source_root: Path = SOURCE_ROOT,
) -> tuple[OutboxEventEmission, ...]:
    emissions: list[OutboxEventEmission] = []
    for source_file in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        source = _source_label(source_file, source_root)
        visitor = _OutboxEmissionVisitor(source)
        visitor.visit(tree)
        emissions.extend(visitor.emissions)
    return tuple(
        sorted(set(emissions), key=lambda item: (item.event_type, item.topic, item.source))
    )


def _source_label(source_file: Path, source_root: Path) -> str:
    try:
        return source_file.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return source_file.relative_to(source_root).as_posix()


def evaluate_outbox_event_contracts(
    emissions: tuple[OutboxEventEmission, ...] | None = None,
    event_definitions: tuple[EventFamilyDefinition, ...] = EVENT_FAMILY_DEFINITIONS,
) -> list[str]:
    errors: list[str] = []
    available_models = {
        name for name in dir(events) if name.endswith("Event") or name.endswith("EventModel")
    }
    try:
        validate_event_supportability_catalog(
            event_definitions,
            available_schema_models=available_models,
        )
    except ValueError as exc:
        errors.append(f"event supportability catalog is invalid: {exc}")

    emissions = discover_outbox_event_emissions() if emissions is None else emissions
    definitions_by_event_type = {
        definition.event_type: definition for definition in event_definitions
    }

    for emission in emissions:
        definition = definitions_by_event_type.get(emission.event_type)
        if definition is None:
            errors.append(
                f"{emission.diagnostic_key} emits an outbox event missing from the "
                "RFC-0083 event supportability catalog"
            )
            continue
        if emission.topic != definition.topic:
            errors.append(
                f"{emission.diagnostic_key} emits topic {emission.topic!r}, "
                f"expected {definition.topic!r}"
            )

    return errors


def main() -> int:
    errors = evaluate_outbox_event_contracts()
    if errors:
        print("Event runtime contract guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Event runtime contract guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
