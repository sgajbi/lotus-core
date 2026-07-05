from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

EXCEPTIONS_PATH = Path("docs/standards/in-process-boundary-exceptions.json")
STANDARD_PATH = Path("docs/standards/in-process-boundary-contract-standard.md")
SERVICE_APP_ROOT = Path("src/services")
FOLLOW_UP_ISSUE_PATTERN = re.compile(r"^#\d+$")

RUNTIME_IMPORT_PREFIXES = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "confluent_kafka",
    "redis",
    "requests",
    "httpx",
    "boto3",
    "botocore",
    "portfolio_common.kafka_utils",
)
APPLICATION_RUNTIME_IMPORT_PREFIXES = (*RUNTIME_IMPORT_PREFIXES, "pydantic")
PORT_RUNTIME_IMPORT_PREFIXES = APPLICATION_RUNTIME_IMPORT_PREFIXES
PERSISTENCE_IMPORT_PREFIXES = (
    "portfolio_common.database_models",
    "src.libs.portfolio-common.portfolio_common.database_models",
)
DOMAIN_FORBIDDEN_LAYER_PARTS = {
    "application",
    "ports",
    "adapters",
    "infrastructure",
    "repositories",
    "repository",
    "routers",
    "delivery",
    "consumers",
    "producers",
    "DTOs",
    "dtos",
    "services",
}
APPLICATION_FORBIDDEN_LAYER_PARTS = {
    "adapters",
    "infrastructure",
    "repositories",
    "repository",
    "routers",
    "delivery",
    "consumers",
    "producers",
    "DTOs",
    "dtos",
    "services",
}
PORTS_FORBIDDEN_LAYER_PARTS = {
    "adapters",
    "infrastructure",
    "repositories",
    "repository",
    "routers",
    "delivery",
    "consumers",
    "producers",
    "DTOs",
    "dtos",
    "services",
}
PROOF_BUILDER_FORBIDDEN_LAYER_PARTS = {
    "repositories",
    "repository",
    "routers",
    "delivery",
    "persistence",
}


@dataclass(frozen=True, slots=True)
class InProcessBoundaryFinding:
    path: str
    line: int
    rule: str
    imported_module: str
    detail: str

    def as_text(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"{location}: {self.rule}: {self.imported_module}: {self.detail}"


@dataclass(frozen=True, slots=True)
class BoundaryException:
    path: str
    rule: str


def find_in_process_boundary_findings(root: Path) -> list[InProcessBoundaryFinding]:
    root = root.resolve()
    raw_findings = _scan_boundaries(root)
    exception_findings, exceptions = _load_valid_exceptions(root)
    filtered_findings = [
        finding
        for finding in raw_findings
        if BoundaryException(path=finding.path, rule=finding.rule) not in exceptions
    ]
    stale_exception_findings = _find_stale_exceptions(exceptions, raw_findings)
    missing_standard_findings = _validate_standard(root)
    return [
        *missing_standard_findings,
        *exception_findings,
        *filtered_findings,
        *stale_exception_findings,
    ]


def _validate_standard(root: Path) -> list[InProcessBoundaryFinding]:
    if (root / STANDARD_PATH).exists():
        return []
    return [
        InProcessBoundaryFinding(
            path=STANDARD_PATH.as_posix(),
            line=0,
            rule="missing-boundary-standard",
            imported_module="",
            detail="in-process boundary contract standard is missing",
        )
    ]


def _scan_boundaries(root: Path) -> list[InProcessBoundaryFinding]:
    findings: list[InProcessBoundaryFinding] = []
    for layer, file_path in _iter_layer_files(root):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        relative_path = file_path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    findings.extend(
                        _classify_import(
                            layer=layer,
                            path=relative_path,
                            line=node.lineno,
                            imported_module=alias.name,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                findings.extend(
                    _classify_import(
                        layer=layer,
                        path=relative_path,
                        line=node.lineno,
                        imported_module=module,
                    )
                )
            elif isinstance(node, ast.Call):
                findings.extend(_classify_runtime_call(layer, relative_path, node))
    return findings


def _iter_layer_files(root: Path) -> list[tuple[str, Path]]:
    layer_files: list[tuple[str, Path]] = []
    for app_root in (root / SERVICE_APP_ROOT).glob("*/app"):
        for layer in ("domain", "application", "use_cases", "ports", "adapters", "proof_builders"):
            layer_path = app_root / layer
            if not layer_path.exists():
                continue
            normalized_layer = "application" if layer == "use_cases" else layer
            for file_path in layer_path.rglob("*.py"):
                layer_files.append((normalized_layer, file_path))
    return layer_files


def _classify_import(
    *,
    layer: str,
    path: str,
    line: int,
    imported_module: str,
) -> list[InProcessBoundaryFinding]:
    if not imported_module:
        return []
    if layer == "domain":
        return _classify_domain_import(path, line, imported_module)
    if layer == "application":
        return _classify_application_import(path, line, imported_module)
    if layer == "ports":
        return _classify_ports_import(path, line, imported_module)
    if layer == "proof_builders":
        return _classify_proof_builder_import(path, line, imported_module)
    return []


def _classify_domain_import(
    path: str, line: int, imported_module: str
) -> list[InProcessBoundaryFinding]:
    findings: list[InProcessBoundaryFinding] = []
    if _matches_prefix(imported_module, RUNTIME_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "domain-forbidden-runtime-import",
                imported_module,
                "domain must be framework-free and infrastructure-free",
            )
        )
    if _matches_prefix(imported_module, PERSISTENCE_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "domain-forbidden-persistence-import",
                imported_module,
                "domain must not import persistence models",
            )
        )
    if _has_forbidden_layer(imported_module, DOMAIN_FORBIDDEN_LAYER_PARTS):
        findings.append(
            _finding(
                path,
                line,
                "domain-forbidden-layer-import",
                imported_module,
                "domain must not depend on application, ports, adapters, delivery, persistence, or legacy service packages",
            )
        )
    return findings


def _classify_application_import(
    path: str, line: int, imported_module: str
) -> list[InProcessBoundaryFinding]:
    findings: list[InProcessBoundaryFinding] = []
    if _matches_prefix(imported_module, APPLICATION_RUNTIME_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "application-forbidden-runtime-import",
                imported_module,
                "application modules must use ports and framework-neutral contracts",
            )
        )
    if _matches_prefix(imported_module, PERSISTENCE_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "application-forbidden-persistence-import",
                imported_module,
                "application modules must not import persistence models",
            )
        )
    if _has_forbidden_layer(imported_module, APPLICATION_FORBIDDEN_LAYER_PARTS):
        findings.append(
            _finding(
                path,
                line,
                "application-forbidden-layer-import",
                imported_module,
                "application modules must not import routers, concrete adapters, infrastructure, repositories, API DTOs, or legacy services",
            )
        )
    return findings


def _classify_ports_import(
    path: str, line: int, imported_module: str
) -> list[InProcessBoundaryFinding]:
    findings: list[InProcessBoundaryFinding] = []
    if _matches_prefix(imported_module, PORT_RUNTIME_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "ports-forbidden-runtime-import",
                imported_module,
                "ports must stay small framework-neutral capability contracts",
            )
        )
    if _matches_prefix(imported_module, PERSISTENCE_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "ports-forbidden-persistence-import",
                imported_module,
                "ports must not expose persistence row types",
            )
        )
    if _has_forbidden_layer(imported_module, PORTS_FORBIDDEN_LAYER_PARTS):
        findings.append(
            _finding(
                path,
                line,
                "ports-forbidden-layer-import",
                imported_module,
                "ports must not import delivery, concrete adapters, infrastructure, repositories, DTOs, or legacy services",
            )
        )
    return findings


def _classify_proof_builder_import(
    path: str, line: int, imported_module: str
) -> list[InProcessBoundaryFinding]:
    findings: list[InProcessBoundaryFinding] = []
    if _matches_prefix(imported_module, RUNTIME_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "proof-builder-forbidden-runtime-import",
                imported_module,
                "proof builders must assemble evidence from domain/application outputs, not framework or infrastructure objects",
            )
        )
    if _matches_prefix(imported_module, PERSISTENCE_IMPORT_PREFIXES):
        findings.append(
            _finding(
                path,
                line,
                "proof-builder-forbidden-persistence-import",
                imported_module,
                "proof builders must not assemble evidence directly from persistence models",
            )
        )
    if _has_forbidden_layer(imported_module, PROOF_BUILDER_FORBIDDEN_LAYER_PARTS):
        findings.append(
            _finding(
                path,
                line,
                "proof-builder-forbidden-layer-import",
                imported_module,
                "proof builders must not live off routers or persistence packages",
            )
        )
    return findings


def _classify_runtime_call(layer: str, path: str, node: ast.Call) -> list[InProcessBoundaryFinding]:
    if layer not in {"domain", "application", "ports"}:
        return []
    name = _call_name(node.func)
    if name not in {"Depends", "get_async_db_session", "get_db_session", "get_kafka_producer"}:
        return []
    rule_prefix = "ports" if layer == "ports" else layer
    return [
        _finding(
            path,
            node.lineno,
            f"{rule_prefix}-forbidden-runtime-call",
            name,
            "runtime wiring belongs in composition roots, routers, consumers, or infrastructure adapters",
        )
    ]


def _load_valid_exceptions(
    root: Path,
) -> tuple[list[InProcessBoundaryFinding], set[BoundaryException]]:
    path = root / EXCEPTIONS_PATH
    if not path.exists():
        return [
            _finding(
                EXCEPTIONS_PATH.as_posix(),
                0,
                "missing-boundary-exception-registry",
                "",
                "controlled exception registry is missing",
            )
        ], set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    exceptions = payload.get("exceptions")
    findings: list[InProcessBoundaryFinding] = []
    valid_exceptions: set[BoundaryException] = set()
    if not isinstance(exceptions, list):
        return [
            _finding(
                EXCEPTIONS_PATH.as_posix(),
                0,
                "invalid-exceptions-registry",
                "",
                "exceptions must be a list",
            )
        ], set()
    for index, entry in enumerate(exceptions, start=1):
        finding = _validate_exception(entry, index)
        if finding is not None:
            findings.append(finding)
            continue
        valid_exceptions.add(
            BoundaryException(path=entry["path"].replace("\\", "/"), rule=entry["rule"])
        )
    return findings, valid_exceptions


def _validate_exception(entry: object, index: int) -> InProcessBoundaryFinding | None:
    path = f"{EXCEPTIONS_PATH.as_posix()}#exceptions[{index}]"
    if not isinstance(entry, dict):
        return _finding(
            path, 0, "invalid-boundary-exception", "", "exception entries must be objects"
        )
    for field_name in ("path", "rule", "owner", "expiresOn", "followUpIssue", "reason"):
        value = entry.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return _finding(
                path,
                0,
                "invalid-boundary-exception",
                field_name,
                f"{field_name} must be a non-empty string",
            )
    if not FOLLOW_UP_ISSUE_PATTERN.match(entry["followUpIssue"]):
        return _finding(
            path,
            0,
            "invalid-boundary-exception",
            "followUpIssue",
            "followUpIssue must be formatted as #123",
        )
    try:
        expiry = date.fromisoformat(entry["expiresOn"])
    except ValueError:
        return _finding(
            path, 0, "invalid-boundary-exception", "expiresOn", "expiresOn must be an ISO date"
        )
    if expiry < date.today():
        return _finding(
            path, 0, "expired-boundary-exception", entry["path"], "exception expiry has passed"
        )
    return None


def _find_stale_exceptions(
    exceptions: set[BoundaryException], raw_findings: list[InProcessBoundaryFinding]
) -> list[InProcessBoundaryFinding]:
    active = {BoundaryException(path=finding.path, rule=finding.rule) for finding in raw_findings}
    stale_exceptions = sorted(exceptions - active, key=lambda item: (item.path, item.rule))
    return [
        _finding(
            exception.path,
            0,
            "stale-boundary-exception",
            exception.rule,
            "exception no longer matches a boundary finding and must be removed",
        )
        for exception in stale_exceptions
    ]


def _matches_prefix(imported_module: str, prefixes: tuple[str, ...]) -> bool:
    normalized = imported_module.lstrip(".")
    return any(normalized == prefix or normalized.startswith(f"{prefix}.") for prefix in prefixes)


def _has_forbidden_layer(imported_module: str, forbidden_parts: set[str]) -> bool:
    parts = [part for part in imported_module.lstrip(".").split(".") if part]
    return any(part in forbidden_parts for part in parts)


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _finding(
    path: str, line: int, rule: str, imported_module: str, detail: str
) -> InProcessBoundaryFinding:
    return InProcessBoundaryFinding(
        path=path,
        line=line,
        rule=rule,
        imported_module=imported_module,
        detail=detail,
    )


def main() -> int:
    findings = find_in_process_boundary_findings(Path.cwd())
    if findings:
        print("In-process boundary guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("In-process boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
