from __future__ import annotations

import ast
from pathlib import Path

LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
SENSITIVE_IDENTIFIER_TOKENS = (
    "account_id",
    "client_id",
    "correlation_id",
    "portfolio_id",
    "request_id",
    "security_id",
    "trace_id",
)

DEFAULT_SCAN_PATHS = (
    Path("src/libs/portfolio-common/portfolio_common/health.py"),
    Path("src/libs/portfolio-common/portfolio_common/kafka_consumer.py"),
    Path("src/libs/portfolio-common/portfolio_common/kafka_utils.py"),
    Path("src/libs/portfolio-common/portfolio_common/outbox_repository.py"),
    Path("src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py"),
    Path("src/services/ingestion_service/app/routers/reprocessing.py"),
    Path("src/services/persistence_service/app/repositories/transaction_db_repo.py"),
    Path(
        "src/services/portfolio_transaction_processing_service/app/delivery/kafka/"
        "transaction_processing_consumer.py"
    ),
    Path("src/services/portfolio_transaction_processing_service/app/infrastructure"),
    Path("src/services/calculators/position_valuation_calculator/app/consumers"),
    Path("src/services/portfolio_derived_state_service/app/delivery"),
    Path("src/services/portfolio_derived_state_service/app/infrastructure"),
    Path("src/services/query_service/app/repositories"),
    Path("src/services/query_service/app/services"),
    Path("src/services/valuation_orchestrator_service/app/core"),
)

HIGH_VOLUME_DEBUG_ONLY_MESSAGES = frozenset(
    {
        "Calculated cashflow for transaction %s: amount=%s classification=%s",
        "Cost-basis processing lock acquired.",
        "Outbox event staged",
        "Position-timeseries materialization completed.",
        "Processing valuation job.",
        "Re-armed valuation and timeseries generation after position history write.",
        "Staged portfolio aggregation jobs.",
        "Staged position history records for the recalculation epoch.",
        "Staged position history records.",
        "Staged portfolio time-series upsert.",
        "Staged position time-series upsert.",
        "Successfully staged cashflow record for transaction_id '%s' in epoch %s",
        "Transaction processing completed.",
        "Transaction upsert staged.",
    }
)


def _python_files(paths: tuple[Path, ...] = DEFAULT_SCAN_PATHS) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def _is_logger_call(node: ast.Call) -> bool:
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr in LOGGER_METHODS
        and isinstance(function.value, ast.Name)
        and function.value.id == "logger"
    )


def _identifier_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _identifier_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _contains_sensitive_identifier(node: ast.AST) -> bool:
    name = _identifier_name(node)
    if not name:
        return False
    normalized = name.lower()
    return any(token in normalized for token in SENSITIVE_IDENTIFIER_TOKENS)


def evaluate_structured_log_guard(paths: tuple[Path, ...] = DEFAULT_SCAN_PATHS) -> list[str]:
    errors: list[str] = []
    for file_path in _python_files(paths):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_logger_call(node):
                continue
            logger_method = node.func.attr
            message = (
                node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            )
            if logger_method == "info" and message in HIGH_VOLUME_DEBUG_ONLY_MESSAGES:
                errors.append(
                    f"{file_path}:{node.lineno}: high-volume routine event must use "
                    "logger.debug or bounded metrics, not logger.info"
                )
            if node.args and isinstance(node.args[0], ast.JoinedStr):
                errors.append(
                    f"{file_path}:{node.lineno}: logger message must not be an f-string; "
                    "use constant text plus structured fields"
                )
            for arg in node.args[1:]:
                if _contains_sensitive_identifier(arg):
                    errors.append(
                        f"{file_path}:{node.lineno}: logger call passes sensitive identifier "
                        f"`{_identifier_name(arg)}` as a message formatting argument"
                    )
    return errors


def main() -> int:
    errors = evaluate_structured_log_guard()
    if errors:
        print("Structured log guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Structured log guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
