import json
import sys
from datetime import date
from pathlib import Path

import pytest

from scripts.quality import dependency_technology_inventory_guard as guard
from scripts.quality.technology_governance_identity import normalized_text_sha256


def _sha(path: Path) -> str:
    return normalized_text_sha256(path)


def _fixture(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    requirements = tmp_path / "requirements"
    contracts = tmp_path / "contracts" / "security"
    requirements.mkdir()
    contracts.mkdir(parents=True)
    lock_specs = (
        ("shared-runtime.lock.txt", "runtime", "linux/amd64"),
        ("shared-runtime-windows.lock.txt", "runtime", "windows/amd64"),
        ("ci-tooling.lock.txt", "ci_build_test", "linux/amd64"),
        ("ci-tooling-windows.lock.txt", "ci_build_test", "windows/amd64"),
    )
    locks = []
    for name, scope, platform in lock_specs:
        lock = requirements / name
        lock.write_text("demo==1.0\n", encoding="utf-8")
        locks.append((lock, scope, platform))
    policy = contracts / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "review_cadence_days": 30,
                "approved_single_spdx_expressions": ["MIT"],
                "classifier_mappings": {"License :: OSI Approved :: MIT License": "MIT"},
                "legacy_license_mappings": {"MIT License": "MIT"},
                "ambiguous_markers": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    inventory_file = contracts / "inventory.json"
    inventory_file.write_text(
        json.dumps(
            {
                "policy": {"path": "contracts/security/policy.json", "sha256": _sha(policy)},
                "source_locks": [
                    {
                        "path": f"requirements/{lock.name}",
                        "scope": scope,
                        "platform": platform,
                        "sha256": _sha(lock),
                    }
                    for lock, scope, platform in locks
                ],
                "components": [
                    {
                        "name": "demo",
                        "version": "1.0",
                        "lock_membership": [
                            "ci_build_test:linux/amd64",
                            "ci_build_test:windows/amd64",
                            "runtime:linux/amd64",
                            "runtime:windows/amd64",
                        ],
                        "pypi_release_url": "https://pypi.org/project/demo/1.0/",
                        "pypi_json_url": "https://pypi.org/pypi/demo/1.0/json",
                        "pypi_metadata_sha256": "c" * 64,
                        "release_uploaded_at": "2026-08-01T00:00:00Z",
                        "license": {
                            "classification": "approved",
                            "classification_reason": "approved_declared_expression",
                            "classification_source": "pypi_license_expression",
                            "declared_expression": "MIT",
                            "legacy_value": None,
                            "classifiers": [],
                            "normalized_expression": "MIT",
                        },
                        "supportability": {
                            "classification": "reviewed",
                            "classification_reason": "governed_authority_reviewed",
                            "upstream_support_policy_url": "https://example.test/support",
                            "vulnerability_disclosure_url": "https://example.test/security",
                            "eol_evidence_url": "https://example.test/lifecycle",
                            "reviewed_on": "2026-08-12",
                            "next_review_due": "2026-09-11",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "INVENTORY_FILE", inventory_file)
    monkeypatch.setattr(guard, "_commit", lambda: "d" * 40)
    return locks[0][0], inventory_file


def test_complete_inventory_produces_allowed_exact_commit_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12))

    assert receipt["certification_decision"] == "allowed"
    assert receipt["component_count"] == 1
    assert receipt["source_commit"] == "d" * 40
    assert receipt["finding_count"] == 0


def test_lock_drift_fails_before_a_receipt_can_certify(tmp_path: Path, monkeypatch) -> None:
    lock, _inventory_file = _fixture(tmp_path, monkeypatch)
    lock.write_text("demo==2.0\n", encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="source lock drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_checkout_newline_conversion_preserves_governed_identity(
    tmp_path: Path, monkeypatch
) -> None:
    lock, inventory_file = _fixture(tmp_path, monkeypatch)
    lock.write_bytes(b"demo==1.0\r\n")
    policy = tmp_path / "contracts" / "security" / "policy.json"
    policy.write_bytes(policy.read_text(encoding="utf-8").replace("\n", "\r\n").encode())

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12))

    assert receipt["certification_decision"] == "allowed"
    assert receipt["inventory_sha256"] == normalized_text_sha256(inventory_file)


def test_review_required_and_stale_evidence_block_certification(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["license"]["classification"] = "review_required"
    data["components"][0]["supportability"]["reviewed_on"] = "2026-07-12"
    data["components"][0]["supportability"]["next_review_due"] = "2026-08-11"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12))

    assert receipt["certification_decision"] == "blocked"
    assert {finding["reason"] for finding in receipt["findings"]} == {
        "license_review_required",
        "review_stale",
    }


def test_reviewed_supportability_without_authority_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["supportability"]["upstream_support_policy_url"] = None
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks authority"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_inventory_cannot_remove_a_governed_source_lock(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    removed = data["source_locks"].pop()
    data["components"][0]["lock_membership"].remove(f"{removed['scope']}:{removed['platform']}")
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="source lock set drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_supportability_review_cannot_be_future_dated(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["supportability"]["reviewed_on"] = "2026-08-13"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="future-dated"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_supportability_deadline_cannot_exceed_policy_cadence(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["supportability"]["next_review_due"] = "2026-09-12"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="review cadence drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_approved_license_must_be_in_policy_allowlist(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["license"]["normalized_expression"] = "GPL-3.0-only"
    data["components"][0]["license"]["declared_expression"] = "GPL-3.0-only"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="outside policy"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_approved_license_must_match_recorded_source_evidence(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["license"]["declared_expression"] = None
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks policy evidence"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_approved_legacy_license_rejects_ambiguous_classifier(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    policy = tmp_path / "contracts" / "security" / "policy.json"
    policy_data = json.loads(policy.read_text(encoding="utf-8"))
    policy_data["ambiguous_markers"] = ["License :: OSI Approved"]
    policy.write_text(json.dumps(policy_data), encoding="utf-8")
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["policy"]["sha256"] = _sha(policy)
    license_evidence = data["components"][0]["license"]
    license_evidence.update(
        {
            "classification_reason": "approved_legacy_mapping",
            "classification_source": "pypi_legacy_mapping",
            "declared_expression": None,
            "legacy_value": "MIT License",
            "classifiers": ["License :: OSI Approved"],
        }
    )
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks policy evidence"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_approved_declared_license_rejects_ambiguous_classifier(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    policy = tmp_path / "contracts" / "security" / "policy.json"
    policy_data = json.loads(policy.read_text(encoding="utf-8"))
    policy_data["ambiguous_markers"] = ["License :: OSI Approved"]
    policy.write_text(json.dumps(policy_data), encoding="utf-8")
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["policy"]["sha256"] = _sha(policy)
    data["components"][0]["license"]["classifiers"] = ["License :: OSI Approved"]
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks policy evidence"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


@pytest.mark.parametrize(
    "invalid_authority",
    ["n/a", "http://example.test/support", "https://user@example.test/support", "https:///support"],
)
def test_reviewed_supportability_requires_https_authority_reference(
    tmp_path: Path, monkeypatch, invalid_authority: str
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["supportability"]["upstream_support_policy_url"] = invalid_authority
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks authority"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_validation_failure_still_writes_fail_closed_receipt(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "receipt.json"
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "INVENTORY_FILE", inventory_file)
    monkeypatch.setattr(guard, "_commit", lambda: "e" * 40)
    monkeypatch.setattr(
        guard,
        "DEFAULT_OUTPUT",
        output,
    )
    monkeypatch.setattr(sys, "argv", ["guard", "--output", str(output)])

    assert guard.main() == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["certification_decision"] == "unavailable"
    assert receipt["claim_boundary"]["release_certifying"] is False
