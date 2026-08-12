from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release.image_scan_policy import (
    POLICY_ID,
    SCHEMA_VERSION,
    ScanPolicyError,
    build_policy_receipt,
    enforce_policy_receipt,
)

FULL_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE_REF = "ghcr.io/sgajbi/lotus-core/query-service"
DIGEST_REF = f"{IMAGE_REF}@{IMAGE_DIGEST}"


def _write_report(tmp_path: Path, *, results: list[object]) -> Path:
    path = tmp_path / "trivy.json"
    path.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactName": DIGEST_REF,
                "ArtifactType": "container_image",
                "Results": results,
            }
        ),
        encoding="utf-8",
    )
    return path


def _receipt(report_path: Path, **overrides: str) -> dict[str, object]:
    values = {
        "service": "query_service",
        "image_ref": IMAGE_REF,
        "image_digest": IMAGE_DIGEST,
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": FULL_SHA,
        "ci_run_id": "12345",
        "ci_run_attempt": "2",
        "scanner_name": "trivy",
        "scanner_version": "0.56.2",
        "scanner_image": "aquasec/trivy:0.56.2",
        "scan_timestamp": "2026-08-12T02:03:04Z",
    }
    values.update(overrides)
    return build_policy_receipt(report_path=report_path, **values)


def _enforce(receipt_path: Path, **overrides: str) -> None:
    values = {
        "expected_service": "query_service",
        "expected_image_ref": IMAGE_REF,
        "expected_image_digest": IMAGE_DIGEST,
        "expected_repository": "sgajbi/lotus-core",
        "expected_git_commit_sha": FULL_SHA,
        "expected_ci_run_id": "12345",
        "expected_ci_run_attempt": "2",
    }
    values.update(overrides)
    enforce_policy_receipt(receipt_path, **values)


def test_clean_report_builds_digest_bound_pass_receipt(tmp_path: Path) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))

    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["generated_at_utc"] == "2026-08-12T02:03:04Z"
    assert receipt["source"] == {
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": FULL_SHA,
        "ci_run_id": "12345",
        "ci_run_attempt": "2",
    }
    assert receipt["subject"] == {
        "service": "query_service",
        "image_ref": IMAGE_REF,
        "image_digest": IMAGE_DIGEST,
        "digest_image_ref": DIGEST_REF,
    }
    assert receipt["policy"] == {
        "policy_id": POLICY_ID,
        "scanners": ["vulnerability", "secret"],
        "blocking_severities": ["CRITICAL", "HIGH"],
        "decision": "passed",
        "finding_count": 0,
        "blocking_finding_count": 0,
        "severity_counts": {"CRITICAL": 0, "HIGH": 0, "LOW": 0, "MEDIUM": 0},
    }
    assert receipt["findings"] == []
    assert str(receipt["scanner"]["report_sha256"]).startswith("sha256:")


def test_high_vulnerability_builds_blocked_normalized_receipt(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "usr/local/lib/python3.11/site-packages",
                "Class": "lang-pkgs",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-1000",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "FixedVersion": "1.0.1",
                        "Severity": "HIGH",
                        "Title": "not copied into the receipt",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["finding_count"] == 1
    assert receipt["policy"]["blocking_finding_count"] == 1
    assert receipt["policy"]["severity_counts"] == {
        "CRITICAL": 0,
        "HIGH": 1,
        "LOW": 0,
        "MEDIUM": 0,
    }
    assert receipt["findings"] == [
        {
            "finding_type": "vulnerability",
            "finding_id": "CVE-2026-1000",
            "severity": "HIGH",
            "target": "usr/local/lib/python3.11/site-packages",
            "target_class": "lang-pkgs",
            "component_name": "example",
            "installed_version": "1.0.0",
            "fixed_version": "1.0.1",
        }
    ]


def test_secret_receipt_never_copies_secret_material(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "app/settings.py",
                "Class": "secret",
                "Secrets": [
                    {
                        "RuleID": "aws-access-key-id",
                        "Category": "AWS",
                        "Severity": "CRITICAL",
                        "Match": "AKIA-SENSITIVE-MATERIAL",
                        "Code": {"Lines": [{"Content": "secret material"}]},
                    }
                ],
            }
        ],
    )

    serialized = json.dumps(_receipt(report))

    assert "aws-access-key-id" in serialized
    assert "AKIA-SENSITIVE-MATERIAL" not in serialized
    assert "secret material" not in serialized


def test_medium_findings_do_not_change_current_release_policy(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-2000",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "MEDIUM",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)

    assert receipt["policy"]["decision"] == "passed"
    assert receipt["policy"]["finding_count"] == 1
    assert receipt["policy"]["blocking_finding_count"] == 0
    assert receipt["policy"]["severity_counts"] == {
        "CRITICAL": 0,
        "HIGH": 0,
        "LOW": 0,
        "MEDIUM": 1,
    }
    assert receipt["findings"] == [
        {
            "finding_type": "vulnerability",
            "finding_id": "CVE-2026-2000",
            "severity": "MEDIUM",
            "target": "os-pkgs",
            "target_class": "debian",
            "component_name": "example",
            "installed_version": "1.0.0",
            "fixed_version": "",
        }
    ]


def test_missing_results_fails_closed(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    del value["Results"]
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="must contain Results"):
        _receipt(report)


def test_unknown_finding_severity_fails_closed(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-UNKNOWN",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "UNKNOWN",
                    }
                ],
            }
        ],
    )

    with pytest.raises(ScanPolicyError, match="unknown vulnerability severity"):
        _receipt(report)


def test_report_for_another_digest_fails_closed(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    value["ArtifactName"] = f"{IMAGE_REF}@sha256:{'c' * 64}"
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="does not match"):
        _receipt(report)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("git_commit_sha", "abc123", "full lowercase SHA"),
        ("image_digest", "sha256:short", "sha256 digest"),
        ("ci_run_id", "0", "positive integer"),
        ("scan_timestamp", "2026-08-12T02:03:04", "explicit UTC"),
    ],
)
def test_invalid_provenance_fails_closed(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    with pytest.raises(ScanPolicyError, match=message):
        _receipt(_write_report(tmp_path, results=[]), **{field: value})


def test_unapproved_scanner_identity_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ScanPolicyError, match="governed release scanner"):
        _receipt(
            _write_report(tmp_path, results=[]),
            scanner_image="aquasec/trivy:latest",
        )


def test_enforcement_accepts_passed_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(_receipt(_write_report(tmp_path, results=[]))), encoding="utf-8"
    )

    _enforce(receipt_path)


def test_enforcement_rejects_blocked_or_inconsistent_receipt(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-3000",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "CRITICAL",
                    }
                ],
            }
        ],
    )
    receipt_path = tmp_path / "receipt.json"
    receipt = _receipt(report)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="release blocked"):
        _enforce(receipt_path)

    receipt["policy"]["blocking_finding_count"] = 0
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="blocking count is inconsistent"):
        _enforce(receipt_path)


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ("source", "source identity does not match"),
        ("subject", "subject identity does not match"),
        ("scanner", "no scanner identity"),
        ("policy", "no policy decision"),
    ],
)
def test_enforcement_rejects_missing_authority_sections(
    tmp_path: Path, section: str, message: str
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = _receipt(_write_report(tmp_path, results=[]))
    del receipt[section]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match=message):
        _enforce(receipt_path)


def test_enforcement_rejects_wrong_expected_digest(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(_receipt(_write_report(tmp_path, results=[]))), encoding="utf-8"
    )

    with pytest.raises(ScanPolicyError, match="subject identity does not match"):
        _enforce(receipt_path, expected_image_digest="sha256:" + "c" * 64)


def test_enforcement_rejects_tampered_policy_and_findings(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["policy"]["policy_id"] = "unapproved"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="unsupported policy ID"):
        _enforce(receipt_path)

    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["findings"] = [{"finding_type": "arbitrary"}]
    receipt["policy"]["blocking_finding_count"] = 1
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="unsupported finding type"):
        _enforce(receipt_path)

    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["scanner"]["version"] = "unapproved"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="unsupported scanner identity"):
        _enforce(receipt_path)
