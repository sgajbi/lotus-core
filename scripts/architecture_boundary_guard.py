from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROUTER_BOUNDARY_EXCEPTIONS_PATH = (
    ROOT / "docs" / "standards" / "api-layer-router-boundary-exceptions.json"
)
API_ROUTER_BOUNDARY_EXCEPTION_SPEC_VERSION = "1.0.0"
APPLICATION = "lotus-core"

FORBIDDEN_ROUTER_CLIENT_IMPORT_PREFIXES = (
    "aiohttp",
    "boto3",
    "botocore",
    "confluent_kafka",
    "httpx",
    "portfolio_common.kafka_utils",
    "redis",
    "requests",
)
ROUTER_DB_SESSION_IMPORT_PREFIXES = (
    "portfolio_common.db",
    "sqlalchemy.ext.asyncio",
)
ROUTER_DB_OPERATION_NAMES = {
    "add",
    "commit",
    "delete",
    "execute",
    "flush",
    "merge",
    "rollback",
    "scalar",
    "scalars",
    "stream",
}
APIRouter_HTTP_METHOD_DECORATORS = {
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
    "websocket",
}
ROUTER_FILE_ACCESS_CALLS = {
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
}


@dataclass(frozen=True)
class DirectImportBoundaryRule:
    name: str
    source_path_prefixes: tuple[str, ...]
    forbidden_module_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ApiRouterBoundaryViolation:
    path: str
    line_no: int
    code: str
    detail: str

    @property
    def exception_key(self) -> tuple[str, str]:
        return (self.path, self.code)

    def format(self) -> str:
        return f"{self.path}:{self.line_no}: {self.code}: {self.detail}"


DIRECT_IMPORT_BOUNDARY_RULES = (
    DirectImportBoundaryRule(
        name="query-control-plane routers must not import query-service repositories",
        source_path_prefixes=("src/services/query_control_plane_service/app/routers/",),
        forbidden_module_prefixes=("services.query_service.app.repositories",),
    ),
    DirectImportBoundaryRule(
        name="query runtime routers must not import query-control-plane internals",
        source_path_prefixes=("src/services/query_service/app/routers/",),
        forbidden_module_prefixes=("services.query_control_plane_service",),
    ),
    DirectImportBoundaryRule(
        name="ingestion routers must not import other service implementations",
        source_path_prefixes=("src/services/ingestion_service/app/routers/",),
        forbidden_module_prefixes=(
            "services.query_service",
            "services.query_control_plane_service",
            "services.event_replay_service",
            "services.financial_reconciliation_service",
            "services.persistence_service",
            "services.pipeline_orchestrator_service",
            "services.portfolio_aggregation_service",
            "services.timeseries_generator_service",
            "services.valuation_orchestrator_service",
            "services.calculators",
        ),
    ),
    DirectImportBoundaryRule(
        name="event-replay routers must not import concrete Kafka utilities",
        source_path_prefixes=("src/services/event_replay_service/app/routers/",),
        forbidden_module_prefixes=("portfolio_common.kafka_utils",),
    ),
    DirectImportBoundaryRule(
        name="valuation scheduler must not import concrete Kafka utilities",
        source_path_prefixes=(
            "src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py",
        ),
        forbidden_module_prefixes=("portfolio_common.kafka_utils",),
    ),
    DirectImportBoundaryRule(
        name="financial reconciliation service must use runtime provider ports",
        source_path_prefixes=(
            "src/services/financial_reconciliation_service/app/services/reconciliation_service.py",
        ),
        forbidden_module_prefixes=("time", "uuid"),
    ),
)


def _collect_python_files() -> list[Path]:
    src_root = ROOT / "src"
    return [p for p in src_root.rglob("*.py") if "__pycache__" not in p.parts]


def _scan_for_disallowed_patterns(files: list[Path], patterns: list[str]) -> list[str]:
    findings: list[str] = []
    for file_path in files:
        rel = file_path.relative_to(ROOT).as_posix()
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(content.splitlines(), start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append(f"{rel}:{idx}: disallowed pattern '{pattern}'")
    return findings


def _normalized_import_name(module_name: str) -> str:
    if module_name.startswith("src."):
        return module_name[len("src.") :]
    return module_name


def _imported_modules(file_path: Path) -> list[tuple[int, str]]:
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as exc:
        return [(exc.lineno or 1, "<syntax-error>")]

    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                (node.lineno, _normalized_import_name(alias.name)) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                continue
            imports.append((node.lineno, _normalized_import_name(node.module)))
    return imports


def _module_matches(import_name: str, forbidden_prefix: str) -> bool:
    return import_name == forbidden_prefix or import_name.startswith(f"{forbidden_prefix}.")


def _is_api_router_file(file_path: Path) -> bool:
    rel_parts = file_path.relative_to(ROOT).parts
    return (
        len(rel_parts) >= 6
        and rel_parts[0:2] == ("src", "services")
        and rel_parts[3:5] == ("app", "routers")
        and file_path.suffix == ".py"
    )


def _service_name_for_app_file(file_path: Path) -> str | None:
    rel_parts = file_path.relative_to(ROOT).parts
    if len(rel_parts) < 5 or rel_parts[0:2] != ("src", "services"):
        return None
    if rel_parts[3] != "app":
        return None
    return rel_parts[2]


def _scan_for_disallowed_imports(
    files: list[Path],
    rules: tuple[DirectImportBoundaryRule, ...] = DIRECT_IMPORT_BOUNDARY_RULES,
) -> list[str]:
    findings: list[str] = []
    for file_path in files:
        rel = file_path.relative_to(ROOT).as_posix()
        matching_rules = [
            rule
            for rule in rules
            if any(rel.startswith(prefix) for prefix in rule.source_path_prefixes)
        ]
        if not matching_rules:
            continue
        for line_no, import_name in _imported_modules(file_path):
            for rule in matching_rules:
                for forbidden_prefix in rule.forbidden_module_prefixes:
                    if _module_matches(import_name, forbidden_prefix):
                        findings.append(
                            f"{rel}:{line_no}: {rule.name}: disallowed direct import "
                            f"'{import_name}'"
                        )
    return findings


def _scan_for_service_runtime_imports(files: list[Path]) -> list[str]:
    findings: list[str] = []
    for file_path in files:
        service_name = _service_name_for_app_file(file_path)
        if service_name is None:
            continue
        rel = file_path.relative_to(ROOT).as_posix()
        forbidden_prefix = f"services.{service_name}.app"
        for line_no, import_name in _imported_modules(file_path):
            if _module_matches(import_name, forbidden_prefix):
                findings.append(
                    f"{rel}:{line_no}: service runtime packages must not import their own "
                    f"app through repo-root module path '{import_name}'; use package-local "
                    "'app...' or relative imports"
                )
    return findings


def _imported_symbol_names(node: ast.ImportFrom) -> set[str]:
    return {alias.asname or alias.name for alias in node.names}


def _name_or_attribute(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _call_name(node: ast.Call) -> str | None:
    return _name_or_attribute(node.func)


def _call_root_name(node: ast.Call) -> str | None:
    current = node.func
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def _call_references_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == name for child in ast.walk(node))


def _relative_path(file_path: Path) -> str:
    return file_path.relative_to(ROOT).as_posix()


def _scan_api_router_boundary_violations(files: list[Path]) -> list[ApiRouterBoundaryViolation]:
    violations: list[ApiRouterBoundaryViolation] = []
    for file_path in files:
        if not _is_api_router_file(file_path):
            continue
        rel = _relative_path(file_path)
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as exc:
            violations.append(
                ApiRouterBoundaryViolation(
                    path=rel,
                    line_no=exc.lineno or 1,
                    code="router_syntax_error",
                    detail="router file could not be parsed for API boundary enforcement",
                )
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_name = _normalized_import_name(alias.name)
                    if any(
                        _module_matches(import_name, prefix)
                        for prefix in FORBIDDEN_ROUTER_CLIENT_IMPORT_PREFIXES
                    ):
                        violations.append(
                            ApiRouterBoundaryViolation(
                                path=rel,
                                line_no=node.lineno,
                                code="router_external_client_dependency",
                                detail=f"router imports external client module '{import_name}'",
                            )
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                import_name = _normalized_import_name(node.module)
                imported_symbols = _imported_symbol_names(node)
                if any(
                    _module_matches(import_name, prefix)
                    for prefix in ROUTER_DB_SESSION_IMPORT_PREFIXES
                ):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_db_session_dependency",
                            detail=f"router imports database session dependency '{import_name}'",
                        )
                    )
                if import_name.endswith(".repositories") or ".repositories." in import_name:
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_repository_dependency",
                            detail=f"router imports repository module '{import_name}'",
                        )
                    )
                if any(symbol.endswith("Repository") for symbol in imported_symbols):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_repository_dependency",
                            detail="router imports repository type directly",
                        )
                    )
                if any(
                    _module_matches(import_name, prefix)
                    for prefix in FORBIDDEN_ROUTER_CLIENT_IMPORT_PREFIXES
                ):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_external_client_dependency",
                            detail=f"router imports external client module '{import_name}'",
                        )
                    )
            elif isinstance(node, ast.Call):
                call_name = _call_name(node)
                root_name = _call_root_name(node)
                if call_name == "Depends" and _call_references_name(node, "get_async_db_session"):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_db_session_dependency",
                            detail="router injects AsyncSession/get_async_db_session directly",
                        )
                    )
                if call_name is not None and call_name.endswith("Repository"):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_repository_dependency",
                            detail=f"router constructs repository '{call_name}' directly",
                        )
                    )
                if call_name in ROUTER_DB_OPERATION_NAMES and not (
                    root_name == "router" and call_name in APIRouter_HTTP_METHOD_DECORATORS
                ):
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_sqlalchemy_operation",
                            detail=f"router calls database operation '{call_name}' directly",
                        )
                    )
                if call_name in ROUTER_FILE_ACCESS_CALLS:
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_file_access",
                            detail=f"router calls file access operation '{call_name}' directly",
                        )
                    )
                if root_name in {"requests", "httpx", "aiohttp", "redis", "boto3"}:
                    violations.append(
                        ApiRouterBoundaryViolation(
                            path=rel,
                            line_no=node.lineno,
                            code="router_external_client_dependency",
                            detail=f"router calls external client '{root_name}' directly",
                        )
                    )
    return violations


def _load_api_router_boundary_exceptions(
    path: Path = API_ROUTER_BOUNDARY_EXCEPTIONS_PATH,
) -> dict[tuple[str, str], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("specVersion") != API_ROUTER_BOUNDARY_EXCEPTION_SPEC_VERSION:
        raise ValueError(
            "api-layer router boundary exceptions specVersion must be "
            f"{API_ROUTER_BOUNDARY_EXCEPTION_SPEC_VERSION!r}"
        )
    if payload.get("application") != APPLICATION:
        raise ValueError(
            f"api-layer router boundary exceptions application must be {APPLICATION!r}"
        )
    exception_map: dict[tuple[str, str], str] = {}
    exceptions = payload.get("transitionalExceptions", [])
    if not isinstance(exceptions, list):
        raise ValueError("api-layer router boundary exceptions must contain transitionalExceptions")
    for index, item in enumerate(exceptions):
        if not isinstance(item, dict):
            raise ValueError(f"transitionalExceptions[{index}] must be an object")
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value.startswith("src/services/"):
            raise ValueError(f"transitionalExceptions[{index}] must declare a service path")
        issue = item.get("issue")
        if not isinstance(issue, str) or not issue.startswith("#"):
            raise ValueError(f"transitionalExceptions[{index}] must declare issue")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"transitionalExceptions[{index}] must declare rationale")
        codes = item.get("violationCodes")
        if not isinstance(codes, list) or not codes:
            raise ValueError(f"transitionalExceptions[{index}] must declare violationCodes")
        for code in codes:
            if not isinstance(code, str) or not code.strip():
                raise ValueError(
                    f"transitionalExceptions[{index}] violationCodes must be non-empty strings"
                )
            key = (path_value, code)
            if key in exception_map:
                raise ValueError(f"duplicate api-layer router boundary exception for {key}")
            exception_map[key] = issue
    return exception_map


def _evaluate_api_router_boundary(
    files: list[Path],
    exception_path: Path = API_ROUTER_BOUNDARY_EXCEPTIONS_PATH,
) -> list[str]:
    violations = _scan_api_router_boundary_violations(files)
    exception_map = _load_api_router_boundary_exceptions(exception_path)
    current_exception_keys = {violation.exception_key for violation in violations}
    findings = [
        violation.format()
        for violation in violations
        if violation.exception_key not in exception_map
    ]
    for stale_key, issue in sorted(exception_map.items()):
        if stale_key not in current_exception_keys:
            path, code = stale_key
            findings.append(
                f"{path}: api-layer router boundary exception for {code} ({issue}) is stale"
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check architecture boundary guardrails. "
            "Validates removed ownership domains and selected direct import boundaries."
        )
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with non-zero exit code on violations. Default mode prints findings only.",
    )
    args = parser.parse_args()

    disallowed_import_patterns = [
        "risk_analytics_engine",
        "performance_calculator_engine",
        "concentration_analytics_engine",
    ]

    files = _collect_python_files()
    findings = _scan_for_disallowed_patterns(files, disallowed_import_patterns)
    findings.extend(_scan_for_disallowed_imports(files))
    findings.extend(_scan_for_service_runtime_imports(files))
    findings.extend(_evaluate_api_router_boundary(files))

    if findings:
        print("Architecture boundary guard findings:")
        for finding in findings:
            print(f" - {finding}")
        if args.strict:
            return 1
        return 0

    print("Architecture boundary guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
