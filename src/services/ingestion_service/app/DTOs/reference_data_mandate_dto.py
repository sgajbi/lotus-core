from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioBenchmarkAssignmentRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    effective_from: date = Field(
        ..., description="Assignment effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null for open-ended assignment.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established this benchmark assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(..., description="Assignment status.", examples=["active"])
    policy_pack_id: str | None = Field(
        None,
        description="Optional policy pack identifier.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None, description="Upstream source system.", examples=["lotus-manage"]
    )
    assignment_recorded_at: datetime | None = Field(
        None,
        description=(
            "Optional assignment capture timestamp from the source system; "
            "defaults to ingestion time when omitted."
        ),
        examples=["2026-03-10T08:15:00Z"],
    )
    assignment_version: int = Field(
        1,
        description="Assignment version used for tie-breaks at same effective_from.",
        examples=[1],
        ge=1,
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingRecord(BaseModel):
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
    mandate_type: Literal["discretionary"] = Field(
        "discretionary",
        description="Mandate type. Slice 5 supports discretionary mandate bindings only.",
        examples=["discretionary"],
    )
    discretionary_authority_status: Literal["active", "pending", "suspended", "terminated"] = Field(
        ...,
        description="Authority lifecycle status that determines DPM execution supportability.",
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
        description="Approved model portfolio identifier selected for the mandate.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier applied to DPM checks for this mandate.",
        examples=["POLICY_DPM_SG_BALANCED_V1"],
    )
    mandate_objective: str | None = Field(
        None,
        description=(
            "Source-owned discretionary mandate objective used by mandate twins and health "
            "checks. This is mandate administration truth, not a local portfolio default."
        ),
        examples=["Preserve and grow global balanced wealth within controlled drawdown limits."],
    )
    risk_profile: str = Field(..., description="Mandate risk profile.", examples=["balanced"])
    investment_horizon: str = Field(
        ..., description="Mandate investment horizon classification.", examples=["long_term"]
    )
    review_cadence: str | None = Field(
        None,
        description="Mandate review cadence from the mandate administration source.",
        examples=["quarterly"],
    )
    last_review_date: date | None = Field(
        None,
        description="Most recent completed discretionary mandate review date.",
        examples=["2026-03-31"],
    )
    next_review_due_date: date | None = Field(
        None,
        description="Next due discretionary mandate review date.",
        examples=["2026-06-30"],
    )
    leverage_allowed: bool = Field(
        False, description="Whether leverage is permitted by the mandate.", examples=[False]
    )
    tax_awareness_allowed: bool = Field(
        False, description="Whether tax-aware DPM execution is allowed.", examples=[True]
    )
    settlement_awareness_required: bool = Field(
        False,
        description="Whether DPM execution must account for settlement constraints.",
        examples=[True],
    )
    rebalance_frequency: str = Field(
        ..., description="Expected rebalance cadence.", examples=["monthly"]
    )
    rebalance_bands: dict[str, str] = Field(
        ...,
        description=(
            "Mandate-level rebalance band settings. Values are decimal strings to preserve "
            "source precision."
        ),
        examples=[{"default_band": "0.0250000000", "cash_reserve_weight": "0.0200000000"}],
    )
    effective_from: date = Field(
        ..., description="Binding effective start date.", examples=["2026-04-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Binding effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    binding_version: int = Field(
        1, description="Binding version used for deterministic effective-date tie-breaks.", ge=1
    )
    source_system: str | None = Field(
        None,
        description="Upstream mandate administration source system.",
        examples=["mandate_admin"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["mandate_001_v1"],
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the binding.",
        examples=["2026-04-01T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the mandate binding.",
        examples=["accepted"],
    )

    @model_validator(mode="after")
    def validate_effective_window(self) -> "DiscretionaryMandateBindingRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    model_config = ConfigDict()


class PortfolioBenchmarkAssignmentIngestionRequest(BaseModel):
    benchmark_assignments: list[PortfolioBenchmarkAssignmentRecord] = Field(
        ...,
        description="Portfolio benchmark assignment records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "DEMO_DPM_EUR_001",
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "effective_from": "2025-01-01",
                    "assignment_source": "benchmark_policy_engine",
                    "assignment_status": "active",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingIngestionRequest(BaseModel):
    mandate_bindings: list[DiscretionaryMandateBindingRecord] = Field(
        ...,
        description="Effective-dated discretionary mandate binding records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                    "client_id": "CIF_SG_000184",
                    "mandate_type": "discretionary",
                    "discretionary_authority_status": "active",
                    "booking_center_code": "Singapore",
                    "jurisdiction_code": "SG",
                    "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
                    "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
                    "risk_profile": "balanced",
                    "investment_horizon": "long_term",
                    "tax_awareness_allowed": True,
                    "settlement_awareness_required": True,
                    "rebalance_frequency": "monthly",
                    "rebalance_bands": {
                        "default_band": "0.0250000000",
                        "cash_reserve_weight": "0.0200000000",
                    },
                    "effective_from": "2026-04-01",
                }
            ]
        ],
    )

    @model_validator(mode="after")
    def validate_binding_uniqueness(self) -> "DiscretionaryMandateBindingIngestionRequest":
        keys = [
            (
                binding.portfolio_id,
                binding.mandate_id,
                binding.effective_from,
                binding.binding_version,
            )
            for binding in self.mandate_bindings
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("mandate_bindings contains duplicate binding records")
        return self

    model_config = ConfigDict()
