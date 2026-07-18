"""Application policy for effective portfolio party-role assignments."""

from datetime import datetime
from typing import cast

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

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
    fingerprint = request_fingerprint(
        {
            "product_name": "PortfolioPartyRoleAssignment",
            "portfolio_id": portfolio_id,
            "request": request.model_dump(mode="json"),
            "source_versions": [
                [record.source_system, record.source_record_id, record.assignment_version]
                for record in records
            ],
        }
    )
    return PortfolioPartyRoleAssignmentResponse(
        portfolio_id=portfolio_id,
        assignments=assignments,
        supportability=PortfolioPartyRoleAssignmentSupportability(
            state="READY" if assignments else "INCOMPLETE",
            reason=(
                "PARTY_ROLE_ASSIGNMENTS_READY"
                if assignments
                else "PARTY_ROLE_ASSIGNMENTS_EMPTY"
            ),
            returned_assignment_count=len(assignments),
            filters_applied=filters,
        ),
        lineage={
            "source_system": "lotus-core",
            "source_table": "portfolio_party_role_assignments",
            "contract_version": "portfolio_party_role_assignment_v1",
            "legacy_advisor_inference": "disabled",
        },
        **cast(
            dict[str, object],
            source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status="ACCEPTED" if assignments else "MISSING",
                latest_evidence_timestamp=_latest_evidence_timestamp(records),
                snapshot_id=f"portfolio_party_roles:{fingerprint}",
            ),
        ),
    )


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
