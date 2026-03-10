from pydantic import BaseModel, Field


class ErroredTransaction(BaseModel):
    """
    Represents a transaction that failed processing, along with the reason for failure.
    """

    transaction_id: str = Field(..., description="The ID of the transaction that failed.")
    error_reason: str = Field(..., description="The reason why the transaction processing failed.")
