from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pytest

from scripts.operations.transaction_processing_release_compose_runtime import (
    COMPOSE_SERVICE,
    IMAGE_DIGEST_ENV,
    TRANSACTION_IMAGE_ENV,
    LocalComposeReleaseConfig,
    LocalComposeReleaseRuntime,
    owned_compose_resource_count,
    transaction_service_recreate_command,
)
from scripts.operations.transaction_processing_release_evidence import (
    COMPOSE_PROJECT_PREFIX,
    ReleaseEvidenceError,
    ReleaseIdentity,
)

PROJECT = COMPOSE_PROJECT_PREFIX + "20260810-160000-a1b2c3d4"
DIGEST = "sha256:" + "c" * 64
ROLLBACK_DIGEST = "sha256:" + "d" * 64
IMAGE_REF = "ghcr.io/sgajbi/lotus-core/portfolio-transaction-processing-service"
DIGEST_REF = f"{IMAGE_REF}@{DIGEST}"
ROLLBACK_DIGEST_REF = f"{IMAGE_REF}@{ROLLBACK_DIGEST}"


@dataclass
class FakeEndpoints:
    compose_project_name: str = PROJECT
    host_database_url: str = "postgresql://user:password@localhost:5432/portfolio_db"
    kafka_bootstrap_servers: str = "localhost:9092"
    e2e_ingestion_url: str = "http://localhost:8000"
    e2e_transaction_processing_url: str = "http://localhost:8085"


@dataclass
class FakeReservation:
    released: int = 0

    def release(self) -> None:
        self.released += 1


@dataclass
class FakeRuntime:
    values: dict[str, str] = field(default_factory=dict)
    port_reservation: FakeReservation = field(default_factory=FakeReservation)
    endpoints: FakeEndpoints = field(default_factory=FakeEndpoints)


@dataclass
class FakeManagedRun:
    runtime: FakeRuntime = field(default_factory=FakeRuntime)
    compose_file: str = "C:/repo/docker-compose.yml"
    entered: int = 0
    exited: int = 0

    def compose_command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-f",
            self.compose_file,
            "-p",
            self.runtime.endpoints.compose_project_name,
            *args,
        ]

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> Literal[False]:
        self.exited += 1
        return False


class RecordingRunner:
    def __init__(self, *, owned_resource: str = "") -> None:
        self.commands: list[list[str]] = []
        self.owned_resource = owned_resource

    def __call__(self, command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            stdout = json.dumps([command[3]])
        elif command[:3] in (
            ["docker", "ps", "-aq"],
            ["docker", "network", "ls"],
            ["docker", "volume", "ls"],
        ):
            stdout = self.owned_resource
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


def _release(
    *,
    digest: str = DIGEST,
    digest_ref: str = DIGEST_REF,
    sha_character: str = "a",
) -> ReleaseIdentity:
    git_sha = sha_character * 40
    return ReleaseIdentity(
        service=COMPOSE_SERVICE,
        git_commit_sha=git_sha,
        digest_image_ref=digest_ref,
        image_digest=digest,
        runtime_env={"LOTUS_GIT_COMMIT_SHA": git_sha},
        oci_labels={"org.opencontainers.image.digest": digest},
        sbom_generated=True,
        vulnerability_scan_status="passed",
        image_signed=True,
        provenance_attestation_generated=True,
    )


def _config(tmp_path: Path, *, pull_images: bool = False) -> LocalComposeReleaseConfig:
    return LocalComposeReleaseConfig(
        receipt_id="transaction-release-rehearsal-20260810-160000-a1b2c3d4",
        repo_root=tmp_path,
        pull_images=pull_images,
    )


def test_recreate_command_is_exact_service_digest_deploy_shape() -> None:
    command = transaction_service_recreate_command(FakeManagedRun())

    assert command == [
        "docker",
        "compose",
        "-f",
        "C:/repo/docker-compose.yml",
        "-p",
        PROJECT,
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "--pull",
        "never",
        COMPOSE_SERVICE,
    ]
    assert not {"--build", "down", "prune"}.intersection(command)


def test_recreate_command_rejects_shared_project_before_command_generation() -> None:
    managed = FakeManagedRun()
    managed.runtime.endpoints.compose_project_name = "lotus-core-app-local"

    with pytest.raises(ReleaseEvidenceError, match="shared Compose project"):
        transaction_service_recreate_command(managed)


def test_preflight_inspects_qualified_images_without_implicit_pull(tmp_path: Path) -> None:
    runner = RecordingRunner()
    runtime = LocalComposeReleaseRuntime(
        managed_run=FakeManagedRun(),
        config=_config(tmp_path),
        runner=runner,
    )

    evidence = runtime.preflight(
        candidate=_release(),
        rollback=_release(
            digest=ROLLBACK_DIGEST,
            digest_ref=ROLLBACK_DIGEST_REF,
            sha_character="b",
        ),
    )

    assert evidence["owned_resource_count_before_start"] == 0
    assert evidence["candidate_image"]["digest_image_ref"] == DIGEST_REF
    assert ["docker", "pull", DIGEST_REF] not in runner.commands
    assert all(isinstance(command, list) for command in runner.commands)


def test_preflight_pulls_only_when_operator_explicitly_requests_it(tmp_path: Path) -> None:
    runner = RecordingRunner()
    runtime = LocalComposeReleaseRuntime(
        managed_run=FakeManagedRun(),
        config=_config(tmp_path, pull_images=True),
        runner=runner,
    )

    runtime.preflight(
        candidate=_release(),
        rollback=_release(
            digest=ROLLBACK_DIGEST,
            digest_ref=ROLLBACK_DIGEST_REF,
            sha_character="b",
        ),
    )

    assert runner.commands.count(["docker", "pull", DIGEST_REF]) == 1
    assert runner.commands.count(["docker", "pull", ROLLBACK_DIGEST_REF]) == 1


def test_preflight_rejects_residual_owned_resources(tmp_path: Path) -> None:
    runner = RecordingRunner(owned_resource="container-123\n")
    runtime = LocalComposeReleaseRuntime(
        managed_run=FakeManagedRun(),
        config=_config(tmp_path),
        runner=runner,
    )

    with pytest.raises(ReleaseEvidenceError, match="already owns resources"):
        runtime.preflight(
            candidate=_release(),
            rollback=_release(
                digest=ROLLBACK_DIGEST,
                digest_ref=ROLLBACK_DIGEST_REF,
                sha_character="b",
            ),
        )

    assert not any(command[:2] == ["docker", "pull"] for command in runner.commands)


def test_preflight_rejects_equal_release_digests_before_docker(tmp_path: Path) -> None:
    runner = RecordingRunner()
    runtime = LocalComposeReleaseRuntime(
        managed_run=FakeManagedRun(),
        config=_config(tmp_path),
        runner=runner,
    )

    with pytest.raises(ReleaseEvidenceError, match="digests must differ"):
        runtime.preflight(candidate=_release(), rollback=_release())

    assert runner.commands == []


def test_owned_resource_count_uses_only_exact_project_label() -> None:
    runner = RecordingRunner(owned_resource="resource-1\n")

    assert owned_compose_resource_count(PROJECT, runner=runner) == 1
    assert len(runner.commands) == 3
    for command in runner.commands:
        assert command[-2:] == ["--filter", f"label=com.docker.compose.project={PROJECT}"]
        assert "prune" not in command


def test_cleanup_without_started_stack_releases_ports_and_checks_exact_ownership(
    tmp_path: Path,
) -> None:
    managed = FakeManagedRun()
    runner = RecordingRunner()
    runtime = LocalComposeReleaseRuntime(
        managed_run=managed,
        config=_config(tmp_path),
        runner=runner,
    )

    assert runtime.cleanup() == 0

    assert managed.runtime.port_reservation.released == 1
    assert managed.exited == 0
    assert len(runner.commands) == 3


def test_release_image_override_cannot_change_project_authority(tmp_path: Path) -> None:
    managed = FakeManagedRun()
    runtime = LocalComposeReleaseRuntime(
        managed_run=managed,
        config=_config(tmp_path),
        runner=RecordingRunner(),
    )

    runtime._set_release_image(_release())

    assert managed.runtime.values == {
        "LOTUS_GIT_COMMIT_SHA": "a" * 40,
        IMAGE_DIGEST_ENV: DIGEST,
        TRANSACTION_IMAGE_ENV: DIGEST_REF,
    }
    assert managed.runtime.endpoints.compose_project_name == PROJECT


@pytest.mark.parametrize("count", [0, 101])
def test_canary_size_is_bounded(tmp_path: Path, count: int) -> None:
    with pytest.raises(ReleaseEvidenceError, match="between 1 and 100"):
        LocalComposeReleaseConfig(
            receipt_id="receipt",
            repo_root=tmp_path,
            canary_transaction_count=count,
        )
