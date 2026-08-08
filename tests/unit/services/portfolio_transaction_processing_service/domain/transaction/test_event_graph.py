"""Test the reusable transaction-domain directed-event graph kernel."""

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    event_graph,
)

DirectedEventGraphReason = event_graph.DirectedEventGraphReason
DirectedEventGraphStatus = event_graph.DirectedEventGraphStatus
DirectedEventNode = event_graph.DirectedEventNode
resolve_directed_event_graph = event_graph.resolve_directed_event_graph


def _node(
    node_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    definition: str | None = None,
    order: str | None = None,
) -> DirectedEventNode:
    return DirectedEventNode(
        node_id=node_id,
        dependency_node_ids=dependencies,
        definition_fingerprint=definition or f"definition:{node_id}",
        order_key=(order or node_id,),
    )


def test_directed_event_graph_returns_canonical_dependency_order() -> None:
    plan = resolve_directed_event_graph(
        (_node("C", dependencies=("A", "B")), _node("B"), _node("A"))
    )

    assert plan.status == DirectedEventGraphStatus.VALID
    assert plan.ordered_node_ids == ("A", "B", "C")
    assert plan.declared_node_count == 3
    assert plan.declared_edge_count == 2


@pytest.mark.parametrize(
    ("nodes", "reason"),
    [
        ((), DirectedEventGraphReason.EMPTY_GRAPH),
        ((_node("A"), _node("A")), DirectedEventGraphReason.DUPLICATE_NODE_ID),
        (
            (_node("A"), _node("A", definition="changed")),
            DirectedEventGraphReason.CONFLICTING_NODE_DEFINITION,
        ),
        (
            (_node("A"), _node("B", dependencies=("A", "A"))),
            DirectedEventGraphReason.DUPLICATE_EDGE,
        ),
        ((_node("A", dependencies=("A",)),), DirectedEventGraphReason.SELF_DEPENDENCY),
        (
            (_node("A", dependencies=("MISSING",)),),
            DirectedEventGraphReason.MISSING_DEPENDENCY,
        ),
    ],
)
def test_directed_event_graph_rejects_structural_defects(
    nodes: tuple[DirectedEventNode, ...],
    reason: DirectedEventGraphReason,
) -> None:
    plan = resolve_directed_event_graph(nodes)

    assert plan.status == DirectedEventGraphStatus.INVALID
    assert plan.ordered_nodes == ()
    assert reason in {finding.reason for finding in plan.findings}


def test_directed_event_graph_separates_cycle_members_from_blocked_descendants() -> None:
    plan = resolve_directed_event_graph(
        (
            _node("A", dependencies=("B",)),
            _node("B", dependencies=("A",)),
            _node("C", dependencies=("A",)),
        )
    )

    assert plan.findings[0].reason == DirectedEventGraphReason.BLOCKED_BY_CYCLE
    assert plan.findings[0].node_ids == ("C",)
    assert plan.findings[1].reason == DirectedEventGraphReason.DEPENDENCY_CYCLE
    assert plan.findings[1].node_ids == ("A", "B")


def test_directed_event_graph_reports_disjoint_cycles_separately() -> None:
    plan = resolve_directed_event_graph(
        (
            _node("A", dependencies=("B",)),
            _node("B", dependencies=("A",)),
            _node("C", dependencies=("D",)),
            _node("D", dependencies=("C",)),
        )
    )

    cycle_findings = [
        finding
        for finding in plan.findings
        if finding.reason == DirectedEventGraphReason.DEPENDENCY_CYCLE
    ]
    assert [finding.node_ids for finding in cycle_findings] == [("A", "B"), ("C", "D")]


def test_directed_event_graph_handles_one_thousand_nodes_without_recursion() -> None:
    nodes = tuple(
        _node(
            f"NODE-{index:04d}",
            dependencies=((f"NODE-{index - 1:04d}",) if index else ()),
        )
        for index in range(1_000)
    )

    plan = resolve_directed_event_graph(reversed(nodes))

    assert plan.status == DirectedEventGraphStatus.VALID
    assert plan.declared_node_count == 1_000
    assert plan.declared_edge_count == 999
    assert plan.ordered_node_ids[0] == "NODE-0000"
    assert plan.ordered_node_ids[-1] == "NODE-0999"
