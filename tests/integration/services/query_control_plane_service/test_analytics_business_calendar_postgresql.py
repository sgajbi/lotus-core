"""Analytics source products must serve only their declared business calendar."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.query_control_plane_service.app.application.analytics.analytics_timeseries_service import (  # noqa: E501
    AnalyticsInputError,
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    AnalyticsWindow,
    PageRequest,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_timeseries_repository import (  # noqa: E501
    AnalyticsTimeseriesRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_unit_of_work import (  # noqa: E501
    SqlAlchemyAnalyticsUnitOfWork,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

PORTFOLIO_ID = "ANALYTICS_BUSINESS_CALENDAR_PG"
SECURITY_ID = "ANALYTICS_CALENDAR_EQUITY"
FRIDAY = date(2026, 4, 10)
WEEKEND = date(2026, 4, 11)
MONDAY = date(2026, 4, 13)
LATER_WEEKEND = date(2026, 4, 18)


class _CalendarAdmissionRaceReader:
    """Commit one calendar date immediately before a selected row read."""

    def __init__(
        self,
        delegate: AnalyticsTimeseriesRepository,
        *,
        admitted_date: date,
        intercept_method: str,
    ) -> None:
        self._delegate = delegate
        self._admitted_date = admitted_date
        self._intercept_method = intercept_method
        self._admitted = False

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    async def _admit_once(self) -> None:
        if self._admitted:
            return
        self._admitted = True
        session_factory = async_sessionmaker(
            bind=self._delegate.db.bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            session.add(BusinessDate(calendar_code="GLOBAL", date=self._admitted_date))
            await session.commit()

    async def list_position_timeseries_rows(self, **kwargs):
        if self._intercept_method == "list_position_timeseries_rows":
            await self._admit_once()
        return await self._delegate.list_position_timeseries_rows(**kwargs)

    async def list_position_observation_dates(self, **kwargs):
        if self._intercept_method == "list_position_observation_dates":
            await self._admit_once()
        return await self._delegate.list_position_observation_dates(**kwargs)

    async def list_latest_position_timeseries_before(self, **kwargs):
        if self._intercept_method == "list_latest_position_timeseries_before":
            await self._admit_once()
        return await self._delegate.list_latest_position_timeseries_before(**kwargs)

    async def get_position_snapshot_epoch(self, **kwargs):
        if self._intercept_method == "get_position_snapshot_epoch":
            await self._admit_once()
        return await self._delegate.get_position_snapshot_epoch(**kwargs)


def _position_timeseries(day: date, market_value: str) -> PositionTimeseries:
    value = Decimal(market_value)
    return PositionTimeseries(
        portfolio_id=PORTFOLIO_ID,
        security_id=SECURITY_ID,
        date=day,
        epoch=2,
        bod_market_value=value,
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=value + Decimal("1"),
        fees=Decimal("0"),
        quantity=Decimal("10"),
        cost=Decimal("100"),
    )


def _portfolio_timeseries(day: date, market_value: str) -> PortfolioTimeseries:
    value = Decimal(market_value)
    return PortfolioTimeseries(
        portfolio_id=PORTFOLIO_ID,
        date=day,
        epoch=0,
        bod_market_value=value,
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("0"),
        eod_market_value=value + Decimal("1"),
        fees=Decimal("0"),
    )


async def test_business_calendar_excludes_durable_weekend_rows_from_both_source_products(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session = async_db_session
    session.add(
        Portfolio(
            tenant_id="tenant-analytics-calendar",
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=FRIDAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="Singapore",
            client_id="CLIENT_ANALYTICS_CALENDAR",
            status="ACTIVE",
        )
    )
    session.add(
        Instrument(
            security_id=SECURITY_ID,
            name="Analytics Calendar Equity",
            isin="ANALYTICS-CALENDAR-PG",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
            sector="Information Technology",
        )
    )
    session.add_all(
        [
            BusinessDate(calendar_code="\tglobal\n", date=FRIDAY),
            BusinessDate(calendar_code="GLOBAL", date=FRIDAY),
            BusinessDate(calendar_code="GLOBAL", date=MONDAY),
        ]
    )
    session.add(
        Transaction(
            transaction_id="ANALYTICS-CALENDAR-BUY",
            portfolio_id=PORTFOLIO_ID,
            instrument_id=SECURITY_ID,
            security_id=SECURITY_ID,
            transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
            settlement_date=datetime(2026, 4, 13, 16, tzinfo=UTC),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("10"),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            currency="USD",
        )
    )
    await session.flush()
    session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=2,
            watermark_date=LATER_WEEKEND,
            status="CURRENT",
        )
    )
    session.add(
        PositionHistory(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            transaction_id="ANALYTICS-CALENDAR-BUY",
            position_date=FRIDAY,
            epoch=2,
            quantity=Decimal("10"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        )
    )
    session.add_all(
        [
            _position_timeseries(FRIDAY, "100"),
            _position_timeseries(WEEKEND, "101"),
            _position_timeseries(MONDAY, "102"),
            _position_timeseries(LATER_WEEKEND, "103"),
            _portfolio_timeseries(FRIDAY, "100"),
            _portfolio_timeseries(WEEKEND, "101"),
            _portfolio_timeseries(MONDAY, "102"),
            _portfolio_timeseries(LATER_WEEKEND, "103"),
        ]
    )
    await session.commit()

    reader = AnalyticsTimeseriesRepository(session)
    service = AnalyticsTimeseriesService(
        reader=reader,
        export_store=AnalyticsExportRepository(session),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(session),
        policy=AnalyticsRuntimePolicy(
            page_token_secret="business-calendar-pg-test",
            page_token_key_id="test",
            page_token_previous_keys={},
            page_token_ttl_seconds=900,
            export_stale_timeout_minutes=15,
            export_execution_timeout_seconds=300,
        ),
    )
    window = AnalyticsWindow(start_date=FRIDAY, end_date=LATER_WEEKEND)

    assert (
        await session.scalar(
            select(func.count())
            .select_from(PositionTimeseries)
            .where(PositionTimeseries.portfolio_id == PORTFOLIO_ID)
        )
        == 4
    )

    for zone in ("UTC", "Asia/Singapore", "America/Los_Angeles"):
        await session.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})

        assert await reader.get_latest_position_timeseries_date(PORTFOLIO_ID) == MONDAY
        assert await reader.get_latest_portfolio_timeseries_date(PORTFOLIO_ID) == MONDAY
        assert await reader.list_business_dates(
            start_date=FRIDAY,
            end_date=LATER_WEEKEND,
        ) == [FRIDAY, MONDAY]
        assert await reader.get_business_calendar_scope(
            start_date=FRIDAY,
            end_date=LATER_WEEKEND,
        ) == ([FRIDAY, MONDAY], True, None)
        assert await reader.get_business_calendar_scope(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
        ) == ([], True, None)
        assert await reader.get_business_calendar_scope(
            start_date=MONDAY,
            end_date=MONDAY,
        ) == ([MONDAY], True, FRIDAY)
        assert await reader.list_position_observation_dates(
            portfolio_id=PORTFOLIO_ID,
            start_date=FRIDAY,
            end_date=LATER_WEEKEND,
            snapshot_epoch=2,
        ) == [FRIDAY, MONDAY]

        positions = await service.get_position_timeseries(
            portfolio_id=PORTFOLIO_ID,
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date=LATER_WEEKEND,
                window=window,
                dimensions=["sector"],
            ),
        )
        assert [row.valuation_date for row in positions.rows] == [FRIDAY, MONDAY]
        assert positions.calendar_id == "business_date_calendar"
        assert positions.missing_observation_policy == "strict"
        assert positions.diagnostics.missing_dates_count == 0
        assert positions.data_quality_status == "COMPLETE"

        portfolio = await service.get_portfolio_timeseries(
            portfolio_id=PORTFOLIO_ID,
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date=LATER_WEEKEND,
                window=window,
            ),
        )
        assert [row.valuation_date for row in portfolio.observations] == [FRIDAY, MONDAY]
        assert portfolio.calendar_id == "business_date_calendar"
        assert portfolio.missing_observation_policy == "strict"
        assert portfolio.diagnostics.missing_dates_count == 0
        assert portfolio.data_quality_status == "COMPLETE"

        reference = await service.get_portfolio_reference(
            portfolio_id=PORTFOLIO_ID,
            request=PortfolioAnalyticsReferenceRequest(as_of_date=LATER_WEEKEND),
        )
        assert reference.performance_end_date == MONDAY

        historical_window = await service.get_portfolio_timeseries(
            portfolio_id=PORTFOLIO_ID,
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date=LATER_WEEKEND,
                window=AnalyticsWindow(start_date=FRIDAY, end_date=FRIDAY),
            ),
        )
        assert [row.valuation_date for row in historical_window.observations] == [FRIDAY]
        assert historical_window.performance_end_date == MONDAY

    predecessor_race_reader = _CalendarAdmissionRaceReader(
        reader,
        admitted_date=WEEKEND,
        intercept_method="list_latest_position_timeseries_before",
    )
    service.repo = predecessor_race_reader
    monday_page = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=MONDAY,
            window=AnalyticsWindow(start_date=MONDAY, end_date=MONDAY),
        ),
    )
    assert monday_page.rows[0].beginning_market_value_position_currency == Decimal("101")
    await session.execute(delete(BusinessDate).where(BusinessDate.date == WEEKEND))
    await session.commit()

    position_race_reader = _CalendarAdmissionRaceReader(
        reader,
        admitted_date=WEEKEND,
        intercept_method="list_position_timeseries_rows",
    )
    service.repo = position_race_reader
    position_before_admission = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
        ),
    )
    assert [row.valuation_date for row in position_before_admission.rows] == [FRIDAY, MONDAY]
    assert position_before_admission.diagnostics.missing_dates_count == 0
    position_after_admission = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
        ),
    )
    assert [row.valuation_date for row in position_after_admission.rows] == [
        FRIDAY,
        WEEKEND,
        MONDAY,
    ]
    await session.execute(delete(BusinessDate).where(BusinessDate.date == WEEKEND))
    await session.commit()

    portfolio_race_reader = _CalendarAdmissionRaceReader(
        reader,
        admitted_date=LATER_WEEKEND,
        intercept_method="list_position_observation_dates",
    )
    service.repo = portfolio_race_reader
    portfolio_before_admission = await service.get_portfolio_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
        ),
    )
    assert [row.valuation_date for row in portfolio_before_admission.observations] == [
        FRIDAY,
        MONDAY,
    ]
    assert portfolio_before_admission.performance_end_date == MONDAY
    assert portfolio_before_admission.diagnostics.missing_dates_count == 0
    portfolio_after_admission = await service.get_portfolio_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
        ),
    )
    assert [row.valuation_date for row in portfolio_after_admission.observations] == [
        FRIDAY,
        MONDAY,
        LATER_WEEKEND,
    ]
    await session.execute(delete(BusinessDate).where(BusinessDate.date == LATER_WEEKEND))
    await session.commit()
    service.repo = reader

    position_first_page = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(page_size=1),
        ),
    )
    portfolio_first_page = await service.get_portfolio_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(page_size=1),
        ),
    )
    assert position_first_page.page.next_page_token is not None
    assert portfolio_first_page.page.next_page_token is not None

    session.add(BusinessDate(calendar_code="GLOBAL", date=WEEKEND))
    await session.commit()

    with pytest.raises(AnalyticsInputError, match="Page token does not match request scope"):
        await service.get_position_timeseries(
            portfolio_id=PORTFOLIO_ID,
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date=LATER_WEEKEND,
                window=window,
                page=PageRequest(
                    page_size=1,
                    page_token=position_first_page.page.next_page_token,
                ),
            ),
        )
    with pytest.raises(AnalyticsInputError, match="Page token does not match request scope"):
        await service.get_portfolio_timeseries(
            portfolio_id=PORTFOLIO_ID,
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date=LATER_WEEKEND,
                window=window,
                page=PageRequest(
                    page_size=1,
                    page_token=portfolio_first_page.page.next_page_token,
                ),
            ),
        )

    await session.execute(
        delete(BusinessDate).where(BusinessDate.date.in_([FRIDAY, WEEKEND, MONDAY]))
    )
    await session.commit()
    epoch_race_reader = _CalendarAdmissionRaceReader(
        reader,
        admitted_date=date(2026, 4, 1),
        intercept_method="get_position_snapshot_epoch",
    )
    service.repo = epoch_race_reader
    fallback_during_calendar_activation = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
        ),
    )
    assert [row.valuation_date for row in fallback_during_calendar_activation.rows] == [
        FRIDAY,
        WEEKEND,
        MONDAY,
        LATER_WEEKEND,
    ]
    await session.execute(delete(BusinessDate).where(BusinessDate.date == date(2026, 4, 1)))
    await session.commit()
    service.repo = reader

    assert await reader.list_position_observation_dates(
        portfolio_id=PORTFOLIO_ID,
        start_date=FRIDAY,
        end_date=LATER_WEEKEND,
        snapshot_epoch=2,
    ) == [FRIDAY, WEEKEND, MONDAY, LATER_WEEKEND]

    fallback_position_page = await service.get_position_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(page_size=1),
        ),
    )
    fallback_portfolio_page = await service.get_portfolio_timeseries(
        portfolio_id=PORTFOLIO_ID,
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(page_size=1),
        ),
    )
    assert fallback_position_page.page.next_page_token is not None
    assert fallback_portfolio_page.page.next_page_token is not None

    session.add(BusinessDate(calendar_code="GLOBAL", date=date(2026, 4, 1)))
    await session.commit()

    for request in (
        PositionAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(
                page_size=1,
                page_token=fallback_position_page.page.next_page_token,
            ),
        ),
        PortfolioAnalyticsTimeseriesRequest(
            as_of_date=LATER_WEEKEND,
            window=window,
            page=PageRequest(
                page_size=1,
                page_token=fallback_portfolio_page.page.next_page_token,
            ),
        ),
    ):
        with pytest.raises(AnalyticsInputError, match="Page token does not match request scope"):
            if isinstance(request, PositionAnalyticsTimeseriesRequest):
                await service.get_position_timeseries(
                    portfolio_id=PORTFOLIO_ID,
                    request=request,
                )
            else:
                await service.get_portfolio_timeseries(
                    portfolio_id=PORTFOLIO_ID,
                    request=request,
                )
