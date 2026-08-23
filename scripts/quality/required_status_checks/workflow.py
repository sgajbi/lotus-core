from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from scripts.quality.required_status_checks.job_policy import (
    default_run_shell,
    dependency_ids,
    effective_environment,
    validate_blocking_job,
)
from scripts.quality.required_status_checks.model import (
    RequiredChecksManifest,
    RequiredStatusChecksError,
    WorkflowPolicy,
    require_non_empty_string,
)

_WORKFLOW_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
_MATRIX_EXPRESSION = re.compile(r"\$\{\{\s*matrix\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_PULL_REQUEST_EVENT_TYPES = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


def _matrix_name_expressions(name: str) -> tuple[re.Match[str], ...]:
    workflow_expressions = tuple(_WORKFLOW_EXPRESSION.finditer(name))
    matrix_expressions = tuple(_MATRIX_EXPRESSION.finditer(name))
    expression_spans = tuple(match.span() for match in workflow_expressions)
    matrix_spans = tuple(match.span() for match in matrix_expressions)
    if ("${{" in name and not workflow_expressions) or expression_spans != matrix_spans:
        raise RequiredStatusChecksError(f"job has unsupported workflow name expression: {name}")
    return matrix_expressions


def _matrix_values(job: Mapping[str, Any], *, matrix_key: str, name: str) -> tuple[str, ...]:
    strategy = job.get("strategy") or {}
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    include = matrix.get("include") if isinstance(matrix, dict) else None
    if not isinstance(include, list) or not include:
        raise RequiredStatusChecksError(f"matrix job has no include rows: {name}")
    values: list[str] = []
    for row in include:
        if not isinstance(row, dict) or matrix_key not in row:
            raise RequiredStatusChecksError(f"matrix include row lacks {matrix_key}: {name}")
        values.append(require_non_empty_string(row[matrix_key], field=f"matrix.{matrix_key}"))
    if len(values) != len(set(values)):
        raise RequiredStatusChecksError(f"matrix values must be unique: {name}")
    return tuple(values)


def _validate_matrix_shape(job: Mapping[str, Any], *, name: str, has_name_expression: bool) -> None:
    strategy = job.get("strategy") or {}
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if matrix is None:
        return
    if not isinstance(matrix, dict):
        raise RequiredStatusChecksError(f"matrix must be an object: {name}")
    if set(matrix) != {"include"}:
        raise RequiredStatusChecksError(f"matrix job has unsupported matrix shape: {name}")
    if not has_name_expression:
        raise RequiredStatusChecksError(f"matrix job name must identify each cell: {name}")


def _expanded_job_contexts(job: Mapping[str, Any]) -> tuple[str, ...]:
    name = require_non_empty_string(job.get("name"), field="workflow job name")
    expression_matches = _matrix_name_expressions(name)
    _validate_matrix_shape(
        job,
        name=name,
        has_name_expression=bool(expression_matches),
    )
    if not expression_matches:
        return (name,)
    if len(expression_matches) != 1:
        raise RequiredStatusChecksError(f"job has unsupported matrix name expression: {name}")
    matrix_key = expression_matches[0].group(1)
    return tuple(
        _MATRIX_EXPRESSION.sub(lambda _match: value, name)
        for value in _matrix_values(job, matrix_key=matrix_key, name=name)
    )


def _required_context_collisions(
    job: Mapping[str, Any], *, required_contexts: set[str]
) -> tuple[str, ...]:
    name = require_non_empty_string(job.get("name"), field="workflow job name")
    expressions = _matrix_name_expressions(name)
    try:
        expanded_contexts = _expanded_job_contexts(job)
    except RequiredStatusChecksError:
        if not expressions:
            raise
        pattern_parts: list[str] = []
        cursor = 0
        for expression in expressions:
            pattern_parts.extend((re.escape(name[cursor : expression.start()]), ".*"))
            cursor = expression.end()
        pattern_parts.append(re.escape(name[cursor:]))
        context_pattern = re.compile("".join(pattern_parts))
        return tuple(
            sorted(context for context in required_contexts if context_pattern.fullmatch(context))
        )
    return tuple(sorted(set(expanded_contexts) & required_contexts))


def _blocking_contexts(job: Mapping[str, Any], *, policy: WorkflowPolicy) -> tuple[str, ...]:
    contexts: list[str] = []
    for context in _expanded_job_contexts(job):
        if context in policy.advisory_contexts:
            continue
        if policy.policy == "all_jobs_blocking" or context.endswith(" Gate"):
            contexts.append(context)
            continue
        raise RequiredStatusChecksError(
            f"workflow job is neither a blocking Gate nor declared advisory: {context}"
        )
    return tuple(contexts)


def blocking_contexts_for_workflow(
    workflow: Mapping[str, Any], *, policy: WorkflowPolicy
) -> tuple[str, ...]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise RequiredStatusChecksError(f"workflow has no jobs: {policy.path}")
    blocking: list[str] = []
    blocking_jobs: dict[str, tuple[Mapping[str, Any], tuple[str, ...]]] = {}
    observed_advisory: set[str] = set()
    workflow_shell = default_run_shell(workflow, scope=f"workflow {policy.path}")
    workflow_environment = effective_environment(workflow, scope=f"workflow {policy.path}")
    for job_id, job in jobs.items():
        if not isinstance(job_id, str) or not job_id:
            raise RequiredStatusChecksError(
                f"workflow job id must be a non-empty string: {policy.path}"
            )
        if not isinstance(job, dict):
            raise RequiredStatusChecksError(f"workflow job must be an object: {policy.path}")
        expanded_contexts = _expanded_job_contexts(job)
        observed_advisory.update(set(expanded_contexts) & policy.advisory_contexts)
        contexts = _blocking_contexts(job, policy=policy)
        if contexts:
            validate_blocking_job(
                job,
                contexts=contexts,
                workflow_shell=workflow_shell,
                workflow_environment=workflow_environment,
            )
            blocking_jobs[job_id] = (job, contexts)
            blocking.extend(contexts)
    for job_id, (job, contexts) in blocking_jobs.items():
        nonblocking_dependencies = sorted(
            dependency
            for dependency in dependency_ids(job, contexts=contexts)
            if dependency not in blocking_jobs
        )
        if nonblocking_dependencies:
            raise RequiredStatusChecksError(
                "blocking workflow jobs may depend only on blocking jobs: "
                f"job={job_id!r}, dependencies={nonblocking_dependencies!r}"
            )
    missing_advisory = policy.advisory_contexts - observed_advisory
    if missing_advisory:
        raise RequiredStatusChecksError(
            "declared advisory contexts are absent from workflow: "
            + ", ".join(sorted(missing_advisory))
        )
    return tuple(blocking)


def _load_workflow(path: Path, *, display_path: Path) -> Mapping[str, Any]:
    try:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RequiredStatusChecksError(f"unable to load workflow: {display_path}") from exc
    if not isinstance(workflow, dict):
        raise RequiredStatusChecksError(f"workflow must be a YAML object: {display_path}")
    return workflow


def _validate_workflow_triggers(workflow: Mapping[str, Any], *, path: Path) -> None:
    triggers = workflow.get("on")
    if triggers is None:
        triggers = next((value for key, value in workflow.items() if key is True), None)
    if not isinstance(triggers, dict):
        raise RequiredStatusChecksError(f"workflow triggers must be an object: {path}")
    pull_request = triggers.get("pull_request")
    if not isinstance(pull_request, dict):
        raise RequiredStatusChecksError(f"workflow must define pull_request triggers: {path}")
    if set(pull_request) != {"branches", "types"}:
        raise RequiredStatusChecksError(f"workflow pull_request triggers are noncanonical: {path}")
    branches = pull_request.get("branches")
    event_types = pull_request.get("types")
    if branches != ["main"] or not isinstance(event_types, list):
        raise RequiredStatusChecksError(f"workflow pull_request triggers are noncanonical: {path}")
    if (
        not all(isinstance(event_type, str) for event_type in event_types)
        or len(event_types) != len(set(event_types))
        or set(event_types) != _PULL_REQUEST_EVENT_TYPES
    ):
        raise RequiredStatusChecksError(f"workflow pull_request triggers are noncanonical: {path}")
    if triggers.get("merge_group") != {"branches": ["main"]}:
        raise RequiredStatusChecksError(f"workflow merge_group triggers are noncanonical: {path}")


def _workflow_jobs(workflow: Mapping[str, Any], *, path: Path) -> Mapping[str, Any]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise RequiredStatusChecksError(f"workflow has no jobs: {path}")
    return jobs


def _governed_contexts(
    manifest: RequiredChecksManifest, *, repository_root: Path
) -> tuple[list[str], dict[str, Path], dict[str, list[str]]]:
    contexts: list[str] = []
    required_producers: dict[str, Path] = {}
    all_producers: dict[str, list[str]] = {}
    for policy in manifest.workflow_policies:
        workflow = _load_workflow(repository_root / policy.path, display_path=policy.path)
        _validate_workflow_triggers(workflow, path=policy.path)
        jobs = _workflow_jobs(workflow, path=policy.path)
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                raise RequiredStatusChecksError(f"workflow job must be an object: {policy.path}")
            for context in _expanded_job_contexts(job):
                all_producers.setdefault(context, []).append(f"{policy.path}:{job_id}")
        policy_contexts = blocking_contexts_for_workflow(workflow, policy=policy)
        contexts.extend(policy_contexts)
        required_producers.update(dict.fromkeys(policy_contexts, policy.path))
    return contexts, required_producers, all_producers


def _validate_governed_contexts(
    manifest: RequiredChecksManifest,
    *,
    workflow_contexts: list[str],
    governed_context_producers: Mapping[str, list[str]],
) -> None:
    if len(workflow_contexts) != len(set(workflow_contexts)):
        raise RequiredStatusChecksError("blocking workflow contexts must be globally unique")
    duplicate_contexts = {
        context: producers
        for context, producers in governed_context_producers.items()
        if len(producers) > 1
    }
    if duplicate_contexts:
        details = "; ".join(
            f"context={context!r}, producers={producers!r}"
            for context, producers in sorted(duplicate_contexts.items())
        )
        raise RequiredStatusChecksError(
            f"governed workflow contexts must be globally unique: {details}"
        )
    manifest_contexts = {check.context for check in manifest.required_checks}
    advisory_contexts = set().union(
        *(policy.advisory_contexts for policy in manifest.workflow_policies)
    )
    required_advisory_overlap = sorted(manifest_contexts & advisory_contexts)
    if required_advisory_overlap:
        raise RequiredStatusChecksError(
            "required checks must not use declared advisory contexts: "
            + ", ".join(required_advisory_overlap)
        )
    workflow_context_set = set(workflow_contexts)
    if manifest_contexts != workflow_context_set:
        missing = sorted(workflow_context_set - manifest_contexts)
        stale = sorted(manifest_contexts - workflow_context_set)
        raise RequiredStatusChecksError(
            f"required-check manifest drift: missing={missing!r}, stale={stale!r}"
        )


def _scan_unmanaged_workflows(
    manifest: RequiredChecksManifest,
    *,
    repository_root: Path,
    required_context_producers: Mapping[str, Path],
) -> None:
    workflow_directory = repository_root / ".github" / "workflows"
    if not workflow_directory.is_dir():
        return
    governed_paths = {policy.path for policy in manifest.workflow_policies}
    for workflow_path in sorted(workflow_directory.glob("*.y*ml")):
        relative_path = workflow_path.relative_to(repository_root)
        if relative_path in governed_paths:
            continue
        workflow = _load_workflow(workflow_path, display_path=relative_path)
        for job in _workflow_jobs(workflow, path=relative_path).values():
            if not isinstance(job, dict):
                raise RequiredStatusChecksError(f"workflow job must be an object: {relative_path}")
            collisions = _required_context_collisions(
                job, required_contexts=set(required_context_producers)
            )
            if collisions:
                context = collisions[0]
                producer = required_context_producers[context]
                raise RequiredStatusChecksError(
                    "required check context is also emitted by an unmanaged workflow: "
                    f"context={context!r}, governed={producer}, collision={relative_path}"
                )


def validate_manifest_against_workflows(
    manifest: RequiredChecksManifest, *, repository_root: Path = Path(".")
) -> None:
    workflow_contexts, required_producers, all_producers = _governed_contexts(
        manifest, repository_root=repository_root
    )
    _validate_governed_contexts(
        manifest,
        workflow_contexts=workflow_contexts,
        governed_context_producers=all_producers,
    )
    _scan_unmanaged_workflows(
        manifest,
        repository_root=repository_root,
        required_context_producers=required_producers,
    )
