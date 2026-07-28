"""Alembic rendering adapter for governed financial numeric types."""

from __future__ import annotations

from typing import Any

from .financial_numeric import ExactNumeric


def render_financial_numeric(
    object_type: str,
    value: Any,
    _autogen_context: Any,
) -> str | bool:
    """Render the runtime decorator as portable standard SQLAlchemy migration DDL."""

    if object_type != "type" or not isinstance(value, ExactNumeric):
        return False
    if value.precision is None and value.scale is None:
        return "sa.Numeric()"
    return f"sa.Numeric(precision={value.precision}, scale={value.scale})"
