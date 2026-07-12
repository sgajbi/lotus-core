"""Tests for portable, exact-source CI runtime image sets."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from scripts.release.runtime_image_set import (
    RuntimeImageSetError,
    create_runtime_image_set,
    load_and_verify_runtime_image_set,
)

SOURCE_SHA = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def _image_inspection(*, source_sha: str = SOURCE_SHA) -> dict[str, object]:
    return {
        "Id": IMAGE_ID,
        "RepoDigests": [],
        "Config": {
            "Labels": {
                "org.opencontainers.image.revision": source_sha,
                "org.opencontainers.image.ref.name": "feat/runtime-image-set",
                "org.opencontainers.image.created": "2026-07-13T00:00:00Z",
                "org.opencontainers.image.source": "https://github.com/sgajbi/lotus-core",
                "org.opencontainers.image.version": source_sha,
                "org.opencontainers.image.ci.run_id": "12345",
            }
        },
    }


def test_create_runtime_image_set_writes_deterministic_manifest_and_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")
    manifest_path = tmp_path / "runtime-images.json"
    bundle_path = tmp_path / "runtime-images.tar"
    commands: list[list[str]] = []

    monkeypatch.setattr(
        "scripts.release.runtime_image_set.SERVICE_BUILDS",
        {"query_service": ("lotus-core/query-service:local", str(dockerfile))},
    )

    def runner(args: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(args)
        if args[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([_image_inspection()]),
                stderr="",
            )
        if args[:3] == ["docker", "image", "save"]:
            bundle_path.write_bytes(b"portable image bundle")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {args}")

    manifest = create_runtime_image_set(
        services=["query_service"],
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        source_commit_sha=SOURCE_SHA,
        source_branch="feat/runtime-image-set",
        repository_url="https://github.com/sgajbi/lotus-core",
        ci_run_id="12345",
        generated_at_utc="2026-07-13T00:00:00Z",
        runner=runner,
    )

    assert manifest["schema_version"] == "lotus-core.runtime-image-set.v1"
    assert manifest["source_commit_sha"] == SOURCE_SHA
    assert manifest["service_count"] == 1
    assert manifest["compose_file_sha256"].startswith("sha256:")
    assert manifest["dependency_lock_sha256"].startswith("sha256:")
    assert manifest["dependency_closure_hash"].startswith("sha256:")
    assert manifest["content_hash"].startswith("sha256:")
    assert manifest["bundle_sha256"].startswith("sha256:")
    assert manifest["services"] == [
        {
            "service": "query_service",
            "image_tag": "lotus-core/query-service:local",
            "image_id": IMAGE_ID,
            "dockerfile": str(dockerfile),
            "dockerfile_sha256": ANY,
        }
    ]
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert commands[-1] == [
        "docker",
        "image",
        "save",
        "--output",
        str(bundle_path),
        "lotus-core/query-service:local",
    ]


def test_load_and_verify_runtime_image_set_rejects_wrong_source_sha(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "runtime-images.json"
    bundle_path = tmp_path / "runtime-images.tar"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "lotus-core.runtime-image-set.v1",
                "source_commit_sha": SOURCE_SHA,
            }
        ),
        encoding="utf-8",
    )
    bundle_path.write_bytes(b"bundle")

    with pytest.raises(RuntimeImageSetError, match="source commit mismatch"):
        load_and_verify_runtime_image_set(
            manifest_path=manifest_path,
            bundle_path=bundle_path,
            expected_commit_sha="c" * 40,
        )


def test_load_and_verify_runtime_image_set_loads_then_verifies_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")
    manifest_path = tmp_path / "runtime-images.json"
    bundle_path = tmp_path / "runtime-images.tar"
    commands: list[list[str]] = []

    monkeypatch.setattr(
        "scripts.release.runtime_image_set.SERVICE_BUILDS",
        {"query_service": ("lotus-core/query-service:local", str(dockerfile))},
    )

    def create_runner(args: list[str], **kwargs: object) -> SimpleNamespace:
        if args[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([_image_inspection()]),
                stderr="",
            )
        if args[:3] == ["docker", "image", "save"]:
            bundle_path.write_bytes(b"portable image bundle")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {args}")

    create_runtime_image_set(
        services=["query_service"],
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        source_commit_sha=SOURCE_SHA,
        source_branch="feat/runtime-image-set",
        repository_url="https://github.com/sgajbi/lotus-core",
        ci_run_id="12345",
        generated_at_utc="2026-07-13T00:00:00Z",
        runner=create_runner,
    )

    def verify_runner(args: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(args)
        if args[:3] == ["docker", "image", "load"]:
            return SimpleNamespace(returncode=0, stdout="loaded", stderr="")
        if args[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([_image_inspection()]),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {args}")

    manifest = load_and_verify_runtime_image_set(
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        expected_commit_sha=SOURCE_SHA,
        runner=verify_runner,
    )

    assert manifest["content_hash"].startswith("sha256:")
    assert commands == [
        ["docker", "image", "load", "--input", str(bundle_path)],
        ["docker", "image", "inspect", "lotus-core/query-service:local"],
    ]


def test_load_and_verify_runtime_image_set_rejects_tampered_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "runtime-images.json"
    bundle_path = tmp_path / "runtime-images.tar"
    bundle_path.write_bytes(b"tampered")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "lotus-core.runtime-image-set.v1",
                "source_commit_sha": SOURCE_SHA,
                "bundle_sha256": "sha256:" + "0" * 64,
                "content_hash": "sha256:" + "1" * 64,
                "services": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeImageSetError, match="bundle digest mismatch"):
        load_and_verify_runtime_image_set(
            manifest_path=manifest_path,
            bundle_path=bundle_path,
            expected_commit_sha=SOURCE_SHA,
        )


def test_create_runtime_image_set_rejects_stale_oci_source_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.release.runtime_image_set.SERVICE_BUILDS",
        {"query_service": ("lotus-core/query-service:local", str(dockerfile))},
    )

    def runner(args: list[str], **kwargs: object) -> SimpleNamespace:
        assert args[:3] == ["docker", "image", "inspect"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([_image_inspection(source_sha="c" * 40)]),
            stderr="",
        )

    with pytest.raises(RuntimeImageSetError, match="OCI label mismatch"):
        create_runtime_image_set(
            services=["query_service"],
            manifest_path=tmp_path / "runtime-images.json",
            bundle_path=tmp_path / "runtime-images.tar",
            source_commit_sha=SOURCE_SHA,
            source_branch="feat/runtime-image-set",
            repository_url="https://github.com/sgajbi/lotus-core",
            ci_run_id="12345",
            generated_at_utc="2026-07-13T00:00:00Z",
            runner=runner,
        )


def test_load_and_verify_runtime_image_set_rejects_non_object_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "runtime-images.json"
    bundle_path = tmp_path / "runtime-images.tar"
    manifest_path.write_text("[]\n", encoding="utf-8")
    bundle_path.write_bytes(b"bundle")

    with pytest.raises(RuntimeImageSetError, match="manifest must be a JSON object"):
        load_and_verify_runtime_image_set(
            manifest_path=manifest_path,
            bundle_path=bundle_path,
            expected_commit_sha=SOURCE_SHA,
        )
