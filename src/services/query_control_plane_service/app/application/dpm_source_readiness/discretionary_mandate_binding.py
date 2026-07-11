"""Application policy for effective discretionary mandate bindings."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from ...contracts.discretionary_mandate_binding import (
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DiscretionaryMandateBindingSupportability,
    RebalanceBandContext,
)
from ...domain.dpm_source_readiness import DiscretionaryMandateBindingEvidence
from ...ports.dpm_source_readiness import DpmReferenceDataReader
from .metadata import dpm_source_runtime_metadata

MandateSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class MandateReviewSchedule:
    """Source-owned mandate review cadence and completed/due dates."""

    cadence: str | None
    last_review_date: date | None
    next_review_due_date: date | None

    @property
    def is_missing(self) -> bool:
        """Return whether the review schedule lacks any required source evidence."""

        return (
            not self.cadence or self.last_review_date is None or self.next_review_due_date is None
        )


@dataclass(slots=True)
class DiscretionaryMandateBindingService:
    """Resolve and assess the effective discretionary mandate for a portfolio."""

    reader: DpmReferenceDataReader
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(
        self,
        *,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        evidence = await self.reader.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
            booking_center_code=request.booking_center_code,
        )
        if evidence is None:
            return None
        return build_discretionary_mandate_binding_response(
            evidence=evidence,
            request=request,
            generated_at=self.clock(),
        )


def build_discretionary_mandate_binding_response(
    *,
    evidence: DiscretionaryMandateBindingEvidence,
    request: DiscretionaryMandateBindingRequest,
    generated_at: datetime,
) -> DiscretionaryMandateBindingResponse:
    """Map mandate evidence and derive supportability without persistence coupling."""

    authority_status = _control_code(evidence.discretionary_authority_status)
    review_schedule = MandateReviewSchedule(
        cadence=evidence.review_cadence,
        last_review_date=evidence.last_review_date,
        next_review_due_date=evidence.next_review_due_date,
    )
    supportability = _supportability(
        evidence=evidence,
        request=request,
        authority_status=authority_status,
        review_schedule=review_schedule,
    )
    lineage = {
        "source_system": evidence.source_system or "unknown",
        "source_record_id": evidence.source_record_id or "unknown",
        "contract_version": "rfc_087_v1",
    }
    content_payload = {
        "portfolio_id": evidence.portfolio_id,
        "mandate_id": evidence.mandate_id,
        "client_id": evidence.client_id,
        "mandate_type": evidence.mandate_type,
        "discretionary_authority_status": authority_status,
        "booking_center_code": evidence.booking_center_code,
        "jurisdiction_code": evidence.jurisdiction_code,
        "model_portfolio_id": evidence.model_portfolio_id,
        "policy_pack_id": evidence.policy_pack_id if request.include_policy_pack else None,
        "mandate_objective": evidence.mandate_objective,
        "risk_profile": evidence.risk_profile,
        "investment_horizon": evidence.investment_horizon,
        "review_cadence": review_schedule.cadence,
        "last_review_date": review_schedule.last_review_date,
        "next_review_due_date": review_schedule.next_review_due_date,
        "leverage_allowed": evidence.leverage_allowed,
        "tax_awareness_allowed": evidence.tax_awareness_allowed,
        "settlement_awareness_required": evidence.settlement_awareness_required,
        "rebalance_frequency": evidence.rebalance_frequency,
        "rebalance_bands": _rebalance_band_context(evidence).model_dump(mode="json"),
        "effective_from": evidence.effective_from,
        "effective_to": evidence.effective_to,
        "binding_version": evidence.binding_version,
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    return DiscretionaryMandateBindingResponse(
        **content_payload,
        **dpm_source_runtime_metadata(
            product_name="DiscretionaryMandateBinding",
            source_key=evidence.portfolio_id,
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status=_source_quality_status(evidence.quality_status),
            latest_evidence_timestamp=_latest_evidence_timestamp(evidence),
            content_payload=content_payload,
            lineage=lineage,
        ),
    )


def _supportability(
    *,
    evidence: DiscretionaryMandateBindingEvidence,
    request: DiscretionaryMandateBindingRequest,
    authority_status: str,
    review_schedule: MandateReviewSchedule,
) -> DiscretionaryMandateBindingSupportability:
    state: MandateSupportabilityState = "READY"
    reason = "MANDATE_BINDING_READY"
    missing: list[str] = []
    if authority_status != "ACTIVE":
        state, reason = "INCOMPLETE", "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
        missing.append("active_discretionary_authority")
    if request.include_policy_pack and not evidence.policy_pack_id:
        state, reason = "INCOMPLETE", "MANDATE_POLICY_PACK_MISSING"
        missing.append("policy_pack")
    if not evidence.mandate_objective:
        if state == "READY":
            state, reason = "INCOMPLETE", "MANDATE_OBJECTIVE_MISSING"
        missing.append("mandate_objective")
    if review_schedule.is_missing:
        if state == "READY":
            state, reason = "INCOMPLETE", "MANDATE_REVIEW_SCHEDULE_MISSING"
        missing.append("mandate_review_schedule")
    elif review_schedule.next_review_due_date < request.as_of_date and state == "READY":
        state, reason = "DEGRADED", "MANDATE_REVIEW_OVERDUE"
    return DiscretionaryMandateBindingSupportability(
        state=state,
        reason=reason,
        missing_data_families=missing,
    )


def _rebalance_band_context(
    evidence: DiscretionaryMandateBindingEvidence,
) -> RebalanceBandContext:
    return RebalanceBandContext(
        default_band=_optional_decimal(evidence.rebalance_bands.get("default_band"))
        or Decimal("0"),
        cash_reserve_weight=_optional_decimal(evidence.rebalance_bands.get("cash_reserve_weight")),
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as error:
        raise ValueError(f"Invalid rebalance-band decimal: {value!r}") from error


def _control_code(value: str, *, default: str = "UNKNOWN") -> str:
    return value.strip().upper() or default


def _source_quality_status(value: str) -> str:
    normalized = _control_code(value)
    if normalized in {"ACCEPTED", "COMPLETE", "READY"}:
        return "COMPLETE"
    if normalized in {"PARTIAL", "ESTIMATED", "STALE"}:
        return "PARTIAL"
    return "UNKNOWN"


def _latest_evidence_timestamp(
    evidence: DiscretionaryMandateBindingEvidence,
) -> datetime | None:
    timestamps = [
        value
        for value in (evidence.observed_at, evidence.updated_at, evidence.created_at)
        if value is not None
    ]
    return max(timestamps) if timestamps else None
