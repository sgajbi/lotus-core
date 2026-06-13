from __future__ import annotations

from dataclasses import dataclass
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

_MandateSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


@dataclass(frozen=True)
class _MandateReviewSchedule:
    cadence: str | None
    last_review_date: Any
    next_review_due_date: Any

    @property
    def is_missing(self) -> bool:
        return (
            not self.cadence or self.last_review_date is None or self.next_review_due_date is None
        )


async def resolve_discretionary_mandate_binding_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: DiscretionaryMandateBindingRequest,
) -> DiscretionaryMandateBindingResponse | None:
    row = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
        booking_center_code=request.booking_center_code,
    )
    if row is None:
        return None

    return build_discretionary_mandate_binding_response(
        row=row,
        request=request,
    )


def build_discretionary_mandate_binding_response(
    *,
    row: Any,
    request: DiscretionaryMandateBindingRequest,
) -> DiscretionaryMandateBindingResponse:
    discretionary_authority_status = control_code(row.discretionary_authority_status)
    mandate_objective = getattr(row, "mandate_objective", None)
    review_schedule = _MandateReviewSchedule(
        cadence=getattr(row, "review_cadence", None),
        last_review_date=getattr(row, "last_review_date", None),
        next_review_due_date=getattr(row, "next_review_due_date", None),
    )

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
        review_cadence=review_schedule.cadence,
        last_review_date=review_schedule.last_review_date,
        next_review_due_date=review_schedule.next_review_due_date,
        leverage_allowed=bool(row.leverage_allowed),
        tax_awareness_allowed=bool(row.tax_awareness_allowed),
        settlement_awareness_required=bool(row.settlement_awareness_required),
        rebalance_frequency=row.rebalance_frequency,
        rebalance_bands=_rebalance_band_context(row),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        supportability=_mandate_binding_supportability(
            row=row,
            request=request,
            discretionary_authority_status=discretionary_authority_status,
            mandate_objective=mandate_objective,
            review_schedule=review_schedule,
        ),
        lineage=_mandate_binding_lineage(row),
        **source_product_runtime_metadata(
            request.as_of_date,
            data_quality_status=control_code(row.quality_status, default="UNKNOWN"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([row]),
        ),
    )


def _mandate_binding_supportability(
    *,
    row: Any,
    request: DiscretionaryMandateBindingRequest,
    discretionary_authority_status: str,
    mandate_objective: str | None,
    review_schedule: _MandateReviewSchedule,
) -> DiscretionaryMandateBindingSupportability:
    missing_data_families: list[str] = []
    supportability_state: _MandateSupportabilityState = "READY"
    supportability_reason = "MANDATE_BINDING_READY"

    if discretionary_authority_status != "ACTIVE":
        supportability_state = "INCOMPLETE"
        supportability_reason = "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
        missing_data_families.append("active_discretionary_authority")
    if request.include_policy_pack and not row.policy_pack_id:
        supportability_state = "INCOMPLETE"
        supportability_reason = "MANDATE_POLICY_PACK_MISSING"
        missing_data_families.append("policy_pack")

    supportability_state, supportability_reason = _apply_mandate_review_supportability(
        request=request,
        mandate_objective=mandate_objective,
        review_schedule=review_schedule,
        supportability_state=supportability_state,
        supportability_reason=supportability_reason,
        missing_data_families=missing_data_families,
    )

    return DiscretionaryMandateBindingSupportability(
        state=supportability_state,
        reason=supportability_reason,
        missing_data_families=missing_data_families,
    )


def _apply_mandate_review_supportability(
    *,
    request: DiscretionaryMandateBindingRequest,
    mandate_objective: str | None,
    review_schedule: _MandateReviewSchedule,
    supportability_state: _MandateSupportabilityState,
    supportability_reason: str,
    missing_data_families: list[str],
) -> tuple[_MandateSupportabilityState, str]:
    if not mandate_objective:
        if supportability_state == "READY":
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_OBJECTIVE_MISSING"
        missing_data_families.append("mandate_objective")
    if review_schedule.is_missing:
        if supportability_state == "READY":
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_REVIEW_SCHEDULE_MISSING"
        missing_data_families.append("mandate_review_schedule")
    elif (
        review_schedule.next_review_due_date < request.as_of_date
        and supportability_state == "READY"
    ):
        supportability_state = "DEGRADED"
        supportability_reason = "MANDATE_REVIEW_OVERDUE"

    return supportability_state, supportability_reason


def _rebalance_band_context(row: Any) -> RebalanceBandContext:
    bands = dict(row.rebalance_bands or {})
    default_band = as_optional_decimal(bands.get("default_band")) or Decimal("0")
    return RebalanceBandContext(
        default_band=default_band,
        cash_reserve_weight=as_optional_decimal(bands.get("cash_reserve_weight")),
    )


def _mandate_binding_lineage(row: Any) -> dict[str, str]:
    return {
        "source_system": row.source_system or "unknown",
        "source_record_id": row.source_record_id or "unknown",
        "contract_version": "rfc_087_v1",
    }
