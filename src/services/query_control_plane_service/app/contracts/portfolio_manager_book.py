"""API contracts for portfolio-manager book membership resolution."""

from datetime import date
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class PortfolioManagerBookMembershipRequest(BaseModel):
    """Filters for resolving a portfolio manager's effective book."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active portfolio membership in the PM book.",
        examples=["2026-05-03"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center filter for regional PM-book resolution.",
        examples=["Singapore"],
    )
    portfolio_types: list[str] = Field(
        default_factory=lambda: ["DISCRETIONARY"],
        description=(
            "Portfolio type allow-list for the book membership. The default keeps the first-wave "
            "DPM cohort scoped to discretionary mandates."
        ),
        examples=[["DISCRETIONARY"]],
    )
    include_inactive: bool = Field(
        False,
        description=(
            "When false, excludes closed or non-active portfolio records as of the requested "
            "business date."
        ),
    )

    model_config = ConfigDict()


class PortfolioManagerBookMember(BaseModel):
    """A source-owned portfolio membership in a manager's book."""

    portfolio_id: str = Field(..., description="Portfolio in the source-owned PM book membership.")
    client_id: str = Field(..., description="Client identifier from the portfolio master.")
    booking_center_code: str = Field(..., description="Booking center owning the portfolio.")
    portfolio_type: str = Field(..., description="Portfolio classification from the master.")
    status: str = Field(..., description="Portfolio lifecycle status from the master.")
    open_date: date = Field(..., description="Portfolio open date.")
    close_date: date | None = Field(None, description="Portfolio close date, if any.")
    base_currency: str = Field(..., description="Portfolio base currency.")
    source_record_id: str = Field(..., description="Stable source record identifier.")

    model_config = ConfigDict()


class PortfolioManagerBookMembershipSupportability(BaseModel):
    """Operational supportability of a resolved manager book."""

    state: Literal["READY", "INCOMPLETE"] = Field(
        ..., description="Supportability state for the resolved PM-book membership."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    returned_portfolio_count: int = Field(
        ..., ge=0, description="Number of portfolio memberships returned."
    )
    filters_applied: list[str] = Field(
        default_factory=list, description="Filters applied by the source product."
    )

    model_config = ConfigDict()


class PortfolioManagerBookMembershipResponse(SourceDataProductRuntimeMetadata):
    """Effective portfolio membership and authoritative source evidence."""

    product_name: Literal["PortfolioManagerBookMembership"] = product_name_field(
        "PortfolioManagerBookMembership"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_manager_id: str = Field(
        ...,
        description=(
            "Portfolio-manager identifier backed by the portfolio master advisor_id field."
        ),
    )
    as_of_date: date = Field(..., description="Business date used to resolve membership.")
    booking_center_code: str | None = Field(
        None, description="Booking-center filter used for the response, if supplied."
    )
    members: list[PortfolioManagerBookMember] = Field(
        default_factory=list,
        description="Deterministically ordered source-owned portfolio memberships.",
    )
    supportability: PortfolioManagerBookMembershipSupportability = Field(
        ..., description="Supportability posture for automatic PM-book cohort discovery."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for the PM-book membership resolution.",
    )

    model_config = ConfigDict()
