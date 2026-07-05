from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TRANSACTION_SORT_FIELDS: Final[tuple[str, ...]] = (
    "transaction_date",
    "settlement_date",
    "quantity",
    "price",
    "gross_transaction_amount",
)
TRANSACTION_SORT_ORDERS: Final[tuple[str, ...]] = ("asc", "desc")
DEFAULT_TRANSACTION_SORT_FIELD: Final[str] = "transaction_date"
DEFAULT_TRANSACTION_SORT_ORDER: Final[str] = "desc"


@dataclass(frozen=True, slots=True)
class TransactionSortValidationError(ValueError):
    field_name: str
    rejected_value: str
    allowed_values: tuple[str, ...]

    def __str__(self) -> str:
        allowed = ", ".join(self.allowed_values)
        return (
            f"Unsupported transaction sort parameter {self.field_name}="
            f"{self.rejected_value!r}. Allowed values: {allowed}."
        )


def normalize_transaction_sort(
    *,
    sort_by: str | None,
    sort_order: str | None,
) -> tuple[str, str]:
    normalized_sort_by = DEFAULT_TRANSACTION_SORT_FIELD if sort_by is None else sort_by
    if normalized_sort_by not in TRANSACTION_SORT_FIELDS:
        raise TransactionSortValidationError(
            field_name="sort_by",
            rejected_value=normalized_sort_by,
            allowed_values=TRANSACTION_SORT_FIELDS,
        )

    normalized_sort_order = (
        DEFAULT_TRANSACTION_SORT_ORDER if sort_order is None else sort_order.lower()
    )
    if normalized_sort_order not in TRANSACTION_SORT_ORDERS:
        raise TransactionSortValidationError(
            field_name="sort_order",
            rejected_value=sort_order or "",
            allowed_values=TRANSACTION_SORT_ORDERS,
        )

    return normalized_sort_by, normalized_sort_order
