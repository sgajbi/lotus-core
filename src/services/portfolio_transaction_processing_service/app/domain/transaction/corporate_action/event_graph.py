"""Adapt corporate-action child declarations to structural event-graph validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from ..event_graph import (
    DirectedEventGraphReason,
    DirectedEventGraphStatus,
    DirectedEventNode,
    resolve_directed_event_graph,
)
from .ordering import corporate_action_dependency_rank


class CorporateActionEventStructuralStatus(StrEnum):
    """Classify graph structure without claiming manifest completeness or readiness."""

    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"
    INVALID = "INVALID"


class CorporateActionEventGraphReason(StrEnum):
    """Expose corporate-action-owned structural defect reasons."""

    EMPTY_EVENT = "CA_EVENT_EMPTY"
    DUPLICATE_CHILD_ID = "CA_EVENT_DUPLICATE_CHILD_ID"
    CONFLICTING_CHILD_DEFINITION = "CA_EVENT_CONFLICTING_CHILD_DEFINITION"
    DUPLICATE_DEPENDENCY_REFERENCE = "CA_EVENT_DUPLICATE_DEPENDENCY_REFERENCE"
    SELF_DEPENDENCY = "CA_EVENT_SELF_DEPENDENCY"
    MISSING_DEPENDENCY = "CA_EVENT_MISSING_DEPENDENCY"
    DEPENDENCY_CYCLE = "CA_EVENT_DEPENDENCY_CYCLE"
    BLOCKED_BY_CYCLE = "CA_EVENT_BLOCKED_BY_CYCLE"


@dataclass(frozen=True, slots=True)
class CorporateActionEventChild:
    """Represent one observed child declaration; it is not a completeness manifest."""

    transaction_id: str
    transaction_type: str
    child_role: str
    dependency_transaction_ids: tuple[str, ...] = ()
    child_sequence_hint: int | None = None
    target_instrument_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _required_text(self.transaction_id, "transaction_id"),
        )
        object.__setattr__(
            self,
            "transaction_type",
            _required_text(self.transaction_type, "transaction_type").upper(),
        )
        object.__setattr__(
            self,
            "child_role",
            _required_text(self.child_role, "child_role").upper(),
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
    """Represent a versioned parent identity and currently observed child declarations."""

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
    """Describe one deterministic structural defect."""

    reason: CorporateActionEventGraphReason
    transaction_ids: tuple[str, ...]
    dependency_transaction_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CorporateActionEventStructuralPlan:
    """Return structural ordering without implying that the event is complete or executable."""

    status: CorporateActionEventStructuralStatus
    ordered_children: tuple[CorporateActionEventChild, ...]
    findings: tuple[CorporateActionEventGraphFinding, ...]
    declared_node_count: int
    declared_edge_count: int

    @property
    def ordered_transaction_ids(self) -> tuple[str, ...]:
        """Return canonical child identities."""

        return tuple(child.transaction_id for child in self.ordered_children)


def resolve_corporate_action_event_graph(
    graph: CorporateActionEventGraph,
) -> CorporateActionEventStructuralPlan:
    """Validate observed child structure without claiming parent-manifest readiness."""

    nodes = tuple(_directed_node(child) for child in graph.children)
    children_by_transaction_id = {child.transaction_id: child for child in graph.children}
    plan = resolve_directed_event_graph(nodes)
    findings = tuple(
        CorporateActionEventGraphFinding(
            reason=_CORPORATE_ACTION_REASON_BY_GRAPH_REASON[finding.reason],
            transaction_ids=finding.node_ids,
            dependency_transaction_ids=finding.dependency_node_ids,
        )
        for finding in plan.findings
    )
    ordered_children = tuple(
        children_by_transaction_id[node.node_id] for node in plan.ordered_nodes
    )
    return CorporateActionEventStructuralPlan(
        status=(
            CorporateActionEventStructuralStatus.STRUCTURALLY_VALID
            if plan.status == DirectedEventGraphStatus.VALID
            else CorporateActionEventStructuralStatus.INVALID
        ),
        ordered_children=ordered_children,
        findings=findings,
        declared_node_count=plan.declared_node_count,
        declared_edge_count=plan.declared_edge_count,
    )


_CORPORATE_ACTION_REASON_BY_GRAPH_REASON = {
    DirectedEventGraphReason.EMPTY_GRAPH: CorporateActionEventGraphReason.EMPTY_EVENT,
    DirectedEventGraphReason.DUPLICATE_NODE_ID: (
        CorporateActionEventGraphReason.DUPLICATE_CHILD_ID
    ),
    DirectedEventGraphReason.CONFLICTING_NODE_DEFINITION: (
        CorporateActionEventGraphReason.CONFLICTING_CHILD_DEFINITION
    ),
    DirectedEventGraphReason.DUPLICATE_EDGE: (
        CorporateActionEventGraphReason.DUPLICATE_DEPENDENCY_REFERENCE
    ),
    DirectedEventGraphReason.SELF_DEPENDENCY: CorporateActionEventGraphReason.SELF_DEPENDENCY,
    DirectedEventGraphReason.MISSING_DEPENDENCY: (
        CorporateActionEventGraphReason.MISSING_DEPENDENCY
    ),
    DirectedEventGraphReason.DEPENDENCY_CYCLE: (CorporateActionEventGraphReason.DEPENDENCY_CYCLE),
    DirectedEventGraphReason.BLOCKED_BY_CYCLE: (CorporateActionEventGraphReason.BLOCKED_BY_CYCLE),
}


def _directed_node(child: CorporateActionEventChild) -> DirectedEventNode:
    sequence = child.child_sequence_hint if child.child_sequence_hint is not None else 2_147_483_647
    payload = {
        "child_role": child.child_role,
        "child_sequence_hint": child.child_sequence_hint,
        "dependency_transaction_ids": list(child.dependency_transaction_ids),
        "target_instrument_id": child.target_instrument_id,
        "transaction_id": child.transaction_id,
        "transaction_type": child.transaction_type,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return DirectedEventNode(
        node_id=child.transaction_id,
        dependency_node_ids=child.dependency_transaction_ids,
        definition_fingerprint="sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        order_key=(
            f"{corporate_action_dependency_rank(child):04d}",
            f"{sequence:010d}",
            child.target_instrument_id or "-",
            child.child_role,
            child.transaction_id,
        ),
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
