from __future__ import annotations

import json
from pathlib import Path

from scripts import incident_playbook_guard as guard


def _playbook(playbook_id: str = "ingestion-stuck-failed", **overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": playbook_id,
        "title": "Ingestion stuck or failed",
        "severity_floor": "sev2",
        "symptoms": ["jobs do not drain"],
        "dashboards_metrics": ["kafka_consumer_events_total"],
        "api_checks": [
            {
                "method": "GET",
                "path": "/ingestion/jobs",
                "expected_fields": ["items", "job_id"],
            }
        ],
        "database_safe_checks": [
            {
                "description": "read only job state",
                "read_only": True,
                "query": "SELECT job_id, status FROM ingestion_jobs WHERE job_id = :job_id;",
            }
        ],
        "repository_native_commands": ["make test-ops-contract"],
        "expected_response_fields": ["job_id", "status"],
        "containment_actions": ["pause new submissions"],
        "escalation_path": ["ingestion owner"],
        "post_incident_evidence": ["job id"],
    }
    payload.update(overrides)
    return payload


def _write_repo(tmp_path: Path, *, playbooks: list[dict[str, object]] | None = None) -> Path:
    playbooks = playbooks or [_playbook(playbook_id) for playbook_id in guard.REQUIRED_PLAYBOOK_IDS]
    contract_path = tmp_path / guard.CONTRACT_PATH
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "schema_version": guard.EXPECTED_SCHEMA_VERSION,
                "repository": "lotus-core",
                "guard_command": "make incident-playbook-guard",
                "documentation_surfaces": [
                    "docs/operations/Incident-Playbooks.md",
                    "docs/operations-runbook.md",
                    "wiki/Operations-Runbook.md",
                    "wiki/Troubleshooting.md",
                ],
                "playbooks": playbooks,
            }
        ),
        encoding="utf-8",
    )
    doc_text = "\n".join(
        [
            guard.CONTRACT_PATH.as_posix(),
            "make incident-playbook-guard",
            *[str(playbook["id"]) for playbook in playbooks],
        ]
    )
    for relative_path in (
        "docs/operations/Incident-Playbooks.md",
        "docs/operations-runbook.md",
        "wiki/Operations-Runbook.md",
        "wiki/Troubleshooting.md",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc_text, encoding="utf-8")
    return tmp_path


def test_incident_playbook_guard_accepts_complete_contract(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path)

    assert guard.find_incident_playbook_findings(repo) == []


def test_incident_playbook_guard_rejects_missing_required_playbook(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        playbooks=[
            _playbook(playbook_id)
            for playbook_id in guard.REQUIRED_PLAYBOOK_IDS
            if playbook_id != "dlq-growth"
        ],
    )

    findings = guard.find_incident_playbook_findings(repo)

    assert any("missing playbook dlq-growth" in finding.detail for finding in findings)


def test_incident_playbook_guard_rejects_destructive_database_check(tmp_path: Path) -> None:
    playbooks = [_playbook(playbook_id) for playbook_id in guard.REQUIRED_PLAYBOOK_IDS]
    playbooks[0] = _playbook(
        "ingestion-stuck-failed",
        database_safe_checks=[
            {
                "description": "bad",
                "read_only": True,
                "query": "DELETE FROM ingestion_jobs WHERE job_id = :job_id;",
            }
        ],
    )
    repo = _write_repo(tmp_path, playbooks=playbooks)

    findings = guard.find_incident_playbook_findings(repo)

    assert any("destructive command" in finding.detail for finding in findings)


def test_incident_playbook_guard_rejects_non_repo_native_command(tmp_path: Path) -> None:
    playbooks = [_playbook(playbook_id) for playbook_id in guard.REQUIRED_PLAYBOOK_IDS]
    playbooks[0] = _playbook(
        "ingestion-stuck-failed",
        repository_native_commands=["kubectl delete pod core"],
    )
    repo = _write_repo(tmp_path, playbooks=playbooks)

    findings = guard.find_incident_playbook_findings(repo)

    assert any("repo-native" in finding.detail for finding in findings)


def test_incident_playbook_guard_rejects_missing_doc_reference(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path)
    (repo / "wiki" / "Troubleshooting.md").write_text(
        f"{guard.CONTRACT_PATH.as_posix()}\nmake incident-playbook-guard\n",
        encoding="utf-8",
    )

    findings = guard.find_incident_playbook_findings(repo)

    assert any("missing playbook reference" in finding.detail for finding in findings)
