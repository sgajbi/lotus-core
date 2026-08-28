from datetime import date

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.reporting_currency_support_dto import (
    ReportingCurrencySupportResponse,
)


def test_reporting_currency_support_response_is_explicit_and_typed() -> None:
    response = ReportingCurrencySupportResponse(
        portfolio_id="PF-1",
        reporting_currency="USD",
        as_of_date=date(2026, 8, 28),
        status="UNSUPPORTED",
        supported=False,
        reason_code="required_fx_source_unavailable",
        source_currencies=["EUR", "USD"],
        missing_source_currencies=["EUR"],
        fx_evidence=[{"source_currency": "EUR", "rate_available": False}],
        observed_selector_currency=True,
    )

    assert response.contract == "ReportingCurrencySupport:v1"
    assert response.status.value == "UNSUPPORTED"
    assert response.supported is False


def test_reporting_currency_support_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReportingCurrencySupportResponse(
            portfolio_id="PF-1",
            reporting_currency="USD",
            as_of_date=date(2026, 8, 28),
            status="SUPPORTED",
            supported=True,
            reason_code="supported",
            unexpected="value",
        )
