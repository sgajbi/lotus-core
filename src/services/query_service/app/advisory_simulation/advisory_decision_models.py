"""Compatibility models for downstream-owned suitability and workflow decisions.

These models remain in Core only to preserve the existing advisory simulation contract while
decision ownership migrates to lotus-advise. Generic Core simulation must not depend on this module.
"""

from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SuitabilityThresholds(BaseModel):
    single_position_max_weight: Decimal = Field(
        default=Decimal("0.10"),
        ge=0,
        le=1,
        description="Maximum advisory suitability weight per single instrument.",
        examples=["0.10"],
    )
    issuer_max_weight: Decimal = Field(
        default=Decimal("0.20"),
        ge=0,
        le=1,
        description="Maximum advisory suitability aggregate weight per issuer.",
        examples=["0.20"],
    )
    max_weight_by_liquidity_tier: Dict[str, Decimal] = Field(
        default_factory=lambda: {"L4": Decimal("0.10"), "L5": Decimal("0.05")},
        description=(
            "Maximum advisory suitability aggregate weight by liquidity tier, "
            "for example {'L4': '0.10', 'L5': '0.05'}."
        ),
        examples=[{"L4": "0.10", "L5": "0.05"}],
    )
    cash_band_min_weight: Decimal = Field(
        default=Decimal("0.01"),
        ge=0,
        le=1,
        description="Minimum advisory suitability cash weight.",
        examples=["0.01"],
    )
    cash_band_max_weight: Decimal = Field(
        default=Decimal("0.05"),
        ge=0,
        le=1,
        description="Maximum advisory suitability cash weight.",
        examples=["0.05"],
    )
    data_quality_issue_severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        default="MEDIUM",
        description="Severity used for suitability data-quality issues.",
        examples=["MEDIUM"],
    )

    @field_validator("max_weight_by_liquidity_tier")
    @classmethod
    def validate_max_weight_by_liquidity_tier(cls, v: Dict[str, Decimal]) -> Dict[str, Decimal]:
        for tier, value in v.items():
            if tier not in {"L1", "L2", "L3", "L4", "L5"}:
                raise ValueError("liquidity tier keys must be one of L1, L2, L3, L4, L5")
            if value < Decimal("0") or value > Decimal("1"):
                raise ValueError("liquidity-tier max weights must be between 0 and 1 inclusive")
        return v

    @model_validator(mode="after")
    def validate_cash_band(self) -> "SuitabilityThresholds":
        if self.cash_band_min_weight > self.cash_band_max_weight:
            raise ValueError("suitability cash band min cannot exceed max")
        return self


class SuitabilityEvidenceSnapshotIds(BaseModel):
    portfolio_snapshot_id: str = Field(
        description="Portfolio snapshot id used as evidence source.",
        examples=["pf_advisory_01"],
    )
    market_data_snapshot_id: str = Field(
        description="Market-data snapshot id used as evidence source.",
        examples=["md_2026_02_19"],
    )


class SuitabilityEvidence(BaseModel):
    as_of: str = Field(
        description="Suitability evidence as-of identifier derived from request snapshots.",
        examples=["md_2026_02_19"],
    )
    snapshot_ids: SuitabilityEvidenceSnapshotIds = Field(
        description="Snapshot identifiers used by suitability checks."
    )


class SuitabilityIssue(BaseModel):
    issue_id: str = Field(
        description="Stable suitability issue identifier.",
        examples=["SUIT_SINGLE_POSITION_MAX"],
    )
    issue_key: str = Field(
        description="Deterministic issue key used for before/after classification.",
        examples=["SINGLE_POSITION_MAX|US_EQ_ETF"],
    )
    dimension: Literal[
        "CONCENTRATION",
        "ISSUER",
        "LIQUIDITY",
        "GOVERNANCE",
        "CASH",
        "DATA_QUALITY",
    ] = Field(
        description="Suitability issue dimension.",
        examples=["CONCENTRATION"],
    )
    severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        description="Advisory suitability severity level.",
        examples=["HIGH"],
    )
    status_change: Literal["NEW", "RESOLVED", "PERSISTENT"] = Field(
        description="Before/after suitability state transition class.",
        examples=["NEW"],
    )
    summary: str = Field(
        description="Short suitability issue narrative.",
        examples=["Single position exceeds 10% cap."],
    )
    details: Dict[str, str] = Field(
        default_factory=dict,
        description="Deterministic suitability measurement details encoded as strings.",
        examples=[
            {
                "threshold": "0.10",
                "measured_before": "0.12",
                "measured_after": "0.09",
                "instrument_id": "US_EQ_ETF",
            }
        ],
    )
    evidence: SuitabilityEvidence = Field(description="Evidence lineage for this issue.")


class SuitabilitySummary(BaseModel):
    new_count: int = Field(description="Count of NEW suitability issues.", examples=[1])
    resolved_count: int = Field(description="Count of RESOLVED suitability issues.", examples=[2])
    persistent_count: int = Field(
        description="Count of PERSISTENT suitability issues.",
        examples=[3],
    )
    highest_severity_new: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = Field(
        default=None,
        description="Highest severity among NEW issues, when present.",
        examples=["HIGH"],
    )


class SuitabilityResult(BaseModel):
    summary: SuitabilitySummary = Field(description="Suitability issue summary counts.")
    issues: List[SuitabilityIssue] = Field(
        default_factory=list,
        description="Deterministic ordered suitability issue list.",
    )
    recommended_gate: Literal["NONE", "RISK_REVIEW", "COMPLIANCE_REVIEW"] = Field(
        description="Advisory gate recommendation derived from NEW issue severities.",
        examples=["COMPLIANCE_REVIEW"],
    )


class GateReason(BaseModel):
    reason_code: str = Field(
        description="Stable workflow reason code.",
        examples=["HARD_RULE_FAIL:INSUFFICIENT_CASH"],
    )
    severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        description="Reason severity level used for deterministic ordering.",
        examples=["HIGH"],
    )
    source: Literal["RULE_ENGINE", "SUITABILITY", "DATA_QUALITY"] = Field(
        description="Reason source subsystem.",
        examples=["RULE_ENGINE"],
    )
    details: Dict[str, str] = Field(
        default_factory=dict,
        description="Deterministic structured details for the reason.",
    )


class GateDecisionSummary(BaseModel):
    hard_fail_count: int = Field(description="Count of hard rule failures.", examples=[1])
    soft_fail_count: int = Field(description="Count of soft rule failures.", examples=[0])
    new_high_suitability_count: int = Field(
        description="Count of NEW suitability issues with HIGH severity.",
        examples=[0],
    )
    new_medium_suitability_count: int = Field(
        description="Count of NEW suitability issues with MEDIUM severity.",
        examples=[0],
    )


class GateDecision(BaseModel):
    gate: Literal[
        "BLOCKED",
        "RISK_REVIEW_REQUIRED",
        "COMPLIANCE_REVIEW_REQUIRED",
        "CLIENT_CONSENT_REQUIRED",
        "EXECUTION_READY",
        "NONE",
    ] = Field(
        description="Deterministic workflow gate outcome.",
        examples=["CLIENT_CONSENT_REQUIRED"],
    )
    recommended_next_step: Literal[
        "FIX_INPUT",
        "RISK_REVIEW",
        "COMPLIANCE_REVIEW",
        "REQUEST_CLIENT_CONSENT",
        "EXECUTE",
        "NONE",
    ] = Field(
        description="Recommended next workflow step based on gate policy.",
        examples=["REQUEST_CLIENT_CONSENT"],
    )
    reasons: List[GateReason] = Field(
        default_factory=list,
        description="Deterministic ordered reasons explaining the gate.",
    )
    summary: GateDecisionSummary = Field(description="Gate summary counters.")


__all__ = [
    "GateDecision",
    "GateDecisionSummary",
    "GateReason",
    "SuitabilityEvidence",
    "SuitabilityEvidenceSnapshotIds",
    "SuitabilityIssue",
    "SuitabilityResult",
    "SuitabilitySummary",
    "SuitabilityThresholds",
]
