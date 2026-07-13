"""Verify currency SQL expressions and retirement of the mixed helper module."""

from pathlib import Path

from sqlalchemy import column

from src.services.query_service.app.repositories.currency_query_expressions import (
    currency_code_sql_expr,
)


def test_currency_code_expression_normalizes_whitespace_and_case() -> None:
    expression = currency_code_sql_expr(column("currency"))

    assert str(expression) == "upper(trim(currency))"


def test_mixed_currency_repository_helper_is_retired() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    retired_path = repository_root / "src/services/query_service/app/repositories/currency_codes.py"

    assert not retired_path.exists()
