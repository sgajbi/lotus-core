"""Build and package the exact-source runtime image set as one fail-fast control."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_METADATA = (
    "LOTUS_RUNTIME_IMAGE_SET_GROUP",
    "LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA",
    "LOTUS_RUNTIME_IMAGE_SET_SOURCE_BRANCH",
    "LOTUS_RUNTIME_IMAGE_SET_REPOSITORY_URL",
    "LOTUS_RUNTIME_IMAGE_SET_CI_RUN_ID",
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _required_metadata(environment: Mapping[str, str]) -> dict[str, str]:
    metadata = {name: environment.get(name, "").strip() for name in REQUIRED_METADATA}
    missing = [name for name, value in metadata.items() if not value]
    if missing:
        raise SystemExit(f"Required runtime image-set metadata is missing: {', '.join(missing)}")
    return metadata


def build_runtime_image_set(
    *,
    environment: Mapping[str, str],
    generated_at_utc: str,
    runner: Runner = subprocess.run,
) -> None:
    """Build images and package them with one timestamp and failure boundary."""

    metadata = _required_metadata(environment)
    child_environment = dict(environment)
    child_environment["LOTUS_BUILD_TIMESTAMP"] = generated_at_utc
    runner(  # nosec B603
        (
            sys.executable,
            "scripts/release/prebuild_ci_images.py",
            "--cache-dir",
            ".buildx-cache",
            "--group",
            metadata["LOTUS_RUNTIME_IMAGE_SET_GROUP"],
            "--metrics-output",
            "output/runtime-image-set/build-metrics.json",
        ),
        cwd=REPO_ROOT,
        check=True,
        env=child_environment,
    )
    runner(  # nosec B603
        (
            sys.executable,
            "scripts/release/runtime_image_set.py",
            "create",
            "--group",
            metadata["LOTUS_RUNTIME_IMAGE_SET_GROUP"],
            "--manifest",
            "output/runtime-image-set/manifest.json",
            "--bundle",
            "output/runtime-image-set/images.tar",
            "--source-commit-sha",
            metadata["LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA"],
            "--source-branch",
            metadata["LOTUS_RUNTIME_IMAGE_SET_SOURCE_BRANCH"],
            "--repository-url",
            metadata["LOTUS_RUNTIME_IMAGE_SET_REPOSITORY_URL"],
            "--ci-run-id",
            metadata["LOTUS_RUNTIME_IMAGE_SET_CI_RUN_ID"],
            "--generated-at-utc",
            generated_at_utc,
        ),
        cwd=REPO_ROOT,
        check=True,
        env=child_environment,
    )


def main() -> int:
    generated_at_utc = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    build_runtime_image_set(
        environment=os.environ,
        generated_at_utc=generated_at_utc,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
