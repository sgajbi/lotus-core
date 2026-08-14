from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.release.cisa_kev as cisa_kev
import scripts.release.image_scan_policy as image_scan_policy
from scripts.release.cisa_kev import CISA_KEV_SOURCE_URL
from scripts.release.image_scan_policy import (
    POLICY_ID,
    SCHEMA_VERSION,
    ScanPolicyError,
    build_policy_receipt,
    build_unavailable_receipt,
    enforce_policy_receipt,
)
from scripts.release.vulnerability_authority_bundle import (
    VulnerabilityAuthorityBundleError,
)

FULL_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE_REF = "ghcr.io/sgajbi/lotus-core/query-service"
DIGEST_REF = f"{IMAGE_REF}@{IMAGE_DIGEST}"


def _write_authority_bundle(tmp_path: Path) -> Path:
    path = tmp_path / "vulnerability-authority-bundle.json"
    payload = {
        "schema_version": "lotus-core.vulnerability-authority-bundle.v1",
        "generated_at_utc": "2026-08-12T02:02:01Z",
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": FULL_SHA,
        "ci_run_id": "12345",
        "ci_run_attempt": "2",
        "cisa_kev": {"source_sha256": "sha256:" + "c" * 64},
        "exception_schema": {"source_sha256": "sha256:" + "d" * 64},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["bundle_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _completeness_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cisa-kev-authority-policy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "lotus-core.cisa-kev-authority-policy.v1",
                "source_url": CISA_KEV_SOURCE_URL,
                "baseline_catalog_version": "2026.08.12",
                "baseline_date_released_utc": "2026-08-12T00:00:00Z",
                "baseline_entry_count": 1,
                "minimum_entry_count": 1,
                "baseline_observed_at_utc": "2026-08-12T02:00:00Z",
                "review_owner": "test",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cisa_kev, "DEFAULT_COMPLETENESS_POLICY_PATH", path)


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


def _write_kev(tmp_path: Path, *, cve_ids: tuple[str, ...] = ("CVE-2020-0001",)) -> Path:
    path = tmp_path / "cisa-kev.json"
    path.write_text(
        json.dumps(
            {
                "title": "CISA Catalog of Known Exploited Vulnerabilities",
                "catalogVersion": "2026.08.12",
                "dateReleased": "2026.08.12",
                "count": len(cve_ids),
                "vulnerabilities": [{"cveID": cve_id} for cve_id in cve_ids],
            }
        ),
        encoding="utf-8",
    )
    return path


def _receipt(report_path: Path, **overrides: Any) -> dict[str, object]:
    kev_catalog_path = overrides.pop("kev_catalog_path", None)
    if kev_catalog_path is None:
        kev_catalog_path = _write_kev(report_path.parent)
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
        "scanner_image": (
            "aquasec/trivy:0.56.2@sha256:"
            "26245f364b6f5d223003dc344ec1eb5eb8439052bfecb31d79aeba0c74344b3a"
        ),
        "scan_timestamp": "2026-08-12T02:03:04Z",
        "kev_catalog_path": kev_catalog_path,
        "kev_fetched_at": "2026-08-12T02:02:00Z",
        "authority_bundle_path": _write_authority_bundle(report_path.parent),
    }
    values.update(overrides)
    return build_policy_receipt(report_path=report_path, **values)


def _enforce(receipt_path: Path, **overrides: Any) -> None:
    values = {
        "report_path": receipt_path.parent / "trivy.json",
        "kev_catalog_path": receipt_path.parent / "cisa-kev.json",
        "authority_bundle_path": receipt_path.parent / "vulnerability-authority-bundle.json",
        "expected_service": "query_service",
        "expected_image_ref": IMAGE_REF,
        "expected_image_digest": IMAGE_DIGEST,
        "expected_repository": "sgajbi/lotus-core",
        "expected_git_commit_sha": FULL_SHA,
        "expected_ci_run_id": "12345",
        "expected_ci_run_attempt": "2",
        "enforced_at": "2026-08-12T02:04:00Z",
    }
    values.update(overrides)
    enforce_policy_receipt(receipt_path, **values)


def test_unavailable_receipt_is_secret_safe_exact_and_fail_closed(tmp_path: Path) -> None:
    receipt = build_unavailable_receipt(
        service="query_service",
        image_ref=IMAGE_REF,
        image_digest=IMAGE_DIGEST,
        repository="sgajbi/lotus-core",
        git_commit_sha=FULL_SHA,
        ci_run_id="12345",
        ci_run_attempt="2",
        generated_at="2026-08-12T02:03:04Z",
        reason_code="cisa_kev_fetch_failed",
        authority_bundle_path=_write_authority_bundle(tmp_path),
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert receipt["evidence_state"] == "unavailable"
    assert receipt["failure"] == {"reason_code": "cisa_kev_fetch_failed"}
    assert "response" not in json.dumps(receipt).lower()
    with pytest.raises(ScanPolicyError, match="cisa_kev_fetch_failed"):
        _enforce(receipt_path)


@pytest.mark.parametrize("enforced_at", ["2026-08-12T03:00:00Z", "2026-08-12T02:01:00Z"])
def test_enforcement_rejects_stale_or_future_receipt(tmp_path: Path, enforced_at: str) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="stale or future-dated"):
        _enforce(receipt_path, enforced_at=enforced_at)


@pytest.mark.parametrize("version", ["v1", "v2", "v3", "v4", "v5"])
def test_current_enforcement_rejects_prior_receipt_versions(tmp_path: Path, version: str) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["schema_version"] = f"lotus-core.image-scan-policy-receipt.{version}"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="unsupported schema version"):
        _enforce(receipt_path)


def test_clean_report_builds_digest_bound_pass_receipt(tmp_path: Path) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))

    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["generated_at_utc"] == "2026-08-12T02:03:04Z"
    assert receipt["evidence_state"] == "available"
    assert receipt["evidence_boundary"] == {
        "posture": "release",
        "release_eligible": True,
        "promotion_eligible": False,
    }
    assert receipt["source"] == {
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": FULL_SHA,
        "ci_run_id": "12345",
        "ci_run_attempt": "2",
    }
    assert receipt["vulnerability_authority"] == {
        "schema_version": "lotus-core.vulnerability-authority-bundle.v1",
        "bundle_sha256": receipt["vulnerability_authority"]["bundle_sha256"],
        "generated_at_utc": "2026-08-12T02:02:01Z",
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
        "owned_plan_required_severities": ["MEDIUM"],
        "known_exploited_exceptionable": False,
        "decision": "passed",
        "finding_count": 0,
        "blocking_finding_count": 0,
        "known_exploited_finding_count": 0,
        "unclassified_exploitation_finding_count": 0,
        "unclassified_severity_finding_count": 0,
        "approved_exception_finding_count": 0,
        "severity_counts": {
            "CRITICAL": 0,
            "HIGH": 0,
            "LOW": 0,
            "MEDIUM": 0,
            "UNKNOWN": 0,
        },
    }
    assert receipt["known_exploited_catalog"] == {
        "source_url": (
            "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        ),
        "catalog_version": "2026.08.12",
        "date_released_utc": "2026-08-12T00:00:00Z",
        "fetched_at_utc": "2026-08-12T02:02:00Z",
        "source_sha256": receipt["known_exploited_catalog"]["source_sha256"],
        "entry_count": 1,
    }
    assert receipt["findings"] == []
    assert str(receipt["scanner"]["report_sha256"]).startswith("sha256:")


def test_enforcement_rejects_tampered_authority_bundle(tmp_path: Path) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    authority_path = tmp_path / "vulnerability-authority-bundle.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["cisa_kev"]["source_sha256"] = "sha256:" + "e" * 64
    authority_path.write_text(json.dumps(authority), encoding="utf-8")

    with pytest.raises(VulnerabilityAuthorityBundleError, match="digest does not match"):
        _enforce(receipt_path)


def test_enforcement_rejects_receipt_authority_substitution(tmp_path: Path) -> None:
    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["vulnerability_authority"]["bundle_sha256"] = "sha256:" + "f" * 64
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="authority identity does not match"):
        _enforce(receipt_path)


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
    assert receipt["policy"]["known_exploited_finding_count"] == 0
    assert receipt["policy"]["unclassified_exploitation_finding_count"] == 0
    assert receipt["policy"]["severity_counts"] == {
        "CRITICAL": 0,
        "HIGH": 1,
        "LOW": 0,
        "MEDIUM": 0,
        "UNKNOWN": 0,
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
            "known_exploited": False,
            "exploitation_status": "not_listed_in_current_cisa_kev",
            "approved_exception_ids": [],
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


def test_medium_secret_finding_blocks_release_without_copying_material(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "app/settings.py",
                "Class": "secret",
                "Secrets": [
                    {
                        "RuleID": "medium-secret",
                        "Category": "credential",
                        "Severity": "MEDIUM",
                        "Match": "do-not-retain-this-value",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["blocking_finding_count"] == 1
    assert "do-not-retain-this-value" not in json.dumps(receipt)


def test_medium_findings_require_an_owned_exception_plan(tmp_path: Path) -> None:
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

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["finding_count"] == 1
    assert receipt["policy"]["blocking_finding_count"] == 1
    assert receipt["policy"]["known_exploited_finding_count"] == 0
    assert receipt["policy"]["unclassified_exploitation_finding_count"] == 0
    assert receipt["policy"]["severity_counts"] == {
        "CRITICAL": 0,
        "HIGH": 0,
        "LOW": 0,
        "MEDIUM": 1,
        "UNKNOWN": 0,
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
            "known_exploited": False,
            "exploitation_status": "not_listed_in_current_cisa_kev",
            "approved_exception_ids": [],
        }
    ]


def test_exact_approved_medium_exception_remains_blocking_until_artifact_re_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ApprovedRegister:
        identity: dict[str, object] = {
            "schema_version": "lotus-platform.vulnerability-exception-register.v1",
            "register_id": "lotus-core-vulnerability-exceptions",
            "generated_at_utc": "2026-08-12T00:00:00Z",
            "register_sha256": "sha256:" + "c" * 64,
            "lane_posture": "blocking",
            "schema_authority": {"source_commit": "d" * 40},
        }

        def approved_exception_ids(
            self, *, image_digest: str, advisory_id: str, severity: str
        ) -> tuple[str, ...]:
            assert (image_digest, advisory_id, severity) == (
                IMAGE_DIGEST,
                "CVE-2026-2000",
                "MEDIUM",
            )
            return ("VX-CORE-0001",)

    monkeypatch.setattr(
        image_scan_policy,
        "load_vulnerability_exception_register",
        lambda *_args, **_kwargs: ApprovedRegister(),
    )
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

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["approved_exception_finding_count"] == 1
    assert receipt["findings"][0]["approved_exception_ids"] == ["VX-CORE-0001"]
    assert receipt["vulnerability_exception_register"]["applicable_exception_ids"] == [
        "VX-CORE-0001"
    ]


def test_exact_approved_high_exception_cannot_override_blocking_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ApprovedRegister:
        identity: dict[str, object] = {
            "schema_version": "lotus-platform.vulnerability-exception-register.v1",
            "register_id": "lotus-core-vulnerability-exceptions",
            "generated_at_utc": "2026-08-12T00:00:00Z",
            "register_sha256": "sha256:" + "c" * 64,
            "lane_posture": "blocking",
            "schema_authority": {"source_commit": "d" * 40},
        }

        def approved_exception_ids(
            self, *, image_digest: str, advisory_id: str, severity: str
        ) -> tuple[str, ...]:
            assert (image_digest, advisory_id, severity) == (
                IMAGE_DIGEST,
                "CVE-2026-2001",
                "HIGH",
            )
            return ("VX-CORE-0002",)

    monkeypatch.setattr(
        image_scan_policy,
        "load_vulnerability_exception_register",
        lambda *_args, **_kwargs: ApprovedRegister(),
    )
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-2001",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "HIGH",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["findings"][0]["approved_exception_ids"] == ["VX-CORE-0002"]


def test_low_known_exploited_vulnerability_blocks_release(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "os-pkgs",
                "Type": "debian",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-4000",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "LOW",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(
        report,
        kev_catalog_path=_write_kev(tmp_path, cve_ids=("CVE-2026-4000",)),
    )

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["known_exploited_finding_count"] == 1
    assert receipt["findings"][0]["known_exploited"] is True
    assert receipt["findings"][0]["exploitation_status"] == "known_exploited"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="1 vulnerability or secret policy finding"):
        _enforce(receipt_path)


def test_non_cve_vulnerability_blocks_as_unclassified(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "python-pkgs",
                "Type": "python-pkg",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "GHSA-abcd-efgh-ijkl",
                        "PkgName": "example",
                        "InstalledVersion": "1.0.0",
                        "Severity": "LOW",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["unclassified_exploitation_finding_count"] == 1
    assert receipt["findings"][0]["known_exploited"] is None
    assert receipt["findings"][0]["exploitation_status"] == "unclassified"


def test_missing_results_fails_closed(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    del value["Results"]
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="must contain Results"):
        _receipt(report)


def test_unknown_finding_severity_builds_actionable_blocked_receipt(tmp_path: Path) -> None:
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

    receipt = _receipt(report)

    assert receipt["evidence_state"] == "available"
    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["blocking_finding_count"] == 1
    assert receipt["policy"]["unclassified_severity_finding_count"] == 1
    assert receipt["policy"]["severity_counts"]["UNKNOWN"] == 1
    assert receipt["findings"][0]["severity"] == "UNKNOWN"
    assert receipt["findings"][0]["approved_exception_ids"] == []
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="release blocked by 1"):
        _enforce(receipt_path)


def test_unknown_secret_severity_is_retained_without_secret_material(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        results=[
            {
                "Target": "app/settings.py",
                "Class": "secret",
                "Secrets": [
                    {
                        "RuleID": "unclassified-secret",
                        "Category": "unknown",
                        "Severity": "UNKNOWN",
                        "Match": "SENSITIVE-MATERIAL",
                    }
                ],
            }
        ],
    )

    receipt = _receipt(report)
    serialized = json.dumps(receipt)

    assert receipt["policy"]["decision"] == "blocked"
    assert receipt["policy"]["unclassified_severity_finding_count"] == 1
    assert receipt["findings"][0]["severity"] == "UNKNOWN"
    assert "SENSITIVE-MATERIAL" not in serialized


def test_report_for_another_digest_fails_closed(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    value["ArtifactName"] = f"{IMAGE_REF}@sha256:{'c' * 64}"
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="does not match"):
        _receipt(report)


def test_diagnostic_report_binds_exact_local_image_id(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    value["ArtifactName"] = IMAGE_REF
    value["Metadata"] = {"ImageID": IMAGE_DIGEST}
    report.write_text(json.dumps(value), encoding="utf-8")

    receipt = _receipt(report, evidence_posture="diagnostic")

    assert receipt["evidence_boundary"] == {
        "posture": "diagnostic",
        "release_eligible": False,
        "promotion_eligible": False,
    }


def test_diagnostic_report_rejects_mismatched_local_image_id(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    value["ArtifactName"] = IMAGE_REF
    value["Metadata"] = {"ImageID": "sha256:" + "c" * 64}
    report.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ScanPolicyError, match="does not match"):
        _receipt(report, evidence_posture="diagnostic")


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


def test_stale_kev_fetch_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ScanPolicyError, match="no more than 60 minutes"):
        _receipt(
            _write_report(tmp_path, results=[]),
            kev_fetched_at="2026-08-12T01:00:00Z",
        )


def test_kev_fetch_remains_valid_through_permitted_image_build_window(tmp_path: Path) -> None:
    receipt = _receipt(
        _write_report(tmp_path, results=[]),
        kev_fetched_at="2026-08-12T01:18:00Z",
    )

    assert receipt["policy"]["decision"] == "passed"


def test_enforcement_accepts_passed_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(_receipt(_write_report(tmp_path, results=[]))), encoding="utf-8"
    )

    _enforce(receipt_path)


def test_release_enforcement_rejects_diagnostic_receipt(tmp_path: Path) -> None:
    report = _write_report(tmp_path, results=[])
    value = json.loads(report.read_text(encoding="utf-8"))
    value["ArtifactName"] = IMAGE_REF
    value["Metadata"] = {"ImageID": IMAGE_DIGEST}
    report.write_text(json.dumps(value), encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(_receipt(report, evidence_posture="diagnostic")), encoding="utf-8"
    )

    with pytest.raises(ScanPolicyError, match="evidence posture does not match"):
        _enforce(receipt_path)

    _enforce(receipt_path, expected_evidence_posture="diagnostic")


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
        ("known_exploited_catalog", "no KEV catalog identity"),
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

    receipt = _receipt(_write_report(tmp_path, results=[]))
    receipt["known_exploited_catalog"]["catalog_version"] = "tampered"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ScanPolicyError, match="does not match its source evidence"):
        _enforce(receipt_path)
