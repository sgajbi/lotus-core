"""Renew report-only technology-governance receipts from an exact-main run."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from scripts.quality import technology_governance_pilot_guard as guard

DEPENDENCY_HEALTH_ARTIFACT = re.compile(r"^main-releasability-dependency-health-\d+$")
GITHUB_RECEIPT_START = re.compile(r'\{\s*"kind"\s*:\s*"github_run"')


def _renewed_artifact_name(current_name: str, run_id: int) -> str:
    if DEPENDENCY_HEALTH_ARTIFACT.fullmatch(current_name):
        return f"main-releasability-dependency-health-{run_id}"
    return current_name


def _successful_exact_revision_assertion(jobs_payload: dict[str, Any]) -> bool:
    jobs = jobs_payload.get("jobs")
    return isinstance(jobs, list) and any(
        job.get("name") == guard.EXACT_REVISION_ASSERTION_JOB
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs
    )


def renew_manifest(manifest: dict[str, Any], *, run_id: int) -> dict[str, Any]:
    run = guard._github_api_payload(f"repos/{guard.GITHUB_REPOSITORY}/actions/runs/{run_id}")
    jobs = guard._github_api_payload(
        f"repos/{guard.GITHUB_REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100"
    )
    artifacts_payload = guard._github_api_payload(
        f"repos/{guard.GITHUB_REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"
    )
    source_commit = run.get("head_sha")
    expected_branch = f"{guard.RENEWABLE_RECEIPT_BRANCH_PREFIX}{source_commit}"
    if (
        not isinstance(source_commit, str)
        or not guard.FULL_SHA_PATTERN.fullmatch(source_commit)
        or run.get("workflow_id") != guard.RECEIPT_WORKFLOW_ID
        or run.get("path") != guard.RECEIPT_WORKFLOW_PATH
        or run.get("event") != guard.RENEWABLE_RECEIPT_EVENT
        or run.get("head_branch") != expected_branch
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise ValueError("run is not a successful governed exact-SHA Main Releasability dispatch")
    if not _successful_exact_revision_assertion(jobs):
        raise ValueError("run does not contain a successful exact revision assertion")

    artifacts = artifacts_payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("GitHub artifact response is malformed")
    renewed = copy.deepcopy(manifest)
    receipt_count = 0
    for _, receipt in guard._github_run_refs(renewed):
        current_name = receipt.get("artifact")
        if not isinstance(current_name, str):
            raise ValueError("GitHub receipt artifact name is missing")
        artifact_name = _renewed_artifact_name(current_name, run_id)
        named_artifacts = [
            artifact for artifact in artifacts if artifact.get("name") == artifact_name
        ]
        if not named_artifacts:
            raise ValueError(f"GitHub artifact does not exist: {artifact_name}")
        current_artifacts = [
            artifact for artifact in named_artifacts if guard._artifact_is_current(artifact)
        ]
        if not current_artifacts:
            raise ValueError(f"GitHub artifact is expired or has invalid expiry: {artifact_name}")
        artifact = current_artifacts[0]
        digest = artifact.get("digest")
        if not isinstance(digest, str) or not guard.ARTIFACT_DIGEST_PATTERN.fullmatch(digest):
            raise ValueError(f"GitHub artifact digest is invalid: {artifact_name}")
        receipt.update(
            {
                "url": f"https://github.com/{guard.GITHUB_REPOSITORY}/actions/runs/{run_id}",
                "artifact": artifact_name,
                "artifact_digest": digest,
                "source_commit": source_commit,
                "workflow_id": guard.RECEIPT_WORKFLOW_ID,
                "workflow_path": guard.RECEIPT_WORKFLOW_PATH,
                "event": guard.RENEWABLE_RECEIPT_EVENT,
                "head_branch": expected_branch,
            }
        )
        receipt_count += 1
    if receipt_count == 0:
        raise ValueError("manifest contains no renewable GitHub receipts")

    errors = guard.validate_manifest(renewed, verify_github=True)
    if errors:
        raise ValueError("renewed manifest is invalid: " + "; ".join(errors))
    return renewed


def _render_renewed_manifest(original_text: str, renewed: dict[str, Any]) -> str:
    renewed_receipts = [receipt for _, receipt in guard._github_run_refs(renewed)]
    spans: list[tuple[int, int]] = []
    decoder = json.JSONDecoder()
    for match in GITHUB_RECEIPT_START.finditer(original_text):
        decoded, end = decoder.raw_decode(original_text, match.start())
        if isinstance(decoded, dict) and decoded.get("kind") == "github_run":
            spans.append((match.start(), end))
    if len(spans) != len(renewed_receipts):
        raise ValueError(
            "manifest text does not contain the expected number of renewable GitHub receipts"
        )
    rendered = original_text
    for (start, end), receipt in reversed(list(zip(spans, renewed_receipts, strict=True))):
        rendered = rendered[:start] + json.dumps(receipt) + rendered[end:]
    if json.loads(rendered) != renewed:
        raise ValueError("format-preserving receipt renewal changed non-receipt manifest content")
    return rendered


def _write_manifest_atomically(path: Path, content: str) -> None:
    manifest_path = path.resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=manifest_path.parent,
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, manifest_path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--manifest", type=Path, default=guard.MANIFEST_PATH)
    args = parser.parse_args(argv)
    try:
        original_text = args.manifest.read_text(encoding="utf-8")
        manifest = json.loads(original_text)
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")
        renewed = renew_manifest(manifest, run_id=args.run_id)
        rendered = _render_renewed_manifest(original_text, renewed)
        _write_manifest_atomically(args.manifest, rendered)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Technology-governance receipt renewal failed: {exc}")
        return 1
    print(f"Renewed technology-governance receipts from exact-main run {args.run_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
