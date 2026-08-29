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
    repository.get_exact_fx_rate_dates.side_effect = [
        {"EUR": date(2026, 8, 28)},
    ]
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "usd", date(2026, 8, 28), " tenant-1 ")
    )

    assert result.status == "SUPPORTED"
    assert result.reason_code == "supported"
    assert result.source_currencies == ("EUR", "USD")
    assert result.missing_source_currencies == ()
    assert result.observed_selector_currency is True
    assert result.fx_evidence == (
        FxSupportEvidence("EUR", date(2026, 8, 28), True),
        FxSupportEvidence("USD", date(2026, 8, 28), True),
    )
    repository.is_selector_currency_observed.assert_awaited_once_with(
        currency="USD", tenant_id="tenant-1"
    )
    repository.get_portfolio_currency_source.assert_awaited_once_with(
        portfolio_id="PF-1",
        tenant_id="tenant-1",
        as_of_date=date(2026, 8, 28),
    )
    repository.get_exact_fx_rate_dates.assert_awaited_once_with(
        from_currencies=("EUR",),
        to_currency="USD",
        as_of_date=date(2026, 8, 28),
    )


async def test_observed_selector_currency_does_not_imply_restatement_support() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = PortfolioCurrencySource(
        tenant_id="tenant-1", base_currency="USD", source_currencies=("EUR", "USD")
    )
    repository.is_selector_currency_observed.return_value = True
    repository.get_exact_fx_rate_dates.side_effect = [{}, {}]
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "EUR", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNSUPPORTED"
    assert result.reason_code == "required_fx_source_unavailable"
    assert result.missing_source_currencies == ("EUR", "USD")
    assert result.observed_selector_currency is True


async def test_support_uses_position_to_base_then_base_to_reporting_legs() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = PortfolioCurrencySource(
        tenant_id="tenant-1", base_currency="USD", source_currencies=("EUR", "USD")
    )
    repository.is_selector_currency_observed.return_value = True
    repository.get_exact_fx_rate_dates.side_effect = [
        {"EUR": date(2026, 8, 28)},
        {"USD": date(2026, 8, 28)},
    ]
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "GBP", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "SUPPORTED"
    assert result.missing_source_currencies == ()
    assert result.fx_evidence[0] == FxSupportEvidence("EUR", date(2026, 8, 28), True)
    assert result.fx_evidence[1] == FxSupportEvidence("USD", date(2026, 8, 28), True)
    assert repository.get_exact_fx_rate_dates.await_args_list[0].kwargs == {
        "from_currencies": ("EUR",),
        "to_currency": "USD",
        "as_of_date": date(2026, 8, 28),
    }
    assert repository.get_exact_fx_rate_dates.await_args_list[1].kwargs == {
        "from_currencies": ("USD",),
        "to_currency": "GBP",
        "as_of_date": date(2026, 8, 28),
    }


async def test_support_rejects_missing_position_to_base_leg_even_when_direct_cross_exists() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = PortfolioCurrencySource(
        tenant_id="tenant-1", base_currency="USD", source_currencies=("EUR", "USD")
    )
    repository.is_selector_currency_observed.return_value = True
    repository.get_exact_fx_rate_dates.side_effect = [
        {},
        {"USD": date(2026, 8, 28)},
    ]
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "GBP", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNSUPPORTED"
    assert result.missing_source_currencies == ("EUR",)


async def test_missing_portfolio_is_typed_unavailable_not_plausible_support() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.return_value = None
    repository.is_selector_currency_observed.return_value = False
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("MISSING", "USD", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_source_unavailable"
    assert result.source_currencies == ()
    repository.get_exact_fx_rate_dates.assert_not_awaited()


async def test_invalid_persisted_currency_is_typed_unavailable() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.side_effect = ValueError("invalid persisted currency")
    repository.is_selector_currency_observed.return_value = False
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "USD", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_currency_source_invalid"


async def test_pre_inception_as_of_is_typed_unavailable() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.side_effect = ValueError(
        "as_of_date precedes portfolio inception"
    )
    repository.is_selector_currency_observed.return_value = True
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "USD", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_as_of_before_inception"


async def test_unresolved_position_currency_is_typed_unavailable() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    repository.get_portfolio_currency_source.side_effect = ValueError(
        "position source currency is unavailable"
    )
    repository.is_selector_currency_observed.return_value = True
    service = _service(repository)

    result = await service.evaluate(
        ReportingCurrencySupportQuery("PF-1", "USD", date(2026, 8, 28), "tenant-1")
    )

    assert result.status == "UNAVAILABLE"
    assert result.reason_code == "portfolio_currency_source_invalid"
    assert result.observed_selector_currency is True


async def test_malformed_currency_is_rejected_before_source_queries() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    service = _service(repository)

    with pytest.raises(ValueError, match="three-letter ISO 4217"):
        await service.evaluate(
            ReportingCurrencySupportQuery("PF-1", "US1", date(2026, 8, 28), "tenant-1")
        )

    repository.get_portfolio_currency_source.assert_not_awaited()


async def test_blank_tenant_is_rejected_before_any_repository_query() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    service = _service(repository)

    with pytest.raises(ValueError, match="tenant_id must not be blank"):
        await service.evaluate(ReportingCurrencySupportQuery("PF-1", "USD", date(2026, 8, 28), " "))

    repository.is_selector_currency_observed.assert_not_awaited()
    repository.get_portfolio_currency_source.assert_not_awaited()


async def test_blank_portfolio_is_rejected_before_any_repository_query() -> None:
    repository = AsyncMock(spec=ReportingCurrencySupportRepository)
    service = _service(repository)

    with pytest.raises(ValueError, match="portfolio_id must not be blank"):
        await service.evaluate(
            ReportingCurrencySupportQuery(" ", "USD", date(2026, 8, 28), "tenant-1")
        )

    repository.is_selector_currency_observed.assert_not_awaited()
    repository.get_portfolio_currency_source.assert_not_awaited()
