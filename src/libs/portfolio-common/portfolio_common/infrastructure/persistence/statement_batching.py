"""Bound caller-sized PostgreSQL statements by rows and bind parameters."""

from collections.abc import Iterator, Sequence
from typing import TypeVar

POSTGRES_STATEMENT_ROW_LIMIT = 1_000
POSTGRES_BIND_PARAMETER_BUDGET = 32_000

_T = TypeVar("_T")


def statement_chunk_size(
    *,
    binds_per_row: int,
    reserved_binds: int = 0,
    row_limit: int = POSTGRES_STATEMENT_ROW_LIMIT,
    bind_budget: int = POSTGRES_BIND_PARAMETER_BUDGET,
) -> int:
    """Return the largest safe row count for one parameterized statement.

    ``reserved_binds`` accounts for scalar predicates or values outside the
    caller-sized row collection.  Invalid budgets fail before repository I/O.
    """

    if binds_per_row <= 0:
        raise ValueError("binds_per_row must be a positive integer")
    if reserved_binds < 0:
        raise ValueError("reserved_binds must be non-negative")
    if row_limit <= 0:
        raise ValueError("row_limit must be a positive integer")
    if bind_budget <= 0:
        raise ValueError("bind_budget must be a positive integer")
    available_binds = bind_budget - reserved_binds
    if available_binds < binds_per_row:
        raise ValueError("bind budget cannot accommodate one row")
    return min(row_limit, available_binds // binds_per_row)


def iter_statement_chunks(
    values: Sequence[_T],
    *,
    binds_per_row: int,
    reserved_binds: int = 0,
) -> Iterator[Sequence[_T]]:
    """Yield order-preserving statement chunks within the governed budget."""

    chunk_size = statement_chunk_size(
        binds_per_row=binds_per_row,
        reserved_binds=reserved_binds,
    )
    for start in range(0, len(values), chunk_size):
        yield values[start : start + chunk_size]
