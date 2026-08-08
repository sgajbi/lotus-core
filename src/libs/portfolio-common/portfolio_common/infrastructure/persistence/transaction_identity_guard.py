"""Atomic PostgreSQL ownership predicates for global transaction identifiers."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from portfolio_common.domain.transaction import (
    TransactionIdentityFamily,
    TransactionIdentityOwnership,
)
from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_lifecycle_families,
)

_REDEMPTION_TRANSACTION_TYPES = tuple(
    production_transaction_types_for_lifecycle_families("redemption")
)
_REDEMPTION_ACCRUED_INTEREST_COMPONENT = "REDEMPTION_ACCRUED_INTEREST"
_REDEMPTION_ACCRUED_INTEREST_LINK = "REDEMPTION_TO_ACCRUED_INTEREST"


@dataclass(frozen=True, slots=True)
class GeneratedTransactionIdentityCollisionError(ValueError):
    """Report a rejected attempt to reclaim an existing global transaction id."""

    transaction_id: str
    reason_code: str = "generated_transaction_identity_collision"

    def __str__(self) -> str:
        return f"{self.reason_code}: ownership conflict for {self.transaction_id}"


def transaction_identity_update_allowed(
    transaction_table: Any,
    ownership: TransactionIdentityOwnership,
    *,
    excluded: Any,
    updated_fields: Collection[str],
) -> ColumnElement[bool]:
    """Require both the stored and post-update rows to retain canonical ownership."""

    merged_row = _merged_identity_row(transaction_table, excluded, updated_fields)
    return and_(
        _ownership_predicate(transaction_table, ownership),
        _ownership_predicate(merged_row, ownership),
    )


def _ownership_predicate(
    transaction_row: Any,
    ownership: TransactionIdentityOwnership,
) -> ColumnElement[bool]:
    same_portfolio = func.trim(transaction_row.portfolio_id) == ownership.portfolio_id
    generated_cash = func.coalesce(_generated_cash_predicate(transaction_row), False)
    redemption_interest = func.coalesce(_redemption_interest_predicate(transaction_row), False)
    if ownership.family is TransactionIdentityFamily.SOURCE:
        same_family = not_(or_(generated_cash, redemption_interest))
    elif ownership.family is TransactionIdentityFamily.GENERATED_SETTLEMENT_CASH:
        same_family = and_(
            generated_cash,
            func.trim(transaction_row.originating_transaction_id)
            == ownership.originating_transaction_id,
            _normalized(transaction_row.originating_transaction_type)
            == ownership.originating_transaction_type,
        )
    else:
        same_family = and_(
            redemption_interest,
            func.trim(transaction_row.originating_transaction_id)
            == ownership.originating_transaction_id,
            _normalized(transaction_row.originating_transaction_type)
            == ownership.originating_transaction_type,
        )
    return and_(same_portfolio, same_family)


@dataclass(frozen=True, slots=True)
class _TransactionIdentityRow:
    transaction_id: Any
    portfolio_id: Any
    transaction_type: Any
    cash_entry_mode: Any
    originating_transaction_id: Any
    originating_transaction_type: Any
    link_type: Any
    component_type: Any
    component_id: Any


def _merged_identity_row(
    transaction_table: Any,
    excluded: Any,
    updated_fields: Collection[str],
) -> _TransactionIdentityRow:
    """Resolve the identity columns that will exist after this sparse upsert."""

    def resulting_column(field_name: str) -> Any:
        row = excluded if field_name in updated_fields else transaction_table
        return getattr(row, field_name)

    return _TransactionIdentityRow(
        **{
            field_name: resulting_column(field_name)
            for field_name in _TransactionIdentityRow.__annotations__
        }
    )


def _generated_cash_predicate(transaction_table: Any) -> ColumnElement[bool]:
    originating_type = _normalized(transaction_table.originating_transaction_type)
    return and_(
        _normalized(transaction_table.transaction_type) == "ADJUSTMENT",
        _normalized(transaction_table.cash_entry_mode) == "AUTO_GENERATE",
        transaction_table.originating_transaction_id.is_not(None),
        func.trim(transaction_table.originating_transaction_id) != "",
        transaction_table.transaction_id
        == func.concat(func.trim(transaction_table.originating_transaction_id), "-CASHLEG"),
        _normalized(transaction_table.link_type) == func.concat(originating_type, "_TO_CASH"),
        or_(
            transaction_table.component_type.is_(None),
            func.trim(transaction_table.component_type) == "",
        ),
        or_(
            transaction_table.component_id.is_(None),
            func.trim(transaction_table.component_id) == "",
        ),
    )


def _redemption_interest_predicate(transaction_table: Any) -> ColumnElement[bool]:
    expected_id = func.concat(
        func.trim(transaction_table.originating_transaction_id),
        "-ACCRUED-INTEREST",
    )
    return and_(
        _normalized(transaction_table.transaction_type) == "INTEREST",
        transaction_table.originating_transaction_id.is_not(None),
        func.trim(transaction_table.originating_transaction_id) != "",
        transaction_table.transaction_id == expected_id,
        _normalized(transaction_table.component_type) == _REDEMPTION_ACCRUED_INTEREST_COMPONENT,
        transaction_table.component_id == func.concat(expected_id, ":v1"),
        _normalized(transaction_table.originating_transaction_type).in_(
            _REDEMPTION_TRANSACTION_TYPES
        ),
        _normalized(transaction_table.link_type) == _REDEMPTION_ACCRUED_INTEREST_LINK,
    )


def _normalized(column: Any) -> Any:
    return func.upper(func.trim(column))
