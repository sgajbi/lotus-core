"""Small, shared helpers for PostgreSQL JSON query-plan assertions."""

from __future__ import annotations

from typing import Any


def _plan_attribute_values(value: Any, attribute: str) -> set[str]:
    values: set[str] = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            attribute_value = item.get(attribute)
            if isinstance(attribute_value, str):
                values.add(attribute_value)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return values


def plan_index_names(value: Any) -> set[str]:
    """Return every index name referenced anywhere in a JSON query plan."""

    return _plan_attribute_values(value, "Index Name")


def plan_node_types(value: Any) -> set[str]:
    """Return every node type referenced anywhere in a JSON query plan."""

    return _plan_attribute_values(value, "Node Type")
