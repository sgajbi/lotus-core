# common/models.py

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, condecimal


class TransactionBase(BaseModel):
    """Base Pydantic model for a transaction, defining common fields."""
    transaction_id: str
    portfolio_id: str = Field()
    instrument_id: str = Field()
    security_id: str
    transaction_type: str
    transaction_date: date
    settlement_date: date
    quantity: condecimal(ge=0)
    gross_transaction_amount: condecimal(ge=0)
    net_transaction_amount: Optional[condecimal(ge=0)] = None
    fees: Optional[Dict[str, Any]] = None # Using Dict[str, Any] for flexibility
    accrued_interest: Optional[condecimal(ge=0)] = Decimal(0)
    average_price: Optional[condecimal(ge=0)] = None
    trade_currency: str = Field()

    class Config:
        json_encoders = {
            Decimal: str # Encode Decimal to string for JSON serialization
        }


class TransactionCreate(TransactionBase):
    """Pydantic model for creating a new transaction."""
    pass


class Transaction(TransactionBase):
    """
    Pydantic model representing a full transaction record,
    including calculated fields and database timestamps.
    """
    id: int # Database primary key
    net_cost: Optional[condecimal()] = None # NEW: Calculated net cost from transaction-cost-engine
    gross_cost: Optional[condecimal()] = None # NEW: Calculated gross cost from transaction-cost-engine
    realized_gain_loss: Optional[condecimal()] = None # NEW: Calculated realized gain/loss from transaction-cost-engine
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Allow ORM models to be converted to this Pydantic model
        json_encoders = {
            Decimal: str
        }


class TransactionCostBase(BaseModel):
    """Base Pydantic model for transaction cost details."""
    transaction_id: str
    fee_type: str
    amount: condecimal(ge=0)
    currency: str


class TransactionCostCreate(TransactionCostBase):
    """Pydantic model for creating new transaction cost records."""
    pass


class TransactionCost(TransactionCostBase):
    """Pydantic model representing a full transaction cost record."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str
        }


class HealthCheckResponse(BaseModel):
    """Pydantic model for health check responses."""
    status: str
    timestamp: datetime
