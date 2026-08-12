"""Create and enforce a secret-safe policy receipt for one Trivy image scan."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "lotus-core.image-scan-policy-receipt.v1"
POLICY_ID = "lotus-core.image-release-high-critical-and-secret.v1"
SCANNER_NAME = "trivy"
SCANNER_VERSION = "0.56.2"
SCANNER_IMAGE = "aquasec/trivy:0.56.2"
BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
KNOWN_NONBLOCKING_SEVERITIES = frozenset({"UNKNOWN", "NEGLIGIBLE", "LOW", "MEDIUM"})
KNOWN_SEVERITIES = BLOCKING_SEVERITIES | KNOWN_NONBLOCKING_SEVERITIES
FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


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
    raw: object, *, target: str, target_class: str
) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        raise ScanPolicyError("Trivy vulnerability entries must be objects")
    severity = _required_string(raw.get("Severity"), field="vulnerability severity").upper()
    if severity not in KNOWN_SEVERITIES:
        raise ScanPolicyError(f"unsupported vulnerability severity: {severity}")
    if severity == "UNKNOWN":
        raise ScanPolicyError("unknown vulnerability severity cannot support a release decision")
    if severity not in BLOCKING_SEVERITIES:
        return None
    return {
        "finding_type": "vulnerability",
        "finding_id": _required_string(raw.get("VulnerabilityID"), field="vulnerability ID"),
        "severity": severity,
        "target": target,
        "target_class": target_class,
        "component_name": _required_string(raw.get("PkgName"), field="package name"),
        "installed_version": _required_string(
            raw.get("InstalledVersion"), field="installed version"
        ),
        "fixed_version": str(raw.get("FixedVersion") or ""),
    }


def _normalized_secret(raw: object, *, target: str, target_class: str) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        raise ScanPolicyError("Trivy secret entries must be objects")
    severity = _required_string(raw.get("Severity"), field="secret severity").upper()
    if severity not in KNOWN_SEVERITIES:
        raise ScanPolicyError(f"unsupported secret severity: {severity}")
    if severity == "UNKNOWN":
        raise ScanPolicyError("unknown secret severity cannot support a release decision")
    if severity not in BLOCKING_SEVERITIES:
        return None
    return {
        "finding_type": "secret",
        "finding_id": _required_string(raw.get("RuleID"), field="secret rule ID"),
        "severity": severity,
        "target": target,
        "target_class": target_class,
        "component_name": str(raw.get("Category") or "secret"),
        "installed_version": "",
        "fixed_version": "",
    }


def _blocking_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    if "Results" not in report:
        raise ScanPolicyError("Trivy report must contain Results")
    results = report["Results"]
    if not isinstance(results, list):
        raise ScanPolicyError("Trivy Results must be an array")

    findings: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict):
            raise ScanPolicyError("Trivy result entries must be objects")
        target = _required_string(result.get("Target"), field="Trivy result target")
        target_class = str(result.get("Class") or result.get("Type") or "unknown")
        for raw in result.get("Vulnerabilities") or []:
            finding = _normalized_vulnerability(raw, target=target, target_class=target_class)
            if finding is not None:
                findings.append(finding)
        for raw in result.get("Secrets") or []:
            finding = _normalized_secret(raw, target=target, target_class=target_class)
            if finding is not None:
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
) -> dict[str, object]:
    service = _required_string(service, field="service")
    image_ref = _required_string(image_ref, field="image ref")
    repository = _required_string(repository, field="repository")
    ci_run_id = _required_string(ci_run_id, field="CI run ID")
    ci_run_attempt = _required_string(ci_run_attempt, field="CI run attempt")
    scanner_name = _required_string(scanner_name, field="scanner name")
    scanner_version = _required_string(scanner_version, field="scanner version")
    scanner_image = _required_string(scanner_image, field="scanner image")
    if (scanner_name, scanner_version, scanner_image) != (
        SCANNER_NAME,
        SCANNER_VERSION,
        SCANNER_IMAGE,
    ):
        raise ScanPolicyError("scanner identity does not match the governed release scanner")
    if not SHA256_DIGEST_PATTERN.fullmatch(image_digest):
        raise ScanPolicyError("image digest must be a sha256 digest")
    if not FULL_GIT_SHA_PATTERN.fullmatch(git_commit_sha):
        raise ScanPolicyError("git commit SHA must be a full lowercase SHA")
    if not ci_run_id.isdecimal() or int(ci_run_id) < 1:
        raise ScanPolicyError("CI run ID must be a positive integer")
    if not ci_run_attempt.isdecimal() or int(ci_run_attempt) < 1:
        raise ScanPolicyError("CI run attempt must be a positive integer")

    report_bytes = report_path.read_bytes()
    report = _load_json_object(report_path, evidence_name="Trivy report")
    if report.get("SchemaVersion") != 2:
        raise ScanPolicyError("Trivy report SchemaVersion must be 2")
    digest_image_ref = f"{image_ref}@{image_digest}"
    if not _report_subject_matches(
        report, digest_image_ref=digest_image_ref, image_digest=image_digest
    ):
        raise ScanPolicyError("Trivy report does not match the expected image digest")

    findings = _blocking_findings(report)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_timestamp(scan_timestamp),
        "source": {
            "repository": repository,
            "git_commit_sha": git_commit_sha,
            "ci_run_id": ci_run_id,
            "ci_run_attempt": ci_run_attempt,
        },
        "subject": {
            "service": service,
            "image_ref": image_ref,
            "image_digest": image_digest,
            "digest_image_ref": digest_image_ref,
        },
        "scanner": {
            "name": scanner_name,
            "version": scanner_version,
            "image": scanner_image,
            "report_sha256": "sha256:" + hashlib.sha256(report_bytes).hexdigest(),
        },
        "policy": {
            "policy_id": POLICY_ID,
            "scanners": ["vulnerability", "secret"],
            "blocking_severities": sorted(BLOCKING_SEVERITIES),
            "decision": "blocked" if findings else "passed",
            "blocking_finding_count": len(findings),
        },
        "findings": findings,
    }


def _validate_finding(raw: object) -> dict[str, str]:
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
    }
    if finding["severity"] not in BLOCKING_SEVERITIES:
        raise ScanPolicyError("receipt findings must use a blocking severity")
    if finding_type == "vulnerability" and not finding["installed_version"]:
        raise ScanPolicyError("vulnerability finding requires installed version")
    return finding


def enforce_policy_receipt(
    receipt_path: Path,
    *,
    expected_service: str,
    expected_image_ref: str,
    expected_image_digest: str,
    expected_repository: str,
    expected_git_commit_sha: str,
    expected_ci_run_id: str,
    expected_ci_run_attempt: str,
) -> None:
    receipt = _load_json_object(receipt_path, evidence_name="image scan policy receipt")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ScanPolicyError("image scan policy receipt has an unsupported schema version")
    _utc_timestamp(_required_string(receipt.get("generated_at_utc"), field="receipt generated-at"))
    expected_source = {
        "repository": expected_repository,
        "git_commit_sha": expected_git_commit_sha,
        "ci_run_id": expected_ci_run_id,
        "ci_run_attempt": expected_ci_run_attempt,
    }
    if receipt.get("source") != expected_source:
        raise ScanPolicyError("image scan policy receipt source identity does not match")
    if not FULL_GIT_SHA_PATTERN.fullmatch(expected_git_commit_sha):
        raise ScanPolicyError("expected git commit SHA must be a full lowercase SHA")
    for value, field in (
        (expected_ci_run_id, "expected CI run ID"),
        (expected_ci_run_attempt, "expected CI run attempt"),
    ):
        if not value.isdecimal() or int(value) < 1:
            raise ScanPolicyError(f"{field} must be a positive integer")
    if not SHA256_DIGEST_PATTERN.fullmatch(expected_image_digest):
        raise ScanPolicyError("expected image digest must be a sha256 digest")
    expected_subject = {
        "service": expected_service,
        "image_ref": expected_image_ref,
        "image_digest": expected_image_digest,
        "digest_image_ref": f"{expected_image_ref}@{expected_image_digest}",
    }
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
    report_digest = _required_string(scanner.get("report_sha256"), field="scanner report digest")
    if not SHA256_DIGEST_PATTERN.fullmatch(report_digest):
        raise ScanPolicyError("scanner report digest must be a sha256 digest")
    policy = receipt.get("policy")
    if not isinstance(policy, dict):
        raise ScanPolicyError("image scan policy receipt has no policy decision")
    if policy.get("policy_id") != POLICY_ID:
        raise ScanPolicyError("image scan policy receipt has an unsupported policy ID")
    if policy.get("scanners") != ["vulnerability", "secret"]:
        raise ScanPolicyError("image scan policy receipt has an unsupported scanner set")
    if policy.get("blocking_severities") != sorted(BLOCKING_SEVERITIES):
        raise ScanPolicyError("image scan policy receipt has an unsupported severity policy")
    decision = policy.get("decision")
    count = policy.get("blocking_finding_count")
    findings = receipt.get("findings")
    if not isinstance(findings, list):
        raise ScanPolicyError("image scan policy receipt findings must be an array")
    normalized_findings = [_validate_finding(finding) for finding in findings]
    if normalized_findings != findings:
        raise ScanPolicyError("image scan policy receipt findings are not normalized")
    if not isinstance(count, int) or count != len(findings):
        raise ScanPolicyError("image scan policy receipt finding count is inconsistent")
    if decision == "passed" and count == 0:
        return
    if decision == "blocked" and count > 0:
        raise ScanPolicyError(
            f"image release blocked by {count} HIGH/CRITICAL vulnerability or secret finding(s)"
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
    evaluate.add_argument("--output", required=True, type=Path)
    enforce = subparsers.add_parser("enforce")
    enforce.add_argument("--receipt", required=True, type=Path)
    enforce.add_argument("--expected-service", required=True)
    enforce.add_argument("--expected-image-ref", required=True)
    enforce.add_argument("--expected-image-digest", required=True)
    enforce.add_argument("--expected-repository", required=True)
    enforce.add_argument("--expected-git-commit-sha", required=True)
    enforce.add_argument("--expected-ci-run-id", required=True)
    enforce.add_argument("--expected-ci-run-attempt", required=True)
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
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return 0
        enforce_policy_receipt(
            args.receipt,
            expected_service=args.expected_service,
            expected_image_ref=args.expected_image_ref,
            expected_image_digest=args.expected_image_digest,
            expected_repository=args.expected_repository,
            expected_git_commit_sha=args.expected_git_commit_sha,
            expected_ci_run_id=args.expected_ci_run_id,
            expected_ci_run_attempt=args.expected_ci_run_attempt,
        )
        return 0
    except (OSError, ScanPolicyError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
