from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientRestrictionProfileSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import client_restriction_profile_entry
from .request_fingerprint import request_fingerprint


def build_client_restriction_profile_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ClientRestrictionProfileRequest,
    rows: list[Any],
) -> ClientRestrictionProfileResponse:
    entries = [client_restriction_profile_entry(row) for row in rows]
    supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "CLIENT_RESTRICTION_PROFILE_READY"
    missing_data_families: list[str] = []
    if not rows:
        supportability_state = "INCOMPLETE"
        supportability_reason = "CLIENT_RESTRICTION_PROFILE_EMPTY"
        missing_data_families.append("client_restrictions")

    return ClientRestrictionProfileResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        restrictions=entries,
        supportability=ClientRestrictionProfileSupportability(
            state=supportability_state,
            reason=supportability_reason,
            restriction_count=len(entries),
            missing_data_families=missing_data_families,
        ),
        lineage={
            "source_system": "lotus-core-query-service",
            "source_table": "client_restriction_profiles,portfolio_mandate_bindings",
            "contract_version": "rfc_040_client_restriction_profile_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=("ACCEPTED" if rows else "MISSING"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([binding], rows),
            source_batch_fingerprint=request_fingerprint(
                {
                    "product": "ClientRestrictionProfile",
                    "portfolio_id": portfolio_id,
                    "client_id": binding.client_id,
                    "mandate_id": binding.mandate_id,
                    "as_of_date": request.as_of_date.isoformat(),
                    "row_count": len(rows),
                }
            ),
            snapshot_id=(
                "client_restriction_profile:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                )
            ),
        ),
    )
