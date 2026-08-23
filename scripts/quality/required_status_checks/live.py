from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - fixed gh executable with argv, no shell
from typing import Any, Mapping

from scripts.quality.required_status_checks.model import (
    RequiredCheck,
    RequiredChecksManifest,
    RequiredStatusChecksError,
)


def _parse_live_check(raw_check: object) -> RequiredCheck:
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
    return RequiredCheck(context=context, app_id=app_id)


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
    live_checks = {_parse_live_check(raw_check) for raw_check in raw_checks}
    if len(live_checks) != len(raw_checks):
        raise RequiredStatusChecksError("live required checks must be unique")
    expected_checks = set(manifest.required_checks)
    if live_checks != expected_checks:
        missing = sorted(expected_checks - live_checks)
        stale = sorted(live_checks - expected_checks)
        raise RequiredStatusChecksError(
            f"live branch-protection drift: missing={missing!r}, stale={stale!r}"
        )


def _bounded_failure_detail(exc: subprocess.CalledProcessError) -> str:
    stderr_lines = [line.strip() for line in (exc.stderr or "").splitlines() if line.strip()]
    return stderr_lines[0][:200] if stderr_lines else "gh api failed"


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
        raise RequiredStatusChecksError(
            f"unable to read live branch protection: {_bounded_failure_detail(exc)}"
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
