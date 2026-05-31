from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    CioModelChangeAffectedCohortSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import cio_model_change_affected_mandate
from .request_fingerprint import request_fingerprint


def build_cio_model_change_affected_cohort_response(
    *,
    definition: Any,
    request: CioModelChangeAffectedCohortRequest,
    mandate_rows: list[Any],
) -> CioModelChangeAffectedCohortResponse:
    affected_mandates = [cio_model_change_affected_mandate(row) for row in mandate_rows]
    filters_applied = ["model_portfolio_id", "as_of_date"]
    if request.booking_center_code:
        filters_applied.append("booking_center_code")
    if not request.include_inactive_mandates:
        filters_applied.append("active_discretionary_authority")

    supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
    supportability_reason = "CIO_MODEL_CHANGE_COHORT_READY"
    if not affected_mandates:
        supportability_state = "INCOMPLETE"
        supportability_reason = "CIO_MODEL_CHANGE_COHORT_EMPTY"

    snapshot_fingerprint = request_fingerprint(
        {
            "product_name": "CioModelChangeAffectedCohort",
            "model_portfolio_id": definition.model_portfolio_id,
            "model_portfolio_version": definition.model_portfolio_version,
            "as_of_date": request.as_of_date.isoformat(),
            "booking_center_code": request.booking_center_code,
            "include_inactive_mandates": request.include_inactive_mandates,
            "mandate_ids": [mandate.mandate_id for mandate in affected_mandates],
            "portfolio_ids": [mandate.portfolio_id for mandate in affected_mandates],
        }
    )
    event_id = (
        "cio_model_change:"
        f"{definition.model_portfolio_id}:"
        f"{definition.model_portfolio_version}:"
        f"{request.as_of_date.isoformat()}:{snapshot_fingerprint}"
    )

    return CioModelChangeAffectedCohortResponse(
        model_portfolio_id=definition.model_portfolio_id,
        model_portfolio_version=definition.model_portfolio_version,
        model_change_event_id=event_id,
        approval_state=definition.approval_status,
        approved_at=definition.approved_at,
        effective_from=definition.effective_from,
        effective_to=definition.effective_to,
        affected_mandates=affected_mandates,
        supportability=CioModelChangeAffectedCohortSupportability(
            state=supportability_state,
            reason=supportability_reason,
            returned_mandate_count=len(affected_mandates),
            filters_applied=filters_applied,
        ),
        lineage={
            "source_system": definition.source_system or "lotus-core",
            "model_definition_source_record_id": definition.source_record_id or "unknown",
            "mandate_binding_table": "portfolio_mandate_bindings",
            "contract_version": "rfc_041_cio_model_change_cohort_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status="ACCEPTED" if affected_mandates else "MISSING",
            latest_evidence_timestamp=latest_reference_evidence_timestamp(
                [definition],
                mandate_rows,
            ),
            source_batch_fingerprint=snapshot_fingerprint,
            snapshot_id=f"cio_model_change_cohort:{snapshot_fingerprint}",
        ),
    )
