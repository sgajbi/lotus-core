"""Bind Core commands to exact outputs of the existing Platform acquisition validator."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

GOVERNANCE_SHA = "0c96dd9ea00d1222e35d3e7d14de6a540a222104"
PYTHON_SOURCE = (
    "python:3.11-slim-bookworm@"
    "sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6"
)
TRIVY_SOURCE = (
    "aquasec/trivy:0.56.2@sha256:26245f364b6f5d223003dc344ec1eb5eb8439052bfecb31d79aeba0c74344b3a"
)
# This table transports fixed source identities; Platform alone owns admission.
BINDINGS = {
    "LOTUS_CORE_PYTHON_IMAGE": (
        PYTHON_SOURCE,
        "docker.io/library/python",
        "public.ecr.aws/docker/library/python@" + PYTHON_SOURCE.split("@", 1)[1],
    ),
    "LOTUS_CORE_POSTGRES_IMAGE": (
        "postgres:16-alpine",
        "docker.io/library/postgres",
        "public.ecr.aws/docker/library/postgres@"
        "sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea",
    ),
    "LOTUS_CORE_PROMETHEUS_IMAGE": (
        "prom/prometheus:v2.47.2",
        "docker.io/prom/prometheus",
        "quay.io/prometheus/prometheus@"
        "sha256:3002935850ea69a59816825d4cb718fafcdb9b124e4e6153ebc6894627525f7f",
    ),
    "LOTUS_CORE_TRIVY_IMAGE": (
        TRIVY_SOURCE,
        "docker.io/aquasec/trivy",
        "ghcr.io/aquasecurity/trivy@" + TRIVY_SOURCE.split("@", 1)[1],
    ),
}
SCOPES = {
    "python": ("LOTUS_CORE_PYTHON_IMAGE",),
    "compose": (
        "LOTUS_CORE_PYTHON_IMAGE",
        "LOTUS_CORE_POSTGRES_IMAGE",
        "LOTUS_CORE_PROMETHEUS_IMAGE",
    ),
    "release": ("LOTUS_CORE_PYTHON_IMAGE", "LOTUS_CORE_TRIVY_IMAGE"),
}


def acquired_image(source: str, environment: Mapping[str, str] | None = None) -> str:
    """Keep local defaults; refuse any override except the exact qualified distribution."""
    values = os.environ if environment is None else environment
    for variable, (original, _, distribution) in BINDINGS.items():
        if source == original:
            selected = values.get(variable, source)
            if selected != source and (
                selected != distribution
                or values.get("LOTUS_PLATFORM_GOVERNANCE_SHA") != GOVERNANCE_SHA
            ):
                raise ValueError(f"Unqualified image binding: {variable}")
            return selected
    return source


def compose_image(reference: str, environment: Mapping[str, str]) -> str:
    """Resolve only the two declared Core Compose bindings, without a generic resolver."""
    for variable in ("LOTUS_CORE_POSTGRES_IMAGE", "LOTUS_CORE_PROMETHEUS_IMAGE"):
        source = BINDINGS[variable][0]
        if reference == "${" + variable + ":-" + source + "}":
            return acquired_image(source, environment)
    return reference


def validate_bindings(environment: Mapping[str, str]) -> None:
    """Reject invalid bindings before Compose consumes environment substitutions."""
    for source, _, _ in BINDINGS.values():
        acquired_image(source, environment)


def authenticate_dockerhub(environment: Mapping[str, str]) -> None:
    """Use only explicitly provisioned publisher read credentials, through stdin."""
    username = environment.get("DOCKERHUB_USERNAME", "")
    token = environment.get("DOCKERHUB_READ_TOKEN", "")
    if not username or not token:
        raise ValueError(
            "DockerHub read credentials are absent; Kafka, ZooKeeper and Grafana remain blocked"
        )
    try:
        subprocess.run(
            ["docker", "login", "docker.io", "--username", username, "--password-stdin"],
            input=token,
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("DockerHub read authentication failed; no image fallback") from None


def prepare(platform_root: Path, scope: str, output: Path, evidence: Path) -> None:
    """Export bindings atomically only after every native live acquisition succeeds."""
    head = subprocess.run(
        ["git", "-C", str(platform_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != GOVERNANCE_SHA:
        raise ValueError("Platform acquisition source must be the qualified commit")
    exports = [f"LOTUS_PLATFORM_GOVERNANCE_SHA={GOVERNANCE_SHA}"]
    evidence.mkdir(parents=True, exist_ok=True)
    for variable in SCOPES[scope]:
        _, repository, distribution = BINDINGS[variable]
        native_output = evidence / f"{variable}.output"
        native_output.unlink(missing_ok=True)
        subprocess.run(
            [
                sys.executable,
                str(platform_root / "automation/validate_technology_governance_policy.py"),
                "--source-image",
                repository + "@" + distribution.split("@", 1)[1],
                "--distribution-image",
                distribution,
                "--platform",
                "linux/amd64",
                "--verify-distribution",
                "--github-output",
                str(native_output),
                "--acquisition-evidence",
                str(evidence / variable),
            ],
            check=True,
        )
        if native_output.read_text(encoding="utf-8").strip() != "image=" + distribution:
            raise ValueError("Native acquisition output differs from the fixed binding")
        exports.append(f"{variable}={distribution}")
    with output.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(exports) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--scope", choices=SCOPES, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if args.scope == "compose":
        authenticate_dockerhub(os.environ)
    prepare(args.platform_root.resolve(), args.scope, args.github_env, args.evidence)


if __name__ == "__main__":
    main()
