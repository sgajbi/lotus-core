from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.operations.outbox_capacity_acceptance import (
    OutboxCapacityAcceptancePlan,
    build_acceptance_plan,
    execute_acceptance_plan,
)


def _contract() -> dict[str, object]:
    return {
        "acceptance_evidence": {
            "restart": ["make test-derived-state-recovery-gate"],
            "rollback": ["tests/integration/test_outbox.py::test_rollback"],
            "duplicate": [
                "tests/integration/test_outbox.py::test_duplicate",
                "tests/integration/test_outbox.py::test_rollback",
            ],
        }
    }


def test_build_acceptance_plan_deduplicates_contract_references() -> None:
    plan = build_acceptance_plan(_contract())

    assert plan.pytest_nodes == (
        "tests/integration/test_outbox.py::test_duplicate",
        "tests/integration/test_outbox.py::test_rollback",
    )
    assert plan.make_targets == ("test-derived-state-recovery-gate",)


@pytest.mark.parametrize(
    "reference",
    [
        "python arbitrary.py",
        "make test-derived-state-recovery-gate && echo unsafe",
        "src/runtime.py::test_not_a_repository_test",
        "tests/integration/test_outbox.py",
    ],
)
def test_build_acceptance_plan_rejects_unsupported_commands(reference: str) -> None:
    contract = {"acceptance_evidence": {"unsafe": [reference]}}

    with pytest.raises(ValueError, match="unsupported reference"):
        build_acceptance_plan(contract)


def test_execute_acceptance_plan_runs_one_pytest_batch_then_make_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "scripts.operations.outbox_capacity_acceptance.shutil.which",
        lambda _name: "make",
    )
    plan = OutboxCapacityAcceptancePlan(
        pytest_nodes=("tests/integration/test_outbox.py::test_one",),
        make_targets=("test-derived-state-recovery-gate",),
    )

    assert execute_acceptance_plan(plan, repo_root=tmp_path, command_runner=run) == 0
    assert commands[0][1:4] == ["-m", "pytest", "-q"]
    assert commands[0][-1] == "tests/integration/test_outbox.py::test_one"
    assert commands[1] == ["make", "test-derived-state-recovery-gate"]


def test_execute_acceptance_plan_stops_before_make_when_pytest_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(
        "scripts.operations.outbox_capacity_acceptance.shutil.which",
        lambda _name: "make",
    )
    plan = OutboxCapacityAcceptancePlan(
        pytest_nodes=("tests/integration/test_outbox.py::test_one",),
        make_targets=("test-derived-state-recovery-gate",),
    )

    assert execute_acceptance_plan(plan, repo_root=tmp_path, command_runner=run) == 7
    assert len(commands) == 1
