"""Application use case for resolving portfolio-manager book membership."""

from datetime import datetime
from typing import Literal, cast

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.portfolio_manager_book import (
    PortfolioManagerBookMember,
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioManagerBookMembershipSupportability,
)
from ..domain.portfolio_manager_book import PortfolioManagerBookRecord
from ..ports.portfolio_manager_book import PortfolioManagerBookReader


class PortfolioManagerBookService:
    """Resolve source-owned effective membership for a portfolio manager's book."""

    def __init__(self, *, reader: PortfolioManagerBookReader, clock: Clock) -> None:
        self._reader = reader
        self._clock = clock

    async def resolve_membership(
        self,
        *,
        portfolio_manager_id: str,
        request: PortfolioManagerBookMembershipRequest,
    ) -> PortfolioManagerBookMembershipResponse:
        portfolio_types = _normalized_portfolio_types(request.portfolio_types)
        records = await self._reader.list_members(
            portfolio_manager_id=portfolio_manager_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            portfolio_types=portfolio_types,
            include_inactive=request.include_inactive,
        )
        return _membership_response(
            portfolio_manager_id=portfolio_manager_id,
            request=request,
            portfolio_types=portfolio_types,
            records=records,
            generated_at=self._clock.utc_now(),
        )


def _normalized_portfolio_types(portfolio_types: list[str]) -> tuple[str, ...]:
    return tuple(value.strip().upper() for value in portfolio_types if value.strip())


def _membership_response(
    *,
    portfolio_manager_id: str,
    request: PortfolioManagerBookMembershipRequest,
    portfolio_types: tuple[str, ...],
    records: list[PortfolioManagerBookRecord],
    generated_at: datetime,
) -> PortfolioManagerBookMembershipResponse:
    members = [_member(record) for record in records]
    filters_applied = ["portfolio_manager_id", "as_of_date"]
    if request.booking_center_code:
        filters_applied.append("booking_center_code")
    if portfolio_types:
        filters_applied.append("portfolio_types")
    if not request.include_inactive:
        filters_applied.extend(["active_lifecycle_window", "active_status"])

    state: Literal["READY", "INCOMPLETE"] = "READY" if members else "INCOMPLETE"
    reason = "PM_BOOK_MEMBERSHIP_READY" if members else "PM_BOOK_MEMBERSHIP_EMPTY"
    fingerprint = request_fingerprint(
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
            state=state,
            reason=reason,
            returned_portfolio_count=len(members),
            filters_applied=filters_applied,
        ),
        lineage={
            "source_system": "lotus-core",
            "source_table": "portfolios",
            "source_field": "advisor_id",
            "contract_version": "rfc_041_pm_book_membership_v1",
        },
        **cast(
            dict[str, object],
            source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status="ACCEPTED" if members else "MISSING",
                latest_evidence_timestamp=_latest_evidence_timestamp(records),
                snapshot_id=f"pm_book_membership:{fingerprint}",
            ),
        ),
    )


def _member(record: PortfolioManagerBookRecord) -> PortfolioManagerBookMember:
    return PortfolioManagerBookMember(
        portfolio_id=record.portfolio_id,
        client_id=record.client_id,
        booking_center_code=record.booking_center_code,
        portfolio_type=record.portfolio_type,
        status=record.status,
        open_date=record.open_date,
        close_date=record.close_date,
        base_currency=record.base_currency,
        source_record_id=f"portfolio:{record.portfolio_id}",
    )


def _latest_evidence_timestamp(records: list[PortfolioManagerBookRecord]) -> datetime | None:
    timestamps = [
        timestamp
        for record in records
        for timestamp in (record.updated_at, record.created_at)
        if timestamp is not None
    ]
    return max(timestamps, default=None)
