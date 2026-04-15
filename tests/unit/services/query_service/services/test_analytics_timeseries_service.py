from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL
from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    AnalyticsWindow,
    CashFlowObservation,
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


def _sum_external_flows(cash_flows) -> Decimal:
    return sum(
        (flow.amount for flow in cash_flows if flow.cash_flow_type == "external_flow"),
        start=Decimal("0"),
    )


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
        list_portfolio_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    amount=Decimal("1"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    amount=Decimal("2"),
                    classification="TRANSFER",
                    timing="EOD",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    amount=Decimal("-0.5"),
                    classification="EXPENSE",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
            ]
        ),
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
    assert response.observations[0].cash_flows[0].cash_flow_type == "external_flow"
    assert response.observations[0].cash_flows[0].flow_scope == "external"
    assert response.observations[0].cash_flows[1].cash_flow_type == "transfer"
    assert response.observations[0].cash_flows[1].flow_scope == "external"
    assert response.observations[0].cash_flows[2].cash_flow_type == "fee"
    assert response.observations[0].cash_flows[2].source_classification == "EXPENSE"
    assert response.observations[0].cash_flow_currency == "EUR"
    assert response.diagnostics.expected_business_dates_count == 1
    assert response.diagnostics.returned_observation_dates_count == 1
    assert response.diagnostics.cash_flows_included is True
    assert response.page.sort_key == "valuation_date:asc"
    assert response.product_name == "PortfolioTimeseriesInput"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2025, 12, 31)
    assert response.generated_at == response.lineage.generated_at
    assert response.restatement_version == "current"
    assert response.reconciliation_status == "UNKNOWN"
    assert response.data_quality_status == "COMPLETE"
    assert response.tenant_id is None
    assert response.snapshot_id is None
    assert response.policy_version is None


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_tracks_missing_business_dates_and_reporting_currency() -> (
    None
):
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
        list_portfolio_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 2),
                    amount=Decimal("5"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                )
            ]
        ),
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
    assert response.observations[0].cash_flows[0].flow_scope == "external"
    assert response.observations[0].cash_flow_currency == "USD"
    assert response.diagnostics.missing_dates_count == 1
    assert response.diagnostics.stale_points_count == 1
    assert response.data_quality_status == "STALE"


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_cash_only_staged_external_flows_are_not_doubled() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P_STAGE",
                base_currency="USD",
                open_date=date(2026, 3, 1),
                close_date=None,
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2026, 3, 16),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("10000"),
                    bod_cashflow=Decimal("10000"),
                    eod_cashflow=Decimal("0"),
                    fees=Decimal("0"),
                    epoch=0,
                ),
                SimpleNamespace(
                    valuation_date=date(2026, 3, 18),
                    bod_market_value=Decimal("10000"),
                    eod_market_value=Decimal("15000"),
                    bod_cashflow=Decimal("5000"),
                    eod_cashflow=Decimal("0"),
                    fees=Decimal("0"),
                    epoch=0,
                ),
                SimpleNamespace(
                    valuation_date=date(2026, 3, 19),
                    bod_market_value=Decimal("15000"),
                    eod_market_value=Decimal("13000"),
                    bod_cashflow=Decimal("0"),
                    eod_cashflow=Decimal("-2000"),
                    fees=Decimal("0"),
                    epoch=0,
                ),
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2026, 3, 20)),
        get_portfolio_snapshot_epoch=AsyncMock(return_value=0),
        list_business_dates=AsyncMock(
            return_value=[date(2026, 3, day) for day in (16, 17, 18, 19, 20)]
        ),
        list_portfolio_observation_dates=AsyncMock(
            return_value=[date(2026, 3, day) for day in (16, 18, 19)]
        ),
        list_portfolio_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    transaction_id="DEP_1",
                    valuation_date=date(2026, 3, 16),
                    amount=Decimal("10000"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    transaction_id="DEP_2",
                    valuation_date=date(2026, 3, 18),
                    amount=Decimal("5000"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    transaction_id="WD_1",
                    valuation_date=date(2026, 3, 19),
                    amount=Decimal("-2000"),
                    classification="CASHFLOW_OUT",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
            ]
        ),
    )

    response = await service.get_portfolio_timeseries(
        portfolio_id="P_STAGE",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2026-03-20",
            window=AnalyticsWindow(start_date="2026-03-16", end_date="2026-03-20"),
            reporting_currency="USD",
        ),
    )

    external_flows_by_date = {
        observation.valuation_date.isoformat(): _sum_external_flows(observation.cash_flows)
        for observation in response.observations
    }
    assert external_flows_by_date == {
        "2026-03-16": Decimal("10000"),
        "2026-03-18": Decimal("5000"),
        "2026-03-19": Decimal("-2000"),
    }


@pytest.mark.asyncio
async def test_portfolio_observation_rows_aggregates_position_rows_with_fx_and_next_page_token() -> (
    None
):
    service = make_service()
    service.repo = SimpleNamespace(
        get_position_snapshot_epoch=AsyncMock(return_value=4),
        list_position_timeseries_rows_unpaged=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_USD",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    epoch=0,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_EUR",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("50"),
                    eod_market_value=Decimal("60"),
                    epoch=1,
                    position_currency="EUR",
                ),
                SimpleNamespace(
                    security_id="SEC_USD",
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("110"),
                    eod_market_value=Decimal("120"),
                    epoch=0,
                    position_currency="USD",
                ),
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("5"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                )
            ]
        ),
        list_position_cashflow_rows=AsyncMock(return_value=[]),
        get_fx_rates_map=AsyncMock(
            side_effect=[
                {date(2025, 1, 1): Decimal("1.2")},
                {date(2025, 1, 1): Decimal("1.5")},
            ]
        ),
    )

    (
        observations,
        quality_distribution,
        observed_dates,
        snapshot_epoch,
        next_page_token,
    ) = await service._portfolio_observation_rows(  # pylint: disable=protected-access
        portfolio_id="P1",
        portfolio_currency="USD",
        reporting_currency="SGD",
        resolved_window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-02"),
        page_size=1,
        cursor_date=None,
        request_scope_fingerprint="scope-1",
    )

    assert snapshot_epoch == 4
    assert observed_dates == [date(2025, 1, 1), date(2025, 1, 2)]
    assert quality_distribution == {"restated": 1}
    assert observations[0].beginning_market_value == Decimal("240.0")
    assert observations[0].ending_market_value == Decimal("273.0")
    assert observations[0].cash_flows[0].amount == Decimal("7.5")
    assert observations[0].valuation_status == "restated"
    assert next_page_token is not None
    token_payload = service._decode_page_token(next_page_token)  # pylint: disable=protected-access
    assert token_payload["valuation_date"] == "2025-01-01"
    assert token_payload["snapshot_epoch"] == 4


@pytest.mark.asyncio
async def test_portfolio_observation_rows_repairs_day_boundary_capital_continuity() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_position_snapshot_epoch=AsyncMock(return_value=14),
        list_position_timeseries_rows_unpaged=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EXISTING",
                    valuation_date=date(2025, 5, 18),
                    bod_market_value=Decimal("95"),
                    eod_market_value=Decimal("100"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=1,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 18),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("0"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=1,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 18),
                    bod_market_value=Decimal("70"),
                    eod_market_value=Decimal("75"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=1,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_EXISTING",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("105"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=1,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("50"),
                    bod_cashflow_position=Decimal("50"),
                    epoch=1,
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("101"),
                    bod_cashflow_position=Decimal("25"),
                    epoch=1,
                    position_currency="USD",
                ),
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(return_value=[]),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 19),
                    amount=Decimal("-50"),
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 19),
                    amount=Decimal("25"),
                    classification="INVESTMENT_INFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )

    observations, _, _, _, _ = await service._portfolio_observation_rows(  # pylint: disable=protected-access
        portfolio_id="P1",
        portfolio_currency="USD",
        reporting_currency="USD",
        resolved_window=AnalyticsWindow(start_date="2025-05-18", end_date="2025-05-19"),
        page_size=10,
        cursor_date=None,
        request_scope_fingerprint="scope-1",
    )

    second_observation = next(
        observation
        for observation in observations
        if observation.valuation_date == date(2025, 5, 19)
    )
    assert second_observation.beginning_market_value == Decimal("250")
    assert second_observation.ending_market_value == Decimal("256")


@pytest.mark.asyncio
async def test_portfolio_observation_rows_neutralizes_internal_cash_book_settlement() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_position_snapshot_epoch=AsyncMock(return_value=14),
        list_position_timeseries_rows_unpaged=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EXISTING",
                    valuation_date=date(2026, 2, 27),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("100"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=14,
                    asset_class="Equity",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="CASH_USD_BOOK_OPERATING",
                    valuation_date=date(2026, 2, 27),
                    bod_market_value=Decimal("-100"),
                    eod_market_value=Decimal("-100"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=14,
                    asset_class="Cash",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_EXISTING",
                    valuation_date=date(2026, 2, 28),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("100"),
                    bod_cashflow_position=Decimal("0"),
                    epoch=14,
                    asset_class="Equity",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="CASH_USD_BOOK_OPERATING",
                    valuation_date=date(2026, 2, 28),
                    bod_market_value=Decimal("-100"),
                    eod_market_value=Decimal("100"),
                    bod_cashflow_position=Decimal("200"),
                    epoch=14,
                    asset_class="Cash",
                    position_currency="USD",
                ),
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(return_value=[]),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="CASH_USD_BOOK_OPERATING",
                    valuation_date=date(2026, 2, 28),
                    amount=Decimal("-200"),
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )

    observations, _, _, _, _ = await service._portfolio_observation_rows(  # pylint: disable=protected-access
        portfolio_id="P1",
        portfolio_currency="USD",
        reporting_currency="USD",
        resolved_window=AnalyticsWindow(start_date="2026-02-27", end_date="2026-02-28"),
        page_size=10,
        cursor_date=None,
        request_scope_fingerprint="scope-1",
    )

    second_observation = next(
        observation
        for observation in observations
        if observation.valuation_date == date(2026, 2, 28)
    )
    assert second_observation.beginning_market_value == Decimal("200")
    assert second_observation.ending_market_value == Decimal("200")


def test_effective_beginning_market_value_keeps_cash_book_fee_drag_explicit() -> None:
    service = make_service()
    row = SimpleNamespace(
        security_id="CASH_USD_BOOK_OPERATING",
        asset_class="Cash",
        bod_market_value=Decimal("100"),
        eod_market_value=Decimal("99.725"),
        bod_cashflow_position=Decimal("0"),
    )
    fee_flow = CashFlowObservation(
        amount=Decimal("-0.275"),
        timing="eod",
        cash_flow_type="fee",
        flow_scope="operational",
        source_classification="EXPENSE",
    )

    result = service._effective_beginning_market_value(  # pylint: disable=protected-access
        row,
        previous_eod_market_value=Decimal("100"),
        cash_flows=[fee_flow],
        has_portfolio_external_flow=False,
    )

    assert result == Decimal("100")


@pytest.mark.asyncio
async def test_portfolio_observation_rows_raises_when_position_fx_missing() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_position_snapshot_epoch=AsyncMock(return_value=1),
        list_position_timeseries_rows_unpaged=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EUR",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    epoch=0,
                    position_currency="EUR",
                )
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(return_value=[]),
        list_position_cashflow_rows=AsyncMock(return_value=[]),
        get_fx_rates_map=AsyncMock(side_effect=[{}, {}]),
    )

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service._portfolio_observation_rows(  # pylint: disable=protected-access
            portfolio_id="P1",
            portfolio_currency="USD",
            reporting_currency="USD",
            resolved_window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-01"),
            page_size=10,
            cursor_date=None,
            request_scope_fingerprint="scope-1",
        )

    assert exc_info.value.code == "INSUFFICIENT_DATA"


def test_portfolio_cash_flows_for_dates_requires_reporting_fx_when_needed() -> None:
    service = make_service()
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._portfolio_cash_flows_for_dates(  # pylint: disable=protected-access
            [
                SimpleNamespace(
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("5"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                )
            ],
            reporting_currency="USD",
            portfolio_currency="EUR",
            fx_rates={},
        )

    assert exc_info.value.code == "INSUFFICIENT_DATA"


def test_position_cash_flows_for_keys_preserves_non_position_amounts() -> None:
    service = make_service()
    result = service._position_cash_flows_for_keys(  # pylint: disable=protected-access
        [
            SimpleNamespace(
                security_id="SEC_A",
                valuation_date=date(2025, 1, 1),
                amount=Decimal("5"),
                classification="TRANSFER",
                timing="BOD",
                is_position_flow=False,
                is_portfolio_flow=True,
            )
        ]
    )

    assert result[("SEC_A", date(2025, 1, 1))][0].amount == Decimal("5")
    assert result[("SEC_A", date(2025, 1, 1))][0].cash_flow_type == "transfer"


def test_timeseries_data_quality_status_classifies_empty_and_missing_windows() -> None:
    assert (
        AnalyticsTimeseriesService._timeseries_data_quality_status(  # pylint: disable=protected-access
            required_count=0,
            observed_count=0,
            stale_count=0,
        )
        == "UNKNOWN"
    )
    assert (
        AnalyticsTimeseriesService._timeseries_data_quality_status(  # pylint: disable=protected-access
            required_count=3,
            observed_count=2,
            stale_count=0,
        )
        == "PARTIAL"
    )


def test_resolve_window_supports_long_periods_and_clamps_to_inception() -> None:
    service = make_service()

    assert service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 12, 31),
        window=None,
        period="three_years",
        inception_date=date(2025, 1, 1),
    ) == AnalyticsWindow(start_date="2025-01-01", end_date="2025-12-31")
    assert service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 12, 31),
        window=None,
        period="five_years",
        inception_date=date(2020, 1, 1),
    ) == AnalyticsWindow(start_date="2021-01-01", end_date="2025-12-31")
    assert service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 12, 31),
        window=None,
        period="inception",
        inception_date=date(2020, 1, 1),
    ) == AnalyticsWindow(start_date="2020-01-01", end_date="2025-12-31")


def test_resolve_window_rejects_inverted_window_and_supports_ytd() -> None:
    service = make_service()

    assert service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 12, 31),
        window=None,
        period="ytd",
        inception_date=date(2020, 1, 1),
    ) == AnalyticsWindow(start_date="2025-01-01", end_date="2025-12-31")

    with pytest.raises(AnalyticsInputError) as exc_info:
        service._resolve_window(  # pylint: disable=protected-access
            as_of_date=date(2025, 1, 10),
            window=AnalyticsWindow(start_date="2025-01-11", end_date="2025-01-12"),
            period=None,
            inception_date=date(2020, 1, 1),
        )

    assert exc_info.value.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_fallback_path_defaults_snapshot_epoch_and_pages() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                close_date=None,
            )
        ),
        list_business_dates=AsyncMock(return_value=[date(2025, 1, 1), date(2025, 1, 2)]),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    epoch=0,
                ),
                SimpleNamespace(
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("110"),
                    eod_market_value=Decimal("120"),
                    epoch=0,
                ),
            ]
        ),
        list_portfolio_observation_dates=AsyncMock(
            return_value=[date(2025, 1, 1), date(2025, 1, 2)]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 1, 2)),
    )

    response = await service.get_portfolio_timeseries(
        portfolio_id="P1",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-01-02",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-02"),
            page=PageRequest(page_size=1),
            reporting_currency="USD",
        ),
    )

    assert len(response.observations) == 1
    assert response.page.snapshot_epoch == 0
    assert response.page.next_page_token is not None
    token_payload = service._decode_page_token(response.page.next_page_token)  # pylint: disable=protected-access
    assert token_payload["snapshot_epoch"] == 0


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
    assert response.product_name == "PositionTimeseriesInput"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2025, 12, 31)
    assert response.generated_at == response.lineage.generated_at
    assert response.restatement_version == "current"
    assert response.reconciliation_status == "UNKNOWN"
    assert response.data_quality_status == "PARTIAL"
    assert response.tenant_id is None
    assert response.snapshot_id is None
    assert response.policy_version is None


@pytest.mark.asyncio
async def test_get_position_timeseries_rejects_scope_mismatch() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                close_date=None,
            )
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {
            "valuation_date": "2025-01-01",
            "security_id": "SEC_A",
            "snapshot_epoch": 7,
            "scope_fingerprint": "wrong",
        }
    )

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_position_timeseries(
            portfolio_id="P1",
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-01-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
                page=PageRequest(page_size=10, page_token=token),
            ),
        )

    assert exc_info.value.code == "INVALID_REQUEST"


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
                updated_at=datetime(2025, 12, 30, 9, 0, tzinfo=UTC),
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
    assert response.product_name == "PortfolioAnalyticsReference"
    assert response.product_version == "v1"
    assert response.generated_at == response.lineage.generated_at
    assert response.as_of_date == date(2025, 12, 31)
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == datetime(2025, 12, 30, 9, 0, tzinfo=UTC)


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
async def test_get_portfolio_reference_marks_missing_performance_horizon_partial() -> None:
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
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=None),
    )
    response = await service.get_portfolio_reference(
        portfolio_id="P1",
        request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-06-30"),
    )

    assert response.performance_end_date is None
    assert response.data_quality_status == PARTIAL
    assert response.latest_evidence_timestamp is None


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
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("-1"),
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("2"),
                    classification="CASHFLOW_IN",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("-0.1"),
                    classification="EXPENSE",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
            ]
        ),
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
    assert response.rows[0].cash_flows[0].amount == Decimal("1")
    assert response.rows[0].cash_flows[0].cash_flow_type == "internal_trade_flow"
    assert response.rows[0].cash_flows[0].flow_scope == "internal"
    assert response.rows[0].cash_flows[1].cash_flow_type == "external_flow"
    assert response.rows[0].cash_flows[1].flow_scope == "external"
    assert response.rows[0].cash_flows[2].cash_flow_type == "fee"
    assert response.diagnostics.cash_flows_included is True
    assert response.diagnostics.requested_dimensions == ["asset_class", "sector", "country"]
    assert response.diagnostics.stale_points_count == 1
    assert response.data_quality_status == "STALE"
    assert response.rows[0].cash_flow_currency == "USD"
    assert response.rows[0].portfolio_to_reporting_fx_rate == Decimal("1.2")


@pytest.mark.asyncio
async def test_get_position_timeseries_distinguishes_internal_trade_flows_from_external_funding() -> (
    None
):
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
                    security_id="SEC_EUR_STOCK",
                    valuation_date=date(2026, 3, 16),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("5720"),
                    bod_cashflow_position=Decimal("5000"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("100"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="DE",
                    position_currency="EUR",
                ),
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 16),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("14500"),
                    bod_cashflow_position=Decimal("20000"),
                    eod_cashflow_position=Decimal("-5500"),
                    bod_cashflow_portfolio=Decimal("20000"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("14500"),
                    epoch=0,
                    asset_class="Cash",
                    sector=None,
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=0),
        get_fx_rates_map=AsyncMock(return_value={date(2026, 3, 16): Decimal("1.1")}),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EUR_STOCK",
                    valuation_date=date(2026, 3, 16),
                    amount=Decimal("-5000"),
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 16),
                    amount=Decimal("20000"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 16),
                    amount=Decimal("-5500"),
                    classification="TRANSFER",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
            ]
        ),
    )

    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2026-03-16",
            window=AnalyticsWindow(start_date="2026-03-16", end_date="2026-03-16"),
            include_cash_flows=True,
        ),
    )

    stock_row = next(row for row in response.rows if row.security_id == "SEC_EUR_STOCK")
    cash_row = next(row for row in response.rows if row.security_id == "CASH_USD")

    assert [
        (flow.amount, flow.cash_flow_type, flow.flow_scope) for flow in stock_row.cash_flows
    ] == [(Decimal("5000"), "internal_trade_flow", "internal")]
    assert [
        (flow.amount, flow.cash_flow_type, flow.flow_scope) for flow in cash_row.cash_flows
    ] == [
        (Decimal("20000"), "external_flow", "external"),
        (Decimal("-5500"), "internal_trade_flow", "internal"),
    ]


@pytest.mark.asyncio
async def test_get_position_timeseries_repairs_beginning_values_for_continuity() -> None:
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
                    security_id="SEC_EXISTING",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("105"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("10"),
                    epoch=1,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("50"),
                    bod_cashflow_position=Decimal("50"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("5"),
                    epoch=1,
                    asset_class="Fund",
                    sector=None,
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("101"),
                    bod_cashflow_position=Decimal("25"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=1,
                    asset_class="Fund",
                    sector=None,
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        list_latest_position_timeseries_before=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_EXISTING",
                    valuation_date=date(2025, 5, 18),
                    eod_market_value=Decimal("100"),
                    epoch=1,
                ),
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 18),
                    eod_market_value=Decimal("0"),
                    epoch=1,
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 18),
                    eod_market_value=Decimal("75"),
                    epoch=1,
                ),
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=14),
        get_fx_rates_map=AsyncMock(return_value={}),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_NEW_INTERNAL",
                    valuation_date=date(2025, 5, 19),
                    amount=Decimal("-50"),
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                SimpleNamespace(
                    security_id="SEC_INTERNAL_BOD_CARRY",
                    valuation_date=date(2025, 5, 19),
                    amount=Decimal("25"),
                    classification="INVESTMENT_INFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(return_value=[]),
    )

    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-05-19",
            window=AnalyticsWindow(start_date="2025-05-19", end_date="2025-05-19"),
            include_cash_flows=True,
        ),
    )

    existing = next(row for row in response.rows if row.security_id == "SEC_EXISTING")
    new_internal = next(row for row in response.rows if row.security_id == "SEC_NEW_INTERNAL")
    internal_bod_carry = next(
        row for row in response.rows if row.security_id == "SEC_INTERNAL_BOD_CARRY"
    )

    assert existing.beginning_market_value_position_currency == Decimal("100")
    assert existing.ending_market_value_position_currency == Decimal("105")
    assert new_internal.beginning_market_value_position_currency == Decimal("50")
    assert new_internal.ending_market_value_position_currency == Decimal("50")
    assert internal_bod_carry.beginning_market_value_position_currency == Decimal("100")
    assert internal_bod_carry.ending_market_value_position_currency == Decimal("101")


@pytest.mark.asyncio
async def test_get_position_timeseries_does_not_carry_beginning_across_absent_dates() -> None:
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
                    security_id="SEC_GAPPED",
                    valuation_date=date(2025, 5, 19),
                    bod_market_value=Decimal("95"),
                    eod_market_value=Decimal("100"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("10"),
                    epoch=1,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_OTHER",
                    valuation_date=date(2025, 5, 20),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("10"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=1,
                    asset_class="Cash",
                    sector=None,
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_GAPPED",
                    valuation_date=date(2025, 5, 21),
                    bod_market_value=Decimal("120"),
                    eod_market_value=Decimal("50"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("5"),
                    epoch=1,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        list_latest_position_timeseries_before=AsyncMock(return_value=[]),
        get_position_snapshot_epoch=AsyncMock(return_value=14),
        get_fx_rates_map=AsyncMock(return_value={}),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_GAPPED",
                    valuation_date=date(2025, 5, 21),
                    amount=Decimal("50"),
                    classification="INVESTMENT_INFLOW",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                )
            ]
        ),
        list_portfolio_cashflow_rows=AsyncMock(return_value=[]),
    )

    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-05-21",
            window=AnalyticsWindow(start_date="2025-05-19", end_date="2025-05-21"),
            include_cash_flows=True,
        ),
    )

    reappearing = next(
        row
        for row in response.rows
        if row.security_id == "SEC_GAPPED" and row.valuation_date == date(2025, 5, 21)
    )

    assert reappearing.beginning_market_value_position_currency == Decimal("50")
    assert reappearing.ending_market_value_position_currency == Decimal("50")


@pytest.mark.asyncio
async def test_get_position_timeseries_cash_only_staged_external_flows_are_not_doubled() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P_STAGE",
                base_currency="USD",
                open_date=date(2026, 3, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 16),
                    bod_market_value=Decimal("0"),
                    eod_market_value=Decimal("10000"),
                    bod_cashflow_position=Decimal("10000"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("10000"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("10000"),
                    epoch=0,
                    asset_class="Cash",
                    sector="Cash",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 18),
                    bod_market_value=Decimal("10000"),
                    eod_market_value=Decimal("15000"),
                    bod_cashflow_position=Decimal("5000"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("5000"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("15000"),
                    epoch=0,
                    asset_class="Cash",
                    sector="Cash",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 19),
                    bod_market_value=Decimal("15000"),
                    eod_market_value=Decimal("13000"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("-2000"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("-2000"),
                    fees=Decimal("0"),
                    quantity=Decimal("13000"),
                    epoch=0,
                    asset_class="Cash",
                    sector="Cash",
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        get_position_snapshot_epoch=AsyncMock(return_value=0),
        get_fx_rates_map=AsyncMock(return_value={}),
        list_position_cashflow_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    transaction_id="DEP_1",
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 16),
                    amount=Decimal("10000"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    transaction_id="DEP_2",
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 18),
                    amount=Decimal("5000"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
                SimpleNamespace(
                    transaction_id="WD_1",
                    security_id="CASH_USD",
                    valuation_date=date(2026, 3, 19),
                    amount=Decimal("-2000"),
                    classification="CASHFLOW_OUT",
                    timing="EOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                ),
            ]
        ),
    )

    response = await service.get_position_timeseries(
        portfolio_id="P_STAGE",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2026-03-20",
            window=AnalyticsWindow(start_date="2026-03-16", end_date="2026-03-20"),
            reporting_currency="USD",
            include_cash_flows=True,
            page=PageRequest(page_size=10),
        ),
    )

    external_flows_by_date = {
        row.valuation_date.isoformat(): _sum_external_flows(row.cash_flows) for row in response.rows
    }
    assert external_flows_by_date == {
        "2026-03-16": Decimal("10000"),
        "2026-03-18": Decimal("5000"),
        "2026-03-19": Decimal("-2000"),
    }


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
async def test_get_position_timeseries_converts_position_values_to_portfolio_and_reporting_currency() -> (
    None
):
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
    assert response.disposition == "created"
    assert response.lifecycle_mode == "inline_job_execution"
    assert response.result_available is True
    assert response.result_endpoint.endswith("/aexp_1/result")


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
    assert response.disposition == "reused_completed"
    assert response.result_available is True


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
    assert response.disposition == "reused_inflight"
    assert response.result_available is False


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
    assert response.disposition == "created"
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
    assert response.disposition == "created"
    assert response.result_available is False


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
async def test_get_export_result_json_success_and_export_job_state_helpers() -> None:
    service = make_service()
    completed_row = SimpleNamespace(
        job_id="aexp_ok",
        status="completed",
        result_payload={
            "job_id": "aexp_ok",
            "dataset_type": "portfolio_timeseries",
            "request_fingerprint": "fp-ok",
            "lifecycle_mode": "inline_job_execution",
            "generated_at": "2026-03-01T00:00:00+00:00",
            "contract_version": "rfc_063_v1",
            "result_row_count": 1,
            "data": [{"valuation_date": "2025-01-01"}],
        },
    )
    running_row = SimpleNamespace(job_id="aexp_ok", status="accepted", result_payload={})
    service.export_repo = SimpleNamespace(
        get_job=AsyncMock(side_effect=[completed_row, running_row, running_row, running_row]),
        mark_running=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(),
    )

    response = await service.get_export_result_json("aexp_ok")
    assert response.job_id == "aexp_ok"
    assert response.result_row_count == 1

    assert await service._mark_export_job_running("aexp_ok") is running_row  # pylint: disable=protected-access
    assert (
        await service._mark_export_job_completed(  # pylint: disable=protected-access
            "aexp_ok",
            result_payload=completed_row.result_payload,
            result_row_count=1,
        )
        is running_row
    )
    assert (
        await service._mark_export_job_failed(  # pylint: disable=protected-access
            "aexp_ok",
            error_message="boom",
        )
        is running_row
    )
    service.export_repo.mark_running.assert_awaited_once_with(running_row)
    service.export_repo.mark_completed.assert_awaited_once()
    service.export_repo.mark_failed.assert_awaited_once_with(running_row, error_message="boom")


@pytest.mark.asyncio
async def test_export_job_state_helpers_raise_when_job_missing() -> None:
    service = make_service()
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=None))

    with pytest.raises(AnalyticsInputError):
        await service._mark_export_job_running("missing")  # pylint: disable=protected-access
    with pytest.raises(AnalyticsInputError):
        await service._mark_export_job_completed(  # pylint: disable=protected-access
            "missing",
            result_payload={},
            result_row_count=0,
        )
    with pytest.raises(AnalyticsInputError):
        await service._mark_export_job_failed(  # pylint: disable=protected-access
            "missing",
            error_message="boom",
        )


@pytest.mark.asyncio
async def test_get_export_job_status_lookup_contract() -> None:
    service = make_service()
    row = SimpleNamespace(
        job_id="aexp_status",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="running",
        request_fingerprint="fp-status",
        result_format="json",
        compression="none",
        result_row_count=None,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        completed_at=None,
        result_payload=None,
    )
    service.export_repo = SimpleNamespace(get_job=AsyncMock(return_value=row))
    response = await service.get_export_job("aexp_status")
    assert response.disposition == "status_lookup"
    assert response.lifecycle_mode == "inline_job_execution"
    assert response.result_available is False
    assert response.result_endpoint.endswith("/aexp_status/result")


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
