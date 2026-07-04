from pathlib import Path

from scripts.application_workflow_policy_guard import (
    find_application_workflow_policy_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_application_workflow_policy_guard_allows_reusable_workflow_policies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/workflow_policies.py",
        "class CorrelationContext: pass\n"
        "class ApplicationCommandEnvelope: pass\n"
        "class IdempotencyWorkflow: pass\n"
        "class AuditWorkflow: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from ..application.workflow_policies import (\n"
        "    ApplicationCommandEnvelope,\n"
        "    AuditWorkflow,\n"
        "    CorrelationContext,\n"
        "    IdempotencyWorkflow,\n"
        ")\n"
        "await IdempotencyWorkflow(store).create_or_get(ApplicationCommandEnvelope())\n"
        "await AuditWorkflow(store).record_replay_audit(record)\n",
    )

    assert find_application_workflow_policy_findings(tmp_path) == []


def test_application_workflow_policy_guard_rejects_direct_store_calls(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/workflow_policies.py",
        "class CorrelationContext: pass\n"
        "class ApplicationCommandEnvelope: pass\n"
        "class IdempotencyWorkflow: pass\n"
        "class AuditWorkflow: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "return await self._job_store_adapter.create_or_get_job()\n"
        "return await self._replay_audit_store_adapter.record_consumer_dlq_replay_audit()\n",
    )

    findings = find_application_workflow_policy_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "IdempotencyWorkflow",
        "AuditWorkflow",
        "ApplicationCommandEnvelope",
        "CorrelationContext",
        "return await self._job_store_adapter.create_or_get_job(",
        "return await self._replay_audit_store_adapter.record_consumer_dlq_replay_audit(",
    ]


def test_application_workflow_policy_guard_rejects_missing_policy_symbol(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/application/workflow_policies.py",
        "class CorrelationContext: pass\n"
        "class ApplicationCommandEnvelope: pass\n"
        "class IdempotencyWorkflow: pass\n",
    )
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "from ..application.workflow_policies import (\n"
        "    ApplicationCommandEnvelope,\n"
        "    AuditWorkflow,\n"
        "    CorrelationContext,\n"
        "    IdempotencyWorkflow,\n"
        ")\n",
    )

    findings = find_application_workflow_policy_findings(tmp_path)

    assert findings[0].path == (
        "src/services/ingestion_service/app/application/workflow_policies.py"
    )
    assert findings[0].snippet == "class AuditWorkflow"
