"""Build normalized currency expressions for Query Service SQL filters."""

from typing import Any

from sqlalchemy import func


def currency_code_sql_expr(currency_code_column: Any):
    return func.upper(func.trim(currency_code_column))
