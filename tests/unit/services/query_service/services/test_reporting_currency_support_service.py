from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.services.query_service.app.application.reporting_currency_support import (
    FxSupportEvidence,
    ReportingCurrencySupportQuery,
)
from src.services.query_service.app.repositories.reporting_currency_support_repository import (
    PortfolioCurrencySource,
    ReportingCurrencySupportRepository,
)
from src.services.query_service.app.services.reporting_currency_support_service import (
    ReportingCurrencySupportService,
)

pytestmark = pytest.mark.asyncio


def _service(repository: AsyncMock) -> ReportingCurrencySupportService:
    with patch(
        "src.services.query_service.app.services.reporting_currency_support_service.ReportingCurrencySupportRepository",
        return_value=repository,
    ):
        return ReportingCurrencySupportService(AsyncMock())


async def test_support_is_true_only_when_every_source_currency_has_as_of_fx() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = PortfolioCurrencySource(
        tenant_id="tenant-1", base_currency="USD", source_currencies=("EUR", "USD")
    )
    repository.is_selector_currency_observed.return_value = True
    repository.get_latest_fx_rate_date.side_effect = [date(2026, 8, 20), date(2026, 8, 28)]
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "usd", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "SUPPORTED"
    assert result.reason_code == "supported"
    assert result.source_currencies == ("EUR", "USD")
    assert result.missing_source_currencies == ()
    assert result.observed_selector_currency is True
    assert result.fx_evidence == (
        FxSupportEvidence("EUR", date(2026, 8, 20), True),
        FxSupportEvidence("USD", date(2026, 8, 28), True),
    )


async def test_observed_selector_currency_does_not_imply_restatement_support() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = PortfolioCurrencySource(
        tenant_id=None, base_currency="USD", source_currencies=("EUR", "USD")
    )
    repository.is_selector_currency_observed.return_value = True
    repository.get_latest_fx_rate_date.side_effect = [None, date(2026, 8, 28)]
    service = _service(repository)

    result = await service.evaluate(ReportingCurrencySupportQuery("PF-1", "EUR", date(2026, 8, 28)))

    assert result.status == "UNSUPPORTED"
    assert result.reason_code == "required_fx_source_unavailable"
    assert result.missing_source_currencies == ("EUR",)
    assert result.observed_selector_currency is True


async def test_missing_portfolio_is_typed_unavailable_not_plausible_support() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = None
    repository.is_selector_currency_observed.return_value = False
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("MISSING", "USD", date(2026, 8, 28))
    )

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_source_unavailable"
    assert result.source_currencies == ()
    repository.get_latest_fx_rate_date.assert_not_awaited()


async def test_invalid_persisted_currency_is_typed_unavailable() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.side_effect = ValueError("invalid persisted currency")
    repository.is_selector_currency_observed.return_value = False
    service = _service(repository)

    result = await service.evaluate(ReportingCurrencySupportQuery("PF-1", "USD", date(2026, 8, 28)))

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_currency_source_invalid"


async def test_malformed_currency_is_rejected_before_source_queries() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    service = _service(repository)

    with pytest.raises(ValueError, match="three-letter ISO 4217"):
        await service.evaluate(ReportingCurrencySupportQuery("PF-1", "US1", date(2026, 8, 28)))

    repository.get_portfolio_currency_source.assert_not_awaited()
