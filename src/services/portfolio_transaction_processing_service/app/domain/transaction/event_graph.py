"""Validate deterministic directed economic-event graphs without framework dependencies."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class DirectedEventGraphStatus(StrEnum):
    """Classify structural graph validity without claiming business readiness."""

    VALID = "VALID"
    INVALID = "INVALID"


class DirectedEventGraphReason(StrEnum):
    """Expose stable structural graph defects."""

    EMPTY_GRAPH = "EVENT_GRAPH_EMPTY"
    DUPLICATE_NODE_ID = "EVENT_GRAPH_DUPLICATE_NODE_ID"
    CONFLICTING_NODE_DEFINITION = "EVENT_GRAPH_CONFLICTING_NODE_DEFINITION"
    DUPLICATE_EDGE = "EVENT_GRAPH_DUPLICATE_EDGE"
    SELF_DEPENDENCY = "EVENT_GRAPH_SELF_DEPENDENCY"
    MISSING_DEPENDENCY = "EVENT_GRAPH_MISSING_DEPENDENCY"
    DEPENDENCY_CYCLE = "EVENT_GRAPH_DEPENDENCY_CYCLE"
    BLOCKED_BY_CYCLE = "EVENT_GRAPH_BLOCKED_BY_CYCLE"


@dataclass(frozen=True, slots=True)
class DirectedEventNode:
    """Represent one immutable node declaration supplied by a domain adapter."""

    node_id: str
    dependency_node_ids: tuple[str, ...]
    definition_fingerprint: str
    order_key: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _required_text(self.node_id, "node_id"))
        if isinstance(self.dependency_node_ids, (str, bytes)):
            raise ValueError("dependency_node_ids must be a collection of node ids")
        object.__setattr__(
            self,
            "dependency_node_ids",
            tuple(
                _required_text(value, "dependency_node_ids") for value in self.dependency_node_ids
            ),
        )
        object.__setattr__(
            self,
            "definition_fingerprint",
            _required_text(self.definition_fingerprint, "definition_fingerprint"),
        )
        if not isinstance(self.order_key, tuple) or not self.order_key:
            raise ValueError("order_key must be a non-empty tuple of strings")
        object.__setattr__(
            self,
            "order_key",
            tuple(_required_text(value, "order_key") for value in self.order_key),
        )


@dataclass(frozen=True, slots=True)
class DirectedEventGraphFinding:
    """Describe one deterministic structural defect."""

    reason: DirectedEventGraphReason
    node_ids: tuple[str, ...]
    dependency_node_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DirectedEventGraphPlan:
    """Return a canonical topological order or a complete fail-closed finding set."""

    status: DirectedEventGraphStatus
    ordered_nodes: tuple[DirectedEventNode, ...]
    findings: tuple[DirectedEventGraphFinding, ...]
    declared_node_count: int
    declared_edge_count: int

    @property
    def ordered_node_ids(self) -> tuple[str, ...]:
        """Return canonical node identities."""

        return tuple(node.node_id for node in self.ordered_nodes)


def resolve_directed_event_graph(nodes: Iterable[DirectedEventNode]) -> DirectedEventGraphPlan:
    """Resolve structural validity and canonical order.

    Graph construction and traversal are linear in declared nodes and edges. Deterministic ready
    selection uses a heap, so worst-case end-to-end complexity is O((V + E) log V).
    """

    declared_nodes = tuple(nodes)
    findings: list[DirectedEventGraphFinding] = []
    nodes_by_id: dict[str, DirectedEventNode] = {}
    for node in declared_nodes:
        existing = nodes_by_id.get(node.node_id)
        if existing is None:
            nodes_by_id[node.node_id] = node
            continue
        findings.append(
            DirectedEventGraphFinding(
                reason=(
                    DirectedEventGraphReason.DUPLICATE_NODE_ID
                    if existing.definition_fingerprint == node.definition_fingerprint
                    else DirectedEventGraphReason.CONFLICTING_NODE_DEFINITION
                ),
                node_ids=(node.node_id,),
            )
        )

    if not declared_nodes:
        findings.append(
            DirectedEventGraphFinding(
                reason=DirectedEventGraphReason.EMPTY_GRAPH,
                node_ids=(),
            )
        )

    if findings:
        return _invalid(findings, node_count=len(nodes_by_id), edge_count=0)

    dependants: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    dependencies: dict[str, tuple[str, ...]] = {}
    indegree = dict.fromkeys(nodes_by_id, 0)
    edge_count = 0
    for node in nodes_by_id.values():
        unique_dependencies = set(node.dependency_node_ids)
        if len(unique_dependencies) != len(node.dependency_node_ids):
            findings.append(
                DirectedEventGraphFinding(
                    reason=DirectedEventGraphReason.DUPLICATE_EDGE,
                    node_ids=(node.node_id,),
                    dependency_node_ids=_duplicates(node.dependency_node_ids),
                )
            )
        if node.node_id in unique_dependencies:
            findings.append(
                DirectedEventGraphFinding(
                    reason=DirectedEventGraphReason.SELF_DEPENDENCY,
                    node_ids=(node.node_id,),
                    dependency_node_ids=(node.node_id,),
                )
            )
        missing = tuple(sorted(unique_dependencies.difference(nodes_by_id)))
        if missing:
            findings.append(
                DirectedEventGraphFinding(
                    reason=DirectedEventGraphReason.MISSING_DEPENDENCY,
                    node_ids=(node.node_id,),
                    dependency_node_ids=missing,
                )
            )
        present_dependencies = tuple(
            sorted(unique_dependencies.intersection(nodes_by_id).difference({node.node_id}))
        )
        dependencies[node.node_id] = present_dependencies
        for dependency_id in present_dependencies:
            dependants[dependency_id].append(node.node_id)
            indegree[node.node_id] += 1
            edge_count += 1

    if findings:
        return _invalid(findings, node_count=len(nodes_by_id), edge_count=edge_count)

    ready: list[tuple[tuple[str, ...], str]] = []
    for node_id, degree in indegree.items():
        if degree == 0:
            node = nodes_by_id[node_id]
            heapq.heappush(ready, (node.order_key, node_id))

    ordered: list[DirectedEventNode] = []
    while ready:
        _, node_id = heapq.heappop(ready)
        ordered.append(nodes_by_id[node_id])
        for dependant_id in dependants[node_id]:
            indegree[dependant_id] -= 1
            if indegree[dependant_id] == 0:
                dependant = nodes_by_id[dependant_id]
                heapq.heappush(ready, (dependant.order_key, dependant_id))

    if len(ordered) != len(nodes_by_id):
        unresolved = frozenset(node_id for node_id, degree in indegree.items() if degree)
        cycle_components = _cyclic_components(
            unresolved=unresolved,
            dependants=dependants,
            dependencies=dependencies,
        )
        cycle_nodes = frozenset(node_id for component in cycle_components for node_id in component)
        findings.extend(
            DirectedEventGraphFinding(
                reason=DirectedEventGraphReason.DEPENDENCY_CYCLE,
                node_ids=component,
            )
            for component in cycle_components
        )
        for blocked_node_id in sorted(unresolved.difference(cycle_nodes)):
            findings.append(
                DirectedEventGraphFinding(
                    reason=DirectedEventGraphReason.BLOCKED_BY_CYCLE,
                    node_ids=(blocked_node_id,),
                    dependency_node_ids=tuple(
                        dependency_id
                        for dependency_id in dependencies[blocked_node_id]
                        if dependency_id in unresolved
                    ),
                )
            )
        return _invalid(findings, node_count=len(nodes_by_id), edge_count=edge_count)

    return DirectedEventGraphPlan(
        status=DirectedEventGraphStatus.VALID,
        ordered_nodes=tuple(ordered),
        findings=(),
        declared_node_count=len(nodes_by_id),
        declared_edge_count=edge_count,
    )


def _cyclic_components(
    *,
    unresolved: frozenset[str],
    dependants: dict[str, list[str]],
    dependencies: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], ...]:
    finish_order: list[str] = []
    visited: set[str] = set()
    for start in sorted(unresolved):
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[str, int, tuple[str, ...]]] = [
            (start, 0, tuple(sorted(set(dependants[start]).intersection(unresolved))))
        ]
        while stack:
            node_id, next_index, neighbours = stack[-1]
            if next_index < len(neighbours):
                neighbour = neighbours[next_index]
                stack[-1] = (node_id, next_index + 1, neighbours)
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(
                        (
                            neighbour,
                            0,
                            tuple(sorted(set(dependants[neighbour]).intersection(unresolved))),
                        )
                    )
                continue
            finish_order.append(node_id)
            stack.pop()

    assigned: set[str] = set()
    components: list[tuple[str, ...]] = []
    for start in reversed(finish_order):
        if start in assigned:
            continue
        component: set[str] = set()
        component_stack = [start]
        while component_stack:
            node_id = component_stack.pop()
            if node_id in assigned:
                continue
            assigned.add(node_id)
            component.add(node_id)
            for predecessor in dependencies[node_id]:
                if predecessor in unresolved and predecessor not in assigned:
                    component_stack.append(predecessor)
        if len(component) > 1:
            components.append(tuple(sorted(component)))
    return tuple(sorted(components))


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _invalid(
    findings: Iterable[DirectedEventGraphFinding],
    *,
    node_count: int,
    edge_count: int,
) -> DirectedEventGraphPlan:
    return DirectedEventGraphPlan(
        status=DirectedEventGraphStatus.INVALID,
        ordered_nodes=(),
        findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.reason,
                    finding.node_ids,
                    finding.dependency_node_ids,
                ),
            )
        ),
        declared_node_count=node_count,
        declared_edge_count=edge_count,
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
