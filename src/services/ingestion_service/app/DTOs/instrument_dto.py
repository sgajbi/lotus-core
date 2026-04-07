# services/ingestion_service/app/DTOs/instrument_dto.py
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Instrument(BaseModel):
    security_id: str = Field(
        ...,
        description=(
            "Canonical security identifier used across portfolios, "
            "transactions, and valuation."
        ),
        examples=["SEC_BARC_PERP"],
    )
    name: str = Field(
        ...,
        description="Display name or long-form instrument description.",
        examples=["Barclays PLC 8% Perpetual"],
    )
    isin: str = Field(
        ...,
        description="International Securities Identification Number for the instrument.",
        examples=["US06738E2046"],
    )
    currency: str = Field(
        ...,
        description="Trading or settlement currency associated with the instrument.",
        examples=["USD"],
    )
    product_type: str = Field(
        ...,
        description="Canonical product type used for downstream analytics and routing.",
        examples=["bond"],
    )
    asset_class: Optional[str] = Field(
        None,
        description="High-level standardized asset-class classification.",
        examples=["fixed_income"],
    )
    portfolio_id: Optional[str] = Field(
        None,
        description="Owning portfolio identifier for portfolio-scoped synthetic instruments.",
        examples=["DEMO_DPM_EUR_001"],
    )
    trade_date: Optional[date] = Field(
        None,
        description="Trade date for portfolio-scoped contract or synthetic instruments.",
        examples=["2026-03-10"],
    )
    pair_base_currency: Optional[str] = Field(
        None,
        description="Base currency for FX contract instruments.",
        examples=["EUR"],
    )
    pair_quote_currency: Optional[str] = Field(
        None,
        description="Quote currency for FX contract instruments.",
        examples=["USD"],
    )
    buy_currency: Optional[str] = Field(
        None,
        description="Bought currency for FX contract instruments.",
        examples=["EUR"],
    )
    sell_currency: Optional[str] = Field(
        None,
        description="Sold currency for FX contract instruments.",
        examples=["USD"],
    )
    buy_amount: Optional[Decimal] = Field(
        None,
        description="Bought notional amount for FX contract instruments.",
        examples=["1000000.00"],
    )
    sell_amount: Optional[Decimal] = Field(
        None,
        description="Sold notional amount for FX contract instruments.",
        examples=["1085000.00"],
    )
    contract_rate: Optional[Decimal] = Field(
        None,
        description="Contract FX rate for synthetic FX contract instruments.",
        examples=["1.0850000000"],
    )
    sector: Optional[str] = Field(
        None,
        description="Sector or industry classification used for analytics.",
        examples=["financials"],
    )
    country_of_risk: Optional[str] = Field(
        None,
        description="Primary country-of-risk classification for the instrument.",
        examples=["GB"],
    )
    rating: Optional[str] = Field(
        None,
        description="Credit rating for fixed-income instruments.",
        examples=["BB+"],
    )
    liquidity_tier: Optional[str] = Field(
        None,
        description="Liquidity tier used by advisory suitability and risk workflows.",
        examples=["L1", "L3"],
    )
    maturity_date: Optional[date] = Field(
        None,
        description="Maturity date for instruments with contractual maturity.",
        examples=["2035-12-31"],
    )
    issuer_id: Optional[str] = Field(
        None,
        description="Canonical identifier for the direct issuer of the security.",
        examples=["ISSUER_BARC"],
    )
    issuer_name: Optional[str] = Field(
        None,
        description="Display name for the direct issuer of the security.",
        examples=["Barclays PLC"],
    )
    ultimate_parent_issuer_id: Optional[str] = Field(
        None,
        description="Canonical identifier for the ultimate parent of the issuer.",
        examples=["ULTIMATE_BARC"],
    )
    ultimate_parent_issuer_name: Optional[str] = Field(
        None,
        description="Display name for the ultimate parent issuer.",
        examples=["Barclays Group Holdings PLC"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "security_id": "SEC_BARC_PERP",
                "name": "Barclays PLC 8% Perpetual",
                "isin": "US06738E2046",
                "currency": "USD",
                "product_type": "Bond",
                "asset_class": "Fixed Income",
                "portfolio_id": None,
                "trade_date": None,
                "pair_base_currency": None,
                "pair_quote_currency": None,
                "buy_currency": None,
                "sell_currency": None,
                "buy_amount": None,
                "sell_amount": None,
                "contract_rate": None,
                "sector": "Financials",
                "country_of_risk": "GB",
                "rating": "BB+",
                "liquidity_tier": "L2",
                "maturity_date": None,
                "issuer_id": "ISSUER_BARC",
                "issuer_name": "Barclays PLC",
                "ultimate_parent_issuer_id": "ULTIMATE_BARC",
                "ultimate_parent_issuer_name": "Barclays Group Holdings PLC",
            }
        }
    )


class InstrumentIngestionRequest(BaseModel):
    instruments: List[Instrument] = Field(
        ...,
        description="Instrument master records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "security_id": "SEC_BARC_PERP",
                    "name": "Barclays PLC 8% Perpetual",
                    "isin": "US06738E2046",
                    "currency": "USD",
                    "product_type": "bond",
                    "asset_class": "fixed_income",
                    "sector": "financials",
                    "country_of_risk": "GB",
                    "rating": "BB+",
                    "liquidity_tier": "L2",
                    "issuer_id": "ISSUER_BARC",
                    "issuer_name": "Barclays PLC",
                    "ultimate_parent_issuer_id": "ULTIMATE_BARC",
                    "ultimate_parent_issuer_name": "Barclays Group Holdings PLC",
                }
            ]
        ],
    )

