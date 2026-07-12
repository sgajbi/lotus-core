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
    Path("src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py"),
    Path("src/services/ingestion_service/app/routers/reprocessing.py"),
    Path("src/services/query_service/app/repositories"),
    Path("src/services/query_service/app/services"),
    Path("src/services/valuation_orchestrator_service/app/core"),
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
