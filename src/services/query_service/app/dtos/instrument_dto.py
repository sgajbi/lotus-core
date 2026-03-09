from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InstrumentRecord(BaseModel):
    """
    Represents a single, detailed instrument record for API responses.
    """

    security_id: str
    name: str
    isin: str
    currency: str
    product_type: str
    asset_class: Optional[str] = None
    portfolio_id: Optional[str] = None
    trade_date: Optional[date] = None
    pair_base_currency: Optional[str] = None
    pair_quote_currency: Optional[str] = None
    buy_currency: Optional[str] = None
    sell_currency: Optional[str] = None
    buy_amount: Optional[Decimal] = None
    sell_amount: Optional[Decimal] = None
    contract_rate: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedInstrumentResponse(BaseModel):
    """
    Represents the paginated API response for an instrument query.
    """

    total: int = Field(..., description="The total number of instruments matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    instruments: List[InstrumentRecord] = Field(
        ..., description="The list of instrument records for the current page."
    )
