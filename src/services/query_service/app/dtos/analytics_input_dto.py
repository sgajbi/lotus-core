from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalyticsWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Inclusive start date for the requested analytics window.",
        examples=["2025-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Inclusive end date for the requested analytics window.",
        examples=["2025-12-31"],
    )

    @model_validator(mode="after")
    def validate_date_order(self) -> "AnalyticsWindow":
        if self.start_date > self.end_date:
            raise ValueError("window.start_date must be before or equal to window.end_date.")
        return self

    model_config = ConfigDict()


class PageRequest(BaseModel):
    page_size: int = Field(
        500,
        ge=1,
        le=5000,
        description="Maximum number of records per response page.",
        examples=[500],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous response page.",
        examples=["eyJwIjp7InZhbHVhdGlvbl9kYXRlIjoiMjAyNS0wMS0zMSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class LineageMetadata(BaseModel):
    generated_by: str = Field(
        ...,
        description="Service component that generated this response.",
        examples=["integration.analytics_inputs"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when the response payload was generated.",
        examples=["2026-03-01T12:00:00Z"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint used for replay and diagnostics.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    data_version: str = Field(
        ...,
        description="Canonical dataset version label for traceability and replay.",
        examples=["state_inputs_v1"],
    )

    model_config = ConfigDict()


class PageMetadata(BaseModel):
    page_size: int = Field(
        ...,
        description="Maximum number of rows requested for this response page.",
        examples=[500],
    )
    returned_row_count: int = Field(
        ...,
        description="Number of rows actually returned in this response page.",
        examples=[248],
    )
    sort_key: str = Field(
        ...,
        description="Stable ordering applied to rows for deterministic paging.",
        examples=["valuation_date:asc,security_id:asc"],
    )
    request_scope_fingerprint: str = Field(
        ...,
        description="Deterministic scope fingerprint used to validate continuation tokens.",
        examples=["4fcad301df7d144f1d3d0570fb0d3e4a"],
    )
    snapshot_epoch: int = Field(
        ...,
        description=(
            "Snapshot epoch pinned for the paged traversal to keep pages internally "
            "consistent."
        ),
        examples=[7],
    )
    next_page_token: str | None = Field(
        None,
        description=(
            "Opaque continuation token for the next page, null when no additional pages remain."
        ),
        examples=["eyJwIjp7InZhbHVhdGlvbl9kYXRlIjoiMjAyNS0wMi0yOCJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class QualityDiagnostics(BaseModel):
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of quality states observed in the dataset.",
        examples=[{"final": 245, "provisional": 3}],
    )
    missing_dates_count: int = Field(
        0,
        description="Count of missing expected valuation dates in the resolved window.",
        examples=[0],
    )
    stale_points_count: int = Field(
        0,
        description="Count of stale points detected based on staleness policy.",
        examples=[1],
    )
    requested_dimensions: list[str] = Field(
        default_factory=list,
        description="Requested row-level dimensions projected into the returned dataset.",
        examples=[["asset_class", "sector"]],
    )
    cash_flows_included: bool = Field(
        False,
        description=(
            "Whether the response rows include canonical per-position cash_flow "
            "observations."
        ),
        examples=[True],
    )

    model_config = ConfigDict()


class PortfolioQualityDiagnostics(BaseModel):
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of valuation quality states observed in the returned page.",
        examples=[{"final": 245, "restated": 3}],
    )
    missing_dates_count: int = Field(
        0,
        description=(
            "Count of expected business-calendar dates in the resolved window that do not "
            "have a portfolio observation in the pinned snapshot epoch."
        ),
        examples=[0],
    )
    stale_points_count: int = Field(
        0,
        description="Count of returned observations whose valuation state is not final.",
        examples=[1],
    )
    expected_business_dates_count: int = Field(
        0,
        description="Number of expected business-calendar dates in the resolved window.",
        examples=[22],
    )
    returned_observation_dates_count: int = Field(
        0,
        description="Number of portfolio valuation dates present in the pinned snapshot epoch.",
        examples=[22],
    )
    cash_flows_included: bool = Field(
        True,
        description="Whether canonical portfolio cash_flows are present on returned observations.",
        examples=[True],
    )

    model_config = ConfigDict()


class CashFlowObservation(BaseModel):
    amount: Decimal = Field(
        ...,
        description="Cash flow amount in the same currency context as the parent observation.",
        examples=["-1500.2500000000"],
    )
    timing: Literal["bod", "eod"] = Field(
        ...,
        description="Cash flow timing relative to valuation boundaries.",
        examples=["eod"],
    )
    cash_flow_type: Literal["external_flow", "fee", "tax", "transfer", "income", "other"] = Field(
        ...,
        description="Canonical cash flow type for performance analytics treatment.",
        examples=["external_flow"],
    )

    model_config = ConfigDict()


class PortfolioAnalyticsTimeseriesRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time cutoff used to resolve permissible observations.",
        examples=["2025-12-31"],
    )
    window: AnalyticsWindow | None = Field(
        None,
        description="Explicit date window for the returned series.",
    )
    period: (
        Literal[
            "one_month", "three_months", "ytd", "one_year", "three_years", "five_years", "inception"
        ]
        | None
    ) = Field(
        None,
        description="Relative period selector used when explicit window is not provided.",
        examples=["one_year"],
    )
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency override; defaults to portfolio base currency.",
        examples=["USD"],
    )
    frequency: Literal["daily"] = Field(
        "daily",
        description="Observation frequency for analytics timeseries.",
        examples=["daily"],
    )
    consumer_system: str = Field(
        "lotus-performance",
        description="Consumer system identifier for lineage and policy controls.",
        examples=["lotus-performance"],
    )
    page: PageRequest = Field(
        default_factory=PageRequest,
        description="Paging controls for high-volume dataset traversal.",
    )

    @model_validator(mode="after")
    def validate_window_or_period(self) -> "PortfolioAnalyticsTimeseriesRequest":
        if self.window is None and self.period is None:
            raise ValueError("Exactly one of window or period must be provided.")
        if self.window is not None and self.period is not None:
            raise ValueError("Exactly one of window or period must be provided.")
        return self

    model_config = ConfigDict()


class PortfolioTimeseriesObservation(BaseModel):
    valuation_date: date = Field(
        ...,
        description="Business date of the valuation observation.",
        examples=["2025-01-31"],
    )
    beginning_market_value: Decimal = Field(
        ...,
        description="Beginning market value in reporting_currency for the valuation_date.",
        examples=["1025000.1200000000"],
    )
    ending_market_value: Decimal = Field(
        ...,
        description="Ending market value in reporting_currency for the valuation_date.",
        examples=["1032000.5600000000"],
    )
    valuation_status: Literal["final", "provisional", "restated"] = Field(
        "final",
        description="Valuation state used by downstream analytics controls.",
        examples=["final"],
    )
    cash_flows: list[CashFlowObservation] = Field(
        default_factory=list,
        description="Canonical cash flow events for the valuation_date.",
    )
    cash_flow_currency: str = Field(
        ...,
        description=(
            "Currency code applied to the observation cash_flows amounts; matches the "
            "effective reporting_currency."
        ),
        examples=["USD"],
    )

    model_config = ConfigDict()


class PortfolioAnalyticsTimeseriesResponse(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["EUR"])
    reporting_currency: str = Field(
        ..., description="Effective reporting currency for returned values.", examples=["USD"]
    )
    portfolio_open_date: date = Field(
        ..., description="Portfolio inception date.", examples=["2020-01-01"]
    )
    portfolio_close_date: date | None = Field(
        None, description="Portfolio close date when closed.", examples=["2026-12-31"]
    )
    performance_end_date: date | None = Field(
        None,
        description="Latest available valuation date in the canonical store for this portfolio.",
        examples=["2025-12-31"],
    )
    resolved_window: AnalyticsWindow = Field(
        ..., description="Resolved request window used for data extraction."
    )
    frequency: Literal["daily"] = Field(
        ..., description="Observation frequency.", examples=["daily"]
    )
    contract_version: str = Field(
        "rfc_063_v1", description="Contract version for this endpoint.", examples=["rfc_063_v1"]
    )
    calendar_id: str = Field(
        "business_date_calendar",
        description="Calendar identifier for resolved observations.",
        examples=["business_date_calendar"],
    )
    missing_observation_policy: Literal["strict", "forward_fill", "skip"] = Field(
        "strict",
        description="Policy describing missing-observation handling semantics.",
        examples=["strict"],
    )
    lineage: LineageMetadata = Field(..., description="Lineage metadata for reproducibility.")
    diagnostics: PortfolioQualityDiagnostics = Field(
        ..., description="Quality and completeness diagnostics."
    )
    page: PageMetadata = Field(..., description="Paging metadata for incremental retrieval.")
    observations: list[PortfolioTimeseriesObservation] = Field(
        default_factory=list,
        description="Ordered portfolio valuation observations.",
    )

    model_config = ConfigDict()


class PositionDimensionFilter(BaseModel):
    dimension: Literal["asset_class", "sector", "country"] = Field(
        ...,
        description="Dimension field used for filter evaluation.",
        examples=["sector"],
    )
    values: list[str] = Field(
        ...,
        min_length=1,
        description="Allowed canonical values for the selected dimension.",
        examples=[["Technology", "Financials"]],
    )

    model_config = ConfigDict()


class PositionAnalyticsFilters(BaseModel):
    security_ids: list[str] = Field(
        default_factory=list,
        description="Optional security_id inclusion filter.",
        examples=[["SEC_AAPL_US"]],
    )
    position_ids: list[str] = Field(
        default_factory=list,
        description="Optional position_id inclusion filter.",
        examples=[["DEMO_DPM_EUR_001:SEC_AAPL_US"]],
    )
    dimension_filters: list[PositionDimensionFilter] = Field(
        default_factory=list,
        description="Optional dimension-based inclusion filters.",
    )

    model_config = ConfigDict()


class PositionAnalyticsTimeseriesRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time cutoff used to resolve permissible observations.",
        examples=["2025-12-31"],
    )
    window: AnalyticsWindow | None = Field(
        None, description="Explicit date window for series extraction."
    )
    period: (
        Literal[
            "one_month", "three_months", "ytd", "one_year", "three_years", "five_years", "inception"
        ]
        | None
    ) = Field(
        None,
        description="Relative period selector when explicit window is not supplied.",
        examples=["three_months"],
    )
    reporting_currency: str | None = Field(
        None, description="Optional reporting currency override.", examples=["USD"]
    )
    frequency: Literal["daily"] = Field(
        "daily", description="Observation frequency for returned rows.", examples=["daily"]
    )
    dimensions: list[Literal["asset_class", "sector", "country"]] = Field(
        default_factory=list,
        description="Dimension labels to project in each position row.",
        examples=[["asset_class", "sector"]],
    )
    include_cash_flows: bool = Field(
        True,
        description=(
            "Whether to include canonical per-position cash_flows in each row. "
            "Defaults to true because acquisition-day and flow-aware analytics are "
            "unsafe without it."
        ),
        examples=[True],
    )
    consumer_system: str = Field(
        "lotus-performance",
        description="Consumer system identifier for lineage and policy controls.",
        examples=["lotus-performance"],
    )
    filters: PositionAnalyticsFilters = Field(
        default_factory=PositionAnalyticsFilters, description="Optional inclusion filters."
    )
    page: PageRequest = Field(
        default_factory=PageRequest, description="Paging controls for high-volume retrieval."
    )

    @model_validator(mode="after")
    def validate_window_or_period(self) -> "PositionAnalyticsTimeseriesRequest":
        if self.window is None and self.period is None:
            raise ValueError("Exactly one of window or period must be provided.")
        if self.window is not None and self.period is not None:
            raise ValueError("Exactly one of window or period must be provided.")
        return self

    model_config = ConfigDict()


class PositionTimeseriesRow(BaseModel):
    position_id: str = Field(
        ..., description="Canonical position identifier.", examples=["DEMO_DPM_EUR_001:SEC_AAPL_US"]
    )
    security_id: str = Field(
        ..., description="Canonical security identifier.", examples=["SEC_AAPL_US"]
    )
    valuation_date: date = Field(
        ..., description="Business date for row valuation.", examples=["2025-01-31"]
    )
    position_currency: str | None = Field(
        None,
        description="Native/local currency code of the position when available.",
        examples=["EUR"],
    )
    cash_flow_currency: str | None = Field(
        None,
        description=(
            "Currency code applied to the row cash_flows amounts; normally matches "
            "position_currency."
        ),
        examples=["EUR"],
    )
    dimensions: dict[str, str | None] = Field(
        default_factory=dict,
        description="Selected dimension values for the row.",
        examples=[{"asset_class": "Equity", "sector": "Technology"}],
    )
    position_to_portfolio_fx_rate: Decimal = Field(
        ...,
        description=(
            "FX rate used to convert position-currency values into portfolio_currency "
            "for this row. Equals 1 when the position currency already matches the "
            "portfolio currency."
        ),
        examples=["1.0850000000"],
    )
    portfolio_to_reporting_fx_rate: Decimal = Field(
        ...,
        description=(
            "FX rate used to convert portfolio-currency values into reporting_currency "
            "for this row. Equals 1 when reporting_currency matches portfolio_currency."
        ),
        examples=["1.0000000000"],
    )
    beginning_market_value_position_currency: Decimal = Field(
        ..., description="Beginning value in position currency.", examples=["125000.1200000000"]
    )
    ending_market_value_position_currency: Decimal = Field(
        ..., description="Ending value in position currency.", examples=["126200.5600000000"]
    )
    beginning_market_value_portfolio_currency: Decimal = Field(
        ..., description="Beginning value in portfolio currency.", examples=["102500.1200000000"]
    )
    ending_market_value_portfolio_currency: Decimal = Field(
        ..., description="Ending value in portfolio currency.", examples=["103200.5600000000"]
    )
    beginning_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Beginning value converted to the effective reporting_currency.",
        examples=["111500.4500000000"],
    )
    ending_market_value_reporting_currency: Decimal = Field(
        ...,
        description="Ending value converted to the effective reporting_currency.",
        examples=["112350.9800000000"],
    )
    valuation_status: Literal["final", "provisional", "restated"] = Field(
        "final",
        description="Valuation state used by downstream analytics controls.",
        examples=["final"],
    )
    quantity: Decimal = Field(
        ..., description="Position quantity for the valuation_date.", examples=["150.0000000000"]
    )
    cash_flows: list[CashFlowObservation] = Field(
        default_factory=list, description="Optional canonical cash flow events for the row."
    )

    model_config = ConfigDict()


class PositionAnalyticsTimeseriesResponse(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["EUR"])
    reporting_currency: str = Field(
        ..., description="Effective reporting currency for converted values.", examples=["USD"]
    )
    resolved_window: AnalyticsWindow = Field(
        ..., description="Resolved request window used for extraction."
    )
    frequency: Literal["daily"] = Field(
        ..., description="Observation frequency.", examples=["daily"]
    )
    contract_version: str = Field(
        "rfc_063_v1", description="Contract version for this endpoint.", examples=["rfc_063_v1"]
    )
    calendar_id: str = Field(
        "business_date_calendar",
        description="Calendar identifier used for date resolution.",
        examples=["business_date_calendar"],
    )
    missing_observation_policy: Literal["strict", "forward_fill", "skip"] = Field(
        "strict",
        description="Policy describing missing-observation handling semantics.",
        examples=["strict"],
    )
    lineage: LineageMetadata = Field(..., description="Lineage metadata for reproducibility.")
    diagnostics: QualityDiagnostics = Field(
        ..., description="Quality and completeness diagnostics."
    )
    page: PageMetadata = Field(..., description="Paging metadata for incremental retrieval.")
    rows: list[PositionTimeseriesRow] = Field(
        default_factory=list, description="Ordered position valuation rows."
    )

    model_config = ConfigDict()


class PortfolioAnalyticsReferenceRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Point-in-time anchor used for contract reproducibility and to bound returned "
            "performance horizon metadata."
        ),
        examples=["2025-12-31"],
    )
    consumer_system: str = Field(
        "lotus-performance",
        description="Consumer system identifier for lineage and governance context.",
        examples=["lotus-performance"],
    )

    model_config = ConfigDict()


class PortfolioAnalyticsReferenceResponse(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    resolved_as_of_date: date = Field(
        ...,
        description="Effective as-of anchor applied to this reference contract.",
        examples=["2025-12-31"],
    )
    portfolio_currency: str = Field(..., description="Portfolio base currency.", examples=["EUR"])
    portfolio_open_date: date = Field(
        ...,
        description=(
            "Current canonical portfolio inception date from the active portfolio record."
        ),
        examples=["2020-01-01"],
    )
    portfolio_close_date: date | None = Field(
        None,
        description="Current canonical portfolio close date when the portfolio is closed.",
        examples=["2026-12-31"],
    )
    performance_end_date: date | None = Field(
        None,
        description=(
            "Latest available portfolio valuation date, bounded by resolved_as_of_date."
        ),
        examples=["2025-12-31"],
    )
    client_id: str = Field(
        ...,
        description="Current canonical client identifier associated with the portfolio.",
        examples=["CIF_100234"],
    )
    booking_center_code: str = Field(
        ...,
        description="Current canonical booking center code for the portfolio.",
        examples=["SGPB"],
    )
    portfolio_type: str = Field(
        ...,
        description="Current canonical portfolio type descriptor.",
        examples=["discretionary"],
    )
    objective: str | None = Field(
        None,
        description="Current canonical portfolio objective text, when defined.",
        examples=["Balanced growth"],
    )
    reference_state_policy: Literal["current_portfolio_reference_state"] = Field(
        "current_portfolio_reference_state",
        description=(
            "Explains that portfolio reference fields reflect the current canonical portfolio "
            "record, not historical effective-dated snapshots."
        ),
        examples=["current_portfolio_reference_state"],
    )
    lineage: LineageMetadata = Field(..., description="Lineage metadata for reproducibility.")
    contract_version: str = Field(
        "rfc_063_v1", description="Contract version for this endpoint.", examples=["rfc_063_v1"]
    )
    supported_grouping_dimensions: list[str] = Field(
        default_factory=lambda: ["asset_class", "sector", "country"],
        description="Canonical grouping dimensions supported by analytics input contracts.",
    )

    model_config = ConfigDict()


class AnalyticsExportCreateRequest(BaseModel):
    dataset_type: Literal["portfolio_timeseries", "position_timeseries"] = Field(
        ...,
        description="Dataset contract to export.",
        examples=["portfolio_timeseries"],
    )
    portfolio_id: str = Field(
        ...,
        description="Canonical portfolio identifier to export.",
        examples=["DEMO_DPM_EUR_001"],
    )
    portfolio_timeseries_request: PortfolioAnalyticsTimeseriesRequest | None = Field(
        None,
        description="Portfolio timeseries request when dataset_type is portfolio_timeseries.",
    )
    position_timeseries_request: PositionAnalyticsTimeseriesRequest | None = Field(
        None,
        description="Position timeseries request when dataset_type is position_timeseries.",
    )
    result_format: Literal["json", "ndjson"] = Field(
        "json",
        description="Preferred result serialization format.",
        examples=["ndjson"],
    )
    compression: Literal["none", "gzip"] = Field(
        "none",
        description="Preferred result compression mode.",
        examples=["gzip"],
    )
    consumer_system: str = Field(
        "lotus-performance",
        description="Consumer system identifier for governance and lineage.",
        examples=["lotus-performance"],
    )

    @model_validator(mode="after")
    def validate_dataset_request_binding(self) -> "AnalyticsExportCreateRequest":
        if self.dataset_type == "portfolio_timeseries":
            if self.portfolio_timeseries_request is None:
                raise ValueError(
                    "portfolio_timeseries_request must be provided when "
                    "dataset_type=portfolio_timeseries."
                )
            if self.position_timeseries_request is not None:
                raise ValueError(
                    "position_timeseries_request must be null when "
                    "dataset_type=portfolio_timeseries."
                )
        if self.dataset_type == "position_timeseries":
            if self.position_timeseries_request is None:
                raise ValueError(
                    "position_timeseries_request must be provided when "
                    "dataset_type=position_timeseries."
                )
            if self.portfolio_timeseries_request is not None:
                raise ValueError(
                    "portfolio_timeseries_request must be null when "
                    "dataset_type=position_timeseries."
                )
        return self

    model_config = ConfigDict()


class AnalyticsExportJobResponse(BaseModel):
    job_id: str = Field(
        ...,
        description="Stable analytics export job identifier.",
        examples=["aexp_7e8ad3e7bc6f4d3b97de66f1"],
    )
    dataset_type: Literal["portfolio_timeseries", "position_timeseries"] = Field(
        ...,
        description="Dataset contract selected for this export job.",
        examples=["position_timeseries"],
    )
    portfolio_id: str = Field(
        ...,
        description="Canonical portfolio identifier for this export job.",
        examples=["DEMO_DPM_EUR_001"],
    )
    status: Literal["accepted", "running", "completed", "failed"] = Field(
        ...,
        description="Current export job lifecycle status.",
        examples=["completed"],
    )
    disposition: Literal["created", "reused_completed", "reused_inflight", "status_lookup"] = Field(
        ...,
        description=(
            "How this response was produced: a newly created job, a reused completed job, "
            "a reused in-flight job, or a direct status lookup."
        ),
        examples=["created"],
    )
    lifecycle_mode: Literal["inline_job_execution"] = Field(
        "inline_job_execution",
        description=(
            "Current execution model for analytics export jobs. "
            "The service executes export processing inline within the create request path."
        ),
        examples=["inline_job_execution"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint for the request payload.",
        examples=["4bb3f6477f1ed3e3f8a04c471e7f6516"],
    )
    result_available: bool = Field(
        ...,
        description="True when a finalized result payload is available for retrieval.",
        examples=[True],
    )
    result_endpoint: str = Field(
        ...,
        description="Deterministic result retrieval path for this export job.",
        examples=["/integration/exports/analytics-timeseries/jobs/aexp_7e8ad3e7bc6f4d3b97de66f1/result"],
    )
    result_format: Literal["json", "ndjson"] = Field(
        ...,
        description="Serialized format for result retrieval.",
        examples=["ndjson"],
    )
    compression: Literal["none", "gzip"] = Field(
        ...,
        description="Compression mode for result retrieval.",
        examples=["gzip"],
    )
    result_row_count: int | None = Field(
        None,
        description="Count of rows exported when status is completed.",
        examples=[3650],
    )
    error_message: str | None = Field(
        None,
        description="Failure reason when status is failed.",
        examples=["Missing FX rate for EUR/USD on 2025-01-31."],
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the export job was created.",
        examples=["2026-03-01T21:30:00Z"],
    )
    started_at: datetime | None = Field(
        None,
        description="UTC timestamp when processing started.",
        examples=["2026-03-01T21:30:01Z"],
    )
    completed_at: datetime | None = Field(
        None,
        description="UTC timestamp when processing completed or failed.",
        examples=["2026-03-01T21:30:03Z"],
    )

    model_config = ConfigDict()


class AnalyticsExportJsonResultResponse(BaseModel):
    job_id: str = Field(
        ...,
        description="Export job identifier.",
        examples=["aexp_7e8ad3e7bc6f4d3b97de66f1"],
    )
    dataset_type: Literal["portfolio_timeseries", "position_timeseries"] = Field(
        ...,
        description="Dataset type included in this result payload.",
        examples=["portfolio_timeseries"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint for the request that produced this result.",
        examples=["4bb3f6477f1ed3e3f8a04c471e7f6516"],
    )
    lifecycle_mode: Literal["inline_job_execution"] = Field(
        "inline_job_execution",
        description="Execution model that produced this export result payload.",
        examples=["inline_job_execution"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when this result was generated.",
        examples=["2026-03-01T21:30:03Z"],
    )
    contract_version: str = Field(
        ...,
        description="Contract version label included in payload lineage.",
        examples=["rfc_063_v1"],
    )
    result_row_count: int = Field(
        ...,
        description="Row count included in this export result payload.",
        examples=[3650],
    )
    data: list[dict[str, object]] = Field(
        default_factory=list,
        description="Serialized observations or rows from the selected dataset.",
        examples=[
            [
                {
                    "valuation_date": "2025-01-31",
                    "beginning_market_value": "1025000.1200000000",
                    "ending_market_value": "1032000.5600000000",
                    "valuation_status": "final",
                    "cash_flows": [],
                }
            ]
        ],
    )

    model_config = ConfigDict()
