from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reference_integration_dto import (
    IntegrationWindow,
    ReferencePageMetadata,
    ReferencePageRequest,
    SeriesRequest,
)
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)

SUPPORTED_BENCHMARK_MARKET_SERIES_FIELDS = frozenset(
    {
        "index_price",
        "index_return",
        "benchmark_return",
        "component_weight",
        "fx_rate",
    }
)


def _normalize_series_fields(series_fields: list[str]) -> list[str]:
    requested_fields = [field.strip() for field in series_fields if field and field.strip()]
    if not requested_fields:
        raise ValueError("series_fields must contain at least one supported value.")
    invalid = sorted(
        {
            field
            for field in requested_fields
            if field not in SUPPORTED_BENCHMARK_MARKET_SERIES_FIELDS
        }
    )
    if invalid:
        raise ValueError("Unsupported series_fields requested: " + ", ".join(invalid))
    return requested_fields


def _validate_fx_field_scope(
    *,
    requested_fields: list[str],
    target_currency: str | None,
) -> None:
    if "fx_rate" in requested_fields and not target_currency:
        raise ValueError("target_currency is required when series_fields includes fx_rate.")


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
        requested_fields = _normalize_series_fields(self.series_fields)
        _validate_fx_field_scope(
            requested_fields=requested_fields,
            target_currency=self.target_currency,
        )
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
