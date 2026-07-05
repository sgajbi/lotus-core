import json
from pathlib import Path

from scripts.in_process_boundary_guard import find_in_process_boundary_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_standard(root: Path) -> None:
    _write(root / "docs/standards/in-process-boundary-contract-standard.md", "standard")
    _write_exceptions(root, [])


def _write_exceptions(root: Path, exceptions: list[dict[str, str]]) -> None:
    _write(
        root / "docs/standards/in-process-boundary-exceptions.json",
        json.dumps(
            {
                "specVersion": "1.0.0",
                "application": "lotus-core",
                "exceptions": exceptions,
            },
            indent=2,
        ),
    )


def _exception(path: str, rule: str) -> dict[str, str]:
    return {
        "path": path,
        "rule": rule,
        "owner": "lotus-core engineering",
        "expiresOn": "2099-12-31",
        "followUpIssue": "#123",
        "reason": "Temporary migration exception with bounded ownership.",
    }


def test_boundary_guard_allows_clean_layer_imports(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    _write(
        tmp_path / "src/services/example_service/app/domain/policy.py",
        "from decimal import Decimal\n",
    )
    _write(
        tmp_path / "src/services/example_service/app/application/use_case.py",
        "from ..ports.publisher import Publisher\n",
    )
    _write(
        tmp_path / "src/services/example_service/app/ports/publisher.py",
        "from typing import Protocol\n",
    )
    _write(
        tmp_path / "src/services/example_service/app/adapters/publisher.py",
        "from confluent_kafka import Producer\n",
    )

    assert find_in_process_boundary_findings(tmp_path) == []


def test_boundary_guard_rejects_domain_runtime_import(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    _write(
        tmp_path / "src/services/example_service/app/domain/policy.py",
        "from sqlalchemy.ext.asyncio import AsyncSession\n",
    )

    findings = find_in_process_boundary_findings(tmp_path)

    assert any(finding.rule == "domain-forbidden-runtime-import" for finding in findings)


def test_boundary_guard_rejects_application_adapter_import(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    _write(
        tmp_path / "src/services/example_service/app/application/use_case.py",
        "from ..adapters.publisher import PublisherAdapter\n",
    )

    findings = find_in_process_boundary_findings(tmp_path)

    assert any(finding.rule == "application-forbidden-layer-import" for finding in findings)


def test_boundary_guard_accepts_owned_exception_for_active_finding(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    path = "src/services/example_service/app/application/use_case.py"
    _write(tmp_path / path, "from ..adapters.publisher import PublisherAdapter\n")
    _write_exceptions(
        tmp_path,
        [_exception(path, "application-forbidden-layer-import")],
    )

    assert find_in_process_boundary_findings(tmp_path) == []


def test_boundary_guard_rejects_port_runtime_import(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    _write(
        tmp_path / "src/services/example_service/app/ports/publisher.py",
        "from pydantic import BaseModel\n",
    )

    findings = find_in_process_boundary_findings(tmp_path)

    assert any(finding.rule == "ports-forbidden-runtime-import" for finding in findings)


def test_boundary_guard_rejects_expired_exception(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    path = "src/services/example_service/app/application/use_case.py"
    expired = _exception(path, "application-forbidden-layer-import")
    expired["expiresOn"] = "2000-01-01"
    _write(tmp_path / path, "from ..adapters.publisher import PublisherAdapter\n")
    _write_exceptions(tmp_path, [expired])

    findings = find_in_process_boundary_findings(tmp_path)

    assert any(finding.rule == "expired-boundary-exception" for finding in findings)
    assert any(finding.rule == "application-forbidden-layer-import" for finding in findings)


def test_boundary_guard_rejects_stale_exception(tmp_path: Path) -> None:
    _write_standard(tmp_path)
    path = "src/services/example_service/app/application/use_case.py"
    _write(tmp_path / path, "from ..ports.publisher import Publisher\n")
    _write_exceptions(
        tmp_path,
        [_exception(path, "application-forbidden-layer-import")],
    )

    findings = find_in_process_boundary_findings(tmp_path)

    assert any(finding.rule == "stale-boundary-exception" for finding in findings)
