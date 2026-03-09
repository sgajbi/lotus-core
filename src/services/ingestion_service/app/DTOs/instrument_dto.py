# services/ingestion_service/app/DTOs/instrument_dto.py
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Instrument(BaseModel):
    """
    Represents a single financial instrument.
    """

    security_id: str = Field(..., description="Unique identifier for the security.")
    name: str = Field(..., description="Full name of the instrument.")
    isin: str = Field(..., description="International Securities Identification Number.")
    currency: str = Field(..., description="The currency of the instrument.")
    product_type: str = Field(..., description="Type of product (e.g., bond, equity, fund).")
    asset_class: Optional[str] = Field(
        None, description="High-level, standardized category (e.g., 'Equity', 'Fixed Income')."
    )
    portfolio_id: Optional[str] = Field(
        None, description="Owning portfolio identifier for portfolio-scoped synthetic instruments."
    )
    trade_date: Optional[date] = Field(
        None, description="Trade date for portfolio-scoped contract instruments."
    )
    pair_base_currency: Optional[str] = Field(
        None, description="Base currency for FX contract instruments."
    )
    pair_quote_currency: Optional[str] = Field(
        None, description="Quote currency for FX contract instruments."
    )
    buy_currency: Optional[str] = Field(
        None, description="Buy currency for FX contract instruments."
    )
    sell_currency: Optional[str] = Field(
        None, description="Sell currency for FX contract instruments."
    )
    buy_amount: Optional[Decimal] = Field(
        None, description="Bought notional for FX contract instruments."
    )
    sell_amount: Optional[Decimal] = Field(
        None, description="Sold notional for FX contract instruments."
    )
    contract_rate: Optional[Decimal] = Field(
        None, description="Contract rate for FX contract instruments."
    )
    sector: Optional[str] = Field(
        None, description="Industry sector for equities (e.g., 'Technology')."
    )
    country_of_risk: Optional[str] = Field(
        None, description="The country of primary risk exposure."
    )
    rating: Optional[str] = Field(
        None, description="Credit rating for fixed income instruments (e.g., 'AAA')."
    )
    maturity_date: Optional[date] = Field(
        None, description="Maturity date for fixed income instruments."
    )
    issuer_id: Optional[str] = Field(
        None, description="Identifier for the direct issuer of the security."
    )
    issuer_name: Optional[str] = Field(
        None, description="Display name for the direct issuer of the security."
    )
    ultimate_parent_issuer_id: Optional[str] = Field(
        None, description="Identifier for the ultimate parent of the issuer."
    )
    ultimate_parent_issuer_name: Optional[str] = Field(
        None, description="Display name for the ultimate parent issuer."
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
                "maturity_date": None,
                "issuer_id": "ISSUER_BARC",
                "issuer_name": "Barclays PLC",
                "ultimate_parent_issuer_id": "ULTIMATE_BARC",
                "ultimate_parent_issuer_name": "Barclays Group Holdings PLC",
            }
        }
    )


class InstrumentIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of instruments.
    """
    instruments: List[Instrument]

