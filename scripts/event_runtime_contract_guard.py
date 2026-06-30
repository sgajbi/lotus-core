"""Validate RFC-0083 event catalog coverage for runtime outbox emissions."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portfolio_common import config, events
from portfolio_common.event_supportability import (
    DIRECT_KAFKA_TOPIC_DEFINITIONS,
    EVENT_FAMILY_DEFINITIONS,
    DirectKafkaTopicDefinition,
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


@dataclass(frozen=True)
class DirectKafkaPublish:
    source: str
    function_name: str
    topic: str

    @property
    def diagnostic_key(self) -> str:
        return f"{self.source}:{self.function_name}: {self.topic}"


@dataclass(frozen=True)
class ConsumerDlqTopicWiring:
    source: str
    function_name: str
    consumer_name: str
    topic: str | None
    expression: str

    @property
    def diagnostic_key(self) -> str:
        return f"{self.source}:{self.function_name}: {self.consumer_name}"


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_topic(node: ast.AST | None, bindings: dict[str, str] | None = None) -> str | None:
    if node is None:
        return None
    topic = _literal_string(node)
    if topic is not None:
        return topic
    if isinstance(node, ast.Name):
        if bindings is not None and node.id in bindings:
            return bindings[node.id]
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


def _is_publish_message_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "publish_message"
    return False


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _source_expression(node: ast.AST | None) -> str:
    if node is None:
        return "<missing>"
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


class _OutboxEmissionVisitor(ast.NodeVisitor):
    def __init__(self, source: str, consumer_class_names: set[str] | None = None) -> None:
        self.source = source
        self.function_name = "<module>"
        self.consumer_class_names = consumer_class_names or set()
        self.emissions: list[OutboxEventEmission] = []
        self.direct_publishes: list[DirectKafkaPublish] = []
        self.consumer_dlq_wirings: list[ConsumerDlqTopicWiring] = []
        self._topic_bindings_stack: list[dict[str, str]] = [{}]

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
        if _is_publish_message_call(node):
            topic = _resolve_topic(_call_keyword_value(node, "topic"), self._topic_bindings)
            if topic is not None:
                self.direct_publishes.append(
                    DirectKafkaPublish(
                        source=self.source,
                        function_name=self.function_name,
                        topic=topic,
                    )
                )
        consumer_name = _call_name(node)
        dlq_topic_node = _call_keyword_value(node, "dlq_topic")
        if consumer_name in self.consumer_class_names and dlq_topic_node is not None:
            self.consumer_dlq_wirings.append(
                ConsumerDlqTopicWiring(
                    source=self.source,
                    function_name=self.function_name,
                    consumer_name=consumer_name or "<unknown>",
                    topic=_resolve_topic(dlq_topic_node, self._topic_bindings),
                    expression=_source_expression(dlq_topic_node),
                )
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        topic = _resolve_topic(node.value, self._topic_bindings)
        if topic is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._topic_bindings[target.id] = topic
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        topic = _resolve_topic(node.value, self._topic_bindings)
        if topic is not None and isinstance(node.target, ast.Name):
            self._topic_bindings[node.target.id] = topic
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
        self._topic_bindings_stack.append(self._topic_bindings.copy())
        self.generic_visit(node)
        self._topic_bindings_stack.pop()
        self.function_name = previous_function_name

    @property
    def _topic_bindings(self) -> dict[str, str]:
        return self._topic_bindings_stack[-1]


def _is_outbox_details_dict(node: ast.Dict) -> bool:
    return _dict_value(node, "event_type") is not None and _dict_value(node, "topic") is not None


def discover_outbox_event_emissions(
    source_root: Path = SOURCE_ROOT,
) -> tuple[OutboxEventEmission, ...]:
    emissions: list[OutboxEventEmission] = []
    consumer_class_names = _discover_consumer_class_names(source_root)
    for source_file in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        source = _source_label(source_file, source_root)
        visitor = _OutboxEmissionVisitor(source, consumer_class_names=consumer_class_names)
        visitor.visit(tree)
        emissions.extend(visitor.emissions)
    return tuple(
        sorted(set(emissions), key=lambda item: (item.event_type, item.topic, item.source))
    )


def discover_direct_kafka_publishes(
    source_root: Path = SOURCE_ROOT,
) -> tuple[DirectKafkaPublish, ...]:
    publishes: list[DirectKafkaPublish] = []
    consumer_class_names = _discover_consumer_class_names(source_root)
    for source_file in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        source = _source_label(source_file, source_root)
        visitor = _OutboxEmissionVisitor(source, consumer_class_names=consumer_class_names)
        visitor.visit(tree)
        publishes.extend(visitor.direct_publishes)
    return tuple(sorted(set(publishes), key=lambda item: (item.topic, item.source)))


def discover_consumer_dlq_topic_wirings(
    source_root: Path = SOURCE_ROOT,
) -> tuple[ConsumerDlqTopicWiring, ...]:
    wirings: list[ConsumerDlqTopicWiring] = []
    consumer_class_names = _discover_consumer_class_names(source_root)
    for source_file in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        source = _source_label(source_file, source_root)
        visitor = _OutboxEmissionVisitor(source, consumer_class_names=consumer_class_names)
        visitor.visit(tree)
        wirings.extend(visitor.consumer_dlq_wirings)
    return tuple(
        sorted(
            set(wirings),
            key=lambda item: (item.topic or "", item.consumer_name, item.source),
        )
    )


def _discover_consumer_class_names(source_root: Path = SOURCE_ROOT) -> set[str]:
    class_bases: dict[str, set[str]] = {}
    for source_file in sorted(source_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_bases[node.name] = {
                    base_name for base in node.bases if (base_name := _base_name(base)) is not None
                }

    consumer_class_names = {"BaseConsumer"}
    changed = True
    while changed:
        changed = False
        for class_name, base_names in class_bases.items():
            if class_name not in consumer_class_names and base_names & consumer_class_names:
                consumer_class_names.add(class_name)
                changed = True
    return consumer_class_names


def _source_label(source_file: Path, source_root: Path) -> str:
    try:
        return source_file.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return source_file.relative_to(source_root).as_posix()


def evaluate_outbox_event_contracts(
    emissions: tuple[OutboxEventEmission, ...] | None = None,
    event_definitions: tuple[EventFamilyDefinition, ...] = EVENT_FAMILY_DEFINITIONS,
    direct_publishes: tuple[DirectKafkaPublish, ...] | None = None,
    direct_topic_definitions: tuple[
        DirectKafkaTopicDefinition, ...
    ] = DIRECT_KAFKA_TOPIC_DEFINITIONS,
    consumer_dlq_wirings: tuple[ConsumerDlqTopicWiring, ...] | None = None,
) -> list[str]:
    errors: list[str] = []
    available_models = {
        name for name in dir(events) if name.endswith("Event") or name.endswith("EventModel")
    }
    try:
        validate_event_supportability_catalog(
            event_definitions,
            direct_kafka_topics=direct_topic_definitions,
            available_schema_models=available_models,
        )
    except ValueError as exc:
        errors.append(f"event supportability catalog is invalid: {exc}")

    emissions = discover_outbox_event_emissions() if emissions is None else emissions
    direct_publishes = (
        discover_direct_kafka_publishes() if direct_publishes is None else direct_publishes
    )
    consumer_dlq_wirings = (
        discover_consumer_dlq_topic_wirings()
        if consumer_dlq_wirings is None
        else consumer_dlq_wirings
    )
    definitions_by_event_type = {
        definition.event_type: definition for definition in event_definitions
    }
    direct_topics = {definition.topic for definition in direct_topic_definitions}

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

    for publish in direct_publishes:
        if publish.topic not in direct_topics:
            errors.append(
                f"{publish.diagnostic_key} publishes a direct Kafka topic missing from the "
                "RFC-0083 direct Kafka topic catalog"
            )

    for wiring in consumer_dlq_wirings:
        if wiring.topic is None:
            errors.append(
                f"{wiring.diagnostic_key} wires an unresolved BaseConsumer DLQ topic "
                f"expression {wiring.expression!r}"
            )
            continue
        if wiring.topic not in direct_topics:
            errors.append(
                f"{wiring.diagnostic_key} wires DLQ topic {wiring.topic!r} missing from the "
                "RFC-0083 direct Kafka topic catalog"
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
