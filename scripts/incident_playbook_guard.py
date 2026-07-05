"""Validate executable incident playbook coverage for lotus-core operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("contracts/operations/incident-playbooks.v1.json")
EXPECTED_SCHEMA_VERSION = "lotus-core.incident-playbooks.v1"
REQUIRED_PLAYBOOK_IDS = {
    "ingestion-stuck-failed",
    "dlq-growth",
    "replay-failure",
    "outbox-backlog",
    "valuation-aggregation-lag",
    "stale-source-data",
    "reconciliation-failure",
    "readiness-failure",
    "database-connectivity",
    "kafka-connectivity",
    "security-audit-denial-spikes",
}
REQUIRED_PLAYBOOK_FIELDS = (
    "id",
    "title",
    "severity_floor",
    "symptoms",
    "dashboards_metrics",
    "api_checks",
    "database_safe_checks",
    "repository_native_commands",
    "expected_response_fields",
    "containment_actions",
    "escalation_path",
    "post_incident_evidence",
)
REQUIRED_API_CHECK_FIELDS = ("method", "path", "expected_fields")
REQUIRED_DATABASE_CHECK_FIELDS = ("description", "read_only", "query")
DESTRUCTIVE_COMMAND_TOKENS = (
    " delete ",
    " truncate ",
    " drop ",
    " update ",
    " insert ",
    " alter ",
    " remove-item ",
    " rm -rf",
    "docker compose down -v",
)


@dataclass(frozen=True)
class IncidentPlaybookFinding:
    location: str
    detail: str


def _load_contract(root: Path) -> dict[str, Any]:
    return json.loads((root / CONTRACT_PATH).read_text(encoding="utf-8"))


def _as_non_empty_list(
    *,
    findings: list[IncidentPlaybookFinding],
    location: str,
    field_name: str,
    value: Any,
) -> list[Any]:
    if not isinstance(value, list) or not value:
        findings.append(IncidentPlaybookFinding(location, f"{field_name} must be a non-empty list"))
        return []
    return value


def _contains_destructive_command(value: str) -> bool:
    normalized = f" {value.strip().lower()} "
    return any(token in normalized for token in DESTRUCTIVE_COMMAND_TOKENS)


def _validate_api_checks(
    findings: list[IncidentPlaybookFinding],
    playbook_id: str,
    api_checks: list[Any],
) -> None:
    for index, api_check in enumerate(api_checks):
        location = f"{playbook_id}.api_checks[{index}]"
        if not isinstance(api_check, dict):
            findings.append(IncidentPlaybookFinding(location, "API check must be an object"))
            continue
        for field_name in REQUIRED_API_CHECK_FIELDS:
            if api_check.get(field_name) in (None, "", []):
                findings.append(IncidentPlaybookFinding(location, f"missing {field_name}"))
        method = api_check.get("method")
        if method not in {"GET", "POST", "PUT", "PATCH"}:
            findings.append(IncidentPlaybookFinding(location, f"unsupported method {method!r}"))
        path = api_check.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            findings.append(IncidentPlaybookFinding(location, "path must start with /"))
        expected_fields = api_check.get("expected_fields")
        _as_non_empty_list(
            findings=findings,
            location=location,
            field_name="expected_fields",
            value=expected_fields,
        )


def _validate_database_checks(
    findings: list[IncidentPlaybookFinding],
    playbook_id: str,
    database_checks: list[Any],
) -> None:
    for index, database_check in enumerate(database_checks):
        location = f"{playbook_id}.database_safe_checks[{index}]"
        if not isinstance(database_check, dict):
            findings.append(IncidentPlaybookFinding(location, "database check must be an object"))
            continue
        for field_name in REQUIRED_DATABASE_CHECK_FIELDS:
            if database_check.get(field_name) in (None, ""):
                findings.append(IncidentPlaybookFinding(location, f"missing {field_name}"))
        if database_check.get("read_only") is not True:
            findings.append(IncidentPlaybookFinding(location, "database check must be read_only"))
        query = str(database_check.get("query", ""))
        if _contains_destructive_command(query):
            findings.append(
                IncidentPlaybookFinding(location, "database check contains destructive command")
            )


def _validate_commands(
    findings: list[IncidentPlaybookFinding],
    playbook_id: str,
    commands: list[Any],
) -> None:
    for index, command in enumerate(commands):
        location = f"{playbook_id}.repository_native_commands[{index}]"
        if not isinstance(command, str) or not command.strip():
            findings.append(IncidentPlaybookFinding(location, "command must be non-empty text"))
            continue
        if _contains_destructive_command(command):
            findings.append(
                IncidentPlaybookFinding(location, "command contains destructive operation")
            )
        if not command.startswith(("make ", "python ", "docker compose ", "git ", "gh ")):
            findings.append(
                IncidentPlaybookFinding(
                    location,
                    "command must use a repo-native make/script/git/gh/docker-compose entrypoint",
                )
            )


def _validate_playbook(
    findings: list[IncidentPlaybookFinding],
    playbook: dict[str, Any],
) -> None:
    playbook_id = str(playbook.get("id") or "<missing-id>")
    for field_name in REQUIRED_PLAYBOOK_FIELDS:
        if playbook.get(field_name) in (None, "", []):
            findings.append(IncidentPlaybookFinding(playbook_id, f"missing {field_name}"))

    for field_name in (
        "symptoms",
        "dashboards_metrics",
        "expected_response_fields",
        "containment_actions",
        "escalation_path",
        "post_incident_evidence",
    ):
        _as_non_empty_list(
            findings=findings,
            location=playbook_id,
            field_name=field_name,
            value=playbook.get(field_name),
        )

    api_checks = _as_non_empty_list(
        findings=findings,
        location=playbook_id,
        field_name="api_checks",
        value=playbook.get("api_checks"),
    )
    _validate_api_checks(findings, playbook_id, api_checks)

    database_checks = _as_non_empty_list(
        findings=findings,
        location=playbook_id,
        field_name="database_safe_checks",
        value=playbook.get("database_safe_checks"),
    )
    _validate_database_checks(findings, playbook_id, database_checks)

    commands = _as_non_empty_list(
        findings=findings,
        location=playbook_id,
        field_name="repository_native_commands",
        value=playbook.get("repository_native_commands"),
    )
    _validate_commands(findings, playbook_id, commands)


def _validate_documentation_surfaces(
    findings: list[IncidentPlaybookFinding],
    root: Path,
    payload: dict[str, Any],
) -> None:
    playbooks = payload.get("playbooks", [])
    guard_command = payload.get("guard_command")
    for surface in payload.get("documentation_surfaces", []):
        surface_path = root / surface
        if not surface_path.exists():
            findings.append(IncidentPlaybookFinding(surface, "documentation surface is missing"))
            continue
        text = surface_path.read_text(encoding="utf-8")
        if CONTRACT_PATH.as_posix() not in text:
            findings.append(
                IncidentPlaybookFinding(
                    surface,
                    f"missing contract reference {CONTRACT_PATH.as_posix()}",
                )
            )
        if guard_command and guard_command not in text:
            findings.append(
                IncidentPlaybookFinding(surface, f"missing guard command {guard_command}")
            )
        for playbook in playbooks:
            playbook_id = playbook.get("id")
            title = playbook.get("title")
            if playbook_id and playbook_id not in text and title and title not in text:
                findings.append(
                    IncidentPlaybookFinding(
                        surface,
                        f"missing playbook reference {playbook_id!r}",
                    )
                )


def find_incident_playbook_findings(root: Path = REPO_ROOT) -> list[IncidentPlaybookFinding]:
    contract = root / CONTRACT_PATH
    if not contract.exists():
        return [IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), "contract is missing")]

    findings: list[IncidentPlaybookFinding] = []
    payload = _load_contract(root)
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        findings.append(
            IncidentPlaybookFinding(
                CONTRACT_PATH.as_posix(),
                f"schema_version must be {EXPECTED_SCHEMA_VERSION}",
            )
        )
    if payload.get("repository") != "lotus-core":
        findings.append(
            IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), "repository must be lotus-core")
        )
    if payload.get("guard_command") != "make incident-playbook-guard":
        findings.append(
            IncidentPlaybookFinding(
                CONTRACT_PATH.as_posix(),
                "guard_command must be make incident-playbook-guard",
            )
        )

    playbooks = payload.get("playbooks")
    if not isinstance(playbooks, list) or not playbooks:
        findings.append(
            IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), "playbooks must be non-empty")
        )
        playbooks = []
    ids = [playbook.get("id") for playbook in playbooks if isinstance(playbook, dict)]
    missing_ids = sorted(REQUIRED_PLAYBOOK_IDS - set(ids))
    extra_ids = sorted(set(ids) - REQUIRED_PLAYBOOK_IDS)
    for playbook_id in missing_ids:
        findings.append(
            IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), f"missing playbook {playbook_id}")
        )
    for playbook_id in extra_ids:
        findings.append(
            IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), f"unexpected playbook {playbook_id}")
        )
    duplicate_ids = sorted({playbook_id for playbook_id in ids if ids.count(playbook_id) > 1})
    for playbook_id in duplicate_ids:
        findings.append(
            IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), f"duplicate playbook {playbook_id}")
        )

    for playbook in playbooks:
        if not isinstance(playbook, dict):
            findings.append(
                IncidentPlaybookFinding(CONTRACT_PATH.as_posix(), "playbook must be an object")
            )
            continue
        _validate_playbook(findings, playbook)

    _validate_documentation_surfaces(findings, root, payload)
    return findings


def main() -> int:
    findings = find_incident_playbook_findings(REPO_ROOT)
    if findings:
        for finding in findings:
            print(f"{finding.location}: {finding.detail}")
        raise SystemExit(1)
    print("Incident playbook guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
