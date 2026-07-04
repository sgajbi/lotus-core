from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SERVICE_PATH = Path("src/services/ingestion_service/app/services/ingestion_job_service.py")
FORBIDDEN_HELPER_TOKENS = {
    "create_or_get_job_result(": "job creation and idempotency must use IngestionJobStore",
    "record_consumer_dlq_replay_audit_response(": "replay audit writes must use ReplayAuditStore",
    "find_successful_replay_audit_by_fingerprint_response(": (
        "replay audit duplicate checks must use ReplayAuditStore"
    ),
    "get_replay_audit_response(": "replay audit reads must use ReplayAuditStore",
    "list_replay_audit_responses(": "replay audit listing must use ReplayAuditStore",
}


@dataclass(frozen=True, slots=True)
class StorePortFinding:
    path: str
    token: str
    reason: str


def find_ingestion_store_port_findings(root: Path) -> list[StorePortFinding]:
    service_path = root / SERVICE_PATH
    if not service_path.exists():
        return [
            StorePortFinding(
                path=SERVICE_PATH.as_posix(),
                token="<missing-file>",
                reason="ingestion job service path was not found",
            )
        ]

    source = service_path.read_text(encoding="utf-8")
    findings: list[StorePortFinding] = []
    for token, reason in FORBIDDEN_HELPER_TOKENS.items():
        if token in source:
            findings.append(
                StorePortFinding(
                    path=SERVICE_PATH.as_posix(),
                    token=token,
                    reason=reason,
                )
            )
    return findings


def main() -> int:
    findings = find_ingestion_store_port_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.token}: {finding.reason}")
        return 1
    print("Ingestion store port guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
