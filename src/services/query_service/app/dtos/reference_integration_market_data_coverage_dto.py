from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class MarketDataCurrencyPair(BaseModel):
    from_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Source currency for an FX conversion pair.",
        examples=["USD"],
    )
    to_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Target currency for an FX conversion pair.",
        examples=["SGD"],
    )

    @model_validator(mode="after")
    def normalize_pair(self) -> "MarketDataCurrencyPair":
        self.from_currency = self.from_currency.strip().upper()
        self.to_currency = self.to_currency.strip().upper()
        if len(self.from_currency) != 3 or len(self.to_currency) != 3:
            raise ValueError("currency pair members must be ISO currency codes")
        if self.from_currency == self.to_currency:
            raise ValueError("currency pair members must be different")
        return self

    model_config = ConfigDict()


def _normalize_market_data_instrument_ids(instrument_ids: list[str]) -> list[str]:
    normalized_instruments = [instrument_id.strip() for instrument_id in instrument_ids]
    if any(not instrument_id for instrument_id in normalized_instruments):
        raise ValueError("instrument_ids must contain non-empty identifiers")
    if len(normalized_instruments) != len(set(normalized_instruments)):
        raise ValueError("instrument_ids must not contain duplicates")
    return normalized_instruments


def _validate_currency_pairs(currency_pairs: list[MarketDataCurrencyPair]) -> None:
    normalized_pairs = [(pair.from_currency, pair.to_currency) for pair in currency_pairs]
    if len(normalized_pairs) != len(set(normalized_pairs)):
        raise ValueError("currency_pairs must not contain duplicates")


class MarketDataCoverageRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve latest available price and FX observations.",
        examples=["2026-04-10"],
    )
    instrument_ids: list[str] = Field(
        default_factory=list,
        description="Held and target instrument identifiers requiring latest price coverage.",
        examples=[["EQ_US_AAPL", "FI_US_TREASURY_10Y"]],
    )
    currency_pairs: list[MarketDataCurrencyPair] = Field(
        default_factory=list,
        description="FX conversion pairs required for valuation and rebalance sizing.",
        examples=[[{"from_currency": "USD", "to_currency": "SGD"}]],
    )
    valuation_currency: str | None = Field(
        None,
        min_length=3,
        max_length=3,
        description="Optional target valuation currency used for supportability lineage.",
        examples=["SGD"],
    )
    max_staleness_days: int = Field(
        5,
        ge=0,
        le=31,
        description=(
            "Maximum acceptable age in calendar days before an observation is marked stale."
        ),
        examples=[5],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_request(self) -> "MarketDataCoverageRequest":
        self.instrument_ids = _normalize_market_data_instrument_ids(self.instrument_ids)
        _validate_currency_pairs(self.currency_pairs)
        if self.valuation_currency is not None:
            self.valuation_currency = self.valuation_currency.strip().upper()
        return self

    model_config = ConfigDict()


class MarketDataPriceCoverageRecord(BaseModel):
    instrument_id: str = Field(
        ..., description="Requested instrument identifier.", examples=["EQ_US_AAPL"]
    )
    found: bool = Field(
        ..., description="Whether core found a price observation on or before as_of_date."
    )
    price_date: date | None = Field(
        None, description="Resolved price observation date.", examples=["2026-04-10"]
    )
    price: Decimal | None = Field(
        None, description="Resolved price value when available.", examples=["187.1200000000"]
    )
    currency: str | None = Field(
        None, description="Price currency when available.", examples=["USD"]
    )
    age_days: int | None = Field(
        None, description="Calendar age of the resolved price observation.", examples=[0]
    )
    quality_status: Literal["READY", "STALE", "MISSING"] = Field(
        ..., description="Price coverage status for this instrument.", examples=["READY"]
    )

    model_config = ConfigDict()


class MarketDataFxCoverageRecord(BaseModel):
    from_currency: str = Field(..., description="Source currency.", examples=["USD"])
    to_currency: str = Field(..., description="Target currency.", examples=["SGD"])
    found: bool = Field(
        ..., description="Whether core found an FX observation on or before as_of_date."
    )
    rate_date: date | None = Field(
        None, description="Resolved FX observation date.", examples=["2026-04-10"]
    )
    rate: Decimal | None = Field(
        None, description="Resolved FX conversion rate.", examples=["1.3521000000"]
    )
    age_days: int | None = Field(
        None, description="Calendar age of the resolved FX observation.", examples=[0]
    )
    quality_status: Literal["READY", "STALE", "MISSING"] = Field(
        ..., description="FX coverage status for this pair.", examples=["READY"]
    )

    model_config = ConfigDict()


class MarketDataCoverageSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using market data in DPM.", examples=["READY"]
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for market-data readiness.",
        examples=["MARKET_DATA_READY"],
    )
    requested_price_count: int = Field(
        ..., description="Number of requested instrument price observations.", examples=[2]
    )
    resolved_price_count: int = Field(
        ..., description="Number of requested instruments with a resolved price.", examples=[2]
    )
    requested_fx_count: int = Field(
        ..., description="Number of requested FX conversion pairs.", examples=[1]
    )
    resolved_fx_count: int = Field(
        ..., description="Number of requested FX pairs with a resolved rate.", examples=[1]
    )
    missing_instrument_ids: list[str] = Field(
        default_factory=list,
        description="Requested instruments without a price observation.",
        examples=[["UNKNOWN_SEC"]],
    )
    stale_instrument_ids: list[str] = Field(
        default_factory=list,
        description="Requested instruments whose latest price is older than max_staleness_days.",
        examples=[["EQ_US_AAPL"]],
    )
    missing_currency_pairs: list[str] = Field(
        default_factory=list,
        description="Requested FX pairs without a rate observation.",
        examples=[["USD/SGD"]],
    )
    stale_currency_pairs: list[str] = Field(
        default_factory=list,
        description="Requested FX pairs whose latest rate is older than max_staleness_days.",
        examples=[["USD/SGD"]],
    )

    model_config = ConfigDict()


class MarketDataCoverageWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["MarketDataCoverageWindow"] = product_name_field(
        "MarketDataCoverageWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ..., description="As-of date used for market-data resolution.", examples=["2026-04-10"]
    )
    valuation_currency: str | None = Field(
        None, description="Requested valuation currency context.", examples=["SGD"]
    )
    price_coverage: list[MarketDataPriceCoverageRecord] = Field(
        default_factory=list,
        description="Coverage records for requested instrument prices.",
    )
    fx_coverage: list[MarketDataFxCoverageRecord] = Field(
        default_factory=list,
        description="Coverage records for requested FX pairs.",
    )
    supportability: MarketDataCoverageSupportability = Field(
        ..., description="Batch-level DPM market-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
        examples=[
            {
                "source_system": "market_prices+fx_rates",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()
