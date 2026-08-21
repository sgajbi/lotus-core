from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from scripts.operations.database_evidence.contract import (
    HotPathPlanResult,
    load_hot_path_plan_fragments,
    load_hot_path_scenario_catalog,
    write_hot_path_plan_fragment,
)
from scripts.operations.database_evidence.runtime_fragments import FRAGMENT_DIRECTORY_ENV
from scripts.operations.database_hot_path_evidence import (
    build_evidence_plan,
    execute_evidence_tests,
    resolve_clean_git_sha,
)

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")


def _result(scenario_id: str) -> HotPathPlanResult:
    return HotPathPlanResult(
        scenario_id=scenario_id,
        status="passed",
        root_actual_rows=1,
        rows_examined=1,
        node_types=("Index Scan",),
        index_names=("ix_governed",),
        sequential_scan_relations=(),
        violations=(),
    )


def test_command_plan_is_exact_and_deduplicated() -> None:
    plan = build_evidence_plan()

    assert len(plan.pytest_nodes) == 5
    assert len(set(plan.pytest_nodes)) == len(plan.pytest_nodes)
    assert all("::test_" in node for node in plan.pytest_nodes)


def test_fragment_round_trip_requires_every_catalog_scenario(tmp_path: Path) -> None:
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
    for scenario in catalog.scenarios:
        write_hot_path_plan_fragment(tmp_path, _result(scenario.scenario_id))

    assert load_hot_path_plan_fragments(tmp_path, catalog=catalog) == tuple(
        _result(scenario.scenario_id) for scenario in catalog.scenarios
    )


def test_evidence_test_runner_uses_exact_nodes_and_isolated_fragment_directory(
    tmp_path: Path,
) -> None:
    runner = Mock(return_value=Mock(returncode=0))
    plan = build_evidence_plan()

    assert (
        execute_evidence_tests(
            plan,
            fragment_directory=tmp_path,
            command_runner=runner,
        )
        == 0
    )

    command = runner.call_args.args[0]
    kwargs = runner.call_args.kwargs
    assert command[:4] == [command[0], "-m", "pytest", "-q"]
    assert tuple(command[4:]) == plan.pytest_nodes
    assert kwargs["env"][FRAGMENT_DIRECTORY_ENV] == str(tmp_path.resolve())
    assert "shell" not in kwargs


def test_fragment_loader_rejects_unknown_or_malformed_output(tmp_path: Path) -> None:
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
    for scenario in catalog.scenarios:
        write_hot_path_plan_fragment(tmp_path, _result(scenario.scenario_id))
    (tmp_path / "unknown.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")

    try:
        load_hot_path_plan_fragments(tmp_path, catalog=catalog)
    except ValueError as exc:
        assert str(exc) == "fragment_scenario_set_invalid"
    else:
        raise AssertionError("unknown fragment must fail closed")


def test_source_revision_requires_clean_worktree() -> None:
    runner = Mock(return_value=Mock(stdout=" M governed.py\n"))

    try:
        resolve_clean_git_sha(command_runner=runner)
    except ValueError as exc:
        assert str(exc) == "source_worktree_not_clean"
    else:
        raise AssertionError("dirty source must fail closed")
    assert runner.call_count == 1


def test_source_revision_uses_exact_clean_head() -> None:
    runner = Mock(
        side_effect=(
            Mock(stdout=""),
            Mock(stdout="a" * 40 + "\n"),
        )
    )

    assert resolve_clean_git_sha(command_runner=runner) == "a" * 40
    assert runner.call_args_list[0].args[0] == ["git", "status", "--porcelain"]
    assert runner.call_args_list[1].args[0] == ["git", "rev-parse", "HEAD"]
