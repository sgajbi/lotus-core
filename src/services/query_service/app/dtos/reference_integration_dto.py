from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class IntegrationWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Window start date for series retrieval (inclusive).",
        examples=["2026-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Window end date for series retrieval (inclusive).",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class IntegrationPolicyContext(BaseModel):
    tenant_id: str | None = Field(
        None,
        description="Tenant identifier for policy-scoped data resolution.",
        examples=["tenant_sg_pb"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier used for deterministic assignment resolution.",
        examples=["policy_pack_wm_v1"],
    )

    model_config = ConfigDict()


class BenchmarkAssignmentRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the active benchmark assignment.",
        examples=["2026-01-31"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional downstream context currency for caller symmetry and lineage. "
            "This field does not change benchmark assignment selection in the current "
            "implementation."
        ),
        examples=["USD"],
    )
    policy_context: IntegrationPolicyContext | None = Field(
        None,
        description=(
            "Optional tenant/policy context reserved for governance metadata and future "
            "policy-bound resolution. The current implementation still resolves the "
            "effective assignment by portfolio_id and as_of_date."
        ),
    )

    model_config = ConfigDict()


class BenchmarkAssignmentResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["BenchmarkAssignment"] = product_name_field("BenchmarkAssignment")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ...,
        description="Canonical portfolio identifier.",
        examples=["DEMO_DPM_EUR_001"],
    )
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve the assignment.",
        examples=["2026-01-31"],
    )
    effective_from: date = Field(
        ...,
        description="Assignment effective start date.",
        examples=["2025-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established the assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(
        ...,
        description="Assignment lifecycle status.",
        examples=["active"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier associated with the assignment record.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system identifier.",
        examples=["lotus-manage"],
    )
    assignment_recorded_at: datetime = Field(
        ...,
        description="Timestamp when assignment record was captured in lotus-core.",
        examples=["2026-01-31T09:15:00Z"],
    )
    assignment_version: int = Field(
        ...,
        description="Monotonic assignment version for effective-date ties.",
        examples=[3],
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Query contract version for benchmark assignment integration.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the approved model target version.",
        examples=["2026-03-25"],
    )
    include_inactive_targets: bool = Field(
        False,
        description=(
            "Include inactive target rows when true. Default false returns only active "
            "target rows suitable for DPM execution."
        ),
        examples=[False],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    model_config = ConfigDict()


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
        description="Optional booking-center selector when downstream context already knows it.",
        examples=["Singapore"],
    )
    include_policy_pack: bool = Field(
        True,
        description="Return policy_pack_id when true. Default true is required by lotus-manage.",
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
        description="Authority status used by lotus-manage to allow, degrade, or block DPM.",
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
        description="Policy pack identifier used for downstream DPM constraints.",
        examples=["POLICY_DPM_SG_BALANCED_V1"],
    )
    risk_profile: str = Field(..., description="Mandate risk profile.", examples=["balanced"])
    investment_horizon: str = Field(
        ..., description="Mandate investment horizon classification.", examples=["long_term"]
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


class ModelPortfolioTargetRow(BaseModel):
    instrument_id: str = Field(
        ...,
        description="Canonical instrument identifier in the model target universe.",
        examples=["EQ_US_AAPL"],
    )
    target_weight: Decimal = Field(
        ...,
        description="Target instrument weight as a decimal ratio between 0 and 1.",
        examples=["0.1200000000"],
    )
    min_weight: Decimal | None = Field(
        None,
        description="Optional minimum target band as a decimal ratio.",
        examples=["0.0800000000"],
    )
    max_weight: Decimal | None = Field(
        None,
        description="Optional maximum target band as a decimal ratio.",
        examples=["0.1600000000"],
    )
    target_status: str = Field(
        ...,
        description="Target lifecycle status from the model source system.",
        examples=["active"],
    )
    quality_status: str = Field(
        ...,
        description="Data quality status for this target row.",
        examples=["accepted"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603_eq_us_aapl"],
    )

    model_config = ConfigDict()


class ModelPortfolioSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for the resolved model target product.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining model target readiness.",
        examples=["MODEL_TARGETS_READY"],
    )
    target_count: int = Field(
        ...,
        description="Number of target rows returned after request filtering.",
        examples=[7],
    )
    total_target_weight: Decimal = Field(
        ...,
        description="Sum of returned target weights as a decimal ratio.",
        examples=["1.0000000000"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmModelPortfolioTarget"] = product_name_field("DpmModelPortfolioTarget")
    product_version: Literal["v1"] = product_version_field()
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version resolved for the as-of date.",
        examples=["2026.03"],
    )
    display_name: str = Field(
        ...,
        description="Business display name for the model portfolio.",
        examples=["Singapore Balanced DPM Model"],
    )
    base_currency: str = Field(..., description="Model base currency.", examples=["SGD"])
    risk_profile: str = Field(
        ...,
        description="Mandate risk profile aligned to this model.",
        examples=["balanced"],
    )
    mandate_type: str = Field(
        ...,
        description="Mandate type for which this model is approved.",
        examples=["discretionary"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Expected rebalance cadence.",
        examples=["monthly"],
    )
    approval_status: str = Field(
        ...,
        description="Approval lifecycle status for the resolved model version.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None,
        description="Timestamp when the resolved model version was approved.",
        examples=["2026-03-20T09:00:00Z"],
    )
    effective_from: date = Field(
        ...,
        description="Resolved model version effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Resolved model version effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    targets: list[ModelPortfolioTargetRow] = Field(
        ...,
        description="Deterministically ordered target rows for the resolved model version.",
    )
    supportability: ModelPortfolioSupportability = Field(
        ...,
        description="Readiness and completeness diagnostics for model target consumption.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage metadata for audit, replay, and downstream diagnostics.",
        examples=[
            {
                "source_system": "investment_office_model_system",
                "source_record_id": "model_sg_balanced_202603",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()


class BenchmarkDefinitionRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve benchmark definition version.",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class BenchmarkCompositionWindowRequest(BaseModel):
    window: IntegrationWindow = Field(
        ...,
        description="Window used to resolve overlapping benchmark composition segments.",
    )

    model_config = ConfigDict()


class BenchmarkComponentResponse(BaseModel):
    index_id: str = Field(
        ...,
        description="Canonical index identifier used as a benchmark component.",
        examples=["IDX_MSCI_WORLD_TR"],
    )
    composition_weight: Decimal = Field(
        ...,
        description="Component weight effective for the benchmark composition.",
        examples=["0.6000000000"],
    )
    composition_effective_from: date = Field(
        ...,
        description="Composition effective start date.",
        examples=["2026-01-01"],
    )
    composition_effective_to: date | None = Field(
        None,
        description="Composition effective end date.",
        examples=["2026-03-31"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier linking related composition changes.",
        examples=["rebalance_2026q1"],
    )

    model_config = ConfigDict()


class BenchmarkCompositionWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["BenchmarkConstituentWindow"] = product_name_field(
        "BenchmarkConstituentWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    benchmark_currency: str = Field(
        ...,
        description="Benchmark currency enforced across the requested composition window.",
        examples=["USD"],
    )
    resolved_window: IntegrationWindow = Field(
        ...,
        description="Resolved date window returned by the composition contract.",
    )
    segments: list[BenchmarkComponentResponse] = Field(
        default_factory=list,
        description="Ordered benchmark composition segments overlapping the requested window.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata (contract_version, source_system, generated_by).",
        examples=[
            {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            }
        ],
    )

    model_config = ConfigDict()


class BenchmarkDefinitionResponse(BaseModel):
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    benchmark_name: str = Field(
        ...,
        description="Display benchmark name.",
        examples=["Global Balanced 60/40 (TR)"],
    )
    benchmark_type: Literal["single_index", "composite"] = Field(
        ...,
        description="Benchmark composition type.",
        examples=["composite"],
    )
    benchmark_currency: str = Field(
        ...,
        description="Benchmark base/reporting currency.",
        examples=["USD"],
    )
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ...,
        description="Benchmark return convention label.",
        examples=["total_return_index"],
    )
    benchmark_status: str = Field(
        ...,
        description="Benchmark lifecycle status.",
        examples=["active"],
    )
    benchmark_family: str | None = Field(
        None,
        description="Benchmark family grouping.",
        examples=["multi_asset_strategic"],
    )
    benchmark_provider: str | None = Field(
        None,
        description="Reference data provider for benchmark definition.",
        examples=["MSCI"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Rebalance cadence for composite benchmark definitions.",
        examples=["quarterly"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier applied to this benchmark.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Canonical benchmark classification labels (asset_class, sector, region, style)."
        ),
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(
        ...,
        description="Definition effective start date.",
        examples=["2025-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Definition effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(
        ...,
        description="Data quality status for the resolved definition record.",
        examples=["accepted"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for resolved definition.",
        examples=["2026-01-31T08:00:00Z"],
    )
    source_vendor: str | None = Field(
        None,
        description="Source vendor identifier for definition lineage.",
        examples=["MSCI"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source vendor record identifier for deterministic replay.",
        examples=["bmk_60_40_v20260131"],
    )
    components: list[BenchmarkComponentResponse] = Field(
        default_factory=list,
        description="Effective benchmark component records for the requested as-of date.",
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Query contract version for benchmark definition integration.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()


class BenchmarkCatalogRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date for benchmark catalog retrieval.",
        examples=["2026-01-31"],
    )
    benchmark_type: str | None = Field(
        None,
        description="Optional benchmark type filter.",
        examples=["composite"],
    )
    benchmark_currency: str | None = Field(
        None,
        description="Optional benchmark currency filter.",
        examples=["USD"],
    )
    benchmark_status: str | None = Field(
        None,
        description="Optional benchmark status filter.",
        examples=["active"],
    )

    model_config = ConfigDict()


class BenchmarkCatalogResponse(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for catalog resolution.",
        examples=["2026-01-31"],
    )
    records: list[BenchmarkDefinitionResponse] = Field(
        default_factory=list,
        description="Benchmark definition records effective for the requested date.",
        examples=[[{"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "benchmark_type": "composite"}]],
    )

    model_config = ConfigDict()


class IndexCatalogRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date for index catalog retrieval.",
        examples=["2026-01-31"],
    )
    index_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional targeted index identifiers to resolve. Use this when the caller already "
            "knows the component universe and needs canonical metadata without scanning the full "
            "effective catalog."
        ),
        examples=[["IDX_MSCI_WORLD_TR", "IDX_BLOOMBERG_GLOBAL_AGG_TR"]],
    )
    index_currency: str | None = Field(
        None,
        description="Optional index currency filter.",
        examples=["USD"],
    )
    index_type: str | None = Field(
        None,
        description="Optional index type filter.",
        examples=["equity_index"],
    )
    index_status: str | None = Field(
        None,
        description="Optional index status filter.",
        examples=["active"],
    )

    model_config = ConfigDict()


class IndexDefinitionResponse(BaseModel):
    index_id: str = Field(
        ..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    index_name: str = Field(
        ..., description="Display index name.", examples=["MSCI World Total Return"]
    )
    index_currency: str = Field(..., description="Index currency.", examples=["USD"])
    index_type: str | None = Field(
        None,
        description="Index type descriptor.",
        examples=["equity_index"],
    )
    index_status: str = Field(..., description="Index status.", examples=["active"])
    index_provider: str | None = Field(
        None,
        description="Index data provider.",
        examples=["MSCI"],
    )
    index_market: str | None = Field(
        None,
        description="Primary market or scope for index universe.",
        examples=["global_developed"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier applied to this index.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Canonical index classification labels required for attribution and benchmark "
            "exposure grouping. Broad benchmark component indices can carry governed "
            "broad-market sector labels rather than issuer sectors."
        ),
        examples=[{"asset_class": "equity", "sector": "broad_market_equity", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Definition effective end date.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(..., description="Data quality status.", examples=["accepted"])
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp.",
        examples=["2026-01-31T08:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor name.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for replay.",
        examples=["idx_world_tr_v20260131"],
    )

    model_config = ConfigDict()


class IndexCatalogResponse(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for catalog resolution.",
        examples=["2026-01-31"],
    )
    records: list[IndexDefinitionResponse] = Field(
        default_factory=list,
        description="Index definition records effective for the requested date.",
        examples=[[{"index_id": "IDX_MSCI_WORLD_TR", "index_currency": "USD"}]],
    )

    model_config = ConfigDict()


class SeriesRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for effective definition/composition resolution.",
        examples=["2026-01-31"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Date window for series extraction.",
    )
    frequency: Literal["daily"] = Field(
        ...,
        description="Requested output frequency label. Currently only daily is supported.",
        examples=["daily"],
    )

    model_config = ConfigDict()


class ReferencePageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum number of component series records to return per page.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous benchmark market-series page.",
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class ReferencePageMetadata(BaseModel):
    page_size: int = Field(
        ...,
        description="Effective component page size used for this response.",
        examples=[250],
    )
    sort_key: str = Field(
        ...,
        description="Deterministic ordering applied to the paged component series.",
        examples=["index_id:asc"],
    )
    returned_component_count: int = Field(
        ...,
        description="Number of component series records returned in the current page.",
        examples=[250],
    )
    request_scope_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint of the request scope bound to this page sequence.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    next_page_token: str | None = Field(
        None,
        description=(
            "Opaque continuation token for the next page, null when no additional pages remain."
        ),
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class BenchmarkMarketSeriesRequest(SeriesRequest):
    target_currency: str | None = Field(
        None,
        description="Optional target currency for response context and fx enrichment.",
        examples=["USD"],
    )
    series_fields: list[str] = Field(
        ...,
        description=(
            "Requested series fields. Supported: index_price, index_return, benchmark_return, "
            "component_weight, fx_rate."
        ),
        examples=[["index_price", "index_return", "component_weight"]],
    )
    page: ReferencePageRequest = Field(
        default_factory=ReferencePageRequest,
        description=(
            "Optional deterministic paging controls for large benchmark component universes."
        ),
    )

    model_config = ConfigDict()

    @model_validator(mode="after")
    def validate_series_fields(self):
        supported_fields = {
            "index_price",
            "index_return",
            "benchmark_return",
            "component_weight",
            "fx_rate",
        }
        requested_fields = [
            field.strip() for field in self.series_fields if field and field.strip()
        ]
        if not requested_fields:
            raise ValueError("series_fields must contain at least one supported value.")
        invalid = sorted({field for field in requested_fields if field not in supported_fields})
        if invalid:
            raise ValueError("Unsupported series_fields requested: " + ", ".join(invalid))
        if "fx_rate" in requested_fields and not self.target_currency:
            raise ValueError("target_currency is required when series_fields includes fx_rate.")
        self.series_fields = requested_fields
        return self


class SeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series point date.", examples=["2026-01-02"])
    series_currency: str | None = Field(
        None,
        description="Native component series currency for the returned price or return point.",
        examples=["USD"],
    )
    index_price: Decimal | None = Field(
        None,
        description="Index price value when requested.",
        examples=["4567.1234000000"],
    )
    index_return: Decimal | None = Field(
        None,
        description="Index return value when requested.",
        examples=["0.0023000000"],
    )
    benchmark_return: Decimal | None = Field(
        None,
        description="Vendor benchmark return value when requested.",
        examples=["0.0019000000"],
    )
    component_weight: Decimal | None = Field(
        None,
        description="Effective benchmark component weight for this point.",
        examples=["0.6000000000"],
    )
    fx_rate: Decimal | None = Field(
        None,
        description=(
            "Benchmark-currency to target-currency FX context rate when target "
            "currency is requested. This is not component-to-benchmark "
            "normalization."
        ),
        examples=["1.0842000000"],
    )
    quality_status: str | None = Field(
        None,
        description="Quality status for this point.",
        examples=["accepted"],
    )

    model_config = ConfigDict()


class ComponentSeriesResponse(BaseModel):
    index_id: str = Field(
        ..., description="Component index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    points: list[SeriesPoint] = Field(
        default_factory=list,
        description="Time series points for the requested component index.",
    )

    model_config = ConfigDict()


class BenchmarkMarketSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["MarketDataWindow"] = product_name_field("MarketDataWindow")
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(..., description="As-of date used for composition resolution.")
    benchmark_currency: str = Field(
        ...,
        description="Benchmark currency resolved for the requested benchmark context.",
        examples=["USD"],
    )
    target_currency: str | None = Field(
        None,
        description="Optional target currency requested by the caller for response context.",
        examples=["EUR"],
    )
    resolved_window: IntegrationWindow = Field(
        ..., description="Resolved window returned by query service."
    )
    frequency: str = Field(
        ..., description="Frequency label returned by the contract.", examples=["daily"]
    )
    component_series: list[ComponentSeriesResponse] = Field(
        default_factory=list,
        description="Component-level benchmark market series records.",
    )
    quality_status_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Aggregate quality status counts over all returned points.",
        examples=[{"accepted": 31, "estimated": 2}],
    )
    fx_context_source_currency: str | None = Field(
        None,
        description="Source currency for the optional FX context series returned in `fx_rate`.",
        examples=["USD"],
    )
    fx_context_target_currency: str | None = Field(
        None,
        description="Target currency for the optional FX context series returned in `fx_rate`.",
        examples=["EUR"],
    )
    normalization_policy: str = Field(
        ...,
        description=(
            "Contract policy label describing how downstream consumers should "
            "interpret the series. Current policy returns native component "
            "series and requires downstream benchmark-currency normalization."
        ),
        examples=["native_component_series_downstream_normalization_required"],
    )
    normalization_status: str = Field(
        ...,
        description=(
            "Status of the optional benchmark-to-target FX context attached to this response."
        ),
        examples=["native_component_series_with_benchmark_to_target_fx_context"],
    )
    component_metadata_policy: str = Field(
        ...,
        description=(
            "Contract guidance for resolving canonical component metadata such as "
            "classification labels. Benchmark market-series returns raw component series; use "
            "`POST /integration/indices/catalog` with targeted `index_ids` when canonical "
            "component metadata is required alongside these series."
        ),
        examples=["targeted_index_catalog_lookup_required_for_component_metadata"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the benchmark market-series scope.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    page: ReferencePageMetadata = Field(
        ...,
        description="Deterministic paging metadata for benchmark component series results.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata (contract_version, source_system, generated_by).",
        examples=[
            {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            }
        ],
    )

    model_config = ConfigDict()


class IndexSeriesRequest(SeriesRequest):
    target_currency: str | None = Field(
        None,
        description="Optional target currency context for price series responses.",
        examples=["USD"],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesRequest(SeriesRequest):
    model_config = ConfigDict()


class RiskFreeSeriesRequest(SeriesRequest):
    currency: str = Field(
        ...,
        description="Series currency.",
        examples=["USD"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Risk-free series mode requested by downstream consumer.",
        examples=["annualized_rate_series"],
    )

    model_config = ConfigDict()


class IndexPriceSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: Decimal = Field(
        ..., description="Index price value.", examples=["4567.1234000000"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    value_convention: str = Field(
        ...,
        description="Value convention label for price series.",
        examples=["close_price"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class BenchmarkReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(
        ..., description="Benchmark return value.", examples=["0.0019000000"]
    )
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexPriceSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    points: list[IndexPriceSeriesPoint] = Field(
        default_factory=list, description="Index price points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class IndexReturnSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw index return series scope.",
        examples=["9ccdb0a1df40f0690241a5b52e9f1c1d"],
    )
    points: list[IndexReturnSeriesPoint] = Field(
        default_factory=list, description="Index return points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesResponse(BaseModel):
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw benchmark return series scope.",
        examples=["f4ea7426d13c0b95bbfd8d7d9dfb29af"],
    )
    points: list[BenchmarkReturnSeriesPoint] = Field(
        default_factory=list,
        description="Raw benchmark return points from upstream provider.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class RiskFreeSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free series value.", examples=["0.0350000000"])
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["annualized_rate"]
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rate interpretation.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention associated with rate series.",
        examples=["simple"],
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class RiskFreeSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["RiskFreeSeriesWindow"] = product_name_field("RiskFreeSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    currency: str = Field(..., description="Series currency code.", examples=["USD"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Series mode returned by the endpoint.",
        examples=["annualized_rate_series"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw risk-free series scope.",
        examples=["6dfc8591d95a53060efd94ddca9a266e"],
    )
    points: list[RiskFreeSeriesPoint] = Field(
        default_factory=list, description="Risk-free series points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for returned records.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class CoverageRequest(BaseModel):
    window: IntegrationWindow = Field(..., description="Coverage observation window.")

    model_config = ConfigDict()


class CoverageResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DataQualityCoverageReport"] = product_name_field(
        "DataQualityCoverageReport"
    )
    product_version: Literal["v1"] = product_version_field()
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the coverage diagnostics scope.",
        examples=["2cb014be96ad2cb65ce1833d9f2b88a2"],
    )
    observed_start_date: date | None = Field(
        None,
        description="Observed first date in data window.",
        examples=["2026-01-01"],
    )
    observed_end_date: date | None = Field(
        None,
        description="Observed last date in data window.",
        examples=["2026-01-31"],
    )
    expected_start_date: date = Field(
        ...,
        description="Expected start date from request window.",
        examples=["2026-01-01"],
    )
    expected_end_date: date = Field(
        ...,
        description="Expected end date from request window.",
        examples=["2026-01-31"],
    )
    total_points: int = Field(
        ...,
        description="Total points available in observed window.",
        examples=[31],
    )
    missing_dates_count: int = Field(
        ...,
        description="Count of missing calendar dates within expected window.",
        examples=[2],
    )
    missing_dates_sample: list[date] = Field(
        default_factory=list,
        description="Sample of missing dates in the expected window.",
        examples=[["2026-01-10", "2026-01-21"]],
    )
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Quality status distribution over observed points.",
        examples=[{"accepted": 29, "estimated": 2}],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyRequest(BaseModel):
    as_of_date: date = Field(
        ..., description="As-of date for taxonomy resolution.", examples=["2026-01-31"]
    )
    taxonomy_scope: str | None = Field(
        None,
        description=(
            "Optional taxonomy scope filter such as `index`, `instrument`, or other "
            "governed source scopes. Omitting the field returns all effective scopes."
        ),
        examples=["index"],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyEntry(BaseModel):
    classification_set_id: str = Field(
        ...,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(
        ..., description="Classification dimension name.", examples=["sector"]
    )
    dimension_value: str = Field(
        ..., description="Classification dimension value.", examples=["technology"]
    )
    dimension_description: str | None = Field(
        None,
        description="Human-readable dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None,
        description="Effective end date.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class ClassificationTaxonomyResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["InstrumentReferenceBundle"] = product_name_field(
        "InstrumentReferenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ...,
        description="As-of date used for taxonomy response.",
        examples=["2026-01-31"],
    )
    records: list[ClassificationTaxonomyEntry] = Field(
        default_factory=list,
        description="Classification taxonomy entries effective on the requested date.",
        examples=[[{"classification_set_id": "wm_global_taxonomy_v1", "dimension_name": "sector"}]],
    )
    taxonomy_version: str = Field(
        "rfc_062_v1",
        description="Taxonomy contract version exposed by query service.",
        examples=["rfc_062_v1"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the taxonomy response scope.",
        examples=["d87368035df24ff9a42cb6e586e17ac7"],
    )

    model_config = ConfigDict()
