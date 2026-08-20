import pytest
from portfolio_common.infrastructure.persistence.statement_batching import (
    POSTGRES_BIND_PARAMETER_BUDGET,
    POSTGRES_STATEMENT_ROW_LIMIT,
    iter_statement_chunks,
    statement_chunk_size,
)


@pytest.mark.parametrize("binds_per_row", [2, 3, 4, 5])
def test_statement_chunks_enforce_row_limit_for_supported_widths(binds_per_row: int) -> None:
    values = list(range(POSTGRES_STATEMENT_ROW_LIMIT + 1))

    chunks = list(iter_statement_chunks(values, binds_per_row=binds_per_row))

    assert [len(chunk) for chunk in chunks] == [POSTGRES_STATEMENT_ROW_LIMIT, 1]
    assert [value for chunk in chunks for value in chunk] == values


def test_statement_chunks_bound_large_inputs_deterministically() -> None:
    values = list(range(10_000))

    chunks = list(iter_statement_chunks(values, binds_per_row=5))

    assert len(chunks) == 10
    assert all(len(chunk) == POSTGRES_STATEMENT_ROW_LIMIT for chunk in chunks)
    assert [value for chunk in chunks for value in chunk] == values


def test_statement_chunk_size_accounts_for_reserved_bind_parameters() -> None:
    assert (
        statement_chunk_size(
            binds_per_row=5,
            reserved_binds=5,
            row_limit=10_000,
            bind_budget=105,
        )
        == 20
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"binds_per_row": 0}, "binds_per_row"),
        ({"binds_per_row": 1, "reserved_binds": -1}, "reserved_binds"),
        ({"binds_per_row": 1, "row_limit": 0}, "row_limit"),
        ({"binds_per_row": 1, "bind_budget": 0}, "bind_budget"),
        (
            {
                "binds_per_row": 2,
                "reserved_binds": POSTGRES_BIND_PARAMETER_BUDGET - 1,
            },
            "cannot accommodate",
        ),
    ],
)
def test_statement_chunk_size_rejects_invalid_budgets(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        statement_chunk_size(**kwargs)
