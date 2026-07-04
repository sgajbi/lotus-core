from pathlib import Path

from scripts.ingestion_store_port_guard import find_ingestion_store_port_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ingestion_store_port_guard_allows_port_calls(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "await self._job_store_adapter.create_or_get_job()\n"
        "await self._replay_audit_store_adapter.record_consumer_dlq_replay_audit(record)\n",
    )

    assert find_ingestion_store_port_findings(tmp_path) == []


def test_ingestion_store_port_guard_rejects_direct_audit_and_idempotency_helpers(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/services/ingestion_service/app/services/ingestion_job_service.py",
        "await create_or_get_job_result(session_factory=get_async_db_session)\n"
        "await record_consumer_dlq_replay_audit_response(session_factory=get_async_db_session)\n",
    )

    findings = find_ingestion_store_port_findings(tmp_path)

    assert [finding.token for finding in findings] == [
        "create_or_get_job_result(",
        "record_consumer_dlq_replay_audit_response(",
    ]
