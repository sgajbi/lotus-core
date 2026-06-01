from __future__ import annotations

from typing import Literal

from ..dtos.reference_integration_dto import (
    DpmSourceFamilyReadiness,
    DpmSourceFamilyState,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    DpmSourceReadinessSupportability,
)
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date

DpmSourceFamilyName = Literal["mandate", "model_targets", "eligibility", "tax_lots", "market_data"]


def dpm_source_family_readiness(
    *,
    family: DpmSourceFamilyName,
    product_name: str,
    state: DpmSourceFamilyState,
    reason: str,
    missing_items: list[str] | None = None,
    stale_items: list[str] | None = None,
    evidence_count: int = 0,
) -> DpmSourceFamilyReadiness:
    return DpmSourceFamilyReadiness(
        family=family,
        product_name=product_name,
        state=state,
        reason=reason,
        missing_items=list(missing_items or []),
        stale_items=list(stale_items or []),
        evidence_count=evidence_count,
    )


def unavailable_dpm_source_family(
    *,
    family: DpmSourceFamilyName,
    product_name: str,
    reason: str,
    missing_items: list[str] | None = None,
) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family=family,
        product_name=product_name,
        state="UNAVAILABLE",
        reason=reason,
        missing_items=missing_items,
    )


def dpm_source_readiness_supportability(
    families: list[DpmSourceFamilyReadiness],
) -> DpmSourceReadinessSupportability:
    counts: dict[DpmSourceFamilyState, int] = {
        "READY": 0,
        "DEGRADED": 0,
        "INCOMPLETE": 0,
        "UNAVAILABLE": 0,
    }
    for family in families:
        counts[family.state] += 1

    if counts["UNAVAILABLE"]:
        state: DpmSourceFamilyState = "UNAVAILABLE"
        reason = "DPM_SOURCE_READINESS_UNAVAILABLE"
    elif counts["INCOMPLETE"]:
        state = "INCOMPLETE"
        reason = "DPM_SOURCE_READINESS_INCOMPLETE"
    elif counts["DEGRADED"]:
        state = "DEGRADED"
        reason = "DPM_SOURCE_READINESS_DEGRADED"
    else:
        state = "READY"
        reason = "DPM_SOURCE_READINESS_READY"

    return DpmSourceReadinessSupportability(
        state=state,
        reason=reason,
        ready_family_count=counts["READY"],
        degraded_family_count=counts["DEGRADED"],
        incomplete_family_count=counts["INCOMPLETE"],
        unavailable_family_count=counts["UNAVAILABLE"],
    )


def build_dpm_source_readiness_response(
    *,
    portfolio_id: str,
    request: DpmSourceReadinessRequest,
    resolved_mandate_id: str | None,
    resolved_model_portfolio_id: str | None,
    evaluated_instrument_ids: list[str],
    families: list[DpmSourceFamilyReadiness],
) -> DpmSourceReadinessResponse:
    supportability = dpm_source_readiness_supportability(families)
    return DpmSourceReadinessResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=resolved_mandate_id,
        model_portfolio_id=resolved_model_portfolio_id,
        evaluated_instrument_ids=evaluated_instrument_ids,
        families=families,
        supportability=supportability,
        lineage={
            "source_system": "lotus-core",
            "contract_version": "rfc_087_v1",
            "readiness_scope": "dpm_source_family",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=("COMPLETE" if supportability.state == "READY" else "PARTIAL"),
            latest_evidence_timestamp=None,
        ),
    )
