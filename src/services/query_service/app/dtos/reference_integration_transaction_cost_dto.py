from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reference_integration_dto import (
    IntegrationWindow,
    ReferencePageMetadata,
)
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


def _validate_transaction_cost_window(window: IntegrationWindow) -> None:
    if window.end_date < window.start_date:
        raise ValueError("window.end_date must be on or after window.start_date")


def _normalize_security_ids(security_ids: list[str] | None) -> list[str] | None:
    if security_ids is None:
        return None
    normalized = [security_id.strip() for security_id in security_ids]
    if any(not security_id for security_id in normalized):
        raise ValueError("security_ids must not contain blank identifiers")
    if len(set(normalized)) != len(normalized):
        raise ValueError("security_ids must not contain duplicates")
    return normalized


def _normalize_transaction_types(transaction_types: list[str] | None) -> list[str] | None:
    if transaction_types is None:
        return None
    normalized_types = [transaction_type.strip().upper() for transaction_type in transaction_types]
    if any(not transaction_type for transaction_type in normalized_types):
        raise ValueError("transaction_types must not contain blank values")
    if len(set(normalized_types)) != len(normalized_types):
        raise ValueError("transaction_types must not contain duplicates")
    return normalized_types


class TransactionCostCurvePageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum observed cost-curve points to return in one response.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous transaction-cost curve page.",
        examples=["eyJwIjp7Imxhc3Rfa2V5IjoiLi4uIn0sInMiOiIuLi4ifQ=="],
    )

    model_config = ConfigDict()


class TransactionCostCurveRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business as-of date used to bound observed transaction-cost evidence.",
        examples=["2026-05-03"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Inclusive transaction-date window used to derive observed cost points.",
    )
    security_ids: list[str] | None = Field(
        None,
        description="Optional security identifiers to restrict observed cost evidence.",
        examples=[["SEC-US-IBM", "SEC-US-AAPL"]],
    )
    transaction_types: list[str] | None = Field(
        None,
        description="Optional transaction types to restrict observed cost evidence.",
        examples=[["BUY", "SELL"]],
    )
    min_observation_count: int = Field(
        1,
        ge=1,
        le=100,
        description="Minimum observed transaction count required before a curve point is returned.",
        examples=[3],
    )
    page: TransactionCostCurvePageRequest = Field(
        default_factory=TransactionCostCurvePageRequest,
        description="Cursor paging request for observed transaction-cost curve points.",
    )
    tenant_id: str | None = Field(
        None,
        description=(
            "Tenant scope for future policy enforcement. Null until tenant partitioning is active."
        ),
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_filters(self) -> "TransactionCostCurveRequest":
        _validate_transaction_cost_window(self.window)
        self.security_ids = _normalize_security_ids(self.security_ids)
        self.transaction_types = _normalize_transaction_types(self.transaction_types)
        return self

    model_config = ConfigDict()


class TransactionCostCurvePoint(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the observed curve point.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    security_id: str = Field(
        ...,
        description="Security identifier represented by this point.",
        examples=["SEC-US-AAPL"],
    )
    transaction_type: str = Field(..., description="Observed transaction type.", examples=["BUY"])
    currency: str = Field(
        ...,
        description="Currency of the observed fee and notional values.",
        examples=["USD"],
    )
    observation_count: int = Field(
        ..., description="Number of transactions represented.", examples=[12]
    )
    total_notional: Decimal = Field(
        ...,
        description="Sum of absolute gross transaction notional.",
        examples=["250000.0000000000"],
    )
    total_cost: Decimal = Field(
        ...,
        description="Sum of observed transaction fees.",
        examples=["125.0000000000"],
    )
    average_cost_bps: Decimal = Field(
        ...,
        description="Observed average cost in basis points of notional, not a predictive quote.",
        examples=["5.0000"],
    )
    min_cost_bps: Decimal = Field(
        ...,
        description="Minimum observed transaction cost in bps.",
        examples=["4.7500"],
    )
    max_cost_bps: Decimal = Field(
        ...,
        description="Maximum observed transaction cost in bps.",
        examples=["5.2500"],
    )
    first_observed_date: date = Field(
        ...,
        description="Earliest transaction date in the point.",
        examples=["2026-04-01"],
    )
    last_observed_date: date = Field(
        ...,
        description="Latest transaction date in the point.",
        examples=["2026-05-03"],
    )
    sample_transaction_ids: list[str] = Field(
        default_factory=list,
        description="Bounded deterministic sample of source transaction identifiers.",
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for the observed transaction-cost evidence.",
        examples=[
            {
                "source_system": "transactions",
                "source_table": "transactions,transaction_costs",
                "contract_version": "rfc_040_wtbd_007_v1",
            }
        ],
    )

    model_config = ConfigDict()


class TransactionCostCurveSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using observed cost evidence in DPM proof packs.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for observed transaction-cost evidence readiness.",
        examples=["TRANSACTION_COST_CURVE_READY"],
    )
    requested_security_count: int | None = Field(
        None,
        description=(
            "Number of securities explicitly requested, null when all observed securities are "
            "allowed."
        ),
    )
    returned_curve_point_count: int = Field(
        ...,
        description="Number of observed transaction-cost curve points returned.",
        examples=[8],
    )
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Requested securities with no returned qualifying cost evidence.",
    )

    model_config = ConfigDict()


class TransactionCostCurveResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["TransactionCostCurve"] = product_name_field("TransactionCostCurve")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    as_of_date: date = Field(
        ..., description="Business as-of date used for the curve.", examples=["2026-05-03"]
    )
    window: IntegrationWindow = Field(..., description="Transaction-date evidence window.")
    curve_points: list[TransactionCostCurvePoint] = Field(
        default_factory=list,
        description="Observed transaction-cost curve points derived from booked transaction fees.",
    )
    page: ReferencePageMetadata = Field(
        ..., description="Cursor pagination metadata for this cost-curve page."
    )
    supportability: TransactionCostCurveSupportability = Field(
        ..., description="Readiness posture for observed transaction-cost evidence."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Product-level source lineage for transaction-cost evidence.",
        examples=[
            {
                "source_system": "transactions",
                "contract_version": "rfc_040_wtbd_007_v1",
            }
        ],
    )

    model_config = ConfigDict()
