from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DirectImportBoundaryRule:
    name: str
    source_path_prefixes: tuple[str, ...]
    forbidden_module_prefixes: tuple[str, ...]


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
