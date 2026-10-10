"""Fail closed on missing lane authority, omitted proof or duplicated full-unit ownership."""

from __future__ import annotations

import yaml

from scripts.quality.change_classification import ROOT
from scripts.quality.pr_validation.policy import TARGETS, TEST_TARGETS

EXEMPT_PR_JOBS = {"workflow-lint", "windows-lock-closures", "lint-typecheck-contracts-security"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def runs(job: dict) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def validate_workflows(pr: dict, main: dict, feature: dict) -> None:
    require(
        bool(pr.get("jobs")) and bool(main.get("jobs")) and bool(feature.get("jobs")),
        "all three delivery workflows must be present and nonempty",
    )
    expected_matrix = {(suite, f"pr-{target}") for target, suite in TEST_TARGETS.items()}
    observed_matrix = {
        (row["suite"], row["target"])
        for row in pr["jobs"]["test-suites"]["strategy"]["matrix"]["include"]
    }
    require(
        observed_matrix == expected_matrix, "PR matrix must preserve every full native test suite"
    )
    for name, job in pr["jobs"].items():
        require("if" not in job, f"required PR job must run unconditionally: {name}")
        if name in EXEMPT_PR_JOBS:
            continue
        classifiers = [step for step in job["steps"] if step.get("id") == "classify"]
        require(
            len(classifiers) == 1
            and classifiers[0].get("run") == "make change-classification"
            and "if" not in classifiers[0],
            f"missing unconditional classifier: {name}",
        )
        enforcement = [step for step in job["steps"] if step.get("id") == "enforce"]
        require(
            len(enforcement) == 1 and "if" not in enforcement[0],
            f"missing unconditional enforcement: {name}",
        )
        target = enforcement[0]["run"].removeprefix("make ")
        require(
            target == "${{ matrix.target }}" or target in {f"pr-{item}" for item in TARGETS},
            f"runtime enforcement bypasses fixed PR selection: {name}",
        )
        require(
            any(
                step.get("with", {}).get("path") == "output/pr-validation/*.json"
                and step.get("if") == "always()"
                for step in job["steps"]
            ),
            f"missing exact-source selection evidence: {name}",
        )
    for workflow in (pr, main):
        require(
            "make warning-gate" not in runs(workflow["jobs"]["lint-typecheck-contracts-security"]),
            "full-unit warning producer is duplicated before coverage unit shard",
        )
    main_rows = main["jobs"]["test-suites"]["strategy"]["matrix"]["include"]
    require(
        sum(row["suite"] == "unit" and row["target"] == "coverage-shard-unit" for row in main_rows)
        == 1,
        "main must retain one full-unit warning/coverage producer",
    )
    require(
        not any("make pr-" in command for job in main["jobs"].values() for command in runs(job)),
        "main must not acquire documentation-only PR dispatch",
    )
    authority = feature["jobs"]["validation-plan"]
    require(
        "make feature-pr-authority" in runs(authority) and "if" not in authority,
        "Feature must resolve exact-head PR authority unconditionally",
    )
    require(
        "make warning-gate" in runs(feature["jobs"]["lint-typecheck-contracts-security"]),
        "Feature fallback must retain its full-unit warning producer",
    )
    for name, job in feature["jobs"].items():
        if name == "validation-plan":
            continue
        require(
            "validation-plan" in job.get("needs", [])
            and job.get("if") == "needs.validation-plan.outputs.run_feature == 'true'",
            f"Feature routing must retain positive-authority/full-fallback decision: {name}",
        )


def main() -> int:
    try:
        workflows = [
            yaml.safe_load((ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"))
            for filename in ("pr-merge-gate.yml", "main-releasability.yml", "feature-lane.yml")
        ]
        validate_workflows(*workflows)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"PR validation contract failed: {error}")
        return 1
    print("PR validation contract passed: required jobs, full unit and main authority retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
