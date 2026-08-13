import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.development import update_base_image_manifest_evidence as updater


def _raw(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path, monkeypatch) -> tuple[bytes, bytes]:
    source_revision = "a" * 40
    child_payload = _raw(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"digest": "sha256:" + "c" * 64},
            "layers": [],
        }
    )
    child_digest = _digest(child_payload)
    index_payload = _raw(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "digest": child_digest,
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "size": len(child_payload),
                    "platform": {"architecture": "amd64", "os": "linux"},
                    "annotations": {
                        "org.opencontainers.image.revision": source_revision,
                        "org.opencontainers.image.source": (
                            "https://github.com/docker-library/python.git#"
                            f"{source_revision}:3.11/slim-bookworm"
                        ),
                    },
                }
            ],
        }
    )
    inventory = tmp_path / "lifecycle.json"
    inventory.write_text(
        json.dumps(
            {
                "base_images": [
                    {
                        "image": f"python:3.11-slim-bookworm@{_digest(index_payload)}",
                        "deployment_platform": "linux/amd64",
                        "observed_on": "2026-08-13",
                        "registry": "docker.io",
                        "repository": "library/python",
                        "tag": "3.11-slim-bookworm",
                        "source_revision": source_revision,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "LIFECYCLE_INVENTORY", inventory)
    monkeypatch.setattr(updater, "EVIDENCE_PATH", tmp_path / "evidence.json")

    def inspect(reference: str) -> bytes:
        return child_payload if reference.endswith(child_digest) else index_payload

    monkeypatch.setattr(updater, "_inspect_raw", inspect)
    return index_payload, child_payload


def test_build_evidence_retains_digest_verifiable_parent_and_child(
    tmp_path: Path, monkeypatch
) -> None:
    index_payload, child_payload = _fixture(tmp_path, monkeypatch)

    evidence = updater.build_evidence()

    assert evidence["index"]["digest"] == _digest(index_payload)
    assert evidence["runtime_manifest"]["digest"] == _digest(child_payload)
    assert evidence["runtime_manifest"]["config_digest"] == "sha256:" + "c" * 64
    assert evidence["deployment_platform"] == "linux/amd64"


def test_build_evidence_rejects_registry_parent_digest_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "_inspect_raw", lambda _reference: b"{}")

    with pytest.raises(updater.ManifestEvidenceRefreshError, match="index bytes"):
        updater.build_evidence()


def test_build_evidence_rejects_missing_platform_manifest(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path, monkeypatch)
    with pytest.raises(updater.ManifestEvidenceRefreshError, match="exactly one"):
        updater._select_platform_manifest({"manifests": []}, "linux/amd64")


def test_build_evidence_rejects_source_revision_not_bound_by_registry_descriptor(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)
    lifecycle = json.loads(updater.LIFECYCLE_INVENTORY.read_text(encoding="utf-8"))
    lifecycle["base_images"][0]["source_revision"] = "0" * 40
    updater.LIFECYCLE_INVENTORY.write_text(json.dumps(lifecycle), encoding="utf-8")

    with pytest.raises(
        updater.ManifestEvidenceRefreshError,
        match="does not bind the governed Official Images source revision",
    ):
        updater.build_evidence()


def test_build_evidence_rejects_registry_without_governed_api_authority(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)
    lifecycle = json.loads(updater.LIFECYCLE_INVENTORY.read_text(encoding="utf-8"))
    record = lifecycle["base_images"][0]
    record["image"] = "ghcr.io/attacker/forged-python@" + str(record["image"]).partition("@")[2]
    record["registry"] = "ghcr.io"
    record["repository"] = "attacker/forged-python"
    updater.LIFECYCLE_INVENTORY.write_text(json.dumps(lifecycle), encoding="utf-8")

    with pytest.raises(updater.ManifestEvidenceRefreshError, match="no approved OCI API authority"):
        updater.build_evidence()


def test_build_evidence_rejects_lifecycle_location_not_bound_to_image(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)
    lifecycle = json.loads(updater.LIFECYCLE_INVENTORY.read_text(encoding="utf-8"))
    lifecycle["base_images"][0]["image"] = (
        "ghcr.io/attacker/forged-python@"
        + str(lifecycle["base_images"][0]["image"]).partition("@")[2]
    )
    updater.LIFECYCLE_INVENTORY.write_text(json.dumps(lifecycle), encoding="utf-8")

    with pytest.raises(updater.ManifestEvidenceRefreshError, match="must match"):
        updater.build_evidence()


def test_inspect_raw_uses_argument_safe_docker_invocation(monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=b"{}")

    monkeypatch.setattr(updater.subprocess, "run", run)

    assert updater._inspect_raw("python@example") == b"{}"
    assert commands == [["docker", "buildx", "imagetools", "inspect", "--raw", "python@example"]]
