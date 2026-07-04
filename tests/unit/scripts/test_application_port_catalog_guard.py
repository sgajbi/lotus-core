import json
from pathlib import Path

from scripts.application_port_catalog_guard import find_application_port_catalog_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_catalog(root: Path, entry: dict) -> None:
    _write(
        root / "docs/architecture/application-port-capability-catalog.json",
        json.dumps(
            {
                "schema_version": "lotus-core.application-port-capability-catalog.v1",
                "catalog_guard": "scripts/application_port_catalog_guard.py",
                "capabilities": [entry],
            }
        ),
    )


def _valid_entry() -> dict:
    return {
        "capability_id": "query.example-reader",
        "capability_family": "repository-reader",
        "owner_service": "query_service",
        "port_module": "src/services/query_service/app/ports/example_ports.py",
        "port_symbols": ["ExampleReader"],
        "adapter_modules": ["src/services/query_service/app/repositories/example_repository.py"],
        "consumer_modules": ["src/services/query_service/app/services/example_service.py"],
        "guard_scripts": ["scripts/example_guard.py"],
        "standards": ["docs/standards/application-port-layer-standard.md"],
        "status": "implemented-representative",
        "runtime_boundary": "design-modularity-only",
    }


def test_application_port_catalog_guard_accepts_cataloged_port(tmp_path: Path) -> None:
    _write(tmp_path / "scripts/application_port_catalog_guard.py", "")
    _write(tmp_path / "scripts/example_guard.py", "")
    _write(
        tmp_path / "src/services/query_service/app/ports/example_ports.py",
        "from typing import Protocol\nclass ExampleReader(Protocol):\n    pass\n",
    )
    _write(tmp_path / "src/services/query_service/app/repositories/example_repository.py", "")
    _write(tmp_path / "src/services/query_service/app/services/example_service.py", "")
    _write(tmp_path / "docs/standards/application-port-layer-standard.md", "")
    _write_catalog(tmp_path, _valid_entry())

    assert find_application_port_catalog_findings(tmp_path) == []


def test_application_port_catalog_guard_rejects_missing_symbol_and_wrong_package(
    tmp_path: Path,
) -> None:
    entry = _valid_entry()
    entry["port_module"] = "src/services/query_service/app/services/example_ports.py"
    _write(tmp_path / "scripts/application_port_catalog_guard.py", "")
    _write(tmp_path / "scripts/example_guard.py", "")
    _write(tmp_path / "src/services/query_service/app/services/example_ports.py", "")
    _write(tmp_path / "src/services/query_service/app/repositories/example_repository.py", "")
    _write(tmp_path / "src/services/query_service/app/services/example_service.py", "")
    _write(tmp_path / "docs/standards/application-port-layer-standard.md", "")
    _write_catalog(tmp_path, entry)

    findings = find_application_port_catalog_findings(tmp_path)

    assert [finding.reason for finding in findings] == [
        "service-local ports must use src/services/<service>/app/ports/",
        "missing port symbol ExampleReader",
    ]


def test_application_port_catalog_guard_allows_transitional_provider_module(
    tmp_path: Path,
) -> None:
    entry = _valid_entry()
    entry["capability_id"] = "reconciliation.runtime-providers"
    entry["capability_family"] = "clock-id-provider"
    entry["port_module"] = (
        "src/services/financial_reconciliation_service/app/services/runtime_providers.py"
    )
    entry["port_symbols"] = ["MonotonicTimer"]
    _write(tmp_path / "scripts/application_port_catalog_guard.py", "")
    _write(tmp_path / "scripts/example_guard.py", "")
    _write(
        tmp_path
        / "src/services/financial_reconciliation_service/app/services/runtime_providers.py",
        "from typing import Protocol\nclass MonotonicTimer(Protocol):\n    pass\n",
    )
    _write(tmp_path / "src/services/query_service/app/repositories/example_repository.py", "")
    _write(tmp_path / "src/services/query_service/app/services/example_service.py", "")
    _write(tmp_path / "docs/standards/application-port-layer-standard.md", "")
    _write_catalog(tmp_path, entry)

    assert find_application_port_catalog_findings(tmp_path) == []
