"""Execute the failure-mode evidence declared by the governed outbox capacity contract."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.quality.outbox_capacity_profile_guard import (
    CONTRACT_PATH,
    REPO_ROOT,
    _load_json,
    validate_outbox_capacity_contract,
)

_MAKE_REFERENCE = re.compile(r"^make ([A-Za-z0-9_.-]+)$")


@dataclass(frozen=True, slots=True)
class OutboxCapacityAcceptancePlan:
    """Deterministic direct-test and repository-command execution plan."""

    pytest_nodes: tuple[str, ...]
    make_targets: tuple[str, ...]


def build_acceptance_plan(contract: dict[str, Any]) -> OutboxCapacityAcceptancePlan:
    """Build a deduplicated plan without evaluating contract text as a shell command."""

    evidence = contract.get("acceptance_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("Outbox capacity contract has no acceptance_evidence object")

    pytest_nodes: list[str] = []
    make_targets: list[str] = []
    for failure_mode in sorted(evidence):
        references = evidence[failure_mode]
        if not isinstance(references, list) or not references:
            raise ValueError(f"Acceptance evidence '{failure_mode}' has no references")
        for raw_reference in references:
            reference = str(raw_reference).strip().replace("\\", "/")
            make_match = _MAKE_REFERENCE.fullmatch(reference)
            if make_match is not None:
                target = make_match.group(1)
                if target not in make_targets:
                    make_targets.append(target)
                continue
            path_value, separator, test_name = reference.partition("::")
            if (
                not separator
                or not path_value.startswith("tests/")
                or not path_value.endswith(".py")
                or not test_name.startswith("test_")
            ):
                raise ValueError(
                    f"Acceptance evidence '{failure_mode}' has unsupported reference: {reference}"
                )
            if reference not in pytest_nodes:
                pytest_nodes.append(reference)

    if not pytest_nodes:
        raise ValueError("Outbox capacity acceptance has no direct pytest nodes")
    return OutboxCapacityAcceptancePlan(
        pytest_nodes=tuple(pytest_nodes),
        make_targets=tuple(make_targets),
    )


def execute_acceptance_plan(
    plan: OutboxCapacityAcceptancePlan,
    *,
    repo_root: Path = REPO_ROOT,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """Run direct nodes once, then approved repository targets, stopping on first failure."""

    pytest_result = command_runner(
        [sys.executable, "-m", "pytest", "-q", *plan.pytest_nodes],
        cwd=repo_root,
        check=False,
        text=True,
    )
    if pytest_result.returncode != 0:
        return int(pytest_result.returncode)

    make_executable = shutil.which("make")
    if plan.make_targets and make_executable is None:
        raise RuntimeError("make executable is required for outbox capacity acceptance")
    for target in plan.make_targets:
        result = command_runner(
            [str(make_executable), target],
            cwd=repo_root,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            return int(result.returncode)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract = _load_json(REPO_ROOT / args.contract)
    findings = validate_outbox_capacity_contract(contract, repo_root=REPO_ROOT)
    if findings:
        print("Outbox capacity acceptance refused an invalid contract:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    plan = build_acceptance_plan(contract)
    if args.plan_only:
        print(json.dumps(asdict(plan), indent=2, sort_keys=True))
        return 0
    return execute_acceptance_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
