from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reference_integration_market_data_coverage_dto import MarketDataCurrencyPair
from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)

DpmSourceFamilyState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


def _normalize_dpm_source_readiness_instrument_ids(instrument_ids: list[str]) -> list[str]:
    normalized_instruments = [instrument_id.strip() for instrument_id in instrument_ids]
    if any(not instrument_id for instrument_id in normalized_instruments):
        raise ValueError("instrument_ids must contain non-empty identifiers")
    if len(normalized_instruments) != len(set(normalized_instruments)):
        raise ValueError("instrument_ids must not contain duplicates")
    return normalized_instruments


class DpmSourceReadinessRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to evaluate DPM source-family readiness.",
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
    model_portfolio_id: str | None = Field(
        None,
        description=(
            "Optional model portfolio identifier. When omitted, readiness uses the model "
            "portfolio resolved from the mandate binding."
        ),
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    instrument_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional held or caller-known instrument identifiers. Readiness unions these with "
            "model target instruments before checking eligibility, tax lots, and market data."
        ),
        examples=[["FO_EQ_AAPL_US", "FO_BOND_UST_2030"]],
    )
    currency_pairs: list[MarketDataCurrencyPair] = Field(
        default_factory=list,
        description="FX conversion pairs required for stateful DPM source assembly.",
        examples=[[{"from_currency": "EUR", "to_currency": "USD"}]],
    )
    valuation_currency: str | None = Field(
        None,
        min_length=3,
        max_length=3,
        description="Optional target valuation currency used for market-data supportability.",
        examples=["USD"],
    )
    max_staleness_days: int = Field(
        5,
        ge=0,
        le=31,
        description="Maximum acceptable market-data age before a price or FX rate is stale.",
        examples=[5],
    )

    @model_validator(mode="after")
    def normalize_request(self) -> "DpmSourceReadinessRequest":
        self.instrument_ids = _normalize_dpm_source_readiness_instrument_ids(self.instrument_ids)
        if self.valuation_currency is not None:
            self.valuation_currency = self.valuation_currency.strip().upper()
        return self

    model_config = ConfigDict()


class DpmSourceFamilyReadiness(BaseModel):
    family: Literal["mandate", "model_targets", "eligibility", "tax_lots", "market_data"] = Field(
        ...,
        description="DPM source family represented by this readiness row.",
        examples=["market_data"],
    )
    product_name: str = Field(
        ...,
        description="Core source-data product used to evaluate this family.",
        examples=["MarketDataCoverageWindow"],
    )
    state: DpmSourceFamilyState = Field(
        ...,
        description="Readiness state for this source family.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining the source-family state.",
        examples=["MARKET_DATA_READY"],
    )
    missing_items: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded missing source items such as securities, FX pairs, or source families."
        ),
        examples=[["UNKNOWN_SEC"]],
    )
    stale_items: list[str] = Field(
        default_factory=list,
        description="Bounded stale source items such as prices or FX pairs older than policy.",
        examples=[["FO_EQ_SAP_DE"]],
    )
    evidence_count: int = Field(
        0,
        ge=0,
        description="Count of records or observations supporting this readiness row.",
        examples=[9],
    )

    model_config = ConfigDict()


class DpmSourceReadinessSupportability(BaseModel):
    state: DpmSourceFamilyState = Field(
        ...,
        description="Overall readiness state for promoting stateful DPM source assembly.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for the overall source-family readiness decision.",
        examples=["DPM_SOURCE_READINESS_READY"],
    )
    ready_family_count: int = Field(
        ..., description="Number of source families in READY state.", examples=[5]
    )
    degraded_family_count: int = Field(
        ..., description="Number of source families in DEGRADED state.", examples=[0]
    )
    incomplete_family_count: int = Field(
        ..., description="Number of source families in INCOMPLETE state.", examples=[0]
    )
    unavailable_family_count: int = Field(
        ..., description="Number of source families in UNAVAILABLE state.", examples=[0]
    )

    model_config = ConfigDict()


class DpmSourceReadinessResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmSourceReadiness"] = product_name_field("DpmSourceReadiness")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier whose DPM source readiness was evaluated.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    as_of_date: date = Field(
        ..., description="As-of date used for readiness evaluation.", examples=["2026-04-10"]
    )
    mandate_id: str | None = Field(
        None,
        description="Resolved mandate identifier when mandate binding was available.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    model_portfolio_id: str | None = Field(
        None,
        description="Resolved model portfolio identifier when model context was available.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    evaluated_instrument_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Instrument identifiers used for eligibility, tax-lot, and market-data readiness."
        ),
        examples=[["FO_EQ_AAPL_US", "FO_BOND_UST_2030"]],
    )
    families: list[DpmSourceFamilyReadiness] = Field(
        ..., description="Readiness row for each DPM source family."
    )
    supportability: DpmSourceReadinessSupportability = Field(
        ..., description="Overall source-family readiness supportability."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and downstream diagnostics.",
        examples=[{"source_system": "lotus-core", "contract_version": "rfc_087_v1"}],
    )

    model_config = ConfigDict()
