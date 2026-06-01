from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import CoverageResponse
from .market_reference_coverage import market_reference_coverage_response
from .request_fingerprint import request_fingerprint as build_request_fingerprint


def build_risk_free_coverage_response(
    *,
    currency: str,
    start_date: date,
    end_date: date,
    coverage: dict[str, Any],
) -> CoverageResponse:
    request_fingerprint = build_request_fingerprint(
        {
            "coverage_key": "risk_free_coverage",
            "currency": currency,
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }
    )
    return market_reference_coverage_response(
        coverage=coverage,
        start_date=start_date,
        end_date=end_date,
        request_fingerprint=request_fingerprint,
    )
