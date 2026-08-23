from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_MANIFEST_PATH = Path("contracts/ci/required-status-checks.v1.json")
CANONICAL_REPOSITORY = "sgajbi/lotus-core"
CANONICAL_BRANCH = "main"
GITHUB_ACTIONS_APP_ID = 15368
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


def require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RequiredStatusChecksError(f"{field} must be a trimmed non-empty string")
    return value


def _parse_policy(raw_policy: object, *, index: int) -> WorkflowPolicy:
    expected_keys = {"path", "policy", "advisory_contexts"}
    if not isinstance(raw_policy, dict) or set(raw_policy) != expected_keys:
        raise RequiredStatusChecksError(f"workflow_policies[{index}] has an unexpected shape")
    policy = require_non_empty_string(raw_policy["policy"], field="workflow policy")
    if policy not in _SUPPORTED_POLICIES:
        raise RequiredStatusChecksError(f"unsupported workflow policy: {policy}")
    advisory = raw_policy["advisory_contexts"]
    if not isinstance(advisory, list):
        raise RequiredStatusChecksError("advisory_contexts must be a list")
    advisory_contexts = tuple(
        require_non_empty_string(value, field="advisory context") for value in advisory
    )
    if len(advisory_contexts) != len(set(advisory_contexts)):
        raise RequiredStatusChecksError("advisory contexts must be unique")
    return WorkflowPolicy(
        path=Path(require_non_empty_string(raw_policy["path"], field="workflow path")),
        policy=policy,
        advisory_contexts=frozenset(advisory_contexts),
    )


def _parse_required_check(raw_check: object, *, index: int) -> RequiredCheck:
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
    return RequiredCheck(
        context=require_non_empty_string(raw_check["context"], field="check context"),
        app_id=app_id,
    )


def _validate_manifest_header(payload: Mapping[str, Any]) -> tuple[str, str]:
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
    repository = require_non_empty_string(payload["repository"], field="repository")
    branch = require_non_empty_string(payload["branch"], field="branch")
    if repository != CANONICAL_REPOSITORY or branch != CANONICAL_BRANCH:
        raise RequiredStatusChecksError(
            "required-check manifest must target canonical protection authority: "
            f"repository={CANONICAL_REPOSITORY}, branch={CANONICAL_BRANCH}"
        )
    return repository, branch


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> RequiredChecksManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequiredStatusChecksError(f"unable to load required-check manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise RequiredStatusChecksError("required-check manifest must be a JSON object")
    repository, branch = _validate_manifest_header(payload)

    raw_policies = payload["workflow_policies"]
    if not isinstance(raw_policies, list) or not raw_policies:
        raise RequiredStatusChecksError("workflow_policies must be a non-empty list")
    policies = tuple(_parse_policy(value, index=index) for index, value in enumerate(raw_policies))

    raw_checks = payload["required_checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise RequiredStatusChecksError("required_checks must be a non-empty list")
    checks = tuple(
        _parse_required_check(value, index=index) for index, value in enumerate(raw_checks)
    )
    if checks != tuple(sorted(checks)):
        raise RequiredStatusChecksError("required_checks must be sorted by context and app_id")
    if len(checks) != len(set(checks)):
        raise RequiredStatusChecksError("required_checks must be unique")

    return RequiredChecksManifest(
        repository=repository,
        branch=branch,
        strict=payload["strict"],
        workflow_policies=policies,
        required_checks=checks,
    )


def desired_protection_payload(manifest: RequiredChecksManifest) -> dict[str, object]:
    return {
        "strict": manifest.strict,
        "contexts": [],
        "checks": [
            {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
        ],
    }
