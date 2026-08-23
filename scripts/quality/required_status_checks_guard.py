from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404 - fixed gh executable with argv, no shell
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

DEFAULT_MANIFEST_PATH = Path("contracts/ci/required-status-checks.v1.json")
GITHUB_ACTIONS_APP_ID = 15368
_WORKFLOW_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
_MATRIX_EXPRESSION = re.compile(r"\$\{\{\s*matrix\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_SUPPORTED_POLICIES = frozenset({"all_jobs_blocking", "gate_jobs_blocking"})


class RequiredStatusChecksError(RuntimeError):
    """Raised when required-check authority is malformed or inconsistent."""


@dataclass(frozen=True, slots=True, order=True)
class RequiredCheck:
    context: str
    app_id: int


@dataclass(frozen=True, slots=True)
class WorkflowPolicy:
    path: Path
    policy: str
    advisory_contexts: frozenset[str]


@dataclass(frozen=True, slots=True)
class RequiredChecksManifest:
    repository: str
    branch: str
    strict: bool
    workflow_policies: tuple[WorkflowPolicy, ...]
    required_checks: tuple[RequiredCheck, ...]


def _require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RequiredStatusChecksError(f"{field} must be a trimmed non-empty string")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> RequiredChecksManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequiredStatusChecksError(f"unable to load required-check manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise RequiredStatusChecksError("required-check manifest must be a JSON object")
    expected_keys = {
        "schema_version",
        "repository",
        "branch",
        "strict",
        "workflow_policies",
        "required_checks",
    }
    if set(payload) != expected_keys:
        raise RequiredStatusChecksError("required-check manifest has an unexpected shape")
    if payload["schema_version"] != 1:
        raise RequiredStatusChecksError("unsupported required-check manifest schema_version")
    if not isinstance(payload["strict"], bool):
        raise RequiredStatusChecksError("strict must be a boolean")

    raw_policies = payload["workflow_policies"]
    if not isinstance(raw_policies, list) or not raw_policies:
        raise RequiredStatusChecksError("workflow_policies must be a non-empty list")
    policies: list[WorkflowPolicy] = []
    for index, raw_policy in enumerate(raw_policies):
        if not isinstance(raw_policy, dict) or set(raw_policy) != {
            "path",
            "policy",
            "advisory_contexts",
        }:
            raise RequiredStatusChecksError(f"workflow_policies[{index}] has an unexpected shape")
        policy = _require_non_empty_string(raw_policy["policy"], field="workflow policy")
        if policy not in _SUPPORTED_POLICIES:
            raise RequiredStatusChecksError(f"unsupported workflow policy: {policy}")
        advisory = raw_policy["advisory_contexts"]
        if not isinstance(advisory, list):
            raise RequiredStatusChecksError("advisory_contexts must be a list")
        advisory_contexts = tuple(
            _require_non_empty_string(value, field="advisory context") for value in advisory
        )
        if len(advisory_contexts) != len(set(advisory_contexts)):
            raise RequiredStatusChecksError("advisory contexts must be unique")
        policies.append(
            WorkflowPolicy(
                path=Path(_require_non_empty_string(raw_policy["path"], field="workflow path")),
                policy=policy,
                advisory_contexts=frozenset(advisory_contexts),
            )
        )

    raw_checks = payload["required_checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise RequiredStatusChecksError("required_checks must be a non-empty list")
    checks: list[RequiredCheck] = []
    for index, raw_check in enumerate(raw_checks):
        if not isinstance(raw_check, dict) or set(raw_check) != {"context", "app_id"}:
            raise RequiredStatusChecksError(f"required_checks[{index}] has an unexpected shape")
        app_id = raw_check["app_id"]
        if not isinstance(app_id, int) or isinstance(app_id, bool) or app_id <= 0:
            raise RequiredStatusChecksError("required check app_id must be a positive integer")
        if app_id != GITHUB_ACTIONS_APP_ID:
            raise RequiredStatusChecksError(
                "required checks must bind to the GitHub Actions application: "
                f"expected={GITHUB_ACTIONS_APP_ID}"
            )
        checks.append(
            RequiredCheck(
                context=_require_non_empty_string(raw_check["context"], field="check context"),
                app_id=app_id,
            )
        )
    if checks != sorted(checks):
        raise RequiredStatusChecksError("required_checks must be sorted by context and app_id")
    if len(checks) != len(set(checks)):
        raise RequiredStatusChecksError("required_checks must be unique")
    contexts = [check.context for check in checks]
    if len(contexts) != len(set(contexts)):
        raise RequiredStatusChecksError("required check contexts must be unique")

    return RequiredChecksManifest(
        repository=_require_non_empty_string(payload["repository"], field="repository"),
        branch=_require_non_empty_string(payload["branch"], field="branch"),
        strict=payload["strict"],
        workflow_policies=tuple(policies),
        required_checks=tuple(checks),
    )


def _matrix_name_expressions(name: str) -> tuple[re.Match[str], ...]:
    workflow_expressions = tuple(_WORKFLOW_EXPRESSION.finditer(name))
    matrix_expressions = tuple(_MATRIX_EXPRESSION.finditer(name))
    if ("${{" in name and not workflow_expressions) or tuple(
        match.span() for match in workflow_expressions
    ) != tuple(match.span() for match in matrix_expressions):
        raise RequiredStatusChecksError(f"job has unsupported workflow name expression: {name}")
    return matrix_expressions


def _expanded_job_contexts(job: Mapping[str, Any]) -> tuple[str, ...]:
    name = _require_non_empty_string(job.get("name"), field="workflow job name")
    expression_matches = _matrix_name_expressions(name)
    expressions = tuple(match.group(1) for match in expression_matches)
    if not expressions:
        return (name,)
    if len(expressions) != 1:
        raise RequiredStatusChecksError(f"job has unsupported matrix name expression: {name}")
    matrix_key = expressions[0]
    strategy = job.get("strategy") or {}
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    include = matrix.get("include") if isinstance(matrix, dict) else None
    if not isinstance(include, list) or not include:
        raise RequiredStatusChecksError(f"matrix job has no include rows: {name}")
    values: list[str] = []
    for row in include:
        if not isinstance(row, dict) or matrix_key not in row:
            raise RequiredStatusChecksError(f"matrix include row lacks {matrix_key}: {name}")
        values.append(_require_non_empty_string(row[matrix_key], field=f"matrix.{matrix_key}"))
    if len(values) != len(set(values)):
        raise RequiredStatusChecksError(f"matrix values must be unique: {name}")
    return tuple(_MATRIX_EXPRESSION.sub(lambda _match: value, name) for value in values)


def _required_context_collisions(
    job: Mapping[str, Any], *, required_contexts: set[str]
) -> tuple[str, ...]:
    name = _require_non_empty_string(job.get("name"), field="workflow job name")
    expressions = _matrix_name_expressions(name)
    try:
        expanded_contexts = _expanded_job_contexts(job)
    except RequiredStatusChecksError:
        if not expressions:
            raise
        pattern_parts: list[str] = []
        cursor = 0
        for expression in expressions:
            pattern_parts.append(re.escape(name[cursor : expression.start()]))
            pattern_parts.append(".+")
            cursor = expression.end()
        pattern_parts.append(re.escape(name[cursor:]))
        context_pattern = re.compile("".join(pattern_parts))
        return tuple(
            sorted(context for context in required_contexts if context_pattern.fullmatch(context))
        )
    return tuple(sorted(set(expanded_contexts) & required_contexts))


def blocking_contexts_for_workflow(
    workflow: Mapping[str, Any], *, policy: WorkflowPolicy
) -> tuple[str, ...]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise RequiredStatusChecksError(f"workflow has no jobs: {policy.path}")
    blocking: list[str] = []
    observed_advisory: set[str] = set()
    for job in jobs.values():
        if not isinstance(job, dict):
            raise RequiredStatusChecksError(f"workflow job must be an object: {policy.path}")
        job_blocking_contexts: list[str] = []
        for context in _expanded_job_contexts(job):
            if context in policy.advisory_contexts:
                observed_advisory.add(context)
                continue
            if policy.policy == "all_jobs_blocking":
                job_blocking_contexts.append(context)
                continue
            if context.endswith(" Gate"):
                job_blocking_contexts.append(context)
                continue
            raise RequiredStatusChecksError(
                f"workflow job is neither a blocking Gate nor declared advisory: {context}"
            )
        if job_blocking_contexts and "if" in job:
            raise RequiredStatusChecksError(
                "blocking workflow jobs must be unconditional: " + ", ".join(job_blocking_contexts)
            )
        blocking.extend(job_blocking_contexts)
    missing_advisory = policy.advisory_contexts - observed_advisory
    if missing_advisory:
        raise RequiredStatusChecksError(
            "declared advisory contexts are absent from workflow: "
            + ", ".join(sorted(missing_advisory))
        )
    return tuple(blocking)


def validate_manifest_against_workflows(
    manifest: RequiredChecksManifest, *, repository_root: Path = Path(".")
) -> None:
    workflow_contexts: list[str] = []
    required_context_producers: dict[str, Path] = {}
    for policy in manifest.workflow_policies:
        workflow_path = repository_root / policy.path
        try:
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise RequiredStatusChecksError(
                f"unable to load governed workflow: {policy.path}"
            ) from exc
        if not isinstance(workflow, dict):
            raise RequiredStatusChecksError(f"workflow must be a YAML object: {policy.path}")
        policy_contexts = blocking_contexts_for_workflow(workflow, policy=policy)
        workflow_contexts.extend(policy_contexts)
        for context in policy_contexts:
            required_context_producers[context] = policy.path
    if len(workflow_contexts) != len(set(workflow_contexts)):
        raise RequiredStatusChecksError("blocking workflow contexts must be globally unique")
    manifest_contexts = {check.context for check in manifest.required_checks}
    workflow_context_set = set(workflow_contexts)
    if manifest_contexts != workflow_context_set:
        missing = sorted(workflow_context_set - manifest_contexts)
        stale = sorted(manifest_contexts - workflow_context_set)
        raise RequiredStatusChecksError(
            f"required-check manifest drift: missing={missing!r}, stale={stale!r}"
        )

    workflow_directory = repository_root / ".github" / "workflows"
    governed_paths = {policy.path for policy in manifest.workflow_policies}
    if workflow_directory.is_dir():
        for workflow_path in sorted(workflow_directory.glob("*.y*ml")):
            relative_path = workflow_path.relative_to(repository_root)
            if relative_path in governed_paths:
                continue
            try:
                workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise RequiredStatusChecksError(
                    f"unable to load repository workflow: {relative_path}"
                ) from exc
            if not isinstance(workflow, dict):
                raise RequiredStatusChecksError(f"workflow must be a YAML object: {relative_path}")
            jobs = workflow.get("jobs")
            if not isinstance(jobs, dict):
                raise RequiredStatusChecksError(f"workflow has no jobs: {relative_path}")
            for job in jobs.values():
                if not isinstance(job, dict):
                    raise RequiredStatusChecksError(
                        f"workflow job must be an object: {relative_path}"
                    )
                collisions = _required_context_collisions(
                    job,
                    required_contexts=set(required_context_producers),
                )
                for context in collisions:
                    producer = required_context_producers[context]
                    raise RequiredStatusChecksError(
                        "required check context is also emitted by an unmanaged workflow: "
                        f"context={context!r}, governed={producer}, collision={relative_path}"
                    )


def validate_live_protection(
    manifest: RequiredChecksManifest, protection: Mapping[str, Any]
) -> None:
    required = protection.get("required_status_checks")
    if not isinstance(required, dict):
        raise RequiredStatusChecksError("branch protection has no required_status_checks object")
    if required.get("strict") is not manifest.strict:
        raise RequiredStatusChecksError("branch protection strict mode differs from manifest")
    raw_checks = required.get("checks")
    if not isinstance(raw_checks, list):
        raise RequiredStatusChecksError("branch protection must expose app-bound checks")
    live_checks: set[RequiredCheck] = set()
    for raw_check in raw_checks:
        if not isinstance(raw_check, dict):
            raise RequiredStatusChecksError("live required check must be an object")
        context = raw_check.get("context")
        app_id = raw_check.get("app_id")
        if (
            not isinstance(context, str)
            or not context.strip()
            or not isinstance(app_id, int)
            or isinstance(app_id, bool)
            or app_id <= 0
        ):
            raise RequiredStatusChecksError(
                f"live required check has invalid context or app_id: context={context!r}"
            )
        live_checks.add(RequiredCheck(context=context, app_id=app_id))
    if len(live_checks) != len(raw_checks):
        raise RequiredStatusChecksError("live required checks must be unique")
    expected_checks = set(manifest.required_checks)
    if live_checks != expected_checks:
        missing = sorted(expected_checks - live_checks)
        stale = sorted(live_checks - expected_checks)
        raise RequiredStatusChecksError(
            f"live branch-protection drift: missing={missing!r}, stale={stale!r}"
        )


def load_live_protection(*, repository: str, branch: str) -> Mapping[str, Any]:
    if not os.environ.get("GH_TOKEN", "").strip():
        raise RequiredStatusChecksError("LOTUS_BRANCH_PROTECTION_READ_TOKEN is not provisioned")
    command = ["gh", "api", f"repos/{repository}/branches/{branch}/protection"]
    try:
        completed = subprocess.run(  # nosec B603 - fixed executable and argument vector
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        stderr_lines = [line.strip() for line in (exc.stderr or "").splitlines() if line.strip()]
        first_line = stderr_lines[0][:200] if stderr_lines else "gh api failed"
        raise RequiredStatusChecksError(
            f"unable to read live branch protection: {first_line}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RequiredStatusChecksError("live branch-protection read timed out") from exc
    except OSError as exc:
        raise RequiredStatusChecksError(
            "unable to start the live branch-protection reader"
        ) from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RequiredStatusChecksError("live branch protection returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise RequiredStatusChecksError("live branch protection response must be an object")
    return payload


def desired_protection_payload(manifest: RequiredChecksManifest) -> dict[str, object]:
    return {
        "strict": manifest.strict,
        "checks": [
            {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate governed required status checks")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--verify-live", action="store_true")
    parser.add_argument("--print-desired-protection", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        validate_manifest_against_workflows(manifest, repository_root=args.repository_root)
        if args.print_desired_protection:
            print(json.dumps(desired_protection_payload(manifest), sort_keys=True))
            return 0
        if args.verify_live:
            protection = load_live_protection(
                repository=manifest.repository,
                branch=manifest.branch,
            )
            validate_live_protection(manifest, protection)
    except RequiredStatusChecksError as exc:
        print(f"required status checks guard failed: {exc}")
        return 1
    print(
        "required status checks guard passed: "
        f"checks={len(manifest.required_checks)} live={args.verify_live}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
