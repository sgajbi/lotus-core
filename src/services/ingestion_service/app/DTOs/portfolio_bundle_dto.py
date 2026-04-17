from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .business_date_dto import BusinessDate
from .fx_rate_dto import FxRate
from .instrument_dto import Instrument
from .market_price_dto import MarketPrice
from .portfolio_dto import Portfolio
from .transaction_dto import Transaction


class PortfolioBundleIngestionRequest(BaseModel):
    source_system: Optional[str] = Field(
        None,
        description="Upstream source system identifier for audit and lineage.",
        json_schema_extra={"example": "UI_UPLOAD"},
    )
    mode: Literal["UPSERT", "REPLACE"] = Field(
        "UPSERT",
        description=(
            "Ingestion mode for bundle semantics; current behavior is UPSERT-style "
            "event publication."
        ),
        examples=["UPSERT"],
    )
    business_dates: List[BusinessDate] = Field(
        default_factory=list,
        description="Canonical business-date records included in the bundle.",
        examples=[[{"business_date": "2026-01-02", "calendar_code": "GLOBAL"}]],
    )
    portfolios: List[Portfolio] = Field(
        default_factory=list,
        description="Canonical portfolio onboarding records included in the bundle.",
        examples=[
            [
                {
                    "portfolio_id": "PORT_001",
                    "base_currency": "USD",
                    "open_date": "2024-01-01",
                }
            ]
        ],
    )
    instruments: List[Instrument] = Field(
        default_factory=list,
        description="Canonical instrument master records included in the bundle.",
        examples=[[{"security_id": "SEC_AAPL", "product_type": "equity"}]],
    )
    transactions: List[Transaction] = Field(
        default_factory=list,
        description="Canonical transaction records included in the bundle.",
        examples=[[{"transaction_id": "TRN_001", "transaction_type": "BUY"}]],
    )
    market_prices: List[MarketPrice] = Field(
        default_factory=list,
        description="Canonical market-price records included in the bundle.",
        examples=[[{"security_id": "SEC_AAPL", "price_date": "2026-01-02"}]],
    )
    fx_rates: List[FxRate] = Field(
        default_factory=list,
        description="Canonical FX-rate records included in the bundle.",
        examples=[[{"from_currency": "USD", "to_currency": "SGD"}]],
    )

    @model_validator(mode="after")
    def validate_non_empty_bundle(self):
        if not any(
            [
                self.business_dates,
                self.portfolios,
                self.instruments,
                self.transactions,
                self.market_prices,
                self.fx_rates,
            ]
        ):
            raise ValueError(
                "Portfolio bundle must include at least one non-empty entity list "
                "(businessDates, portfolios, instruments, transactions, marketPrices, fxRates)."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_system": "UI_UPLOAD",
                "mode": "UPSERT",
                "business_dates": [{"business_date": "2026-01-02"}],
                "portfolios": [
                    {
                        "portfolio_id": "PORT_001",
                        "base_currency": "USD",
                        "open_date": "2024-01-01",
                        "risk_exposure": "Medium",
                        "investment_time_horizon": "Long",
                        "portfolio_type": "Discretionary",
                        "booking_center_code": "Singapore",
                        "client_id": "CIF_12345",
                        "status": "Active",
                    }
                ],
                "instruments": [
                    {
                        "security_id": "SEC_AAPL",
                        "name": "Apple Inc.",
                        "isin": "US0378331005",
                        "currency": "USD",
                        "product_type": "Equity",
                    }
                ],
                "transactions": [
                    {
                        "transaction_id": "TRN_001",
                        "portfolio_id": "PORT_001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC_AAPL",
                        "transaction_date": "2026-01-02T10:00:00Z",
                        "transaction_type": "BUY",
                        "quantity": 10,
                        "price": 200,
                        "gross_transaction_amount": 2000,
                        "trade_currency": "USD",
                        "currency": "USD",
                    }
                ],
                "market_prices": [
                    {
                        "security_id": "SEC_AAPL",
                        "price_date": "2026-01-02",
                        "price": 200,
                        "currency": "USD",
                    }
                ],
                "fx_rates": [
                    {
                        "from_currency": "USD",
                        "to_currency": "SGD",
                        "rate_date": "2026-01-02",
                        "rate": 1.35,
                    }
                ],
            }
        },
    }
