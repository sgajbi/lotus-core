# src/services/ingestion_service/app/DTOs/reprocessing_dto.py
from typing import Annotated, List

from pydantic import BaseModel, Field, StringConstraints

CanonicalTransactionId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ReprocessingRequest(BaseModel):
    transaction_ids: List[CanonicalTransactionId] = Field(
        ...,
        min_length=1,
        description=(
            "Canonical transaction identifiers to reprocess. Core resolves each identifier "
            "against the authoritative transaction ledger before publishing a portfolio-ordered "
            "repair command."
        ),
        examples=[["TRN_001", "TRN_002"]],
    )
