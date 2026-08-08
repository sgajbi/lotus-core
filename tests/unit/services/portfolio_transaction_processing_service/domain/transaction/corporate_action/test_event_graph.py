"""Test fail-closed corporate-action parent event dependency planning."""

from itertools import permutations

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

CorporateActionEventChild = corporate_action.CorporateActionEventChild
CorporateActionEventGraph = corporate_action.CorporateActionEventGraph
CorporateActionEventGraphReason = corporate_action.CorporateActionEventGraphReason
CorporateActionEventGraphStatus = corporate_action.CorporateActionEventGraphStatus
resolve_corporate_action_event_graph = corporate_action.resolve_corporate_action_event_graph


def _child(
    transaction_id: str,
    transaction_type: str,
    *,
    role: str,
    dependencies: tuple[str, ...] = (),
    sequence: int | None = None,
    target: str | None = None,
) -> CorporateActionEventChild:
    return CorporateActionEventChild(
        transaction_id=transaction_id,
        transaction_type=transaction_type,
        child_role=role,
        dependency_transaction_ids=dependencies,
        child_sequence_hint=sequence,
        target_instrument_id=target,
    )


def _graph(*children: CorporateActionEventChild) -> CorporateActionEventGraph:
    return CorporateActionEventGraph(
        corporate_action_event_id="CA-EVENT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="UPSTREAM-CA-001",
        version=1,
        children=children,
    )


def test_event_graph_orders_multi_target_and_mixed_consideration_by_dependencies() -> None:
    source = _child("SOURCE", "DEMERGER_OUT", role="SOURCE_POSITION_REDUCE")
    target_b = _child(
        "TARGET-B",
        "DEMERGER_IN",
        role="TARGET_POSITION_ADD",
        dependencies=("SOURCE",),
        sequence=2,
        target="SEC-B",
    )
    target_a = _child(
        "TARGET-A",
        "DEMERGER_IN",
        role="TARGET_POSITION_ADD",
        dependencies=("SOURCE",),
        sequence=1,
        target="SEC-A",
    )
    cash = _child(
        "CASH",
        "CASH_CONSIDERATION",
        role="CASH_CONSIDERATION",
        dependencies=("TARGET-A", "TARGET-B"),
    )

    plan = resolve_corporate_action_event_graph(_graph(cash, target_b, source, target_a))

    assert plan.status == CorporateActionEventGraphStatus.READY
    assert plan.ordered_transaction_ids == ("SOURCE", "TARGET-A", "TARGET-B", "CASH")
    assert plan.findings == ()
    assert plan.examined_node_count == 4
    assert plan.examined_edge_count == 4


def test_event_graph_output_is_independent_of_child_arrival_order() -> None:
    children = (
        _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE"),
        _child(
            "TARGET-A",
            "SPIN_IN",
            role="TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            target="SEC-A",
        ),
        _child(
            "TARGET-B",
            "SPIN_IN",
            role="TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            target="SEC-B",
        ),
    )

    orders = {
        resolve_corporate_action_event_graph(_graph(*candidate)).ordered_transaction_ids
        for candidate in permutations(children)
    }

    assert orders == {("SOURCE", "TARGET-A", "TARGET-B")}


@pytest.mark.parametrize(
    ("children", "reason"),
    [
        ((), CorporateActionEventGraphReason.EMPTY_EVENT),
        (
            (
                _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE"),
                _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE"),
            ),
            CorporateActionEventGraphReason.DUPLICATE_CHILD_ID,
        ),
        (
            (
                _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE"),
                _child("SOURCE", "DEMERGER_OUT", role="SOURCE_POSITION_REDUCE"),
            ),
            CorporateActionEventGraphReason.CONFLICTING_CHILD_DEFINITION,
        ),
        (
            (
                _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE"),
                _child(
                    "TARGET",
                    "SPIN_IN",
                    role="TARGET_POSITION_ADD",
                    dependencies=("SOURCE", "SOURCE"),
                ),
            ),
            CorporateActionEventGraphReason.DUPLICATE_DEPENDENCY_REFERENCE,
        ),
        (
            (
                _child(
                    "SOURCE",
                    "SPIN_OFF",
                    role="SOURCE_POSITION_REDUCE",
                    dependencies=("SOURCE",),
                ),
            ),
            CorporateActionEventGraphReason.SELF_DEPENDENCY,
        ),
        (
            (
                _child(
                    "TARGET",
                    "SPIN_IN",
                    role="TARGET_POSITION_ADD",
                    dependencies=("MISSING",),
                ),
            ),
            CorporateActionEventGraphReason.MISSING_DEPENDENCY,
        ),
    ],
)
def test_event_graph_parks_invalid_child_sets(
    children: tuple[CorporateActionEventChild, ...],
    reason: CorporateActionEventGraphReason,
) -> None:
    plan = resolve_corporate_action_event_graph(_graph(*children))

    assert plan.status == CorporateActionEventGraphStatus.PARKED
    assert plan.ordered_children == ()
    assert reason in {finding.reason for finding in plan.findings}


def test_event_graph_parks_cycles_without_returning_a_partial_plan() -> None:
    plan = resolve_corporate_action_event_graph(
        _graph(
            _child(
                "TARGET-A",
                "SPIN_IN",
                role="TARGET_POSITION_ADD",
                dependencies=("TARGET-B",),
            ),
            _child(
                "TARGET-B",
                "SPIN_IN",
                role="TARGET_POSITION_ADD",
                dependencies=("TARGET-A",),
            ),
        )
    )

    assert plan.status == CorporateActionEventGraphStatus.PARKED
    assert plan.ordered_children == ()
    assert len(plan.findings) == 1
    assert plan.findings[0].reason == CorporateActionEventGraphReason.DEPENDENCY_CYCLE
    assert plan.findings[0].transaction_ids == ("TARGET-A", "TARGET-B")


def test_event_graph_resolves_one_thousand_children_with_linear_traversal_counts() -> None:
    source = _child("SOURCE", "SPIN_OFF", role="SOURCE_POSITION_REDUCE")
    targets = tuple(
        _child(
            f"TARGET-{index:04d}",
            "SPIN_IN",
            role="TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            sequence=index,
            target=f"SEC-{index:04d}",
        )
        for index in range(999)
    )

    plan = resolve_corporate_action_event_graph(_graph(*reversed((source, *targets))))

    assert plan.status == CorporateActionEventGraphStatus.READY
    assert plan.examined_node_count == 1_000
    assert plan.examined_edge_count == 999
    assert plan.ordered_transaction_ids[0] == "SOURCE"
    assert plan.ordered_transaction_ids[-1] == "TARGET-0998"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CorporateActionEventChild(" ", "SPIN_OFF", "SOURCE"),
        lambda: CorporateActionEventChild("SOURCE", " ", "SOURCE"),
        lambda: CorporateActionEventChild("SOURCE", "SPIN_OFF", " "),
        lambda: CorporateActionEventChild("SOURCE", "SPIN_OFF", "SOURCE", child_sequence_hint=-1),
        lambda: CorporateActionEventChild("SOURCE", "SPIN_OFF", "SOURCE", child_sequence_hint=True),
        lambda: CorporateActionEventChild(
            "SOURCE",
            "SPIN_OFF",
            "SOURCE",
            dependency_transaction_ids="SOURCE",  # type: ignore[arg-type]
        ),
        lambda: CorporateActionEventGraph("EVENT", "GROUP", "PARENT", 0, ()),
        lambda: CorporateActionEventGraph("EVENT", "GROUP", "PARENT", True, ()),
    ],
)
def test_event_graph_rejects_invalid_immutable_identity(factory) -> None:
    with pytest.raises(ValueError):
        factory()
