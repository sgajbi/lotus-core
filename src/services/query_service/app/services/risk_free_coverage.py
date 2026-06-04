from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import CoverageResponse
from ..repositories.currency_codes import normalize_currency_code
from .market_reference_coverage import market_reference_coverage_response
from .request_fingerprint import request_fingerprint as build_request_fingerprint


async def resolve_risk_free_coverage_response(
    *,
    repository: Any,
    currency: str,
    start_date: date,
    end_date: date,
) -> CoverageResponse:
    normalized_currency = normalize_currency_code(currency)
    coverage = await repository.get_risk_free_coverage(
        currency=normalized_currency,
        start_date=start_date,
        end_date=end_date,
    )
    return build_risk_free_coverage_response(
        currency=normalized_currency,
        coverage=coverage,
        start_date=start_date,
        end_date=end_date,
    )


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
