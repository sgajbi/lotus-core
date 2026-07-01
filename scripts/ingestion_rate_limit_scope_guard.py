"""Validate ingestion write rate-limit scope truth across code and docs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.ingestion_service.app import ops_controls  # noqa: E402

REQUIRED_RATE_LIMIT_SCOPES = {
    "local_process",
    "upstream_gateway",
    "local_process_with_upstream_gateway",
}

DOC_REQUIRED_PHRASES = {
    "docs/operations/ingestion-api-gold-standard.md": (
        "local_process",
        "not a global service-level limit",
        "upstream_gateway",
        "local_process_with_upstream_gateway",
        "LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID",
    ),
    "quality/quality_scorecard.md": (
        "local_process",
        "upstream_gateway",
        "local_process_with_upstream_gateway",
        "gateway policy ID",
    ),
    "quality/refactor_health_report.md": (
        "rate-limit scope explicit",
        "gateway-backed global enforcement claims",
    ),
    "docs/architecture/CR-1196-INGESTION-RATE-LIMIT-SCOPE-CONTRACT.md": (
        "local_process",
        "not a global control",
        "upstream_gateway",
        "LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID",
    ),
}


def _docs_with_missing_phrases(
    *,
    repo_root: Path = REPO_ROOT,
    required_phrases: dict[str, tuple[str, ...]] = DOC_REQUIRED_PHRASES,
) -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    for relative_path, phrases in required_phrases.items():
        path = repo_root / relative_path
        if not path.exists():
            violations.append({"file": relative_path, "missing_file": True})
            continue
        text = path.read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in text]
        if missing:
            violations.append({"file": relative_path, "missing_phrases": missing})
    return violations


def _runtime_contract_violations(contract: dict[str, object]) -> list[str]:
    violations: list[str] = []
    if contract.get("enforcement_scope") == "local_process":
        if contract.get("global_enforcement_claimed") is not False:
            violations.append("local_process scope must not claim global enforcement")
        if contract.get("local_process_enforcement") is not True:
            violations.append("local_process scope must keep local process enforcement active")
        if contract.get("gateway_policy_id") is not None:
            violations.append("local_process scope must not report a gateway policy ID")
    return violations


def _implementation_scope_violations() -> list[str]:
    violations: list[str] = []
    if set(ops_controls._LOCAL_RATE_LIMIT_SCOPES) != {
        "local_process",
        "local_process_with_upstream_gateway",
    }:
        violations.append("local rate-limit scopes drifted from the governed contract")
    if set(ops_controls._GATEWAY_RATE_LIMIT_SCOPES) != {
        "upstream_gateway",
        "local_process_with_upstream_gateway",
    }:
        violations.append("gateway-backed rate-limit scopes drifted from the governed contract")
    configured_scopes = set(ops_controls._LOCAL_RATE_LIMIT_SCOPES) | set(
        ops_controls._GATEWAY_RATE_LIMIT_SCOPES
    )
    if configured_scopes != REQUIRED_RATE_LIMIT_SCOPES:
        violations.append("configured rate-limit scopes do not match the documented scope set")
    return violations


def evaluate_ingestion_rate_limit_scope_truth(
    *,
    repo_root: Path = REPO_ROOT,
    contract: dict[str, object] | None = None,
    required_phrases: dict[str, tuple[str, ...]] = DOC_REQUIRED_PHRASES,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    docs_findings = _docs_with_missing_phrases(
        repo_root=repo_root,
        required_phrases=required_phrases,
    )
    findings.extend(docs_findings)

    runtime_contract = contract or ops_controls.ingestion_write_rate_limit_contract()
    runtime_violations = _runtime_contract_violations(runtime_contract)
    if runtime_violations:
        findings.append({"runtime_contract": runtime_violations})

    implementation_violations = _implementation_scope_violations()
    if implementation_violations:
        findings.append({"implementation": implementation_violations})

    return findings


def main() -> int:
    findings = evaluate_ingestion_rate_limit_scope_truth()
    if findings:
        print("Ingestion rate-limit scope guard failed:")
        print(json.dumps(findings, indent=2))
        return 1
    print("Ingestion rate-limit scope guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
