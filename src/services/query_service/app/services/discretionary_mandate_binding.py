from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DiscretionaryMandateBindingSupportability,
    RebalanceBandContext,
)
from .integration_value_normalization import as_optional_decimal, control_code
from .reference_data_helpers import latest_reference_evidence_timestamp
from .source_data_runtime import source_product_runtime_metadata


def build_discretionary_mandate_binding_response(
    *,
    row: Any,
    request: DiscretionaryMandateBindingRequest,
) -> DiscretionaryMandateBindingResponse:
    missing_data_families: list[str] = []
    supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "MANDATE_BINDING_READY"
    discretionary_authority_status = control_code(row.discretionary_authority_status)
    if discretionary_authority_status != "ACTIVE":
        supportability_state = "INCOMPLETE"
        supportability_reason = "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
        missing_data_families.append("active_discretionary_authority")
    if request.include_policy_pack and not row.policy_pack_id:
        supportability_state = "INCOMPLETE"
        supportability_reason = "MANDATE_POLICY_PACK_MISSING"
        missing_data_families.append("policy_pack")

    mandate_objective = getattr(row, "mandate_objective", None)
    review_cadence = getattr(row, "review_cadence", None)
    last_review_date = getattr(row, "last_review_date", None)
    next_review_due_date = getattr(row, "next_review_due_date", None)
    if not mandate_objective:
        if supportability_state == "READY":
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_OBJECTIVE_MISSING"
        missing_data_families.append("mandate_objective")
    if not review_cadence or last_review_date is None or next_review_due_date is None:
        if supportability_state == "READY":
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_REVIEW_SCHEDULE_MISSING"
        missing_data_families.append("mandate_review_schedule")
    elif next_review_due_date < request.as_of_date and supportability_state == "READY":
        supportability_state = "DEGRADED"
        supportability_reason = "MANDATE_REVIEW_OVERDUE"

    bands = dict(row.rebalance_bands or {})
    default_band = as_optional_decimal(bands.get("default_band")) or Decimal("0")

    return DiscretionaryMandateBindingResponse(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        mandate_type=row.mandate_type,
        discretionary_authority_status=discretionary_authority_status,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id if request.include_policy_pack else None,
        mandate_objective=mandate_objective,
        risk_profile=row.risk_profile,
        investment_horizon=row.investment_horizon,
        review_cadence=review_cadence,
        last_review_date=last_review_date,
        next_review_due_date=next_review_due_date,
        leverage_allowed=bool(row.leverage_allowed),
        tax_awareness_allowed=bool(row.tax_awareness_allowed),
        settlement_awareness_required=bool(row.settlement_awareness_required),
        rebalance_frequency=row.rebalance_frequency,
        rebalance_bands=RebalanceBandContext(
            default_band=default_band,
            cash_reserve_weight=as_optional_decimal(bands.get("cash_reserve_weight")),
        ),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        supportability=DiscretionaryMandateBindingSupportability(
            state=supportability_state,
            reason=supportability_reason,
            missing_data_families=missing_data_families,
        ),
        lineage={
            "source_system": row.source_system or "unknown",
            "source_record_id": row.source_record_id or "unknown",
            "contract_version": "rfc_087_v1",
        },
        **source_product_runtime_metadata(
            request.as_of_date,
            data_quality_status=control_code(row.quality_status, default="UNKNOWN"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([row]),
        ),
    )
