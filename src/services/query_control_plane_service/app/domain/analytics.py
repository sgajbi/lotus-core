"""Immutable records used across QCP analytics application ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PortfolioAnalyticsSource:
    """Portfolio master fields required to source analytics inputs."""

    portfolio_id: str
    base_currency: str
    open_date: date
    close_date: date | None
    client_id: str
    booking_center_code: str
    portfolio_type: str
    objective: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class AnalyticsExportJobRecord:
    """Durable analytics export lifecycle state without ORM identity."""

    job_id: str
    dataset_type: str
    portfolio_id: str
    status: str
    request_fingerprint: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    result_row_count: int | None
    result_format: str
    compression: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
