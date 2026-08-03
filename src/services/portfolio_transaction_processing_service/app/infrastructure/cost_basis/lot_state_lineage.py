"""Canonical durable output contract for cost-basis lot-state lineage."""

from collections.abc import Mapping

from portfolio_common.database_models import PositionLotState

LOT_STATE_LINEAGE_OUTPUT_FIELDS = (
    "lot_id",
    "source_transaction_id",
    "portfolio_id",
    "instrument_id",
    "security_id",
    "acquisition_date",
    "original_quantity",
    "open_quantity",
    "lot_cost_local",
    "lot_cost_base",
    "accrued_interest_paid_local",
    "economic_event_id",
    "linked_transaction_group_id",
    "calculation_policy_id",
    "calculation_policy_version",
    "source_system",
    "amortized_cost_profile_id",
    "amortized_cost_profile_version",
    "amortized_cost_profile_content_hash",
    "amortized_cost_recognized_through",
    "amortized_cost_scheduled_local",
)


def lot_state_lineage_output_from_mapping(
    values: Mapping[str, object],
) -> dict[str, object]:
    """Project complete durable lot-state values into their lineage output."""

    missing_fields = [field for field in LOT_STATE_LINEAGE_OUTPUT_FIELDS if field not in values]
    if missing_fields:
        raise ValueError(
            "Cost-basis lot-state lineage is missing durable fields: " + ", ".join(missing_fields)
        )
    return {field: values[field] for field in LOT_STATE_LINEAGE_OUTPUT_FIELDS}


def lot_state_lineage_output_from_row(row: PositionLotState) -> dict[str, object]:
    """Project one persisted lot-state row into its complete lineage output."""

    return {field: getattr(row, field) for field in LOT_STATE_LINEAGE_OUTPUT_FIELDS}
