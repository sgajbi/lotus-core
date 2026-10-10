"""Audit the single Core composite that precedes native image acquisition."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from scripts.quality.required_status_checks.model import RequiredStatusChecksError

ACTION = "./.github/actions/acquire-images"
COMPOSE_MATRIX_CONDITION = (
    'contains(fromJSON(\'["unit-db","critical-db-coverage","critical-lifecycle-db",'
    '"query-authority-db-contract","integration-lite"]\'), matrix.suite)'
)
ACTION_PATH = Path(__file__).resolve().parents[3] / ".github/actions/acquire-images/action.yml"


def validate_action_payload(payload: Mapping[str, Any]) -> None:
    """Refuse hidden steps, mutable source, weakened failure posture and input escapes."""
    expected = [
        {
            "uses": "actions/checkout@v6",
            "with": {
                "repository": "sgajbi/lotus-platform",
                "ref": "0c96dd9ea00d1222e35d3e7d14de6a540a222104",
                "persist-credentials": False,
                "path": ".lotus-platform",
            },
        },
        {
            "name": "Verify and export exact native acquisition outputs",
            "shell": "bash",
            "env": {
                "ACQUISITION_SCOPE": "${{ inputs.scope }}",
                "DOCKERHUB_USERNAME": "${{ inputs.dockerhub-username }}",
                "DOCKERHUB_READ_TOKEN": "${{ inputs.dockerhub-read-token }}",  # nosec B105
            },
            "run": "python -m scripts.release.image_acquisition_bindings "
            '--platform-root .lotus-platform --scope "$ACQUISITION_SCOPE" '
            '--github-env "$GITHUB_ENV" --evidence "$RUNNER_TEMP/core-image-acquisition"',
        },
        {
            "name": "Preserve acquisition failure evidence",
            "if": "always()",
            "uses": "actions/upload-artifact@v7",
            "with": {
                "name": "core-image-acquisition-${{ github.job }}-${{ inputs.evidence-id }}",
                "path": "${{ runner.temp }}/core-image-acquisition",
                "if-no-files-found": "ignore",
                "retention-days": 14,
            },
        },
    ]
    if payload.get("runs") != {"using": "composite", "steps": expected}:
        raise RequiredStatusChecksError("Core image acquisition composite execution drifted")


def validate_action_inputs(step: Mapping[str, Any], inputs: Mapping[str, Any]) -> None:
    if inputs.get("scope") not in {"python", "compose", "release"}:
        raise RequiredStatusChecksError("Core acquisition scope is not audited")
    if "if" in step and step["if"] != COMPOSE_MATRIX_CONDITION:
        raise RequiredStatusChecksError("Core acquisition condition is not audited")
    if inputs.get("evidence-id", "single") not in {"single", "${{ strategy.job-index }}"}:
        raise RequiredStatusChecksError("Core acquisition evidence identity is not audited")
    credentials = {
        name: inputs.get(name) for name in ("dockerhub-username", "dockerhub-read-token")
    }
    expected = (
        {
            "dockerhub-username": "${{ secrets.DOCKERHUB_USERNAME }}",
            "dockerhub-read-token": "${{ secrets.DOCKERHUB_READ_TOKEN }}",
        }
        if inputs["scope"] == "compose"
        else {"dockerhub-username": None, "dockerhub-read-token": None}
    )
    if credentials != expected:
        raise RequiredStatusChecksError("Core acquisition credential references are not audited")
    try:
        payload = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RequiredStatusChecksError("Core acquisition composite is unavailable") from error
    if not isinstance(payload, dict):
        raise RequiredStatusChecksError("Core acquisition composite must be an object")
    validate_action_payload(payload)
