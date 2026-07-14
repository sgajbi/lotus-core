"""Map cost-basis transactions to SQLAlchemy lot-state persistence values."""

from decimal import Decimal

from sqlalchemy.dialects.postgresql.dml import Insert

from ...domain.cost_basis import CostBasisTransaction

_IMMUTABLE_LOT_STATE_FIELDS = frozenset({"id", "lot_id", "source_transaction_id"})


def buy_lot_state_payload(transaction: CostBasisTransaction) -> dict[str, object]:
    """Return the durable lot-state values opened by a purchase transaction."""

    accrued_interest_local = transaction.accrued_interest or Decimal(0)
    return {
        "lot_id": f"LOT-{transaction.transaction_id}",
        "source_transaction_id": transaction.transaction_id,
        "portfolio_id": transaction.portfolio_id,
        "instrument_id": transaction.instrument_id,
        "security_id": transaction.security_id,
        "acquisition_date": transaction.transaction_date.date(),
        "original_quantity": transaction.quantity,
        "open_quantity": transaction.quantity,
        "lot_cost_local": transaction.net_cost_local or Decimal(0),
        "lot_cost_base": transaction.net_cost or Decimal(0),
        "accrued_interest_paid_local": accrued_interest_local,
        "economic_event_id": getattr(transaction, "economic_event_id", None),
        "linked_transaction_group_id": getattr(
            transaction,
            "linked_transaction_group_id",
            None,
        ),
        "calculation_policy_id": getattr(transaction, "calculation_policy_id", None),
        "calculation_policy_version": getattr(
            transaction,
            "calculation_policy_version",
            None,
        ),
        "source_system": getattr(transaction, "source_system", None),
    }


def mutable_lot_state_fields(insert_statement: Insert) -> dict[str, object]:
    """Return conflict-update fields while preserving durable lot identity."""

    return {
        column.name: column
        for column in insert_statement.excluded
        if column.name not in _IMMUTABLE_LOT_STATE_FIELDS
    }
