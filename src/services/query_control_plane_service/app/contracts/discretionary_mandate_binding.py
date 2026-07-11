"""Public contracts for the discretionary mandate binding source product."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class DiscretionaryMandateBindingRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the effective mandate binding.",
        examples=["2026-04-10"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier to disambiguate the portfolio binding.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center selector when request context already provides it.",
        examples=["Singapore"],
    )
    include_policy_pack: bool = Field(
        True,
        description=(
            "Return policy_pack_id when true. Default true preserves complete mandate-policy "
            "evidence in the source-data response."
        ),
        examples=[True],
    )

    model_config = ConfigDict()


class RebalanceBandContext(BaseModel):
    default_band: Decimal = Field(
        ...,
        description="Default instrument rebalance band as a decimal ratio.",
        examples=["0.0250000000"],
    )
    cash_reserve_weight: Decimal | None = Field(
        None,
        description="Optional target cash reserve weight as a decimal ratio.",
        examples=["0.0200000000"],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using this binding in stateful DPM.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining mandate binding readiness.",
        examples=["MANDATE_BINDING_READY"],
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="Missing source families that block or degrade stateful DPM source assembly.",
        examples=[[]],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DiscretionaryMandateBinding"] = product_name_field(
        "DiscretionaryMandateBinding"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    mandate_id: str = Field(
        ...,
        description="Canonical discretionary mandate identifier.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    client_id: str = Field(
        ...,
        description="Canonical client identifier bound to the mandate.",
        examples=["CIF_SG_000184"],
    )
    mandate_type: str = Field(
        ..., description="Mandate type resolved for this binding.", examples=["discretionary"]
    )
    discretionary_authority_status: str = Field(
        ...,
        description=(
            "Authority status used to determine whether discretionary portfolio management is "
            "allowed, degraded, or blocked."
        ),
        examples=["active"],
    )
    booking_center_code: str = Field(
        ..., description="Booking center governing the mandate.", examples=["Singapore"]
    )
    jurisdiction_code: str = Field(
        ..., description="Legal or regulatory jurisdiction code for the mandate.", examples=["SG"]
    )
    model_portfolio_id: str = Field(
        ...,
        description="Approved model portfolio identifier selected for this mandate.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier used for discretionary mandate constraints.",
        examples=["POLICY_DPM_SG_BALANCED_V1"],
    )
    mandate_objective: str | None = Field(
        None,
        description=(
            "Source-owned discretionary mandate objective for digital-twin and mandate-health "
            "workflows. Null means no mandate administration source value was available."
        ),
        examples=["Preserve and grow global balanced wealth within controlled drawdown limits."],
    )
    risk_profile: str = Field(..., description="Mandate risk profile.", examples=["balanced"])
    investment_horizon: str = Field(
        ..., description="Mandate investment horizon classification.", examples=["long_term"]
    )
    review_cadence: str | None = Field(
        None,
        description="Source-owned mandate review cadence used for review-cycle health evidence.",
        examples=["quarterly"],
    )
    last_review_date: date | None = Field(
        None,
        description="Most recent completed discretionary mandate review date from source data.",
        examples=["2026-03-31"],
    )
    next_review_due_date: date | None = Field(
        None,
        description="Next due discretionary mandate review date from source data.",
        examples=["2026-06-30"],
    )
    leverage_allowed: bool = Field(
        ..., description="Whether leverage is permitted by the mandate.", examples=[False]
    )
    tax_awareness_allowed: bool = Field(
        ..., description="Whether tax-aware DPM execution is allowed.", examples=[True]
    )
    settlement_awareness_required: bool = Field(
        ..., description="Whether settlement-aware DPM execution is required.", examples=[True]
    )
    rebalance_frequency: str = Field(
        ..., description="Expected rebalance cadence.", examples=["monthly"]
    )
    rebalance_bands: RebalanceBandContext = Field(
        ..., description="Mandate-level rebalance bands and cash reserve policy."
    )
    effective_from: date = Field(
        ..., description="Resolved binding effective start date.", examples=["2026-04-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Resolved binding effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    binding_version: int = Field(
        ..., description="Binding version selected for deterministic tie-breaks.", examples=[1]
    )
    supportability: DiscretionaryMandateBindingSupportability = Field(
        ..., description="Readiness and completeness diagnostics for this mandate binding."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage metadata for audit, replay, and downstream diagnostics.",
        examples=[
            {
                "source_system": "mandate_admin",
                "source_record_id": "mandate_001_v1",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()
