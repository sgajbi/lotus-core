from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WORKFLOW_POLICY_MODULE = Path("src/services/ingestion_service/app/application/workflow_policies.py")
INGESTION_JOB_SERVICE = Path("src/services/ingestion_service/app/services/ingestion_job_service.py")
REQUIRED_POLICY_SYMBOLS = (
    "class CorrelationContext",
    "class ApplicationCommandEnvelope",
    "class IdempotencyWorkflow",
    "class AuditWorkflow",
)
REQUIRED_SERVICE_SNIPPETS = (
    "IdempotencyWorkflow",
    "AuditWorkflow",
    "ApplicationCommandEnvelope",
    "CorrelationContext",
)
FORBIDDEN_SERVICE_SNIPPETS = {
    "return await self._job_store_adapter.create_or_get_job(": (
        "ingestion job creation must flow through IdempotencyWorkflow"
    ),
    "return await self._replay_audit_store_adapter.record_consumer_dlq_replay_audit(": (
        "consumer DLQ replay audit writes must flow through AuditWorkflow"
    ),
}


@dataclass(frozen=True, slots=True)
class ApplicationWorkflowPolicyFinding:
    path: str
    snippet: str
    reason: str


def find_application_workflow_policy_findings(
    root: Path,
) -> list[ApplicationWorkflowPolicyFinding]:
    findings: list[ApplicationWorkflowPolicyFinding] = []

    policy_path = root / WORKFLOW_POLICY_MODULE
    if not policy_path.exists():
        findings.append(
            ApplicationWorkflowPolicyFinding(
                path=WORKFLOW_POLICY_MODULE.as_posix(),
                snippet="<missing-file>",
                reason="application workflow policy module is missing",
            )
        )
    else:
        policy_source = policy_path.read_text(encoding="utf-8")
        for snippet in REQUIRED_POLICY_SYMBOLS:
            if snippet not in policy_source:
                findings.append(
                    ApplicationWorkflowPolicyFinding(
                        path=WORKFLOW_POLICY_MODULE.as_posix(),
                        snippet=snippet,
                        reason="application workflow policy symbol is required",
                    )
                )

    service_path = root / INGESTION_JOB_SERVICE
    if not service_path.exists():
        findings.append(
            ApplicationWorkflowPolicyFinding(
                path=INGESTION_JOB_SERVICE.as_posix(),
                snippet="<missing-file>",
                reason="ingestion job service module is missing",
            )
        )
        return findings

    service_source = service_path.read_text(encoding="utf-8")
    for snippet in REQUIRED_SERVICE_SNIPPETS:
        if snippet not in service_source:
            findings.append(
                ApplicationWorkflowPolicyFinding(
                    path=INGESTION_JOB_SERVICE.as_posix(),
                    snippet=snippet,
                    reason="ingestion job service must use reusable workflow policies",
                )
            )
    for snippet, reason in FORBIDDEN_SERVICE_SNIPPETS.items():
        if snippet in service_source:
            findings.append(
                ApplicationWorkflowPolicyFinding(
                    path=INGESTION_JOB_SERVICE.as_posix(),
                    snippet=snippet,
                    reason=reason,
                )
            )

    return findings


def main() -> int:
    findings = find_application_workflow_policy_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Application workflow policy guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
