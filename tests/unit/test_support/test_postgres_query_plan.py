"""Tests for shared PostgreSQL JSON query-plan traversal."""

from tests.test_support.postgres_query_plan import plan_index_names, plan_node_types


def test_query_plan_traversal_collects_nested_indexes_and_node_types() -> None:
    plan = [
        {
            "Plan": {
                "Node Type": "Aggregate",
                "Plans": [
                    {
                        "Node Type": "Bitmap Heap Scan",
                        "Plans": [
                            {
                                "Node Type": "Bitmap Index Scan",
                                "Index Name": "ix_outbox_events_aggregate_id",
                            }
                        ],
                    }
                ],
            }
        }
    ]

    assert plan_index_names(plan) == {"ix_outbox_events_aggregate_id"}
    assert plan_node_types(plan) == {
        "Aggregate",
        "Bitmap Heap Scan",
        "Bitmap Index Scan",
    }


def test_query_plan_traversal_ignores_non_plan_scalars() -> None:
    plan: dict[str, object] = {
        "Planning Time": 0.2,
        "Execution Time": 0.1,
        "Index Name": 123,
        "Node Type": None,
        "Triggers": [],
    }

    assert plan_index_names(plan) == set()
    assert plan_node_types(plan) == set()
