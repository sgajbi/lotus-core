from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.operations.database_evidence.contract import (
    DatabaseEvidenceContractError,
    HotPathPlanResult,
    build_hot_path_evidence_artifact,
    evaluate_hot_path_plan,
    load_hot_path_scenario_catalog,
)

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")


def _plan(
    *,
    node_type: str = "Index Scan",
    actual_rows: int = 25,
    actual_loops: int = 1,
    index_name: str | None = "ix_governed_hot_path",
) -> list[dict[str, object]]:
    node: dict[str, object] = {
        "Node Type": node_type,
        "Actual Rows": actual_rows,
        "Actual Loops": actual_loops,
    }
    if index_name is not None:
        node["Index Name"] = index_name
    return [{"Plan": node, "Planning Time": 0.1, "Execution Time": 0.2}]


def test_catalog_is_versioned_complete_and_deterministically_ordered() -> None:
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)

    assert catalog.evidence_posture == "report_only"
    assert [scenario.scenario_id for scenario in catalog.scenarios] == [
        "latest_position_snapshot",
        "operations_support_page",
        "reconciliation_estate_scan",
        "transaction_ledger_count",
        "transaction_ledger_page",
        "valuation_job_claim",
    ]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda payload: payload.update(schema_version="v0"), "catalog_schema_version_unsupported"),
        (
            lambda payload: payload["scenarios"].append(payload["scenarios"][0]),
            "catalog_scenario_duplicate",
        ),
        (
            lambda payload: payload["scenarios"][0].update(unowned_field=True),
            "catalog_scenario_shape_invalid",
        ),
    ],
)
def test_catalog_rejects_stale_duplicate_and_unknown_shapes(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    mutation(payload)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DatabaseEvidenceContractError, match=reason):
        load_hot_path_scenario_catalog(path)


def test_plan_evaluator_accepts_indexed_bounded_optimizer_alternative() -> None:
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).scenarios[0]

    result = evaluate_hot_path_plan(
        scenario,
        _plan(node_type="Bitmap Index Scan", index_name="ix_alternative"),
    )

    assert result.status == "passed"
    assert result.index_names == ("ix_alternative",)
    assert result.violations == ()


@pytest.mark.parametrize(
    ("plan", "violation"),
    [
        (_plan(node_type="Seq Scan", index_name=None), "prohibited_node_type:Seq Scan"),
        (_plan(node_type="WindowAgg", index_name=None), "prohibited_node_type:WindowAgg"),
        (_plan(node_type="Sort", index_name=None), "indexed_access_missing"),
        (_plan(actual_rows=501), "root_actual_rows_exceeded"),
        (_plan(actual_rows=500, actual_loops=61), "rows_examined_exceeded"),
    ],
)
def test_plan_evaluator_rejects_governed_regressions(plan, violation: str) -> None:
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).scenarios[0]

    result = evaluate_hot_path_plan(scenario, plan)

    assert result.status == "failed"
    assert violation in result.violations


@pytest.mark.parametrize(
    "plan",
    [
        {},
        [{"Plan": {"Node Type": "Index Scan", "Actual Rows": 1}}],
        [{"Plan": {"Node Type": "Index Scan", "Actual Rows": 1, "Actual Loops": -1}}],
        [{"Plan": {"Node Type": "Index Scan", "Actual Rows": 1, "Actual Loops": 1, "Plans": {}}}],
    ],
)
def test_plan_evaluator_fails_closed_on_malformed_runtime_evidence(plan) -> None:
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).scenarios[0]

    with pytest.raises(DatabaseEvidenceContractError):
        evaluate_hot_path_plan(scenario, plan)


def test_artifact_identity_is_stable_and_omits_execution_secrets() -> None:
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
    results = tuple(
        HotPathPlanResult(
            scenario_id=scenario.scenario_id,
            status="passed",
            root_actual_rows=1,
            rows_examined=1,
            node_types=("Index Scan",),
            index_names=("ix_governed_hot_path",),
            sequential_scan_relations=(),
            violations=(),
        )
        for scenario in catalog.scenarios
    )
    first = build_hot_path_evidence_artifact(
        catalog=catalog,
        results=results,
        git_sha="a" * 40,
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    second = build_hot_path_evidence_artifact(
        catalog=catalog,
        results=results,
        git_sha="a" * 40,
        generated_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )

    assert first["content_hash"] == second["content_hash"]
    serialized = json.dumps(first).lower()
    assert "postgresql://" not in serialized
    assert "password=" not in serialized
    assert "statement" not in serialized
    assert "parameters" not in serialized


def test_artifact_requires_every_catalog_scenario_once_and_in_order() -> None:
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
    result = HotPathPlanResult(
        scenario_id=catalog.scenarios[0].scenario_id,
        status="passed",
        root_actual_rows=1,
        rows_examined=1,
        node_types=("Index Scan",),
        index_names=("ix_governed_hot_path",),
        sequential_scan_relations=(),
        violations=(),
    )

    with pytest.raises(
        DatabaseEvidenceContractError,
        match="artifact_scenario_set_or_order_invalid",
    ):
        build_hot_path_evidence_artifact(
            catalog=catalog,
            results=(result,),
            git_sha="a" * 40,
            generated_at=datetime.now(timezone.utc),
        )
