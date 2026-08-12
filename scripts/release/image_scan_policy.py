"""Create and enforce a secret-safe policy receipt for one Trivy image scan."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from scripts.release.cisa_kev import (
    CVE_PATTERN,
    CisaKevCatalog,
    CisaKevError,
    load_cisa_kev_catalog,
)
from scripts.release.vulnerability_exception_policy import (
    DEFAULT_REGISTER_PATH,
    VulnerabilityExceptionError,
    VulnerabilityExceptionRegister,
    load_vulnerability_exception_register,
)

SCHEMA_VERSION = "lotus-core.image-scan-policy-receipt.v4"
POLICY_ID = "lotus-core.image-release-vulnerability-secret-kev-exceptions.v2"
SCANNER_NAME = "trivy"
SCANNER_VERSION = "0.56.2"
SCANNER_IMAGE = "aquasec/trivy:0.56.2"
BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
KNOWN_NONBLOCKING_SEVERITIES = frozenset({"LOW", "MEDIUM"})
UNCLASSIFIED_SEVERITIES = frozenset({"UNKNOWN"})
KNOWN_SEVERITIES = BLOCKING_SEVERITIES | KNOWN_NONBLOCKING_SEVERITIES | UNCLASSIFIED_SEVERITIES
FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_KEV_TO_SCAN_AGE_SECONDS = 900
MAX_RECEIPT_TO_ENFORCEMENT_AGE_SECONDS = 1800
MAX_ENFORCEMENT_FUTURE_SKEW_SECONDS = 60
UNAVAILABLE_REASON_CODES = frozenset(
    {
        "cisa_kev_fetch_failed",
        "exception_schema_fetch_failed",
        "trivy_scan_failed",
        "evidence_evaluation_failed",
    }
)


class ScanPolicyError(ValueError):
    """Raised when scan evidence cannot support a release decision."""


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScanPolicyError(f"{field} must be a non-empty string")
    return value.strip()


def _utc_timestamp(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ScanPolicyError("scan timestamp must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ScanPolicyError("scan timestamp must include an explicit UTC offset")
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(_utc_timestamp(value).replace("Z", "+00:00"))


def _source_identity(
    *, repository: str, git_commit_sha: str, ci_run_id: str, ci_run_attempt: str
) -> dict[str, str]:
    repository = _required_string(repository, field="repository")
    if not FULL_GIT_SHA_PATTERN.fullmatch(git_commit_sha):
        raise ScanPolicyError("git commit SHA must be a full lowercase SHA")
    for value, field in ((ci_run_id, "CI run ID"), (ci_run_attempt, "CI run attempt")):
        if not value.isdecimal() or int(value) < 1:
            raise ScanPolicyError(f"{field} must be a positive integer")
    return {
        "repository": repository,
        "git_commit_sha": git_commit_sha,
        "ci_run_id": ci_run_id,
        "ci_run_attempt": ci_run_attempt,
    }


def _subject_identity(*, service: str, image_ref: str, image_digest: str) -> dict[str, str]:
    service = _required_string(service, field="service")
    image_ref = _required_string(image_ref, field="image ref")
    if not SHA256_DIGEST_PATTERN.fullmatch(image_digest):
        raise ScanPolicyError("image digest must be a sha256 digest")
    return {
        "service": service,
        "image_ref": image_ref,
        "image_digest": image_digest,
        "digest_image_ref": f"{image_ref}@{image_digest}",
    }


def build_unavailable_receipt(
    *,
    service: str,
    image_ref: str,
    image_digest: str,
    repository: str,
    git_commit_sha: str,
    ci_run_id: str,
    ci_run_attempt: str,
    generated_at: str,
    reason_code: str,
) -> dict[str, object]:
    if reason_code not in UNAVAILABLE_REASON_CODES:
        raise ScanPolicyError("unsupported evidence-unavailable reason code")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_timestamp(generated_at),
        "evidence_state": "unavailable",
        "source": _source_identity(
            repository=repository,
            git_commit_sha=git_commit_sha,
            ci_run_id=ci_run_id,
            ci_run_attempt=ci_run_attempt,
        ),
        "subject": _subject_identity(
            service=service, image_ref=image_ref, image_digest=image_digest
        ),
        "scanner": {"name": SCANNER_NAME, "version": SCANNER_VERSION, "image": SCANNER_IMAGE},
        "known_exploited_catalog": None,
        "vulnerability_exception_register": None,
        "policy": {"policy_id": POLICY_ID, "decision": "blocked"},
        "failure": {"reason_code": reason_code},
        "findings": [],
    }


def _load_json_object(path: Path, *, evidence_name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanPolicyError(f"cannot read {evidence_name} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ScanPolicyError(f"{evidence_name} must contain a JSON object")
    return value


def _report_subject_matches(
    report: dict[str, Any], *, digest_image_ref: str, image_digest: str
) -> bool:
    if report.get("ArtifactName") == digest_image_ref:
        return True
    metadata = report.get("Metadata")
    if not isinstance(metadata, dict):
        return False
    repo_digests = metadata.get("RepoDigests")
    return isinstance(repo_digests, list) and any(
        isinstance(value, str) and value.endswith(f"@{image_digest}") and value == digest_image_ref
        for value in repo_digests
    )


def _normalized_vulnerability(
    raw: object,
    *,
    target: str,
    target_class: str,
    kev_catalog: CisaKevCatalog,
    exception_register: VulnerabilityExceptionRegister,
    image_digest: str,
) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ScanPolicyError("Trivy vulnerability entries must be objects")
    severity = _required_string(raw.get("Severity"), field="vulnerability severity").upper()
    if severity not in KNOWN_SEVERITIES:
        raise ScanPolicyError(f"unsupported vulnerability severity: {severity}")
    finding_id = _required_string(raw.get("VulnerabilityID"), field="vulnerability ID")
    known_exploited: bool | None = None
    exploitation_status = "unclassified"
    if CVE_PATTERN.fullmatch(finding_id):
        known_exploited = finding_id in kev_catalog.cve_ids
        exploitation_status = (
            "known_exploited" if known_exploited else "not_listed_in_current_cisa_kev"
        )
    approved_exception_ids: tuple[str, ...] = ()
    if known_exploited is False and severity not in UNCLASSIFIED_SEVERITIES:
        approved_exception_ids = exception_register.approved_exception_ids(
            image_digest=image_digest, advisory_id=finding_id, severity=severity
        )
    return {
        "finding_type": "vulnerability",
        "finding_id": finding_id,
        "severity": severity,
        "target": target,
        "target_class": target_class,
        "component_name": _required_string(raw.get("PkgName"), field="package name"),
        "installed_version": _required_string(
            raw.get("InstalledVersion"), field="installed version"
        ),
        "fixed_version": str(raw.get("FixedVersion") or ""),
        "known_exploited": known_exploited,
        "exploitation_status": exploitation_status,
        "approved_exception_ids": list(approved_exception_ids),
    }


def _normalized_secret(raw: object, *, target: str, target_class: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ScanPolicyError("Trivy secret entries must be objects")
    severity = _required_string(raw.get("Severity"), field="secret severity").upper()
    if severity not in KNOWN_SEVERITIES:
        raise ScanPolicyError(f"unsupported secret severity: {severity}")
    return {
        "finding_type": "secret",
        "finding_id": _required_string(raw.get("RuleID"), field="secret rule ID"),
        "severity": severity,
        "target": target,
        "target_class": target_class,
        "component_name": str(raw.get("Category") or "secret"),
        "installed_version": "",
        "fixed_version": "",
        "known_exploited": None,
        "exploitation_status": "not_applicable",
        "approved_exception_ids": [],
    }


def _normalized_findings(
    report: dict[str, Any],
    *,
    kev_catalog: CisaKevCatalog,
    exception_register: VulnerabilityExceptionRegister,
    image_digest: str,
) -> list[dict[str, object]]:
    if "Results" not in report:
        raise ScanPolicyError("Trivy report must contain Results")
    results = report["Results"]
    if not isinstance(results, list):
        raise ScanPolicyError("Trivy Results must be an array")

    findings: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, dict):
            raise ScanPolicyError("Trivy result entries must be objects")
        target = _required_string(result.get("Target"), field="Trivy result target")
        target_class = str(result.get("Class") or result.get("Type") or "unknown")
        for raw in result.get("Vulnerabilities") or []:
            finding = _normalized_vulnerability(
                raw,
                target=target,
                target_class=target_class,
                kev_catalog=kev_catalog,
                exception_register=exception_register,
                image_digest=image_digest,
            )
            findings.append(finding)
        for raw in result.get("Secrets") or []:
            finding = _normalized_secret(raw, target=target, target_class=target_class)
            findings.append(finding)
    return sorted(
        findings,
        key=lambda finding: (
            finding["finding_type"],
            finding["severity"],
            finding["finding_id"],
            finding["target"],
            finding["component_name"],
            finding["installed_version"],
        ),
    )


def _finding_blocks(finding: dict[str, object]) -> bool:
    if finding["severity"] in UNCLASSIFIED_SEVERITIES:
        return True
    if finding["finding_type"] == "secret":
        return finding["severity"] in BLOCKING_SEVERITIES
    if finding["known_exploited"] is True or finding["known_exploited"] is None:
        return True
    if finding["approved_exception_ids"]:
        return False
    return finding["severity"] in BLOCKING_SEVERITIES or finding["severity"] == "MEDIUM"


def build_policy_receipt(
    *,
    report_path: Path,
    service: str,
    image_ref: str,
    image_digest: str,
    repository: str,
    git_commit_sha: str,
    ci_run_id: str,
    ci_run_attempt: str,
    scanner_name: str,
    scanner_version: str,
    scanner_image: str,
    scan_timestamp: str,
    kev_catalog_path: Path,
    kev_fetched_at: str,
    exception_register_path: Path = DEFAULT_REGISTER_PATH,
    exception_schema_path: Path | None = None,
) -> dict[str, object]:
    source_identity = _source_identity(
        repository=repository,
        git_commit_sha=git_commit_sha,
        ci_run_id=ci_run_id,
        ci_run_attempt=ci_run_attempt,
    )
    subject_identity = _subject_identity(
        service=service, image_ref=image_ref, image_digest=image_digest
    )
    scanner_name = _required_string(scanner_name, field="scanner name")
    scanner_version = _required_string(scanner_version, field="scanner version")
    scanner_image = _required_string(scanner_image, field="scanner image")
    if (scanner_name, scanner_version, scanner_image) != (
        SCANNER_NAME,
        SCANNER_VERSION,
        SCANNER_IMAGE,
    ):
        raise ScanPolicyError("scanner identity does not match the governed release scanner")
    normalized_scan_timestamp = _utc_timestamp(scan_timestamp)
    kev_catalog = load_cisa_kev_catalog(kev_catalog_path, fetched_at=kev_fetched_at)
    exception_register = load_vulnerability_exception_register(
        exception_register_path,
        evaluated_at=normalized_scan_timestamp,
        canonical_schema_path=exception_schema_path,
    )
    scan_time = datetime.fromisoformat(normalized_scan_timestamp.replace("Z", "+00:00"))
    catalog_age_seconds = (scan_time - kev_catalog.fetched_at_utc).total_seconds()
    if not 0 <= catalog_age_seconds <= MAX_KEV_TO_SCAN_AGE_SECONDS:
        raise ScanPolicyError(
            "CISA KEV fetch must precede the scan receipt by no more than 15 minutes"
        )
    report_bytes = report_path.read_bytes()
    report = _load_json_object(report_path, evidence_name="Trivy report")
    if report.get("SchemaVersion") != 2:
        raise ScanPolicyError("Trivy report SchemaVersion must be 2")
    digest_image_ref = subject_identity["digest_image_ref"]
    if not _report_subject_matches(
        report, digest_image_ref=digest_image_ref, image_digest=image_digest
    ):
        raise ScanPolicyError("Trivy report does not match the expected image digest")

    findings = _normalized_findings(
        report,
        kev_catalog=kev_catalog,
        exception_register=exception_register,
        image_digest=image_digest,
    )
    severity_counts = {
        severity: sum(finding["severity"] == severity for finding in findings)
        for severity in sorted(KNOWN_SEVERITIES)
    }
    blocking_count = sum(_finding_blocks(finding) for finding in findings)
    known_exploited_count = sum(finding["known_exploited"] is True for finding in findings)
    unclassified_exploitation_count = sum(
        finding["finding_type"] == "vulnerability" and finding["known_exploited"] is None
        for finding in findings
    )
    unclassified_severity_count = sum(
        finding["severity"] in UNCLASSIFIED_SEVERITIES for finding in findings
    )
    approved_exception_count = sum(bool(finding["approved_exception_ids"]) for finding in findings)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": normalized_scan_timestamp,
        "evidence_state": "available",
        "source": source_identity,
        "subject": subject_identity,
        "scanner": {
            "name": scanner_name,
            "version": scanner_version,
            "image": scanner_image,
            "report_sha256": "sha256:" + hashlib.sha256(report_bytes).hexdigest(),
        },
        "known_exploited_catalog": kev_catalog.receipt_identity(),
        "vulnerability_exception_register": {
            **exception_register.identity,
            "applicable_exception_ids": sorted(
                exception_id
                for finding in findings
                for exception_id in cast(list[str], finding["approved_exception_ids"])
            ),
        },
        "policy": {
            "policy_id": POLICY_ID,
            "scanners": ["vulnerability", "secret"],
            "blocking_severities": sorted(BLOCKING_SEVERITIES),
            "owned_plan_required_severities": ["MEDIUM"],
            "known_exploited_exceptionable": False,
            "decision": "blocked" if blocking_count else "passed",
            "finding_count": len(findings),
            "blocking_finding_count": blocking_count,
            "known_exploited_finding_count": known_exploited_count,
            "unclassified_exploitation_finding_count": unclassified_exploitation_count,
            "unclassified_severity_finding_count": unclassified_severity_count,
            "approved_exception_finding_count": approved_exception_count,
            "severity_counts": severity_counts,
        },
        "findings": findings,
    }


def _validate_finding(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ScanPolicyError("image scan policy receipt findings must be objects")
    finding_type = _required_string(raw.get("finding_type"), field="finding type")
    if finding_type not in {"vulnerability", "secret"}:
        raise ScanPolicyError(f"unsupported finding type: {finding_type}")
    finding = {
        "finding_type": finding_type,
        "finding_id": _required_string(raw.get("finding_id"), field="finding ID"),
        "severity": _required_string(raw.get("severity"), field="finding severity").upper(),
        "target": _required_string(raw.get("target"), field="finding target"),
        "target_class": _required_string(raw.get("target_class"), field="finding target class"),
        "component_name": _required_string(
            raw.get("component_name"), field="finding component name"
        ),
        "installed_version": str(raw.get("installed_version") or ""),
        "fixed_version": str(raw.get("fixed_version") or ""),
        "known_exploited": raw.get("known_exploited"),
        "exploitation_status": _required_string(
            raw.get("exploitation_status"), field="finding exploitation status"
        ),
        "approved_exception_ids": raw.get("approved_exception_ids"),
    }
    if finding["severity"] not in KNOWN_SEVERITIES:
        raise ScanPolicyError("receipt findings must use a known severity")
    if finding_type == "vulnerability" and not finding["installed_version"]:
        raise ScanPolicyError("vulnerability finding requires installed version")
    exception_ids = finding["approved_exception_ids"]
    if (
        not isinstance(exception_ids, list)
        or exception_ids != sorted(exception_ids)
        or len(exception_ids) != len(set(exception_ids))
        or any(not isinstance(value, str) or not value.startswith("VX-") for value in exception_ids)
    ):
        raise ScanPolicyError("finding exception identities are not normalized")
    if finding_type == "secret":
        if (
            exception_ids
            or finding["known_exploited"] is not None
            or (finding["exploitation_status"] != "not_applicable")
        ):
            raise ScanPolicyError("secret finding has invalid exploitation classification")
    elif finding["known_exploited"] is True:
        if exception_ids or finding["exploitation_status"] != "known_exploited":
            raise ScanPolicyError("known-exploited finding classification is inconsistent")
    elif finding["known_exploited"] is False:
        if finding["exploitation_status"] != "not_listed_in_current_cisa_kev":
            raise ScanPolicyError("non-KEV finding classification is inconsistent")
    elif finding["exploitation_status"] != "unclassified":
        raise ScanPolicyError("unclassified finding classification is inconsistent")
    return finding


def enforce_policy_receipt(
    receipt_path: Path,
    *,
    report_path: Path,
    kev_catalog_path: Path,
    exception_register_path: Path = DEFAULT_REGISTER_PATH,
    exception_schema_path: Path | None = None,
    expected_service: str,
    expected_image_ref: str,
    expected_image_digest: str,
    expected_repository: str,
    expected_git_commit_sha: str,
    expected_ci_run_id: str,
    expected_ci_run_attempt: str,
    enforced_at: str,
) -> None:
    receipt = _load_json_object(receipt_path, evidence_name="image scan policy receipt")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ScanPolicyError("image scan policy receipt has an unsupported schema version")
    generated_at = _utc_datetime(
        _required_string(receipt.get("generated_at_utc"), field="receipt generated-at")
    )
    enforcement_time = _utc_datetime(enforced_at)
    receipt_age_seconds = (enforcement_time - generated_at).total_seconds()
    if not (
        -MAX_ENFORCEMENT_FUTURE_SKEW_SECONDS
        <= receipt_age_seconds
        <= MAX_RECEIPT_TO_ENFORCEMENT_AGE_SECONDS
    ):
        raise ScanPolicyError("image scan policy receipt is stale or future-dated")
    expected_source = _source_identity(
        repository=expected_repository,
        git_commit_sha=expected_git_commit_sha,
        ci_run_id=expected_ci_run_id,
        ci_run_attempt=expected_ci_run_attempt,
    )
    if receipt.get("source") != expected_source:
        raise ScanPolicyError("image scan policy receipt source identity does not match")
    expected_subject = _subject_identity(
        service=expected_service,
        image_ref=expected_image_ref,
        image_digest=expected_image_digest,
    )
    if receipt.get("subject") != expected_subject:
        raise ScanPolicyError("image scan policy receipt subject identity does not match")
    scanner = receipt.get("scanner")
    if not isinstance(scanner, dict):
        raise ScanPolicyError("image scan policy receipt has no scanner identity")
    expected_scanner_identity = {
        "name": SCANNER_NAME,
        "version": SCANNER_VERSION,
        "image": SCANNER_IMAGE,
    }
    if {field: scanner.get(field) for field in expected_scanner_identity} != (
        expected_scanner_identity
    ):
        raise ScanPolicyError("image scan policy receipt has an unsupported scanner identity")
    if receipt.get("evidence_state") == "unavailable":
        failure = receipt.get("failure")
        reason_code = failure.get("reason_code") if isinstance(failure, dict) else None
        expected_unavailable = build_unavailable_receipt(
            service=expected_service,
            image_ref=expected_image_ref,
            image_digest=expected_image_digest,
            repository=expected_repository,
            git_commit_sha=expected_git_commit_sha,
            ci_run_id=expected_ci_run_id,
            ci_run_attempt=expected_ci_run_attempt,
            generated_at=receipt["generated_at_utc"],
            reason_code=str(reason_code or ""),
        )
        if receipt != expected_unavailable:
            raise ScanPolicyError("unavailable image scan receipt is not normalized")
        raise ScanPolicyError(f"image scan evidence unavailable: {reason_code}")
    if receipt.get("evidence_state") != "available":
        raise ScanPolicyError("image scan policy receipt has an unsupported evidence state")
    report_digest = _required_string(scanner.get("report_sha256"), field="scanner report digest")
    if not SHA256_DIGEST_PATTERN.fullmatch(report_digest):
        raise ScanPolicyError("scanner report digest must be a sha256 digest")
    kev_identity = receipt.get("known_exploited_catalog")
    if not isinstance(kev_identity, dict):
        raise ScanPolicyError("image scan policy receipt has no KEV catalog identity")
    expected_kev_source = (
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    )
    if kev_identity.get("source_url") != expected_kev_source:
        raise ScanPolicyError("image scan policy receipt has an unsupported KEV source")
    for field in ("catalog_version", "date_released_utc", "fetched_at_utc"):
        _required_string(kev_identity.get(field), field=f"KEV {field}")
    kev_fetched_at = _utc_datetime(str(kev_identity["fetched_at_utc"]))
    kev_age_seconds = (enforcement_time - kev_fetched_at).total_seconds()
    if not (
        -MAX_ENFORCEMENT_FUTURE_SKEW_SECONDS
        <= kev_age_seconds
        <= MAX_RECEIPT_TO_ENFORCEMENT_AGE_SECONDS
    ):
        raise ScanPolicyError("CISA KEV authority evidence is stale or future-dated")
    kev_digest = _required_string(kev_identity.get("source_sha256"), field="KEV source digest")
    if not SHA256_DIGEST_PATTERN.fullmatch(kev_digest):
        raise ScanPolicyError("KEV source digest must be a sha256 digest")
    if not isinstance(kev_identity.get("entry_count"), int) or kev_identity["entry_count"] < 1:
        raise ScanPolicyError("KEV entry count must be positive")
    exception_identity = receipt.get("vulnerability_exception_register")
    if not isinstance(exception_identity, dict):
        raise ScanPolicyError("image scan policy receipt has no exception-register identity")
    policy = receipt.get("policy")
    if not isinstance(policy, dict):
        raise ScanPolicyError("image scan policy receipt has no policy decision")
    if policy.get("policy_id") != POLICY_ID:
        raise ScanPolicyError("image scan policy receipt has an unsupported policy ID")
    if policy.get("scanners") != ["vulnerability", "secret"]:
        raise ScanPolicyError("image scan policy receipt has an unsupported scanner set")
    if policy.get("blocking_severities") != sorted(BLOCKING_SEVERITIES):
        raise ScanPolicyError("image scan policy receipt has an unsupported severity policy")
    if policy.get("owned_plan_required_severities") != ["MEDIUM"]:
        raise ScanPolicyError("image scan policy receipt has an unsupported remediation policy")
    if policy.get("known_exploited_exceptionable") is not False:
        raise ScanPolicyError("known-exploited findings must remain non-exceptionable")
    decision = policy.get("decision")
    finding_count = policy.get("finding_count")
    count = policy.get("blocking_finding_count")
    known_exploited_count = policy.get("known_exploited_finding_count")
    unclassified_exploitation_count = policy.get("unclassified_exploitation_finding_count")
    unclassified_severity_count = policy.get("unclassified_severity_finding_count")
    approved_exception_count = policy.get("approved_exception_finding_count")
    severity_counts = policy.get("severity_counts")
    findings = receipt.get("findings")
    if not isinstance(findings, list):
        raise ScanPolicyError("image scan policy receipt findings must be an array")
    normalized_findings = [_validate_finding(finding) for finding in findings]
    if normalized_findings != findings:
        raise ScanPolicyError("image scan policy receipt findings are not normalized")
    expected_severity_counts = {
        severity: sum(finding["severity"] == severity for finding in findings)
        for severity in sorted(KNOWN_SEVERITIES)
    }
    expected_blocking_count = sum(_finding_blocks(finding) for finding in normalized_findings)
    expected_known_exploited_count = sum(finding["known_exploited"] is True for finding in findings)
    expected_unclassified_count = sum(
        finding["finding_type"] == "vulnerability" and finding["known_exploited"] is None
        for finding in findings
    )
    expected_unclassified_severity_count = sum(
        finding["severity"] in UNCLASSIFIED_SEVERITIES for finding in findings
    )
    expected_approved_exception_count = sum(
        bool(finding["approved_exception_ids"]) for finding in findings
    )
    if finding_count != len(findings) or severity_counts != expected_severity_counts:
        raise ScanPolicyError("image scan policy receipt finding totals are inconsistent")
    if not isinstance(count, int) or count != expected_blocking_count:
        raise ScanPolicyError("image scan policy receipt blocking count is inconsistent")
    if known_exploited_count != expected_known_exploited_count:
        raise ScanPolicyError("image scan policy receipt known-exploited count is inconsistent")
    if unclassified_exploitation_count != expected_unclassified_count:
        raise ScanPolicyError("image scan policy receipt exploitation count is inconsistent")
    if unclassified_severity_count != expected_unclassified_severity_count:
        raise ScanPolicyError("image scan policy receipt severity count is inconsistent")
    if approved_exception_count != expected_approved_exception_count:
        raise ScanPolicyError("image scan policy receipt exception count is inconsistent")
    expected_receipt = build_policy_receipt(
        report_path=report_path,
        service=expected_service,
        image_ref=expected_image_ref,
        image_digest=expected_image_digest,
        repository=expected_repository,
        git_commit_sha=expected_git_commit_sha,
        ci_run_id=expected_ci_run_id,
        ci_run_attempt=expected_ci_run_attempt,
        scanner_name=SCANNER_NAME,
        scanner_version=SCANNER_VERSION,
        scanner_image=SCANNER_IMAGE,
        scan_timestamp=_required_string(
            receipt.get("generated_at_utc"), field="receipt generated-at"
        ),
        kev_catalog_path=kev_catalog_path,
        kev_fetched_at=_required_string(kev_identity.get("fetched_at_utc"), field="KEV fetched-at"),
        exception_register_path=exception_register_path,
        exception_schema_path=exception_schema_path,
    )
    if receipt != expected_receipt:
        raise ScanPolicyError("image scan policy receipt does not match its source evidence")
    if decision == "passed" and expected_blocking_count == 0:
        return
    if decision == "blocked" and expected_blocking_count > 0:
        raise ScanPolicyError(
            f"image release blocked by {count} vulnerability or secret policy finding(s)"
        )
    raise ScanPolicyError("image scan policy receipt decision is inconsistent")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--report", required=True, type=Path)
    evaluate.add_argument("--service", required=True)
    evaluate.add_argument("--image-ref", required=True)
    evaluate.add_argument("--image-digest", required=True)
    evaluate.add_argument("--repository", required=True)
    evaluate.add_argument("--git-commit-sha", required=True)
    evaluate.add_argument("--ci-run-id", required=True)
    evaluate.add_argument("--ci-run-attempt", required=True)
    evaluate.add_argument("--scanner-name", required=True)
    evaluate.add_argument("--scanner-version", required=True)
    evaluate.add_argument("--scanner-image", required=True)
    evaluate.add_argument("--scan-timestamp", required=True)
    evaluate.add_argument("--kev-catalog", required=True, type=Path)
    evaluate.add_argument("--kev-fetched-at", required=True)
    evaluate.add_argument("--exception-register", required=True, type=Path)
    evaluate.add_argument("--exception-schema", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    unavailable = subparsers.add_parser("unavailable")
    unavailable.add_argument("--service", required=True)
    unavailable.add_argument("--image-ref", required=True)
    unavailable.add_argument("--image-digest", required=True)
    unavailable.add_argument("--repository", required=True)
    unavailable.add_argument("--git-commit-sha", required=True)
    unavailable.add_argument("--ci-run-id", required=True)
    unavailable.add_argument("--ci-run-attempt", required=True)
    unavailable.add_argument("--generated-at", required=True)
    unavailable.add_argument(
        "--reason-code", required=True, choices=sorted(UNAVAILABLE_REASON_CODES)
    )
    unavailable.add_argument("--output", required=True, type=Path)
    enforce = subparsers.add_parser("enforce")
    enforce.add_argument("--receipt", required=True, type=Path)
    enforce.add_argument("--report", required=True, type=Path)
    enforce.add_argument("--kev-catalog", required=True, type=Path)
    enforce.add_argument("--exception-register", required=True, type=Path)
    enforce.add_argument("--exception-schema", required=True, type=Path)
    enforce.add_argument("--expected-service", required=True)
    enforce.add_argument("--expected-image-ref", required=True)
    enforce.add_argument("--expected-image-digest", required=True)
    enforce.add_argument("--expected-repository", required=True)
    enforce.add_argument("--expected-git-commit-sha", required=True)
    enforce.add_argument("--expected-ci-run-id", required=True)
    enforce.add_argument("--expected-ci-run-attempt", required=True)
    enforce.add_argument("--enforced-at", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "evaluate":
            receipt = build_policy_receipt(
                report_path=args.report,
                service=args.service,
                image_ref=args.image_ref,
                image_digest=args.image_digest,
                repository=args.repository,
                git_commit_sha=args.git_commit_sha,
                ci_run_id=args.ci_run_id,
                ci_run_attempt=args.ci_run_attempt,
                scanner_name=args.scanner_name,
                scanner_version=args.scanner_version,
                scanner_image=args.scanner_image,
                scan_timestamp=args.scan_timestamp,
                kev_catalog_path=args.kev_catalog,
                kev_fetched_at=args.kev_fetched_at,
                exception_register_path=args.exception_register,
                exception_schema_path=args.exception_schema,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return 0
        if args.command == "unavailable":
            receipt = build_unavailable_receipt(
                service=args.service,
                image_ref=args.image_ref,
                image_digest=args.image_digest,
                repository=args.repository,
                git_commit_sha=args.git_commit_sha,
                ci_run_id=args.ci_run_id,
                ci_run_attempt=args.ci_run_attempt,
                generated_at=args.generated_at,
                reason_code=args.reason_code,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return 0
        enforce_policy_receipt(
            args.receipt,
            report_path=args.report,
            kev_catalog_path=args.kev_catalog,
            exception_register_path=args.exception_register,
            exception_schema_path=args.exception_schema,
            expected_service=args.expected_service,
            expected_image_ref=args.expected_image_ref,
            expected_image_digest=args.expected_image_digest,
            expected_repository=args.expected_repository,
            expected_git_commit_sha=args.expected_git_commit_sha,
            expected_ci_run_id=args.expected_ci_run_id,
            expected_ci_run_attempt=args.expected_ci_run_attempt,
            enforced_at=args.enforced_at,
        )
        return 0
    except (OSError, CisaKevError, ScanPolicyError, VulnerabilityExceptionError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
