# services/ingestion_service/app/DTOs/transaction_ingestion_request_dto.py
from typing import List

from pydantic import BaseModel, Field

from .transaction_model_dto import Transaction


class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction] = Field(
        ...,
        description=(
            "Canonical transaction records to ingest or upsert asynchronously. "
            "An empty list is accepted as a no-op batch for client workflow consistency."
        ),
        examples=[
            [],
            [
                {
                    "transaction_id": "TRN001",
                    "portfolio_id": "PORT001",
                    "instrument_id": "AAPL",
                    "security_id": "SEC_AAPL",
                    "transaction_date": "2023-01-15T10:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": "10.0",
                    "price": "150.0",
                    "gross_transaction_amount": "1500.0",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "trade_fee": "5.0",
                    "settlement_date": "2023-01-17T10:00:00Z",
                }
            ],
        ],
    )
