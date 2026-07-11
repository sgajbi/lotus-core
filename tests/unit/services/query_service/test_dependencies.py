import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dependencies import (
    get_buy_state_service,
    get_cash_account_service,
    get_cash_balance_service,
    get_fx_rate_service,
    get_instrument_service,
    get_liquidity_ladder_service,
    get_market_price_service,
    get_reporting_service,
    get_sell_state_service,
    pagination_params,
    sorting_params,
)
from src.services.query_service.app.services.buy_state_service import BuyStateService
from src.services.query_service.app.services.cash_account_service import CashAccountService
from src.services.query_service.app.services.cash_balance_service import CashBalanceService
from src.services.query_service.app.services.fx_rate_service import FxRateService
from src.services.query_service.app.services.instrument_service import InstrumentService
from src.services.query_service.app.services.liquidity_ladder_service import (
    PortfolioLiquidityLadderService,
)
from src.services.query_service.app.services.price_service import MarketPriceService
from src.services.query_service.app.services.reporting_service import ReportingService
from src.services.query_service.app.services.sell_state_service import SellStateService


def test_pagination_params_default_values():
    result = pagination_params(skip=0, limit=100)
    assert result == {"skip": 0, "limit": 100}


def test_pagination_params_custom_values():
    result = pagination_params(skip=25, limit=250)
    assert result == {"skip": 25, "limit": 250}


def test_sorting_params_default_values():
    result = sorting_params(sort_by=None, sort_order="desc")
    assert result == {"sort_by": None, "sort_order": "desc"}


def test_sorting_params_custom_values():
    result = sorting_params(sort_by="transaction_date", sort_order="asc")
    assert result == {"sort_by": "transaction_date", "sort_order": "asc"}


def test_sorting_params_rejects_invalid_sort_field():
    with pytest.raises(HTTPException) as exc_info:
        sorting_params(sort_by="settlement_currency", sort_order="asc")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_TRANSACTION_SORT_PARAMETER"
    assert exc_info.value.detail["field"] == "sort_by"
    assert "transaction_date" in exc_info.value.detail["allowed_values"]


def test_sorting_params_rejects_invalid_sort_order():
    with pytest.raises(HTTPException) as exc_info:
        sorting_params(sort_by="transaction_date", sort_order="ascending")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_TRANSACTION_SORT_PARAMETER"
    assert exc_info.value.detail["field"] == "sort_order"
    assert exc_info.value.detail["allowed_values"] == ["asc", "desc"]


@pytest.mark.parametrize(
    ("factory", "service_type", "repository_attributes"),
    [
        (get_buy_state_service, BuyStateService, ("repo",)),
        (get_cash_account_service, CashAccountService, ("repo",)),
        (get_cash_balance_service, CashBalanceService, ("repo",)),
        (get_fx_rate_service, FxRateService, ("repo",)),
        (get_instrument_service, InstrumentService, ("repo",)),
        (
            get_liquidity_ladder_service,
            PortfolioLiquidityLadderService,
            ("reporting_repo", "cashflow_repo"),
        ),
        (get_market_price_service, MarketPriceService, ("repo",)),
        (get_reporting_service, ReportingService, ("repo",)),
        (get_sell_state_service, SellStateService, ("repo",)),
    ],
)
def test_query_service_factories_bind_services_to_the_request_session(
    factory,
    service_type,
    repository_attributes,
) -> None:
    request_session = AsyncSession()

    service = factory(request_session)

    assert isinstance(service, service_type)
    for attribute in repository_attributes:
        assert getattr(service, attribute).db is request_session
