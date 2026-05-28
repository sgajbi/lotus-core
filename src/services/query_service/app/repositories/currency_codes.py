from typing import Any

from portfolio_common.currency_codes import normalize_currency_code as _normalize_currency_code
from sqlalchemy import func


def normalize_currency_code(currency_code: object) -> str:
    return _normalize_currency_code(currency_code)


def currency_code_sql_expr(currency_code_column: Any):
    return func.upper(func.trim(currency_code_column))
