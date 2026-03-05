# src/core/models/request.py

import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TransactionProcessingRequest(BaseModel):
    """
    Represents the input payload for the transaction processing API.
    """

    existing_transactions: list[dict] = Field(
        default_factory=list,
        description=(
            "List of previously processed transactions "
            "(raw dictionaries) with cost fields already computed."
        ),
    )
    new_transactions: list[dict] = Field(
        ...,
        description=(
            "New transactions to be processed "
            "(raw dictionaries, including possible backdated ones)."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "existing_transactions": [],
                "new_transactions": [
                    {
                        "transaction_id": "new_buy_001",
                        "portfolio_id": "PORT001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "BUY",
                        "transaction_date": "2023-01-10T00:00:00Z",
                        "settlement_date": "2023-01-12T00:00:00Z",
                        "quantity": 5.0,
                        "gross_transaction_amount": 760.0,
                        "fees": {"brokerage": 2.0},
                        "trade_currency": "USD",
                    }
                ],
            }
        },
        extra="ignore",
    )
