from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PortfolioRecord(BaseModel):
    """
    Represents a single, detailed portfolio record for API responses.
    """

    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    base_currency: str = Field(..., description="ISO base currency code.", examples=["USD"])
    open_date: date = Field(
        ..., description="Portfolio inception/open date.", examples=["2024-01-01"]
    )
    close_date: Optional[date] = Field(
        None,
        description="Portfolio close date, if portfolio is closed.",
        examples=["2026-12-31"],
    )
    risk_exposure: str = Field(
        ..., description="Client risk exposure classification.", examples=["MODERATE"]
    )
    investment_time_horizon: str = Field(
        ..., description="Investment horizon category.", examples=["LONG_TERM"]
    )
    portfolio_type: str = Field(
        ..., description="Portfolio product/type classification.", examples=["DISCRETIONARY"]
    )
    objective: Optional[str] = Field(
        None, description="Primary client objective for this portfolio.", examples=["GROWTH"]
    )
    booking_center_code: str = Field(
        ..., description="Booking center owning the portfolio.", examples=["LON-01"]
    )
    client_id: str = Field(..., description="Client CIF identifier.", examples=["CIF-12345"])
    is_leverage_allowed: bool = Field(
        ..., description="Whether leverage is allowed for this portfolio.", examples=[False]
    )
    advisor_id: Optional[str] = Field(
        None, description="Primary advisor identifier.", examples=["ADV-987"]
    )
    status: str = Field(..., description="Portfolio lifecycle status.", examples=["ACTIVE"])

    model_config = ConfigDict(from_attributes=True)


class PortfolioQueryResponse(BaseModel):
    """
    Represents the API response for a portfolio query.
    """

    portfolios: List[PortfolioRecord] = Field(
        ...,
        description="List of portfolio records matching the applied query filters.",
    )
