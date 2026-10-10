"""Exercise native acquisition output binding at Core command boundaries."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.release import image_acquisition_bindings as bindings
from scripts.release import prebuild_ci_images
from scripts.release.local_image_build import LocalBuildMetadata, docker_build_command
from tests.test_support.docker_stack import (
    _load_compose_pull_images,
    ensure_required_images_available,
)


def _environment():
    return {
        "LOTUS_PLATFORM_GOVERNANCE_SHA": bindings.GOVERNANCE_SHA,
        **{name: item[2] for name, item in bindings.BINDINGS.items()},
    }


@pytest.mark.parametrize(
    "credentials", [{}, {"DOCKERHUB_USERNAME": "owner"}, {"DOCKERHUB_READ_TOKEN": "test-token"}]
)
def test_missing_publisher_credentials_fail_before_docker_login(credentials, monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Missing credentials must not reach Docker")

    monkeypatch.setattr(bindings.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="remain blocked"):
        bindings.authenticate_dockerhub(credentials)


def test_compose_cli_refuses_missing_credentials_before_any_external_command(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKERHUB_USERNAME", raising=False)
    monkeypatch.delenv("DOCKERHUB_READ_TOKEN", raising=False)
    monkeypatch.setattr(
        bindings.sys,
        "argv",
        [
            "acquire",
            "--platform-root",
            str(tmp_path),
            "--scope",
            "compose",
            "--github-env",
            str(tmp_path / "env"),
            "--evidence",
            str(tmp_path / "evidence"),
        ],
    )

    def unexpected(*_args, **_kwargs):
        pytest.fail("Missing operator configuration must fail before git, registry or Docker")

    monkeypatch.setattr(bindings.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="remain blocked"):
        bindings.main()
    assert not (tmp_path / "env").exists()


@pytest.mark.parametrize("fails", [False, True])
def test_publisher_login_uses_stdin_and_masks_failures(monkeypatch, fails):
    commands = []
    token = "test-only-token-never-logged"

    def run(command, **kwargs):
        commands.append(command)
        assert token not in command
        assert kwargs["input"] == token
        assert kwargs["timeout"] == 60
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is True
        if fails:
            raise subprocess.CalledProcessError(1, command, stderr=token)

    monkeypatch.setattr(bindings.subprocess, "run", run)
    credentials = {"DOCKERHUB_USERNAME": "owner", "DOCKERHUB_READ_TOKEN": token}
    if fails:
        with pytest.raises(ValueError) as error:
            bindings.authenticate_dockerhub(credentials)
        assert token not in str(error.value)
    else:
        bindings.authenticate_dockerhub(credentials)
    assert commands == [["docker", "login", "docker.io", "--username", "owner", "--password-stdin"]]


@pytest.mark.parametrize("name", bindings.BINDINGS)
def test_binding_accepts_only_exact_source_or_qualified_distribution(name):
    source, _, distribution = bindings.BINDINGS[name]
    assert bindings.acquired_image(source, {}) == source
    assert bindings.acquired_image(source, _environment()) == distribution
    for invalid in ("", distribution + ":latest", distribution.replace("sha256:", "sha256:0")):
        with pytest.raises(ValueError, match="Unqualified image binding"):
            bindings.acquired_image(source, {**_environment(), name: invalid})
    with pytest.raises(ValueError, match="Unqualified image binding"):
        bindings.acquired_image(source, {name: distribution})
    with pytest.raises(ValueError, match="Unqualified image binding"):
        bindings.acquired_image(source, {**_environment(), "LOTUS_PLATFORM_GOVERNANCE_SHA": "main"})


@pytest.mark.parametrize("scope", bindings.SCOPES)
def test_exports_only_actual_successful_native_outputs(tmp_path, monkeypatch, scope):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["check"] is True
        if command[0] == "git":
            return SimpleNamespace(stdout=bindings.GOVERNANCE_SHA + "\n")
        assert "--verify-distribution" in command
        assert command[command.index("--platform") + 1] == "linux/amd64"
        destination = command[command.index("--distribution-image") + 1]
        output = Path(command[command.index("--github-output") + 1])
        output.write_text("image=" + destination + "\n", encoding="utf-8")

    monkeypatch.setattr(bindings.subprocess, "run", run)
    output = tmp_path / "github-env"
    bindings.prepare(tmp_path, scope, output, tmp_path / "evidence")
    exported = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert exported == {
        "LOTUS_PLATFORM_GOVERNANCE_SHA": bindings.GOVERNANCE_SHA,
        **{name: bindings.BINDINGS[name][2] for name in bindings.SCOPES[scope]},
    }
    assert len(commands) == len(bindings.SCOPES[scope]) + 1


@pytest.mark.parametrize(
    "failure", ["unavailable", "unauthorized", "rate_limited", "digest_mismatch"]
)
def test_native_failure_never_exports_partial_or_fallback_bindings(tmp_path, monkeypatch, failure):
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        if command[0] == "git":
            return SimpleNamespace(stdout=bindings.GOVERNANCE_SHA)
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(1, command, stderr=failure)
        destination = command[command.index("--distribution-image") + 1]
        Path(command[command.index("--github-output") + 1]).write_text(
            "image=" + destination, encoding="utf-8"
        )

    monkeypatch.setattr(bindings.subprocess, "run", run)
    output = tmp_path / "github-env"
    with pytest.raises(subprocess.CalledProcessError):
        bindings.prepare(tmp_path, "compose", output, tmp_path / "evidence")
    assert not output.exists()
    assert calls == 2  # no Core retry layer on top of the bounded native validator


@pytest.mark.parametrize("corruption", ["wrong_head", "wrong_output", "missing_output"])
def test_untrusted_source_or_output_cannot_export_bindings(tmp_path, monkeypatch, corruption):
    def run(command, **kwargs):
        if command[0] == "git":
            return SimpleNamespace(
                stdout="main" if corruption == "wrong_head" else bindings.GOVERNANCE_SHA
            )
        if corruption == "wrong_output":
            Path(command[command.index("--github-output") + 1]).write_text(
                "image=unapproved.example/image@sha256:bad", encoding="utf-8"
            )

    monkeypatch.setattr(bindings.subprocess, "run", run)
    output = tmp_path / "github-env"
    with pytest.raises((ValueError, FileNotFoundError)):
        bindings.prepare(tmp_path, "python", output, tmp_path / "evidence")
    assert not output.exists()


def test_all_five_compose_images_reach_native_inspection_with_same_bound_references(monkeypatch):
    environment = _environment()
    compose_file = str(Path("docker-compose.yml").resolve())
    images = _load_compose_pull_images(compose_file, environment)
    assert len(images) == 5
    assert bindings.BINDINGS["LOTUS_CORE_POSTGRES_IMAGE"][2] in images
    assert bindings.BINDINGS["LOTUS_CORE_PROMETHEUS_IMAGE"][2] in images
    assert {
        "confluentinc/cp-kafka:7.5.0",
        "confluentinc/cp-zookeeper:7.5.0",
        "grafana/grafana:10.1.5",
    } < set(images)
    inspected = []

    def runner(command, **kwargs):
        inspected.append(command[-1])
        return SimpleNamespace(returncode=0)

    ensure_required_images_available(compose_file, runner, environment=environment)
    assert inspected == images
    invalid = {**environment, "LOTUS_CORE_POSTGRES_IMAGE": "postgres:latest"}
    with pytest.raises(ValueError):
        _load_compose_pull_images(compose_file, invalid)


def test_both_build_command_paths_pass_exact_python_output_to_builder(tmp_path, monkeypatch):
    for name, value in _environment().items():
        monkeypatch.setenv(name, value)
    image_argument = "PYTHON_IMAGE=" + bindings.BINDINGS["LOTUS_CORE_PYTHON_IMAGE"][2]
    metadata = LocalBuildMetadata("a" * 40, "feature", "2026-10-10T00:00:00Z", "repo", "version")
    local_command = docker_build_command(metadata)
    assert image_argument in local_command
    assert local_command[local_command.index("--platform") + 1] == "linux/amd64"
    commands = []
    monkeypatch.setattr(prebuild_ci_images, "_run", commands.append)
    monkeypatch.setattr(prebuild_ci_images, "_swap_cache", lambda *_args: None)
    prebuild_ci_images._build("query_service", tmp_path / "cache")
    assert image_argument in commands[0]
    assert commands[0][commands[0].index("--platform") + 1] == "linux/amd64"


def test_release_uses_same_bound_scanner_for_scans_and_sbom():
    workflow = yaml.safe_load(Path(".github/workflows/image-release.yml").read_text())
    for job in ("publish-images", "diagnose-images"):
        steps = workflow["jobs"][job]["steps"]
        acquire = next(
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "./.github/actions/acquire-images"
        )
        build = next(
            index
            for index, step in enumerate(steps)
            if "docker buildx build" in step.get("run", "")
        )
        assert acquire < build
        assert "PYTHON_IMAGE=${LOTUS_CORE_PYTHON_IMAGE:?" in steps[build]["run"]
        text = "\n".join(step.get("run", "") for step in steps)
        assert "aquasec/trivy:" not in text
        assert 'scanner_image="${LOTUS_CORE_TRIVY_IMAGE:?' in text
    export = next(
        step
        for step in workflow["jobs"]["publish-images"]["steps"]
        if step.get("name") == "Export image SBOM"
    )
    assert '"${LOTUS_CORE_TRIVY_IMAGE:?' in export["run"]
