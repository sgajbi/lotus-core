from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .source_data_product_identity import product_name_field, product_version_field


class CoreSnapshotMode(str, Enum):
    BASELINE = "BASELINE"
    SIMULATION = "SIMULATION"


class CoreSnapshotSection(str, Enum):
    POSITIONS_BASELINE = "positions_baseline"
    POSITIONS_PROJECTED = "positions_projected"
    POSITIONS_DELTA = "positions_delta"
    PORTFOLIO_TOTALS = "portfolio_totals"
    INSTRUMENT_ENRICHMENT = "instrument_enrichment"


class CoreSnapshotPositionBasis(str, Enum):
    MARKET_VALUE_BASE = "market_value_base"


class CoreSnapshotWeightBasis(str, Enum):
    TOTAL_MARKET_VALUE_BASE = "total_market_value_base"


class CoreSnapshotSimulationOptions(BaseModel):
    session_id: str = Field(
        ...,
        description="Simulation session identifier created by /simulation-sessions.",
        examples=["SIM_0001"],
    )
    expected_version: Optional[int] = Field(
        None,
        description="Optional optimistic lock for simulation session version.",
        examples=[3],
    )


class CoreSnapshotRequestOptions(BaseModel):
    include_zero_quantity_positions: bool = Field(
        False,
        description="Include positions with zero quantity in section responses.",
        examples=[False],
    )
    include_cash_positions: bool = Field(
        True,
        description="Include cash-class positions in section responses.",
        examples=[True],
    )
    position_basis: CoreSnapshotPositionBasis = Field(
        CoreSnapshotPositionBasis.MARKET_VALUE_BASE,
        description="Basis used for position valuation fields.",
        examples=["market_value_base"],
    )
    weight_basis: CoreSnapshotWeightBasis = Field(
        CoreSnapshotWeightBasis.TOTAL_MARKET_VALUE_BASE,
        description="Basis used to calculate weight fields.",
        examples=["total_market_value_base"],
    )


class CoreSnapshotRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve baseline positions and valuation context.",
        examples=["2026-02-27"],
    )
    snapshot_mode: CoreSnapshotMode = Field(
        CoreSnapshotMode.BASELINE,
        description="Snapshot mode: BASELINE for current state or SIMULATION for projected state.",
        examples=["SIMULATION"],
    )
    reporting_currency: Optional[str] = Field(
        None,
        description=(
            "ISO currency code for reporting conversion. Defaults to portfolio base currency."
        ),
        examples=["USD"],
    )
    consumer_system: str = Field(
        "lotus-performance",
        description="Downstream consumer system requesting the core snapshot contract.",
        examples=["lotus-performance"],
    )
    tenant_id: str = Field(
        "default",
        description="Tenant identifier used for governance and policy resolution.",
        examples=["tenant_sg_pb"],
    )
    sections: list[CoreSnapshotSection] = Field(
        ...,
        description="Requested snapshot sections to include in the response payload.",
        examples=[["positions_baseline", "positions_projected", "positions_delta"]],
    )
    simulation: Optional[CoreSnapshotSimulationOptions] = Field(
        None,
        description="Simulation options required for SIMULATION mode.",
    )
    options: CoreSnapshotRequestOptions = Field(
        default_factory=CoreSnapshotRequestOptions,
        description="Section behavior options.",
    )

    @model_validator(mode="after")
    def validate_request(self):
        if not self.sections:
            raise ValueError("sections must contain at least one value")
        if self.snapshot_mode == CoreSnapshotMode.SIMULATION and self.simulation is None:
            raise ValueError("simulation.session_id is required for SIMULATION mode")
        if self.snapshot_mode == CoreSnapshotMode.BASELINE and self.simulation is not None:
            raise ValueError("simulation block is not allowed for BASELINE mode")
        return self


class CoreSnapshotValuationContext(BaseModel):
    portfolio_currency: str = Field(
        ...,
        description="Portfolio base currency used by lotus-core for valuation storage.",
        examples=["EUR"],
    )
    reporting_currency: str = Field(
        ...,
        description="Reporting currency used in response monetary fields.",
        examples=["USD"],
    )
    position_basis: CoreSnapshotPositionBasis = Field(
        ...,
        description="Position valuation basis applied to position and delta sections.",
        examples=["market_value_base"],
    )
    weight_basis: CoreSnapshotWeightBasis = Field(
        ...,
        description="Weight calculation basis applied to baseline and projected sections.",
        examples=["total_market_value_base"],
    )


class CoreSnapshotSimulationMetadata(BaseModel):
    session_id: str = Field(
        ...,
        description="Simulation session identifier used to produce projected and delta sections.",
        examples=["SIM_0001"],
    )
    version: int = Field(
        ...,
        description="Simulation session version resolved by lotus-core for deterministic replay.",
        examples=[3],
    )
    baseline_as_of_date: date = Field(
        ...,
        description="Baseline business date used to resolve the simulation comparison state.",
        examples=["2026-02-27"],
    )


class CoreSnapshotPolicyProvenance(BaseModel):
    policy_version: str = Field(
        ...,
        description="Version label for the resolved integration policy.",
        examples=["tenant-default-v1"],
    )
    policy_source: str = Field(
        ...,
        description="Policy source level used for snapshot governance resolution.",
        examples=["tenant"],
    )
    matched_rule_id: str = Field(
        ...,
        description="Deterministic identifier of the matched governance rule.",
        examples=["tenant.tenant_sg_pb.consumers.lotus-performance"],
    )
    strict_mode: bool = Field(
        ...,
        description="Whether strict section gating was enforced.",
        examples=[True],
    )


class CoreSnapshotGovernanceMetadata(BaseModel):
    consumer_system: str = Field(
        ...,
        description="Canonical downstream consumer identity used for policy resolution.",
        examples=["lotus-performance"],
    )
    tenant_id: str = Field(
        ...,
        description="Tenant identifier used for policy resolution.",
        examples=["tenant_sg_pb"],
    )
    requested_sections: list[CoreSnapshotSection] = Field(
        ...,
        description="Original section list requested by caller before policy application.",
        examples=[["positions_baseline", "positions_projected", "positions_delta"]],
    )
    applied_sections: list[CoreSnapshotSection] = Field(
        ...,
        description="Section list applied after policy evaluation.",
        examples=[["positions_baseline", "positions_projected", "positions_delta"]],
    )
    dropped_sections: list[CoreSnapshotSection] = Field(
        default_factory=list,
        description="Requested sections removed by policy evaluation.",
        examples=[["portfolio_totals"]],
    )
    policy_provenance: CoreSnapshotPolicyProvenance = Field(
        ...,
        description="Policy lineage and strict-mode attributes used in this response.",
        examples=[
            {
                "policy_version": "tenant-default-v1",
                "policy_source": "tenant",
                "matched_rule_id": "tenant.tenant_sg_pb.consumers.lotus-performance",
                "strict_mode": True,
            }
        ],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Governance warnings emitted during policy evaluation.",
        examples=[["NO_ALLOWED_SECTION_RESTRICTION"]],
    )


class CoreSnapshotFreshnessMetadata(BaseModel):
    freshness_status: str = Field(
        ...,
        description="Freshness classification for baseline snapshot resolution.",
        examples=["CURRENT_SNAPSHOT"],
    )
    baseline_source: str = Field(
        ...,
        description="Baseline source used to assemble positions.",
        examples=["position_state"],
    )
    snapshot_timestamp: Optional[datetime] = Field(
        None,
        description="UTC timestamp of the resolved baseline snapshot when one exists.",
        examples=["2026-02-27T10:30:00Z"],
    )
    snapshot_epoch: Optional[int] = Field(
        None,
        description="Resolved baseline epoch when snapshot-backed state was used.",
        examples=[7],
    )
    fallback_reason: Optional[str] = Field(
        None,
        description="Reason historical fallback was used instead of current snapshot-backed state.",
        examples=["NO_CURRENT_POSITION_STATE_ROWS"],
    )


class CoreSnapshotPositionRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical Lotus security identifier.",
        examples=["SEC_AAPL_US"],
    )
    quantity: Decimal = Field(
        ...,
        description="Position quantity at the requested snapshot state.",
        examples=["100.0000000000"],
    )
    market_value_base: Optional[Decimal] = Field(
        None,
        description="Position market value in reporting currency.",
        examples=["19500.25"],
    )
    market_value_local: Optional[Decimal] = Field(
        None,
        description="Position market value in instrument local currency.",
        examples=["18000.00"],
    )
    weight: Optional[Decimal] = Field(
        None,
        description="Position weight versus portfolio total market value.",
        examples=["0.1245"],
    )
    currency: Optional[str] = Field(
        None,
        description="Instrument local currency for market_value_local.",
        examples=["USD"],
    )


class CoreSnapshotDeltaRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical Lotus security identifier.",
        examples=["SEC_AAPL_US"],
    )
    baseline_quantity: Decimal = Field(
        ...,
        description="Baseline quantity before applying simulation changes.",
        examples=["100.0000000000"],
    )
    projected_quantity: Decimal = Field(
        ...,
        description="Projected quantity after applying simulation changes.",
        examples=["120.0000000000"],
    )
    delta_quantity: Decimal = Field(
        ...,
        description="Projected quantity minus baseline quantity.",
        examples=["20.0000000000"],
    )
    baseline_market_value_base: Optional[Decimal] = Field(
        None,
        description="Baseline market value in reporting currency.",
        examples=["19500.25"],
    )
    projected_market_value_base: Optional[Decimal] = Field(
        None,
        description="Projected market value in reporting currency.",
        examples=["23400.30"],
    )
    delta_market_value_base: Optional[Decimal] = Field(
        None,
        description="Projected market value minus baseline market value in reporting currency.",
        examples=["3900.05"],
    )
    delta_weight: Optional[Decimal] = Field(
        None,
        description="Projected weight minus baseline weight.",
        examples=["0.0175"],
    )


class CoreSnapshotInstrumentEnrichmentRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical Lotus security identifier.",
        examples=["SEC_AAPL_US"],
    )
    isin: Optional[str] = Field(
        None,
        description="ISIN associated with the security.",
        examples=["US0378331005"],
    )
    asset_class: Optional[str] = Field(
        None,
        description="Instrument asset class used for portfolio grouping.",
        examples=["EQUITY"],
    )
    sector: Optional[str] = Field(
        None,
        description="Instrument sector classification.",
        examples=["TECHNOLOGY"],
    )
    country_of_risk: Optional[str] = Field(
        None,
        description="Primary country of risk exposure.",
        examples=["US"],
    )
    instrument_name: Optional[str] = Field(
        None,
        description="Instrument display name.",
        examples=["Apple Inc."],
    )
    issuer_id: Optional[str] = Field(
        None,
        description="Canonical direct issuer identifier.",
        examples=["ISSUER_APPLE_INC"],
    )
    issuer_name: Optional[str] = Field(
        None,
        description="Display name for direct issuer.",
        examples=["Apple Inc."],
    )
    ultimate_parent_issuer_id: Optional[str] = Field(
        None,
        description="Canonical ultimate parent issuer identifier.",
        examples=["ISSUER_APPLE_HOLDING"],
    )
    ultimate_parent_issuer_name: Optional[str] = Field(
        None,
        description="Display name for ultimate parent issuer.",
        examples=["Apple Holdings PLC"],
    )
    liquidity_tier: Optional[str] = Field(
        None,
        description="Liquidity tier used by suitability and concentration workflows.",
        examples=["L1", "L5"],
    )


class CoreSnapshotPortfolioTotals(BaseModel):
    baseline_total_market_value_base: Optional[Decimal] = Field(
        None,
        description="Portfolio baseline total market value in reporting currency.",
        examples=["156600.40"],
    )
    projected_total_market_value_base: Optional[Decimal] = Field(
        None,
        description="Portfolio projected total market value in reporting currency.",
        examples=["160500.45"],
    )
    delta_total_market_value_base: Optional[Decimal] = Field(
        None,
        description="Projected total minus baseline total in reporting currency.",
        examples=["3900.05"],
    )


class CoreSnapshotSections(BaseModel):
    positions_baseline: Optional[list[CoreSnapshotPositionRecord]] = Field(
        None,
        description="Baseline positions resolved for as_of_date.",
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "quantity": "100.0000000000",
                    "market_value_base": "19500.25",
                    "weight": "0.1245",
                }
            ]
        ],
    )
    positions_projected: Optional[list[CoreSnapshotPositionRecord]] = Field(
        None,
        description="Projected positions after applying simulation changes.",
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "quantity": "120.0000000000",
                    "market_value_base": "23400.30",
                    "weight": "0.1420",
                }
            ]
        ],
    )
    positions_delta: Optional[list[CoreSnapshotDeltaRecord]] = Field(
        None,
        description="Per-security baseline versus projected deltas.",
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "baseline_quantity": "100.0000000000",
                    "projected_quantity": "120.0000000000",
                    "delta_quantity": "20.0000000000",
                    "delta_market_value_base": "3900.05",
                }
            ]
        ],
    )
    portfolio_totals: Optional[CoreSnapshotPortfolioTotals] = Field(
        None,
        description="Portfolio-level baseline/projected totals and delta.",
        examples=[
            {
                "baseline_total_market_value_base": "156600.40",
                "projected_total_market_value_base": "160500.45",
                "delta_total_market_value_base": "3900.05",
            }
        ],
    )
    instrument_enrichment: Optional[list[CoreSnapshotInstrumentEnrichmentRecord]] = Field(
        None,
        description="Reference enrichment for securities included in snapshot sections.",
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "isin": "US0378331005",
                    "instrument_name": "Apple Inc.",
                    "issuer_name": "Apple Inc.",
                }
            ]
        ],
    )


class CoreSnapshotResponse(BaseModel):
    product_name: Literal["PortfolioStateSnapshot"] = product_name_field("PortfolioStateSnapshot")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the generated snapshot.",
        examples=["DEMO_DPM_EUR_001"],
    )
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve baseline state.",
        examples=["2026-02-27"],
    )
    snapshot_mode: CoreSnapshotMode = Field(
        ...,
        description="Snapshot mode used for this response.",
        examples=["SIMULATION"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when lotus-core generated the snapshot response.",
        examples=["2026-02-27T10:30:00Z"],
    )
    contract_version: str = Field(
        "rfc_081_v1",
        description="Contract version for the core snapshot response.",
        examples=["rfc_081_v1"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint of the full core snapshot request contract.",
        examples=["9f8a6325b52fcb11b0a5e7c44a4e8d86"],
    )
    freshness: CoreSnapshotFreshnessMetadata = Field(
        ...,
        description="Freshness and baseline lineage metadata for snapshot assembly.",
    )
    governance: CoreSnapshotGovernanceMetadata = Field(
        ...,
        description="Section governance and policy provenance metadata for this snapshot response.",
    )
    valuation_context: CoreSnapshotValuationContext = Field(
        ...,
        description="Valuation and weight basis context applied to all sections.",
        examples=[
            {
                "portfolio_currency": "EUR",
                "reporting_currency": "USD",
                "position_basis": "market_value_base",
                "weight_basis": "total_market_value_base",
            }
        ],
    )
    simulation: Optional[CoreSnapshotSimulationMetadata] = Field(
        None,
        description="Simulation metadata present only when snapshot_mode=SIMULATION.",
        examples=[{"session_id": "SIM_0001", "version": 3, "baseline_as_of_date": "2026-02-27"}],
    )
    sections: CoreSnapshotSections = Field(
        ...,
        description="Requested snapshot sections payload.",
        examples=[
            {
                "positions_baseline": [
                    {"security_id": "SEC_AAPL_US", "quantity": "100.0000000000"}
                ],
                "positions_projected": [
                    {"security_id": "SEC_AAPL_US", "quantity": "120.0000000000"}
                ],
                "positions_delta": [
                    {"security_id": "SEC_AAPL_US", "delta_quantity": "20.0000000000"}
                ],
            }
        ],
    )

    model_config = ConfigDict()
