"""Validate the ingestion write-rate gateway policy contract."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    REPO_ROOT
    / "contracts"
    / "operational-controls"
    / "ingestion-write-rate-limit-gateway-policy.v1.json"
)
ROUTER_ROOT = REPO_ROOT / "src" / "services" / "ingestion_service" / "app" / "routers"

POLICY_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")
REQUIRED_POLICY_ID = "lotus-core-ingestion-write-global-v1"
REQUIRED_CONTROL_ID = "lotus-core.ingestion.write-rate-limit.global.v1"
REQUIRED_SCOPE_VALUES = {"upstream_gateway", "local_process_with_upstream_gateway"}
REQUIRED_DENIAL_LABELS = {"endpoint", "reason", "enforcement_scope"}
FORBIDDEN_OBSERVABILITY_LABELS = {
    "portfolio_id",
    "account_id",
    "client_id",
    "security_id",
    "request_id",
    "correlation_id",
    "trace_id",
    "payload",
}
DOC_REQUIRED_PHRASES = {
    "docs/operations/ingestion-api-gold-standard.md": (
        "lotus-core-ingestion-write-global-v1",
        "contracts/operational-controls/ingestion-write-rate-limit-gateway-policy.v1.json",
        "make ingestion-gateway-rate-limit-policy-guard",
    ),
    "quality/quality_scorecard.md": ("lotus-core-ingestion-write-global-v1",),
    "quality/refactor_health_report.md": ("ingestion gateway rate-limit policy",),
}


def _load_policy(policy_path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(policy_path.read_text(encoding="utf-8"))


def _literal_endpoint_keywords(router_root: Path = ROUTER_ROOT) -> set[str]:
    endpoints: set[str] = set()
    for path in router_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "endpoint":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    endpoints.add(keyword.value.value)
    return endpoints


def _docs_with_missing_phrases(
    *,
    repo_root: Path = REPO_ROOT,
    required_phrases: dict[str, tuple[str, ...]] = DOC_REQUIRED_PHRASES,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for relative_path, phrases in required_phrases.items():
        path = repo_root / relative_path
        if not path.exists():
            findings.append({"file": relative_path, "missing_file": True})
            continue
        text = path.read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in text]
        if missing:
            findings.append({"file": relative_path, "missing_phrases": missing})
    return findings


def _policy_shape_findings(policy: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if policy.get("control_id") != REQUIRED_CONTROL_ID:
        findings.append("control_id does not match the governed ingestion write-rate control")
    policy_id = policy.get("policy_id")
    if policy_id != REQUIRED_POLICY_ID:
        findings.append("policy_id does not match the governed gateway policy id")
    if not isinstance(policy_id, str) or not POLICY_ID_PATTERN.fullmatch(policy_id):
        findings.append("policy_id must be kebab-case with a version suffix")
    if policy.get("owner") != "lotus-platform-gateway":
        findings.append("owner must remain lotus-platform-gateway")
    if policy.get("effective_scope") != "global_service":
        findings.append("effective_scope must be global_service")
    scope_values = set(policy.get("required_runtime_scope_values", []))
    if scope_values != REQUIRED_SCOPE_VALUES:
        findings.append("required_runtime_scope_values do not match gateway-backed scopes")
    runtime_env = policy.get("required_runtime_env", {})
    if runtime_env.get("LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID") != REQUIRED_POLICY_ID:
        findings.append("runtime gateway policy id does not match policy_id")
    if set(runtime_env.get("LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE", [])) != (
        REQUIRED_SCOPE_VALUES
    ):
        findings.append("runtime enforcement scope values do not match gateway-backed scopes")
    window = policy.get("rolling_window", {})
    if window.get("window_seconds") != 60:
        findings.append("rolling window seconds must stay aligned to the default local budget")
    if window.get("max_requests") != 120:
        findings.append("max_requests must stay aligned to the default local budget")
    if window.get("max_records") != 10000:
        findings.append("max_records must stay aligned to the default local budget")
    validation = policy.get("validation", {})
    if validation.get("repo_guard") != "make ingestion-gateway-rate-limit-policy-guard":
        findings.append("validation.repo_guard must name the repo guard")
    if validation.get("platform_runtime_validation_required") is not True:
        findings.append("platform runtime validation must remain required")
    return findings


def _endpoint_findings(policy: dict[str, Any], router_endpoints: set[str]) -> list[str]:
    contract_endpoints = set(policy.get("required_endpoint_templates", []))
    findings: list[str] = []
    missing = sorted(router_endpoints - contract_endpoints)
    stale = sorted(contract_endpoints - router_endpoints)
    if missing:
        findings.append(f"policy missing router endpoint templates: {missing}")
    if stale:
        findings.append(f"policy lists endpoint templates not found in routers: {stale}")
    return findings


def _observability_findings(policy: dict[str, Any]) -> list[str]:
    observability = policy.get("source_safe_observability", {})
    labels = set(observability.get("required_labels", []))
    forbidden = set(observability.get("forbidden_labels", []))
    findings: list[str] = []
    if labels != REQUIRED_DENIAL_LABELS:
        findings.append("denial metric labels must remain endpoint, reason, enforcement_scope")
    missing_forbidden = sorted(FORBIDDEN_OBSERVABILITY_LABELS - forbidden)
    if missing_forbidden:
        findings.append(f"forbidden observability labels missing: {missing_forbidden}")
    return findings


def evaluate_gateway_rate_limit_policy(
    *,
    policy: dict[str, Any] | None = None,
    router_endpoints: set[str] | None = None,
    repo_root: Path = REPO_ROOT,
    required_phrases: dict[str, tuple[str, ...]] = DOC_REQUIRED_PHRASES,
) -> list[dict[str, object]]:
    policy = policy or _load_policy()
    router_endpoints = router_endpoints or _literal_endpoint_keywords()

    findings: list[dict[str, object]] = []
    policy_findings = _policy_shape_findings(policy)
    if policy_findings:
        findings.append({"policy": policy_findings})

    endpoint_findings = _endpoint_findings(policy, router_endpoints)
    if endpoint_findings:
        findings.append({"endpoints": endpoint_findings})

    observability_findings = _observability_findings(policy)
    if observability_findings:
        findings.append({"observability": observability_findings})

    findings.extend(
        _docs_with_missing_phrases(
            repo_root=repo_root,
            required_phrases=required_phrases,
        )
    )
    return findings


def main() -> int:
    findings = evaluate_gateway_rate_limit_policy()
    if findings:
        print("Ingestion gateway rate-limit policy guard failed:")
        print(json.dumps(findings, indent=2))
        return 1
    print("Ingestion gateway rate-limit policy guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
