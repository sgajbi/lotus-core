"""Write a minimal SLSA v1 provenance predicate for a Core image build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SLSA_BUILD_TYPE = "https://github.com/Attestations/GitHubActionsWorkflow@v1"


def build_predicate(
    *,
    repository: str,
    repository_url: str,
    git_commit_sha: str,
    workflow_ref: str,
    service: str,
    dockerfile: str,
    ci_run_id: str,
    ci_run_attempt: str,
    buildx_metadata: dict[str, Any],
    sbom_sha256: str,
) -> dict[str, Any]:
    """Bind source, workflow, build inputs, and Buildx result metadata."""
    if not FULL_GIT_SHA_PATTERN.fullmatch(git_commit_sha):
        raise ValueError("Git commit SHA must be a full lowercase SHA")
    required = {
        "repository": repository,
        "repository URL": repository_url,
        "workflow ref": workflow_ref,
        "service": service,
        "Dockerfile": dockerfile,
        "CI run ID": ci_run_id,
        "CI run attempt": ci_run_attempt,
    }
    for name, value in required.items():
        if not value.strip():
            raise ValueError(f"{name} is required")
    if not ci_run_id.isdecimal() or not ci_run_attempt.isdecimal():
        raise ValueError("CI run identity must be numeric")
    container_digest = buildx_metadata.get("containerimage.digest")
    if not isinstance(container_digest, str) or not container_digest.startswith("sha256:"):
        raise ValueError("Buildx metadata must contain the container image digest")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", sbom_sha256):
        raise ValueError("SBOM digest must be sha256")
    return {
        "buildDefinition": {
            "buildType": SLSA_BUILD_TYPE,
            "externalParameters": {
                "repository": repository,
                "workflow_ref": workflow_ref,
                "service": service,
                "dockerfile": dockerfile,
            },
            "internalParameters": {
                "ci_run_id": ci_run_id,
                "ci_run_attempt": ci_run_attempt,
            },
            "resolvedDependencies": [
                {
                    "uri": f"git+{repository_url}",
                    "digest": {"gitCommit": git_commit_sha},
                }
            ],
        },
        "runDetails": {
            "builder": {"id": workflow_ref},
            "metadata": {
                "invocationId": f"{repository}/actions/runs/{ci_run_id}/attempts/{ci_run_attempt}",
            },
            "byproducts": [
                {
                    "name": "buildx-result",
                    "content": buildx_metadata,
                },
                {"name": "cyclonedx-sbom", "digest": {"sha256": sbom_sha256[7:]}},
            ],
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--git-commit-sha", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--dockerfile", required=True)
    parser.add_argument("--ci-run-id", required=True)
    parser.add_argument("--ci-run-attempt", required=True)
    parser.add_argument("--buildx-metadata", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        metadata = json.loads(args.buildx_metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("cannot read Buildx metadata") from exc
    if not isinstance(metadata, dict):
        raise SystemExit("Buildx metadata must be an object")
    predicate = build_predicate(
        repository=args.repository,
        repository_url=args.repository_url,
        git_commit_sha=args.git_commit_sha,
        workflow_ref=args.workflow_ref,
        service=args.service,
        dockerfile=args.dockerfile,
        ci_run_id=args.ci_run_id,
        ci_run_attempt=args.ci_run_attempt,
        buildx_metadata=metadata,
        sbom_sha256="sha256:" + hashlib.sha256(args.sbom.read_bytes()).hexdigest(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predicate, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
