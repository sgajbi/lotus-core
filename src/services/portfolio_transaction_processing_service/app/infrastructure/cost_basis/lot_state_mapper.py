"""Map cost-basis transactions to SQLAlchemy lot-state persistence values."""

from decimal import Decimal

from portfolio_common.domain.calculation_lineage import CalculationLineage
from sqlalchemy.dialects.postgresql.dml import Insert

from ...domain.cost_basis import CostBasisTransaction
from ...domain.cost_basis.state_lineage import build_cost_basis_state_lineage
from .lot_state_lineage import lot_state_lineage_output_from_mapping

_IMMUTABLE_LOT_STATE_FIELDS = frozenset({"id", "lot_id", "source_transaction_id"})


def buy_lot_state_payload(transaction: CostBasisTransaction) -> dict[str, object]:
    """Return the durable lot-state values opened by a purchase transaction."""

    accrued_interest_local = transaction.accrued_interest or Decimal(0)
    payload: dict[str, object] = {
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
        "amortized_cost_profile_id": None,
        "amortized_cost_profile_version": None,
        "amortized_cost_profile_content_hash": None,
        "amortized_cost_recognized_through": None,
        "amortized_cost_scheduled_local": None,
    }
    parent_lineage = getattr(transaction, "calculation_lineage", None)
    lineage = build_cost_basis_state_lineage(
        algorithm_id="cost-basis-opening-lot-materialization",
        input_payload={
            "calculated_transaction_lineage": (
                parent_lineage.lineage_payload()
                if isinstance(parent_lineage, CalculationLineage)
                else None
            ),
            "source_transaction_id": transaction.transaction_id,
        },
        output_payload=lot_state_lineage_output_from_mapping(payload),
    )
    payload["calculation_lineage"] = lineage.lineage_payload()
    return payload


def mutable_lot_state_fields(insert_statement: Insert) -> dict[str, object]:
    """Return conflict-update fields while preserving durable lot identity."""

    return {
        column.name: column
        for column in insert_statement.excluded
        if column.name not in _IMMUTABLE_LOT_STATE_FIELDS
    }
