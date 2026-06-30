from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reference_integration_dto import ReferencePageMetadata
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


def _normalize_tax_lot_security_ids(security_ids: list[str] | None) -> list[str] | None:
    if security_ids is None:
        return None
    normalized = [security_id.strip() for security_id in security_ids]
    if any(not security_id for security_id in normalized):
        raise ValueError("security_ids must contain non-empty identifiers")
    if len(normalized) != len(set(normalized)):
        raise ValueError("security_ids must not contain duplicates")
    return normalized


class PortfolioTaxLotPageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum tax-lot records to return for this page.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous portfolio tax-lot page.",
        examples=["eyJwIjp7Imxhc3RfbG90X2lkIjoiTE9ULTAwMSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve current tax-lot state.",
        examples=["2026-04-10"],
    )
    security_ids: list[str] | None = Field(
        None,
        description=(
            "Optional security filter. Omit to return tax lots for all securities in the portfolio "
            "window."
        ),
        examples=[["EQ_US_AAPL", "FI_US_TREASURY_10Y"]],
    )
    lot_status_filter: Literal["OPEN", "CLOSED"] | None = Field(
        None,
        description=(
            "Optional explicit lot status filter. When omitted, open lots are returned by default."
        ),
        examples=["OPEN"],
    )
    include_closed_lots: bool = Field(
        False,
        description="Whether to include closed lots when lot_status_filter is not explicitly set.",
        examples=[False],
    )
    page: PortfolioTaxLotPageRequest = Field(
        default_factory=PortfolioTaxLotPageRequest,
        description="Cursor pagination request for large tax-lot windows.",
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_security_filter(self) -> "PortfolioTaxLotWindowRequest":
        self.security_ids = _normalize_tax_lot_security_ids(self.security_ids)
        return self

    model_config = ConfigDict()


class PortfolioTaxLotRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    security_id: str = Field(
        ..., description="Canonical security identifier.", examples=["EQ_US_AAPL"]
    )
    instrument_id: str = Field(
        ..., description="Canonical instrument identifier.", examples=["EQ_US_AAPL"]
    )
    lot_id: str = Field(
        ..., description="Stable tax-lot identifier.", examples=["LOT-TXN-BUY-AAPL-001"]
    )
    open_quantity: Decimal = Field(
        ..., description="Current open lot quantity.", examples=["100.0000000000"]
    )
    original_quantity: Decimal = Field(
        ..., description="Original acquired lot quantity.", examples=["100.0000000000"]
    )
    acquisition_date: date = Field(
        ..., description="Lot acquisition date.", examples=["2026-03-25"]
    )
    cost_basis_base: Decimal = Field(
        ...,
        description="Current lot cost basis in portfolio base currency.",
        examples=["15005.5000000000"],
    )
    cost_basis_local: Decimal = Field(
        ...,
        description="Current lot cost basis in local trade currency.",
        examples=["15005.5000000000"],
    )
    local_currency: str | None = Field(
        None, description="Local trade currency for this lot.", examples=["USD"]
    )
    tax_lot_status: Literal["OPEN", "CLOSED"] = Field(
        ..., description="Current tax-lot status.", examples=["OPEN"]
    )
    source_transaction_id: str = Field(
        ...,
        description="Source BUY or transfer transaction identifier.",
        examples=["TXN-BUY-AAPL-001"],
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lot-level lineage tying the row to source transaction and calculation policy.",
        examples=[
            {
                "source_system": "front_office_portfolio_seed",
                "calculation_policy_id": "BUY_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
            }
        ],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using tax lots in DPM.", examples=["READY"]
    )
    reason: str = Field(
        ..., description="Bounded reason code for tax-lot readiness.", examples=["TAX_LOTS_READY"]
    )
    requested_security_count: int | None = Field(
        None,
        description=(
            "Number of securities explicitly requested, null when the full portfolio was requested."
        ),
        examples=[2],
    )
    returned_lot_count: int = Field(
        ..., description="Number of tax lots returned in this page.", examples=[25]
    )
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Requested securities with no lots in the resolved page scope.",
        examples=[["UNKNOWN_SEC"]],
    )
    missing_instrument_security_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Returned lot security identifiers that do not resolve to governed instrument master "
            "rows."
        ),
        examples=[["ORPHAN_SEC"]],
    )
    missing_instrument_reference_count: int = Field(
        0,
        description=(
            "Number of returned lot security identifiers without instrument master support."
        ),
        examples=[0],
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="Bounded supportability reason codes for the tax-lot window.",
        examples=[["TAX_LOTS_READY"]],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioTaxLotWindow"] = product_name_field("PortfolioTaxLotWindow")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    as_of_date: date = Field(
        ..., description="As-of date used for lot resolution.", examples=["2026-04-10"]
    )
    lots: list[PortfolioTaxLotRecord] = Field(
        default_factory=list,
        description="Paged portfolio-window tax lots ordered by acquisition date and lot id.",
    )
    page: ReferencePageMetadata = Field(
        ..., description="Cursor pagination metadata for this tax-lot page."
    )
    supportability: PortfolioTaxLotWindowSupportability = Field(
        ..., description="Batch-level DPM tax-lot source-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
        examples=[{"source_system": "position_lot_state", "contract_version": "rfc_087_v1"}],
    )

    model_config = ConfigDict()
