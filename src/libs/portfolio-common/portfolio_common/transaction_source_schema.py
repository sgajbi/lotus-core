"""Transaction source provenance columns; supplier and child references stay distinct."""

from sqlalchemy import Column, DateTime, String


class TransactionSourceColumns:
    source_system = Column(String, nullable=True)
    source_record_id = Column(String(256), nullable=True)
    source_batch_id = Column(String(256), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    source_instrument_id = Column(String, nullable=True, index=True)
    source_transaction_reference = Column(String, nullable=True, index=True)
