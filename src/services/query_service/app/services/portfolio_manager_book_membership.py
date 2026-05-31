from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioManagerBookMembershipSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import portfolio_manager_book_member
from .request_fingerprint import request_fingerprint


def portfolio_manager_book_membership_portfolio_types(
    request: PortfolioManagerBookMembershipRequest,
) -> list[str]:
    return [
        portfolio_type.strip().upper()
        for portfolio_type in request.portfolio_types
        if portfolio_type.strip()
    ]


def build_portfolio_manager_book_membership_response(
    *,
    portfolio_manager_id: str,
    request: PortfolioManagerBookMembershipRequest,
    portfolio_types: list[str],
    rows: list[Any],
) -> PortfolioManagerBookMembershipResponse:
    members = [portfolio_manager_book_member(row) for row in rows]
    filters_applied = ["portfolio_manager_id", "as_of_date"]
    if request.booking_center_code:
        filters_applied.append("booking_center_code")
    if portfolio_types:
        filters_applied.append("portfolio_types")
    if not request.include_inactive:
        filters_applied.extend(["active_lifecycle_window", "active_status"])

    supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
    supportability_reason = "PM_BOOK_MEMBERSHIP_READY"
    if not members:
        supportability_state = "INCOMPLETE"
        supportability_reason = "PM_BOOK_MEMBERSHIP_EMPTY"

    snapshot_id = request_fingerprint(
        {
            "product_name": "PortfolioManagerBookMembership",
            "portfolio_manager_id": portfolio_manager_id,
            "as_of_date": request.as_of_date.isoformat(),
            "booking_center_code": request.booking_center_code,
            "portfolio_types": portfolio_types,
            "include_inactive": request.include_inactive,
            "portfolio_ids": [member.portfolio_id for member in members],
        }
    )

    return PortfolioManagerBookMembershipResponse(
        portfolio_manager_id=portfolio_manager_id,
        booking_center_code=request.booking_center_code,
        members=members,
        supportability=PortfolioManagerBookMembershipSupportability(
            state=supportability_state,
            reason=supportability_reason,
            returned_portfolio_count=len(members),
            filters_applied=filters_applied,
        ),
        lineage={
            "source_system": "lotus-core",
            "source_table": "portfolios",
            "source_field": "advisor_id",
            "contract_version": "rfc_041_pm_book_membership_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            data_quality_status="ACCEPTED" if members else "MISSING",
            latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            snapshot_id=f"pm_book_membership:{snapshot_id}",
        ),
    )
