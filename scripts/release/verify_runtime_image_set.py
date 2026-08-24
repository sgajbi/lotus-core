"""Verify an optional runtime image set against the exact current source."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.runtime_image_set import (  # noqa: E402
    FULL_GIT_SHA_PATTERN,
    RuntimeImageSetError,
    load_and_verify_runtime_image_set,
)

_CI_TRUTHY_VALUES = frozenset({"1", "true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON"})
Runner = Callable[..., subprocess.CompletedProcess[str]]
Verifier = Callable[..., dict[str, Any]]


def _expected_source_sha(
    *,
    environment: Mapping[str, str],
    workspace: Path,
    runner: Runner,
) -> str:
    ci_enabled = environment.get("CI", "").strip() in _CI_TRUTHY_VALUES
    github_sha = environment.get("GITHUB_SHA", "").strip()
    if ci_enabled and not github_sha:
        raise RuntimeImageSetError("GITHUB_SHA is required in CI")
    if github_sha:
        expected_sha = github_sha
    else:
        result = runner(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        expected_sha = result.stdout.strip()
    if FULL_GIT_SHA_PATTERN.fullmatch(expected_sha) is None:
        raise RuntimeImageSetError("expected source commit must be a full lowercase Git SHA")
    return expected_sha


def verify_runtime_image_set_for_current_source(
    *,
    environment: Mapping[str, str],
    workspace: Path = REPO_ROOT,
    runner: Runner = subprocess.run,
    verifier: Verifier = load_and_verify_runtime_image_set,
    output: Callable[[str], None] = print,
) -> bool:
    """Load exact-source images when present and publish a verified-source receipt."""

    runtime_directory = workspace / "output" / "runtime-image-set"
    manifest_path = runtime_directory / "manifest.json"
    bundle_path = runtime_directory / "images.tar"
    receipt_path = runtime_directory / "verified-source-sha"
    ci_enabled = environment.get("CI", "").strip() in _CI_TRUTHY_VALUES
    if not ci_enabled and not manifest_path.is_file():
        receipt_path.unlink(missing_ok=True)
        output("No runtime image set present; controls build from source.")
        return False

    expected_sha = _expected_source_sha(
        environment=environment,
        workspace=workspace,
        runner=runner,
    )
    verifier(
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        expected_commit_sha=expected_sha,
        runner=runner,
    )
    runtime_directory.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(f"{expected_sha}\n", encoding="utf-8")
    return True


def main() -> int:
    verify_runtime_image_set_for_current_source(environment=os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
