"""Application policy for effective portfolio party-role assignments."""

from datetime import datetime
from typing import Literal, cast

from portfolio_common.domain.portfolio_party_roles import PortfolioPartyRoleQualityStatus
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.portfolio_party_roles import (
    PortfolioPartyRoleAssignmentItem,
    PortfolioPartyRoleAssignmentRequest,
    PortfolioPartyRoleAssignmentResponse,
    PortfolioPartyRoleAssignmentSupportability,
)
from ..domain.portfolio_party_roles import PortfolioPartyRoleRecord
from ..ports.portfolio_party_roles import PortfolioPartyRoleReader


class PortfolioPartyRoleAssignmentService:
    def __init__(self, *, reader: PortfolioPartyRoleReader, clock: Clock) -> None:
        self._reader = reader
        self._clock = clock

    async def resolve(
        self,
        *,
        portfolio_id: str,
        request: PortfolioPartyRoleAssignmentRequest,
    ) -> PortfolioPartyRoleAssignmentResponse:
        records = await self._reader.list_effective_assignments(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            party_id=request.party_id,
            role_types=tuple(request.role_types),
            role_scopes=tuple(request.role_scopes),
            include_non_accepted=request.include_non_accepted,
        )
        return _response(
            portfolio_id=portfolio_id,
            request=request,
            records=records,
            generated_at=self._clock.utc_now(),
        )


def _response(
    *,
    portfolio_id: str,
    request: PortfolioPartyRoleAssignmentRequest,
    records: list[PortfolioPartyRoleRecord],
    generated_at: datetime,
) -> PortfolioPartyRoleAssignmentResponse:
    assignments = [_item(record) for record in records]
    filters = ["portfolio_id", "as_of_date", "latest_source_version"]
    if request.party_id:
        filters.append("party_id")
    if request.role_types:
        filters.append("role_types")
    if request.role_scopes:
        filters.append("role_scopes")
    if not request.include_non_accepted:
        filters.append("accepted_quality_status")
    data_quality_status = _data_quality_status(records)
    assignments_ready = data_quality_status == "COMPLETE"
    supportability_reason: Literal[
        "PARTY_ROLE_ASSIGNMENTS_READY",
        "PARTY_ROLE_ASSIGNMENTS_EMPTY",
        "PARTY_ROLE_ASSIGNMENTS_NON_ACCEPTED",
    ]
    if assignments_ready:
        supportability_reason = "PARTY_ROLE_ASSIGNMENTS_READY"
    elif assignments:
        supportability_reason = "PARTY_ROLE_ASSIGNMENTS_NON_ACCEPTED"
    else:
        supportability_reason = "PARTY_ROLE_ASSIGNMENTS_EMPTY"
    supportability = PortfolioPartyRoleAssignmentSupportability(
        state="READY" if assignments_ready else "INCOMPLETE",
        reason=supportability_reason,
        returned_assignment_count=len(assignments),
        filters_applied=filters,
    )
    lineage = {
        "source_system": "lotus-core",
        "source_table": "portfolio_party_role_assignments",
        "contract_version": "portfolio_party_role_assignment_v1",
        "legacy_advisor_inference": "disabled",
    }
    latest_evidence_timestamp = _latest_evidence_timestamp(records)
    content_hash = stable_content_hash(
        {
            "product_name": "PortfolioPartyRoleAssignment",
            "product_version": "v1",
            "portfolio_id": portfolio_id,
            "request": request.model_dump(mode="json"),
            "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
            "data_quality_status": data_quality_status,
            "latest_evidence_timestamp": latest_evidence_timestamp,
            "supportability": supportability.model_dump(mode="json"),
            "lineage": lineage,
        }
    )
    return PortfolioPartyRoleAssignmentResponse(
        portfolio_id=portfolio_id,
        assignments=assignments,
        supportability=supportability,
        lineage=lineage,
        **cast(
            dict[str, object],
            source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status=data_quality_status,
                latest_evidence_timestamp=latest_evidence_timestamp,
                snapshot_id=(f"portfolio_party_roles:{content_hash.removeprefix('sha256:')[:24]}"),
                content_hash=content_hash,
                use_content_hash_as_source_batch_fingerprint=True,
            ),
        ),
    )


def _data_quality_status(records: list[PortfolioPartyRoleRecord]) -> str:
    if not records:
        return "MISSING"
    if all(record.quality_status is PortfolioPartyRoleQualityStatus.ACCEPTED for record in records):
        return "COMPLETE"
    return "PARTIAL"


def _item(record: PortfolioPartyRoleRecord) -> PortfolioPartyRoleAssignmentItem:
    return PortfolioPartyRoleAssignmentItem(
        party_id=record.party_id,
        role_type=record.role_type,
        role_scope=record.role_scope,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        assignment_version=record.assignment_version,
        source_system=record.source_system,
        source_record_id=record.source_record_id,
        observed_at=record.observed_at,
        quality_status=record.quality_status,
    )


def _latest_evidence_timestamp(records: list[PortfolioPartyRoleRecord]) -> datetime | None:
    return max(
        (
            timestamp
            for record in records
            for timestamp in (record.observed_at, record.updated_at, record.created_at)
            if timestamp is not None
        ),
        default=None,
    )
