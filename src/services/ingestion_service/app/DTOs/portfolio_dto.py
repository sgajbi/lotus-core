from datetime import date
from typing import List, Optional

from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Portfolio(BaseModel):
    """
    Represents a single portfolio for ingestion.
    """

    portfolio_id: str = Field(...)
    base_currency: str = Field(...)
    open_date: date = Field(...)
    close_date: Optional[date] = Field(None)
    risk_exposure: str = Field(...)
    investment_time_horizon: str = Field(...)
    portfolio_type: str = Field(...)
    objective: Optional[str] = None
    booking_center_code: str = Field(...)
    client_id: str = Field(...)
    is_leverage_allowed: bool = Field(False)
    advisor_id: Optional[str] = Field(None)
    status: str
    cost_basis_method: Optional[CostBasisMethod] = Field(CostBasisMethod.FIFO)

    @field_validator("cost_basis_method", mode="before")
    @classmethod
    def _normalize_cost_basis_method(cls, value: object) -> CostBasisMethod:
        return normalize_cost_basis_method(value)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portfolioId": "PORT_001",
                "baseCurrency": "USD",
                "openDate": "2024-01-01",
                "riskExposure": "Medium",
                "investmentTimeHorizon": "Long",
                "portfolioType": "Discretionary",
                "bookingCenter": "Singapore",
                "cifId": "CIF_12345",
                "status": "Active",
                "costBasisMethod": "AVCO",
            }
        }
    )


class PortfolioIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of portfolios.
    """

    portfolios: List[Portfolio]
