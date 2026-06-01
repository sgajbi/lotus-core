from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    InstrumentEligibilitySupportability,
)
from ..repositories.identifier_normalization import normalize_security_id
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import (
    instrument_eligibility_record,
    missing_instrument_eligibility_record,
)
from .source_data_runtime import source_product_runtime_metadata


async def resolve_instrument_eligibility_bulk_response(
    *,
    repository: Any,
    request: InstrumentEligibilityBulkRequest,
) -> InstrumentEligibilityBulkResponse:
    rows = await repository.list_instrument_eligibility_profiles(
        security_ids=request.security_ids,
        as_of_date=request.as_of_date,
    )
    return build_instrument_eligibility_bulk_response(request=request, rows=rows)


def build_instrument_eligibility_bulk_response(
    *,
    request: InstrumentEligibilityBulkRequest,
    rows: list[Any],
) -> InstrumentEligibilityBulkResponse:
    rows_by_security_id = {normalize_security_id(row.security_id): row for row in rows}

    records = []
    missing_security_ids: list[str] = []
    for requested_security_id in request.security_ids:
        security_id = normalize_security_id(requested_security_id)
        row = rows_by_security_id.get(security_id)
        if row is None:
            missing_security_ids.append(security_id)
            records.append(missing_instrument_eligibility_record(security_id))
            continue
        records.append(instrument_eligibility_record(row))

    supportability_state = "READY"
    supportability_reason = "INSTRUMENT_ELIGIBILITY_READY"
    if missing_security_ids:
        supportability_state = "INCOMPLETE"
        supportability_reason = "INSTRUMENT_ELIGIBILITY_MISSING"

    return InstrumentEligibilityBulkResponse(
        records=records,
        supportability=InstrumentEligibilitySupportability(
            state=supportability_state,
            reason=supportability_reason,
            requested_count=len(request.security_ids),
            resolved_count=len(request.security_ids) - len(missing_security_ids),
            missing_security_ids=missing_security_ids,
        ),
        lineage={
            "source_system": "instrument_eligibility",
            "contract_version": "rfc_087_v1",
        },
        **source_product_runtime_metadata(
            request.as_of_date,
            data_quality_status=market_reference_data_quality_status(
                rows,
                required_count=len(request.security_ids),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
        ),
    )
