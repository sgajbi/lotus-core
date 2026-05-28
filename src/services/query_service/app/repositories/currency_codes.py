from typing import Any

from sqlalchemy import func


def normalize_currency_code(currency_code: str) -> str:
    return currency_code.strip().upper()


def currency_code_sql_expr(currency_code_column: Any):
    return func.upper(func.trim(currency_code_column))
