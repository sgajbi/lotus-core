from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    AnalyticsWindow,
    PageRequest,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsInputError,
    AnalyticsTimeseriesService,
)


def make_service() -> AnalyticsTimeseriesService:
    service = AnalyticsTimeseriesService(MagicMock(spec=AsyncSession))
    service._analytics_export_stale_timeout_minutes = 15  # pylint: disable=protected-access
    return service


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_happy_path() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
                client_id="CIF_123",
                booking_center_code="SGPB",
                portfolio_type="discretionary",
                objective="Balanced growth",
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    bod_cashflow=Decimal("1"),
                    eod_cashflow=Decimal("2"),
                    fees=Decimal("-0.5"),
                    epoch=0,
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
        get_portfolio_snapshot_epoch=AsyncMock(return_value=0),
        list_business_dates=AsyncMock(return_value=[date(2025, 1, 31)]),
        list_portfolio_observation_dates=AsyncMock(return_value=[date(2025, 1, 31)]),
    )

    response = await service.get_portfolio_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            reporting_currency="EUR",
        ),
    )

    assert response.portfolio_id == "DEMO_DPM_EUR_001"
    assert response.observations[0].beginning_market_value == Decimal("100")
    assert len(response.observations[0].cash_flows) == 3
    assert response.observations[0].cash_flow_currency == "EUR"
    assert response.diagnostics.expected_business_dates_count == 1
    assert response.diagnostics.returned_observation_dates_count == 1
    assert response.diagnostics.cash_flows_included is True
    assert response.page.sort_key == "valuation_date:asc"


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_tracks_missing_business_dates_and_reporting_currency(
) -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2025, 1, 1),
                close_date=None,
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    bod_cashflow=Decimal("5"),
                    eod_cashflow=Decimal("0"),
                    fees=Decimal("0"),
                    epoch=1,
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={date(2025, 1, 2): Decimal("1.5")}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 1, 2)),
        get_portfolio_snapshot_epoch=AsyncMock(return_value=1),
        list_business_dates=AsyncMock(return_value=[date(2025, 1, 1), date(2025, 1, 2)]),
        list_portfolio_observation_dates=AsyncMock(return_value=[date(2025, 1, 2)]),
    )

    response = await service.get_portfolio_timeseries(
        portfolio_id="P1",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-01-02",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-02"),
            reporting_currency="USD",
        ),
    )

    assert response.observations[0].beginning_market_value == Decimal("150.0")
    assert response.observations[0].cash_flows[0].amount == Decimal("7.5")
    assert response.observations[0].cash_flow_currency == "USD"
    assert response.diagnostics.missing_dates_count == 1
    assert response.diagnostics.stale_points_count == 1


@pytest.mark.asyncio
async def test_get_position_timeseries_paging_token_generation() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_B",
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("20"),
                    eod_market_value=Decimal("21"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Healthcare",
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=7),
        get_fx_rates_map=AsyncMock(return_value={date(2025, 1, 1): Decimal("0.92")}),
    )

    response = await service.get_position_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            page=PageRequest(page_size=1),
        ),
    )

    assert len(response.rows) == 1
    assert response.rows[0].position_currency == "USD"
    assert response.page.page_size == 1
    assert response.page.returned_row_count == 1
    assert response.page.sort_key == "valuation_date:asc,security_id:asc"
    assert response.page.next_page_token is not None
    token_payload = service._decode_page_token(response.page.next_page_token)  # pylint: disable=protected-access
    assert token_payload["snapshot_epoch"] == 7
    assert "scope_fingerprint" in token_payload


@pytest.mark.asyncio
async def test_invalid_page_token_raises_invalid_request() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="DEMO_DPM_EUR_001",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
                page=PageRequest(page_size=100, page_token="invalid"),
            ),
        )
    assert exc_info.value.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_page_token_scope_mismatch_raises_invalid_request() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(return_value=[]),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
        get_portfolio_snapshot_epoch=AsyncMock(return_value=5),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {
            "valuation_date": "2025-01-01",
            "snapshot_epoch": 5,
            "scope_fingerprint": "different-scope",
        }
    )

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="DEMO_DPM_EUR_001",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
                page=PageRequest(page_size=10, page_token=token),
            ),
        )

    assert exc_info.value.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_position_timeseries_reuses_token_snapshot_epoch_under_concurrent_drift() -> None:
    service = make_service()
    list_rows = AsyncMock(
        side_effect=[
            [
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=7,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=7,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
            ],
            [],
        ]
    )
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=list_rows,
        get_position_snapshot_epoch=AsyncMock(side_effect=[7, 99]),
        get_fx_rates_map=AsyncMock(return_value={date(2025, 1, 1): Decimal("0.92")}),
    )

    first_page = await service.get_position_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            page=PageRequest(page_size=1),
        ),
    )
    assert first_page.page.next_page_token is not None

    await service.get_position_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            page=PageRequest(page_size=1, page_token=first_page.page.next_page_token),
        ),
    )

    assert list_rows.await_count == 2
    assert list_rows.await_args_list[1].kwargs["snapshot_epoch"] == 7


@pytest.mark.asyncio
async def test_get_portfolio_reference_not_found() -> None:
    service = make_service()
    service.repo = SimpleNamespace(get_portfolio=AsyncMock(return_value=None))

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_reference(
            portfolio_id="UNKNOWN",
            request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-12-31"),
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_portfolio_reference_success() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
                client_id="CIF_1",
                booking_center_code="SGPB",
                portfolio_type="advisory",
                objective="Growth",
            )
        ),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
    )
    response = await service.get_portfolio_reference(
        portfolio_id="P1",
        request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-12-31"),
    )
    assert response.portfolio_id == "P1"
    assert response.resolved_as_of_date == date(2025, 12, 31)
    assert response.performance_end_date == date(2025, 12, 31)
    assert response.reference_state_policy == "current_portfolio_reference_state"
    assert response.supported_grouping_dimensions == ["asset_class", "sector", "country"]


@pytest.mark.asyncio
async def test_get_portfolio_reference_bounds_performance_end_date_by_as_of_date() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
                client_id="CIF_1",
                booking_center_code="SGPB",
                portfolio_type="advisory",
                objective="Growth",
            )
        ),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
    )
    response = await service.get_portfolio_reference(
        portfolio_id="P1",
        request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-06-30"),
    )
    assert response.performance_end_date == date(2025, 6, 30)


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_period_resolution_and_missing_fx() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    bod_cashflow=Decimal("0"),
                    eod_cashflow=Decimal("0"),
                    fees=Decimal("0"),
                    epoch=0,
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
        get_portfolio_snapshot_epoch=AsyncMock(return_value=0),
        list_business_dates=AsyncMock(return_value=[date(2025, 1, 31)]),
        list_portfolio_observation_dates=AsyncMock(return_value=[date(2025, 1, 31)]),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="P1",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_year",
                reporting_currency="USD",
            ),
        )
    assert exc_info.value.code == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_get_position_timeseries_with_cash_flows_and_cursor() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("1"),
                    eod_cashflow_position=Decimal("2"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("-0.1"),
                    quantity=Decimal("1"),
                    epoch=1,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={date(2025, 1, 1): Decimal("1.2")}),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"valuation_date": "2025-01-01", "security_id": "SEC_A"}
    )
    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            reporting_currency="USD",
            include_cash_flows=True,
            page=PageRequest(page_size=10, page_token=token),
            dimensions=["asset_class", "sector", "country"],
        ),
    )
    assert response.rows[0].valuation_status == "restated"
    assert len(response.rows[0].cash_flows) == 3
    assert response.diagnostics.cash_flows_included is True
    assert response.diagnostics.requested_dimensions == ["asset_class", "sector", "country"]
    assert response.rows[0].cash_flow_currency == "USD"
    assert response.rows[0].portfolio_to_reporting_fx_rate == Decimal("1.2")


@pytest.mark.asyncio
async def test_get_position_timeseries_seeded_stock_contract_semantics() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="E2E_TS_PORT",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            side_effect=[
                [
                    SimpleNamespace(
                        security_id="SEC_EUR_STOCK",
                        valuation_date=date(2025, 8, 28),
                        bod_market_value=Decimal("0"),
                        eod_market_value=Decimal("5720"),
                        bod_cashflow_position=Decimal("0"),
                        eod_cashflow_position=Decimal("0"),
                        bod_cashflow_portfolio=Decimal("0"),
                        eod_cashflow_portfolio=Decimal("0"),
                        fees=Decimal("0"),
                        quantity=Decimal("100"),
                        epoch=0,
                        asset_class="Equity",
                        sector=None,
                        country=None,
                        position_currency="EUR",
                    )
                ],
                [
                    SimpleNamespace(
                        security_id="SEC_EUR_STOCK",
                        valuation_date=date(2025, 8, 29),
                        bod_market_value=Decimal("5720"),
                        eod_market_value=Decimal("6600"),
                        bod_cashflow_position=Decimal("0"),
                        eod_cashflow_position=Decimal("0"),
                        bod_cashflow_portfolio=Decimal("0"),
                        eod_cashflow_portfolio=Decimal("0"),
                        fees=Decimal("0"),
                        quantity=Decimal("100"),
                        epoch=0,
                        asset_class="Equity",
                        sector=None,
                        country=None,
                        position_currency="EUR",
                    )
                ],
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=0),
        get_fx_rates_map=AsyncMock(
            side_effect=[
                {date(2025, 8, 28): Decimal("1.10")},
                {date(2025, 8, 29): Decimal("1.12")},
            ]
        ),
    )

    day_1 = await service.get_position_timeseries(
        portfolio_id="E2E_TS_PORT",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-08-28",
            window=AnalyticsWindow(start_date="2025-08-28", end_date="2025-08-28"),
            page=PageRequest(page_size=50),
        ),
    )
    day_2 = await service.get_position_timeseries(
        portfolio_id="E2E_TS_PORT",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-08-29",
            window=AnalyticsWindow(start_date="2025-08-29", end_date="2025-08-29"),
            page=PageRequest(page_size=50),
        ),
    )

    assert len(day_1.rows) == 1
    assert day_1.rows[0].security_id == "SEC_EUR_STOCK"
    assert day_1.rows[0].position_currency == "EUR"
    assert day_1.rows[0].position_to_portfolio_fx_rate == Decimal("1.10")
    assert day_1.rows[0].quantity == Decimal("100")
    assert day_1.rows[0].ending_market_value_portfolio_currency == Decimal("6292.00")
    assert day_1.rows[0].ending_market_value_reporting_currency == Decimal("6292.00")

    assert len(day_2.rows) == 1
    assert day_2.rows[0].security_id == "SEC_EUR_STOCK"
    assert day_2.rows[0].quantity == Decimal("100")
    assert (
        day_2.rows[0].ending_market_value_portfolio_currency
        > day_1.rows[0].ending_market_value_portfolio_currency
    )


@pytest.mark.asyncio
async def test_get_position_timeseries_converts_position_values_to_portfolio_and_reporting_currency(
) -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="USD",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EUR",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("1"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="DE",
                    position_currency="EUR",
                )
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=3),
        get_fx_rates_map=AsyncMock(
            side_effect=[
                {date(2025, 1, 1): Decimal("1.30")},
                {date(2025, 1, 1): Decimal("1.10")},
            ]
        ),
    )

    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            reporting_currency="SGD",
            include_cash_flows=True,
        ),
    )

    row = response.rows[0]
    assert row.beginning_market_value_position_currency == Decimal("10")
    assert row.beginning_market_value_portfolio_currency == Decimal("11.00")
    assert row.ending_market_value_portfolio_currency == Decimal("12.10")
    assert row.beginning_market_value_reporting_currency == Decimal("14.3000")
    assert row.ending_market_value_reporting_currency == Decimal("15.7300")
    assert row.position_to_portfolio_fx_rate == Decimal("1.10")
    assert row.portfolio_to_reporting_fx_rate == Decimal("1.30")


@pytest.mark.asyncio
async def test_get_position_timeseries_missing_position_to_portfolio_fx_rate() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="USD",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EUR",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="DE",
                    position_currency="EUR",
                )
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=1),
        get_fx_rates_map=AsyncMock(side_effect=[{}, {}]),
    )

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_position_timeseries(
            portfolio_id="P1",
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
                reporting_currency="SGD",
            ),
        )
    assert exc_info.value.code == "INSUFFICIENT_DATA"


def test_decode_page_token_invalid_signature() -> None:
    service = make_service()
    token = service._encode_page_token({"valuation_date": "2025-01-01"})  # pylint: disable=protected-access
    service._page_token_secret = "different-secret"  # pylint: disable=protected-access
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._decode_page_token(token)  # pylint: disable=protected-access
    assert exc_info.value.code == "INVALID_REQUEST"


def test_resolve_window_invalid_order() -> None:
    with pytest.raises(ValidationError):
        AnalyticsWindow(start_date="2025-02-01", end_date="2025-01-31")


def test_resolve_window_unsupported_period() -> None:
    service = make_service()
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._resolve_window(  # pylint: disable=protected-access
            as_of_date=date(2025, 1, 31),
            window=None,
            period="bad_period",
            inception_date=date(2020, 1, 1),
        )
    assert exc_info.value.code == "INVALID_REQUEST"


def test_resolve_window_inception_clamp() -> None:
    service = make_service()
    window = service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 1, 31),
        window=None,
        period="five_years",
        inception_date=date(2023, 1, 1),
    )
    assert window.start_date == date(2023, 1, 1)


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_not_found() -> None:
    service = make_service()
    service.repo = SimpleNamespace(get_portfolio=AsyncMock(return_value=None))
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="UNKNOWN",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_year",
            ),
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_position_timeseries_missing_fx_rate() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_position_timeseries(
            portfolio_id="P1",
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
                reporting_currency="USD",
            ),
        )
    assert exc_info.value.code == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_create_export_job_completed() -> None:
    service = make_service()
    row = SimpleNamespace(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="accepted",
        request_fingerprint="fp1",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )
    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=None),
        create_job=AsyncMock(return_value=row),
        get_job=AsyncMock(return_value=row),
        mark_running=AsyncMock(
            side_effect=lambda *_args, **_kwargs: setattr(row, "status", "running")
        ),
        mark_completed=AsyncMock(
            side_effect=lambda *_args, **_kwargs: setattr(row, "status", "completed")
        ),
        mark_failed=AsyncMock(),
    )
    service._collect_portfolio_timeseries_for_export = AsyncMock(  # pylint: disable=protected-access
        return_value=([{"valuation_date": "2025-01-01"}], 1)
    )

    response = await service.create_export_job(
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
            result_format="json",
            compression="none",
        )
    )
    assert response.status == "completed"


@pytest.mark.asyncio
async def test_get_export_job_not_found() -> None:
    service = make_service()
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=None))
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_export_job("missing")
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_export_result_ndjson_gzip() -> None:
    service = make_service()
    row = SimpleNamespace(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        status="completed",
        result_payload={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "generated_at": "2026-03-01T12:00:00Z",
            "contract_version": "rfc_063_v1",
            "data": [{"valuation_date": "2025-01-01"}],
        },
    )
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=row))
    payload, media_type, encoding = await service.get_export_result_ndjson(
        "aexp_1", compression="gzip"
    )
    assert media_type == "application/x-ndjson"
    assert encoding == "gzip"
    assert len(payload) > 0


def test_jsonable_converts_decimal_and_date() -> None:
    service = make_service()
    converted = service._jsonable(  # pylint: disable=protected-access
        {"amount": Decimal("1.23"), "as_of_date": date(2025, 1, 1), "nested": [Decimal("2.00")]}
    )
    assert converted == {
        "amount": "1.23",
        "as_of_date": "2025-01-01",
        "nested": ["2.00"],
    }


@pytest.mark.asyncio
async def test_create_export_job_reuses_existing() -> None:
    service = make_service()
    existing = SimpleNamespace(
        job_id="aexp_existing",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="completed",
        request_fingerprint="fp",
        result_format="json",
        compression="none",
        result_row_count=1,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, tzinfo=UTC),
        updated_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=existing),
    )
    response = await service.create_export_job(
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )
    )
    assert response.job_id == "aexp_existing"


@pytest.mark.asyncio
async def test_create_export_job_reuses_fresh_running_job() -> None:
    service = make_service()
    existing = SimpleNamespace(
        job_id="aexp_running",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="running",
        request_fingerprint="fp",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        completed_at=None,
        updated_at=datetime.now(UTC),
    )
    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=existing),
    )

    response = await service.create_export_job(
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )
    )

    assert response.job_id == "aexp_running"


@pytest.mark.asyncio
async def test_create_export_job_replaces_stale_running_job() -> None:
    service = make_service()
    existing = SimpleNamespace(
        job_id="aexp_stale",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="running",
        request_fingerprint="fp",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        completed_at=None,
        updated_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    new_row = SimpleNamespace(
        job_id="aexp_new",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="accepted",
        request_fingerprint="fp2",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
        updated_at=datetime.now(UTC),
    )

    async def _mark_failed(row, *, error_message):
        row.status = "failed"
        row.error_message = error_message

    async def _mark_running(row):
        row.status = "running"

    async def _mark_completed(row, *, result_payload, result_row_count):
        row.status = "completed"
        row.result_payload = result_payload
        row.result_row_count = result_row_count

    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=existing),
        create_job=AsyncMock(return_value=new_row),
        get_job=AsyncMock(return_value=new_row),
        mark_failed=AsyncMock(side_effect=_mark_failed),
        mark_running=AsyncMock(side_effect=_mark_running),
        mark_completed=AsyncMock(side_effect=_mark_completed),
    )
    service._collect_portfolio_timeseries_for_export = AsyncMock(  # pylint: disable=protected-access
        return_value=([{"valuation_date": "2025-01-01"}], 1)
    )

    response = await service.create_export_job(
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )
    )

    assert existing.status == "failed"
    assert existing.error_message == "Stale analytics export job superseded by a new request."
    assert response.job_id == "aexp_new"
    service.export_repo.create_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_export_job_marks_failed_on_input_error() -> None:
    service = make_service()
    row = SimpleNamespace(
        job_id="aexp_2",
        dataset_type="position_timeseries",
        portfolio_id="P1",
        status="accepted",
        request_fingerprint="fp1",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )
    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=None),
        create_job=AsyncMock(return_value=row),
        get_job=AsyncMock(return_value=row),
        mark_running=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(side_effect=lambda *_a, **_k: setattr(row, "status", "failed")),
    )
    service._collect_position_timeseries_for_export = AsyncMock(  # pylint: disable=protected-access
        side_effect=AnalyticsInputError("INSUFFICIENT_DATA", "missing")
    )
    response = await service.create_export_job(
        AnalyticsExportCreateRequest(
            dataset_type="position_timeseries",
            portfolio_id="P1",
            position_timeseries_request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )
    )
    assert response.status == "failed"


@pytest.mark.asyncio
async def test_create_export_job_marks_failed_on_unexpected_error_and_reraises() -> None:
    service = make_service()
    row = SimpleNamespace(
        job_id="aexp_3",
        dataset_type="position_timeseries",
        portfolio_id="P1",
        status="accepted",
        request_fingerprint="fp3",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )
    failed_messages: list[str] = []

    async def _mark_failed(*_args, **kwargs):
        row.status = "failed"
        row.error_message = kwargs["error_message"]
        failed_messages.append(kwargs["error_message"])

    service.export_repo = SimpleNamespace(
        get_latest_by_fingerprint=AsyncMock(return_value=None),
        create_job=AsyncMock(return_value=row),
        get_job=AsyncMock(return_value=row),
        mark_running=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(side_effect=_mark_failed),
    )
    service._collect_position_timeseries_for_export = AsyncMock(  # pylint: disable=protected-access
        side_effect=RuntimeError("boom")
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.create_export_job(
            AnalyticsExportCreateRequest(
                dataset_type="position_timeseries",
                portfolio_id="P1",
                position_timeseries_request=PositionAnalyticsTimeseriesRequest(
                    as_of_date="2025-12-31",
                    period="one_month",
                ),
            )
        )

    assert row.status == "failed"
    assert failed_messages == ["Unexpected analytics export processing failure."]


@pytest.mark.asyncio
async def test_get_export_result_json_error_branches() -> None:
    service = make_service()
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=None))
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_json("missing")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(return_value=SimpleNamespace(status="running", result_payload={}))
    )
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_json("running")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(return_value=SimpleNamespace(status="completed", result_payload="bad"))
    )
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_json("bad")


@pytest.mark.asyncio
async def test_get_export_result_ndjson_error_and_plain_branches() -> None:
    service = make_service()
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=None))
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_ndjson("missing", compression="none")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(return_value=SimpleNamespace(status="running", result_payload={}))
    )
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_ndjson("running", compression="none")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(return_value=SimpleNamespace(status="completed", result_payload="bad"))
    )
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_ndjson("bad", compression="none")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(
            return_value=SimpleNamespace(
                status="completed",
                job_id="aexp_ok",
                dataset_type="portfolio_timeseries",
                result_payload={
                    "generated_at": "2026-03-01T00:00:00Z",
                    "contract_version": "rfc_063_v1",
                    "data": "bad",
                },
            )
        )
    )
    with pytest.raises(AnalyticsInputError):
        await service.get_export_result_ndjson("malformed", compression="none")

    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(
            return_value=SimpleNamespace(
                status="completed",
                job_id="aexp_ok",
                dataset_type="portfolio_timeseries",
                result_payload={
                    "generated_at": "2026-03-01T00:00:00Z",
                    "contract_version": "rfc_063_v1",
                    "data": [{"valuation_date": "2025-01-01"}],
                },
            )
        )
    )
    payload, media_type, encoding = await service.get_export_result_ndjson(
        "aexp_ok", compression="none"
    )
    assert media_type == "application/x-ndjson"
    assert encoding == "none"
    assert b'"record_type":"metadata"' in payload


@pytest.mark.asyncio
async def test_collect_export_helpers_page_through_all_tokens() -> None:
    service = make_service()
    service.get_portfolio_timeseries = AsyncMock(
        side_effect=[
            SimpleNamespace(
                observations=[SimpleNamespace(model_dump=lambda mode="json": {"d": "1"})],
                page=SimpleNamespace(next_page_token="n1"),
            ),
            SimpleNamespace(
                observations=[SimpleNamespace(model_dump=lambda mode="json": {"d": "2"})],
                page=SimpleNamespace(next_page_token=None),
            ),
        ]
    )
    rows, depth = await service._collect_portfolio_timeseries_for_export(  # pylint: disable=protected-access
        portfolio_id="P1",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            period="one_month",
        ),
    )
    assert rows == [{"d": "1"}, {"d": "2"}]
    assert depth == 2

    service.get_position_timeseries = AsyncMock(
        side_effect=[
            SimpleNamespace(
                rows=[SimpleNamespace(model_dump=lambda mode="json": {"p": "1"})],
                page=SimpleNamespace(next_page_token="n1"),
            ),
            SimpleNamespace(
                rows=[SimpleNamespace(model_dump=lambda mode="json": {"p": "2"})],
                page=SimpleNamespace(next_page_token=None),
            ),
        ]
    )
    rows_pos, depth_pos = await service._collect_position_timeseries_for_export(  # pylint: disable=protected-access
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            period="one_month",
        ),
    )
    assert rows_pos == [{"p": "1"}, {"p": "2"}]
    assert depth_pos == 2
