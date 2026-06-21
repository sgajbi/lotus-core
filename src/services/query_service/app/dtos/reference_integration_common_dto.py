from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class IntegrationWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Window start date for series retrieval (inclusive).",
        examples=["2026-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Window end date for series retrieval (inclusive).",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()
