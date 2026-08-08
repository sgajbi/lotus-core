"""Resolve immutable corporate-action child dependencies before financial execution."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .ordering import corporate_action_dependency_rank


class CorporateActionEventGraphStatus(StrEnum):
    """Classify whether an event graph is safe to execute."""

    READY = "READY"
    PARKED = "PARKED"


class CorporateActionEventGraphReason(StrEnum):
    """Expose stable reasons why a graph cannot be executed."""

    EMPTY_EVENT = "CA_EVENT_EMPTY"
    DUPLICATE_CHILD_ID = "CA_EVENT_DUPLICATE_CHILD_ID"
    CONFLICTING_CHILD_DEFINITION = "CA_EVENT_CONFLICTING_CHILD_DEFINITION"
    DUPLICATE_DEPENDENCY_REFERENCE = "CA_EVENT_DUPLICATE_DEPENDENCY_REFERENCE"
    SELF_DEPENDENCY = "CA_EVENT_SELF_DEPENDENCY"
    MISSING_DEPENDENCY = "CA_EVENT_MISSING_DEPENDENCY"
    DEPENDENCY_CYCLE = "CA_EVENT_DEPENDENCY_CYCLE"


@dataclass(frozen=True, slots=True)
class CorporateActionEventChild:
    """Represent one immutable child node in a corporate-action event graph."""

    transaction_id: str
    transaction_type: str
    child_role: str
    dependency_transaction_ids: tuple[str, ...] = ()
    child_sequence_hint: int | None = None
    target_instrument_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "transaction_id", _required_text(self.transaction_id, "transaction_id")
        )
        object.__setattr__(
            self,
            "transaction_type",
            _required_text(self.transaction_type, "transaction_type").upper(),
        )
        object.__setattr__(
            self, "child_role", _required_text(self.child_role, "child_role").upper()
        )
        if isinstance(self.dependency_transaction_ids, (str, bytes)):
            raise ValueError("dependency_transaction_ids must be a collection of transaction ids")
        object.__setattr__(
            self,
            "dependency_transaction_ids",
            tuple(
                _required_text(value, "dependency_transaction_ids")
                for value in self.dependency_transaction_ids
            ),
        )
        if self.child_sequence_hint is not None:
            if isinstance(self.child_sequence_hint, bool) or not isinstance(
                self.child_sequence_hint, int
            ):
                raise ValueError("child_sequence_hint must be an integer when provided")
            if self.child_sequence_hint < 0:
                raise ValueError("child_sequence_hint must be non-negative when provided")
        if self.target_instrument_id is not None:
            object.__setattr__(
                self,
                "target_instrument_id",
                _required_text(self.target_instrument_id, "target_instrument_id"),
            )


@dataclass(frozen=True, slots=True)
class CorporateActionEventGraph:
    """Represent one versioned parent event and its complete captured child set."""

    corporate_action_event_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    version: int
    children: tuple[CorporateActionEventChild, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "corporate_action_event_id",
            _required_text(self.corporate_action_event_id, "corporate_action_event_id"),
        )
        object.__setattr__(
            self,
            "linked_transaction_group_id",
            _required_text(self.linked_transaction_group_id, "linked_transaction_group_id"),
        )
        object.__setattr__(
            self,
            "parent_event_reference",
            _required_text(self.parent_event_reference, "parent_event_reference"),
        )
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise ValueError("version must be an integer")
        if self.version < 1:
            raise ValueError("version must be greater than zero")
        if not isinstance(self.children, tuple) or not all(
            isinstance(child, CorporateActionEventChild) for child in self.children
        ):
            raise ValueError("children must be a tuple of CorporateActionEventChild values")


@dataclass(frozen=True, slots=True)
class CorporateActionEventGraphFinding:
    """Describe one deterministic graph-readiness defect."""

    reason: CorporateActionEventGraphReason
    transaction_ids: tuple[str, ...]
    dependency_transaction_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CorporateActionEventExecutionPlan:
    """Return the deterministic order or the complete fail-closed finding set."""

    status: CorporateActionEventGraphStatus
    ordered_children: tuple[CorporateActionEventChild, ...]
    findings: tuple[CorporateActionEventGraphFinding, ...]
    examined_node_count: int
    examined_edge_count: int

    @property
    def ordered_transaction_ids(self) -> tuple[str, ...]:
        """Return the planned transaction identities without losing node evidence."""

        return tuple(child.transaction_id for child in self.ordered_children)


def resolve_corporate_action_event_graph(
    graph: CorporateActionEventGraph,
) -> CorporateActionEventExecutionPlan:
    """Resolve a deterministic dependency-respecting order or park the event."""

    findings: list[CorporateActionEventGraphFinding] = []
    children_by_id: dict[str, CorporateActionEventChild] = {}
    for child in graph.children:
        existing = children_by_id.get(child.transaction_id)
        if existing is None:
            children_by_id[child.transaction_id] = child
            continue
        reason = (
            CorporateActionEventGraphReason.DUPLICATE_CHILD_ID
            if existing == child
            else CorporateActionEventGraphReason.CONFLICTING_CHILD_DEFINITION
        )
        findings.append(
            CorporateActionEventGraphFinding(
                reason=reason,
                transaction_ids=(child.transaction_id,),
            )
        )

    if not graph.children:
        findings.append(
            CorporateActionEventGraphFinding(
                reason=CorporateActionEventGraphReason.EMPTY_EVENT,
                transaction_ids=(),
            )
        )

    if findings:
        return _parked(findings=findings, node_count=len(children_by_id), edge_count=0)

    dependants: dict[str, list[str]] = {transaction_id: [] for transaction_id in children_by_id}
    indegree = dict.fromkeys(children_by_id, 0)
    edge_count = 0
    for child in children_by_id.values():
        dependencies = child.dependency_transaction_ids
        unique_dependencies = set(dependencies)
        if len(unique_dependencies) != len(dependencies):
            findings.append(
                CorporateActionEventGraphFinding(
                    reason=CorporateActionEventGraphReason.DUPLICATE_DEPENDENCY_REFERENCE,
                    transaction_ids=(child.transaction_id,),
                    dependency_transaction_ids=_duplicates(dependencies),
                )
            )
        if child.transaction_id in unique_dependencies:
            findings.append(
                CorporateActionEventGraphFinding(
                    reason=CorporateActionEventGraphReason.SELF_DEPENDENCY,
                    transaction_ids=(child.transaction_id,),
                    dependency_transaction_ids=(child.transaction_id,),
                )
            )
        missing = tuple(sorted(unique_dependencies.difference(children_by_id)))
        if missing:
            findings.append(
                CorporateActionEventGraphFinding(
                    reason=CorporateActionEventGraphReason.MISSING_DEPENDENCY,
                    transaction_ids=(child.transaction_id,),
                    dependency_transaction_ids=missing,
                )
            )
        for dependency_id in sorted(unique_dependencies.intersection(children_by_id)):
            if dependency_id == child.transaction_id:
                continue
            dependants[dependency_id].append(child.transaction_id)
            indegree[child.transaction_id] += 1
            edge_count += 1

    if findings:
        return _parked(
            findings=findings,
            node_count=len(children_by_id),
            edge_count=edge_count,
        )

    ready: list[tuple[tuple[int, int, str, str, str], str]] = []
    for transaction_id, degree in indegree.items():
        if degree == 0:
            child = children_by_id[transaction_id]
            heapq.heappush(ready, (_execution_order_key(child), transaction_id))

    ordered: list[CorporateActionEventChild] = []
    examined_edge_count = 0
    while ready:
        _, transaction_id = heapq.heappop(ready)
        child = children_by_id[transaction_id]
        ordered.append(child)
        for dependant_id in dependants[transaction_id]:
            examined_edge_count += 1
            indegree[dependant_id] -= 1
            if indegree[dependant_id] == 0:
                dependant = children_by_id[dependant_id]
                heapq.heappush(ready, (_execution_order_key(dependant), dependant_id))

    if len(ordered) != len(children_by_id):
        cycle_ids = tuple(
            sorted(transaction_id for transaction_id, degree in indegree.items() if degree)
        )
        return CorporateActionEventExecutionPlan(
            status=CorporateActionEventGraphStatus.PARKED,
            ordered_children=(),
            findings=(
                CorporateActionEventGraphFinding(
                    reason=CorporateActionEventGraphReason.DEPENDENCY_CYCLE,
                    transaction_ids=cycle_ids,
                ),
            ),
            examined_node_count=len(ordered),
            examined_edge_count=examined_edge_count,
        )

    return CorporateActionEventExecutionPlan(
        status=CorporateActionEventGraphStatus.READY,
        ordered_children=tuple(ordered),
        findings=(),
        examined_node_count=len(ordered),
        examined_edge_count=examined_edge_count,
    )


def _execution_order_key(child: CorporateActionEventChild) -> tuple[int, int, str, str, str]:
    sequence = child.child_sequence_hint if child.child_sequence_hint is not None else 2_147_483_647
    return (
        corporate_action_dependency_rank(child),
        sequence,
        child.target_instrument_id or "",
        child.child_role,
        child.transaction_id,
    )


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _parked(
    *,
    findings: Iterable[CorporateActionEventGraphFinding],
    node_count: int,
    edge_count: int,
) -> CorporateActionEventExecutionPlan:
    return CorporateActionEventExecutionPlan(
        status=CorporateActionEventGraphStatus.PARKED,
        ordered_children=(),
        findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.reason,
                    finding.transaction_ids,
                    finding.dependency_transaction_ids,
                ),
            )
        ),
        examined_node_count=node_count,
        examined_edge_count=edge_count,
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
