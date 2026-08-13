import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from scripts.quality import dependency_technology_inventory_guard as guard
from scripts.quality.technology_governance_identity import normalized_text_sha256


def _sha(path: Path) -> str:
    return normalized_text_sha256(path)


def _pypi_payload() -> dict[str, object]:
    return {
        "info": {
            "yanked": False,
            "license_expression": "MIT",
            "license": "",
            "classifiers": [],
        },
        "urls": [{"upload_time_iso_8601": "2026-08-01T00:00:00Z"}],
    }


def _metadata_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                "schema_version": guard.INVENTORY_SCHEMA_VERSION,
                "inventory_id": guard.INVENTORY_ID,
                "repository": guard.INVENTORY_REPOSITORY,
                "governed_by_issue": guard.INVENTORY_ISSUE,
                "generator": guard.INVENTORY_GENERATOR,
                "source_baseline_commit": "c" * 40,
                "generated_at_utc": "2026-08-12T00:00:00Z",
                "claim_boundary": {
                    "bank_buyable_claim": False,
                    "popularity_based_approval": False,
                    "production_ready_claim": False,
                    "technology_state": "approved_default_candidate",
                },
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
                        "pypi_metadata_sha256": _metadata_sha256(_pypi_payload()),
                        "release_uploaded_at": "2026-08-01T00:00:00Z",
                        "yanked": False,
                        "prerelease": False,
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
                            "release_evidence_url": "https://pypi.org/project/demo/1.0/",
                            "upstream_support_policy_url": "https://example.test/support",
                            "vulnerability_disclosure_url": "https://example.test/security",
                            "eol_evidence_url": "https://example.test/lifecycle",
                            "reviewed_on": "2026-08-12",
                            "next_review_due": "2026-09-11",
                            "approval_inference": "none",
                        },
                    }
                ],
                "summary": {
                    "approved_license_count": 1,
                    "blocked_or_review_required_count": 0,
                    "certification_decision": "allowed",
                    "component_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "INVENTORY_FILE", inventory_file)
    monkeypatch.setattr(guard, "_commit", lambda: "d" * 40)
    monkeypatch.setattr(guard, "_commit_is_ancestor", lambda _candidate: True)
    return locks[0][0], inventory_file


def test_complete_inventory_requires_online_authority_before_certification(
    tmp_path: Path, monkeypatch
) -> None:
    _fixture(tmp_path, monkeypatch)

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12))

    assert receipt["certification_decision"] == "blocked"
    assert receipt["component_count"] == 1
    assert receipt["source_commit"] == "d" * 40
    assert receipt["finding_count"] == 0
    assert receipt["pypi_authority_revalidation"]["status"] == "not_run"


@pytest.mark.parametrize(
    "field",
    ["production_ready_claim", "bank_buyable_claim", "popularity_based_approval"],
)
def test_inventory_prohibited_claims_fail_closed(tmp_path: Path, monkeypatch, field: str) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["claim_boundary"][field] = True
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match=f"prohibits {field}"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("component_count", 2),
        ("approved_license_count", 0),
        ("blocked_or_review_required_count", 1),
        ("certification_decision", "blocked"),
    ],
)
def test_inventory_summary_must_match_component_evidence(
    tmp_path: Path, monkeypatch, field: str, value: object
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["summary"][field] = value
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="summary contradicts"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_inventory_technology_state_must_match_component_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["claim_boundary"]["technology_state"] = "non_certifying"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="technology state contradicts"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "lotus-core.dependency-technology-inventory.v0"),
        ("inventory_id", "another-inventory"),
        ("repository", "https://github.com/example/fork"),
        ("governed_by_issue", "https://github.com/sgajbi/lotus-core/issues/1"),
        ("generator", {"id": "uncontrolled-generator", "version": "1.0.0"}),
    ],
)
def test_inventory_provenance_must_match_governed_identity(
    tmp_path: Path, monkeypatch, field: str, value: object
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data[field] = value
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match=f"{field} provenance drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_inventory_source_commit_must_be_a_reachable_full_sha(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["source_baseline_commit"] = "not-a-sha"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="must be a full SHA"):
        guard.validate_inventory(as_of=date(2026, 8, 12))

    data["source_baseline_commit"] = "b" * 40
    inventory_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(guard, "_commit_is_ancestor", lambda _candidate: False)
    with pytest.raises(guard.InventoryValidationError, match="not an ancestor"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_inventory_generation_time_cannot_be_future_dated(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["generated_at_utc"] = "2026-08-13T00:00:00Z"
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="generation time is invalid"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_exact_online_pypi_authority_allows_certification(tmp_path: Path, monkeypatch) -> None:
    _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(guard, "_fetch_pypi_metadata", lambda _url: _pypi_payload())

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12), verify_pypi_authority=True)

    assert receipt["certification_decision"] == "allowed"
    assert receipt["claim_boundary"]["release_certifying"] is True
    assert receipt["pypi_authority_revalidation"]["status"] == "passed"


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

    assert receipt["certification_decision"] == "blocked"
    assert receipt["inventory_sha256"] == normalized_text_sha256(inventory_file)


def test_review_required_and_stale_evidence_block_certification(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["license"]["classification"] = "review_required"
    data["components"][0]["supportability"]["reviewed_on"] = "2026-07-12"
    data["components"][0]["supportability"]["next_review_due"] = "2026-08-11"
    data["claim_boundary"]["technology_state"] = "non_certifying"
    data["summary"].update(
        {
            "approved_license_count": 0,
            "blocked_or_review_required_count": 1,
            "certification_decision": "blocked",
        }
    )
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


def test_approved_classifier_license_rejects_ambiguous_marker(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    policy = tmp_path / "contracts" / "security" / "policy.json"
    policy_data = json.loads(policy.read_text(encoding="utf-8"))
    policy_data["ambiguous_markers"] = ["License :: OSI Approved"]
    policy.write_text(json.dumps(policy_data), encoding="utf-8")
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["policy"]["sha256"] = _sha(policy)
    data["components"][0]["license"].update(
        {
            "classification_reason": "approved_classifier_mapping",
            "classification_source": "pypi_classifier_mapping",
            "declared_expression": None,
            "classifiers": [
                "License :: OSI Approved",
                "License :: OSI Approved :: MIT License",
            ],
        }
    )
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="lacks policy evidence"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_yanked_release_blocks_certification(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["yanked"] = True
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    receipt = guard.validate_inventory(as_of=date(2026, 8, 12))

    assert receipt["certification_decision"] == "blocked"
    assert {finding["reason"] for finding in receipt["findings"]} == {"release_yanked"}


def test_online_authority_rejects_recorded_yanked_posture_drift(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    payload = _pypi_payload()
    payload["info"]["yanked"] = True  # type: ignore[index]
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["pypi_metadata_sha256"] = _metadata_sha256(payload)
    inventory_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(guard, "_fetch_pypi_metadata", lambda _url: payload)

    with pytest.raises(guard.InventoryValidationError, match="yanked evidence drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12), verify_pypi_authority=True)


def test_online_authority_rejects_recorded_license_evidence_drift(
    tmp_path: Path, monkeypatch
) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    payload = _pypi_payload()
    payload["info"]["classifiers"] = [  # type: ignore[index]
        "License :: OSI Approved :: MIT License"
    ]
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["pypi_metadata_sha256"] = _metadata_sha256(payload)
    inventory_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(guard, "_fetch_pypi_metadata", lambda _url: payload)

    with pytest.raises(guard.InventoryValidationError, match="license evidence drift"):
        guard.validate_inventory(as_of=date(2026, 8, 12), verify_pypi_authority=True)


def test_release_posture_flags_are_required(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0].pop("prerelease")
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="invalid release posture flags"):
        guard.validate_inventory(as_of=date(2026, 8, 12))


def test_prerelease_flag_must_match_locked_version(tmp_path: Path, monkeypatch) -> None:
    _lock, inventory_file = _fixture(tmp_path, monkeypatch)
    data = json.loads(inventory_file.read_text(encoding="utf-8"))
    data["components"][0]["prerelease"] = True
    inventory_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(guard.InventoryValidationError, match="prerelease evidence drift"):
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
