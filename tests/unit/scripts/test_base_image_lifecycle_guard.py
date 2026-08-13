import copy
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.quality.base_image_lifecycle_guard import (
    INVENTORY_PATH,
    MANIFEST_EVIDENCE_PATH,
    REPO_ROOT,
    find_base_image_lifecycle_findings,
)

GOVERNED_IMAGE = (
    "python:3.11-slim-bookworm@"
    "sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6"
)


def _inventory() -> dict[str, object]:
    return json.loads((REPO_ROOT / INVENTORY_PATH).read_text(encoding="utf-8"))


def _manifest_evidence() -> dict[str, object]:
    return json.loads((REPO_ROOT / MANIFEST_EVIDENCE_PATH).read_text(encoding="utf-8"))


def _write_fixture(
    root: Path,
    inventory: dict[str, object],
    manifest_evidence: dict[str, object] | None = None,
) -> None:
    dockerfile = root / "src/services/query_service/Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(f"ARG PYTHON_IMAGE={GOVERNED_IMAGE}\n", encoding="utf-8")
    record = inventory["base_images"][0]  # type: ignore[index]
    record["covered_dockerfiles"] = ["src/services/query_service/Dockerfile"]
    boundary = inventory["outside_release_boundary"]  # type: ignore[index]
    images = boundary["local_compose_dependency_images"]  # type: ignore[index]
    root.joinpath("docker-compose.yml").write_text(
        "\n".join(f"  image: {image}" for image in images) + "\n",
        encoding="utf-8",
    )
    inventory_path = root / INVENTORY_PATH
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(inventory, indent=2) + "\n",
        encoding="utf-8",
    )
    evidence_path = root / MANIFEST_EVIDENCE_PATH
    evidence_path.write_text(
        json.dumps(manifest_evidence or _manifest_evidence(), indent=2) + "\n",
        encoding="utf-8",
    )


def _details(root: Path, *, today: date = date(2026, 8, 12)) -> list[str]:
    return [finding.detail for finding in find_base_image_lifecycle_findings(root, today=today)]


def test_repository_base_image_lifecycle_inventory_is_current() -> None:
    assert find_base_image_lifecycle_findings(REPO_ROOT, today=date(2026, 8, 12)) == []


def test_guard_accepts_deterministic_replay(tmp_path: Path) -> None:
    _write_fixture(tmp_path, _inventory())

    first = _details(tmp_path)
    second = _details(tmp_path)

    assert first == second == []


def test_guard_rejects_dockerfile_digest_drift(tmp_path: Path) -> None:
    _write_fixture(tmp_path, _inventory())
    dockerfile = tmp_path / "src/services/query_service/Dockerfile"
    dockerfile.write_text(
        "ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:" + "0" * 64 + "\n",
        encoding="utf-8",
    )

    assert any("does not use the governed base image" in detail for detail in _details(tmp_path))


def test_guard_rejects_missing_lifecycle_inventory(tmp_path: Path) -> None:
    findings = find_base_image_lifecycle_findings(tmp_path, today=date(2026, 8, 12))

    assert [finding.detail for finding in findings] == ["missing lifecycle inventory"]


def test_guard_rejects_stale_review(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["base_images"][0]["next_review_on"] = "2026-08-11"  # type: ignore[index]
    _write_fixture(tmp_path, inventory)

    assert "base-image lifecycle evidence is stale" in _details(tmp_path)


def test_guard_rejects_package_support_evidence_not_refreshed_with_review(
    tmp_path: Path,
) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["observed_on"] = "2026-08-13"
    record["next_review_on"] = "2026-09-12"
    _write_fixture(tmp_path, inventory)

    assert "Debian package support evidence must be refreshed with observed_on" in _details(
        tmp_path, today=date(2026, 8, 13)
    )


def test_guard_rejects_future_dated_package_support_evidence(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["distribution_package_support"]["verified_on"] = "2026-08-13"
    _write_fixture(tmp_path, inventory)

    assert "Debian package support evidence cannot be future-dated" in _details(tmp_path)


def test_guard_rejects_official_image_identity_not_refreshed_with_review(
    tmp_path: Path,
) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["observed_on"] = "2026-08-13"
    record["next_review_on"] = "2026-09-12"
    record["distribution_package_support"]["verified_on"] = "2026-08-13"
    _write_fixture(tmp_path, inventory)

    assert "Official Images identity evidence must be refreshed with observed_on" in _details(
        tmp_path, today=date(2026, 8, 13)
    )


def test_guard_rejects_future_dated_official_image_identity(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["identity_evidence"]["verified_on"] = "2026-08-13"
    _write_fixture(tmp_path, inventory)

    assert "Official Images identity evidence cannot be future-dated" in _details(tmp_path)


@pytest.mark.parametrize(
    "field",
    ["official_image_source", "official_image_registry", "verified_command"],
)
def test_guard_rejects_incomplete_official_image_identity(tmp_path: Path, field: str) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["identity_evidence"].pop(field)
    _write_fixture(tmp_path, inventory)

    assert any(f"identity_evidence.{field}" in detail for detail in _details(tmp_path))


def test_guard_rejects_credentialed_official_image_authority(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["identity_evidence"]["official_image_source"] = (
        "https://user:secret@github.com/docker-library/python"
    )
    _write_fixture(tmp_path, inventory)

    assert any(
        "official_image_source must be a credential-free HTTPS authority" in detail
        for detail in _details(tmp_path)
    )


def test_guard_rejects_identity_command_for_another_image(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["identity_evidence"]["verified_command"] = (
        "docker buildx imagetools inspect python:3.12-slim-bookworm@sha256:" + "0" * 64
    )
    _write_fixture(tmp_path, inventory)

    assert "Official Images identity command must bind the governed image" in _details(tmp_path)


def test_guard_rejects_end_of_life_component(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["supported_through"] = "2026-08-11"
    record["support_components"][0]["local_fail_closed_cutoff"] = "2026-08-11"
    _write_fixture(tmp_path, inventory)

    details = _details(tmp_path)
    assert "base image runtime or distribution is end-of-life" in details
    assert "support component cpython is end-of-life" in details


def test_guard_rejects_local_cutoff_after_upstream_authority(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["supported_through"] = "2027-10-02"
    record["support_components"][0]["local_fail_closed_cutoff"] = "2027-10-02"
    _write_fixture(tmp_path, inventory)

    assert "support component cpython local cutoff exceeds upstream authority" in _details(tmp_path)


def test_guard_rejects_missing_machine_readable_authority_end(tmp_path: Path) -> None:
    inventory = _inventory()
    record = inventory["base_images"][0]  # type: ignore[index]
    record["support_components"][0].pop("authority_support_end_on")
    _write_fixture(tmp_path, inventory)

    assert "support_components.cpython.authority_support_end_on must be an ISO date" in _details(
        tmp_path
    )


def test_guard_rejects_experimental_base_image(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["base_images"][0]["maturity"] = "experimental"  # type: ignore[index]
    _write_fixture(tmp_path, inventory)

    assert any("experimental images are prohibited" in detail for detail in _details(tmp_path))


def test_guard_rejects_unclassified_external_compose_image(tmp_path: Path) -> None:
    inventory = copy.deepcopy(_inventory())
    _write_fixture(tmp_path, inventory)
    with tmp_path.joinpath("docker-compose.yml").open("a", encoding="utf-8") as stream:
        stream.write("  image: redis:8\n")

    assert any(
        "exactly classify external Compose images" in detail for detail in _details(tmp_path)
    )


def test_guard_rejects_unresolved_deployment_child_digest(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["base_images"][0]["resolved_manifest_digest"] = "unknown"  # type: ignore[index]
    _write_fixture(tmp_path, inventory)

    assert any("resolved_manifest_digest" in detail for detail in _details(tmp_path))


def test_guard_rejects_missing_exact_image_package_support(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["base_images"][0].pop("distribution_package_support")  # type: ignore[index]
    _write_fixture(tmp_path, inventory)

    assert "distribution_package_support evidence is required" in _details(tmp_path)
