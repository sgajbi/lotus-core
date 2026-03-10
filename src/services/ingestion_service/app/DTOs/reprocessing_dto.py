# src/services/ingestion_service/app/DTOs/reprocessing_dto.py
from typing import List

from pydantic import BaseModel, Field


class ReprocessingRequest(BaseModel):
    transaction_ids: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "Canonical transaction identifiers to reprocess in the current replay request."
        ),
        examples=[["TRN_001", "TRN_002"]],
    )
