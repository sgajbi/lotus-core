from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.reporting_dto import (
    AssetAllocationQueryRequest,
    AssetsUnderManagementQueryRequest,
    BulkPortfolioSummaryQueryRequest,
    PortfolioSummaryQueryRequest,
    ReportingScope,
)
from src.services.query_service.app.repositories.reporting_repository import (
    InstrumentLookthroughComponentRow,
    ReportingSnapshotRow,
    SnapshotPresence,
)
from src.services.query_service.app.services.reporting_service import (
    ReportingService,
    _aum_coverage_state,
)

pytestmark = pytest.mark.asyncio


def _portfolio(
    portfolio_id: str,
    *,
    base_currency: str = "USD",
    booking_center_code: str = "SGPB",
    client_id: str = "CIF-1",
):
    return SimpleNamespace(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        booking_center_code=booking_center_code,
        client_id=client_id,
    )


def _instrument(
    security_id: str,
    *,
    name: str = "Instrument",
    currency: str = "USD",
    asset_class: str | None = "EQUITY",
    sector: str | None = "TECH",
    country_of_risk: str | None = "US",
    product_type: str | None = "EQUITY",
    rating: str | None = None,
    issuer_id: str | None = None,
    issuer_name: str | None = None,
    ultimate_parent_issuer_id: str | None = None,
    ultimate_parent_issuer_name: str | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        name=name,
        currency=currency,
        asset_class=asset_class,
        sector=sector,
        country_of_risk=country_of_risk,
        product_type=product_type,
        rating=rating,
        issuer_id=issuer_id,
        issuer_name=issuer_name,
        ultimate_parent_issuer_id=ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=ultimate_parent_issuer_name,
    )


def _snapshot(
    security_id: str,
    *,
    market_value: str,
    snapshot_id: int = 1,
    market_value_local: str | None = None,
    quantity: str = "1",
    valuation_status: str | None = "VALUED",
    snapshot_date: date = date(2026, 3, 27),
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        id=snapshot_id,
        security_id=security_id,
        date=snapshot_date,
        market_value=Decimal(market_value),
        market_value_local=Decimal(market_value_local or market_value),
        quantity=Decimal(quantity),
        valuation_status=valuation_status,
        created_at=created_at,
        updated_at=updated_at,
    )


async def test_get_assets_under_management_defaults_to_portfolio_currency_for_single_scope() -> (
    None
):
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency=" usd ")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", sector="HEALTHCARE"),
        ),
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_assets_under_management(
            AssetsUnderManagementQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
            )
        )

    assert response.reporting_currency == "USD"
    assert response.totals.aum_reporting_currency == Decimal("150")
    assert response.totals.position_count == 2
    assert response.portfolios[0].portfolio_currency == "USD"
    assert response.portfolios[0].aum_portfolio_currency == Decimal("150")
    assert response.portfolios[0].snapshot_found is True
    assert response.portfolios[0].snapshot_date == date(2026, 3, 27)
    assert response.portfolios[0].coverage_state == "MEASURED"


@pytest.mark.parametrize(
    ("rows", "presence", "expected"),
    [
        ([], None, "NO_SNAPSHOT"),
        ([], SnapshotPresence(snapshot_date=date(2026, 3, 26), row_count=1), "LOADED_EMPTY"),
        (
            [ReportingSnapshotRow(_portfolio("P1"), _snapshot("SEC1", market_value="0"), None)],
            SnapshotPresence(date(2026, 3, 27), 1),
            "MEASURED_ZERO",
        ),
        (
            [ReportingSnapshotRow(_portfolio("P1"), _snapshot("SEC1", market_value="10"), None)],
            SnapshotPresence(date(2026, 3, 27), 1),
            "MEASURED",
        ),
        (
            [
                ReportingSnapshotRow(
                    _portfolio("P1"),
                    SimpleNamespace(market_value=None, date=date(2026, 3, 27)),
                    None,
                )
            ],
            SnapshotPresence(date(2026, 3, 27), 1),
            "UNAVAILABLE",
        ),
        (
            [
                ReportingSnapshotRow(
                    _portfolio("P1"),
                    _snapshot("SEC1", market_value="10", snapshot_date=date(2026, 3, 26)),
                    None,
                )
            ],
            SnapshotPresence(date(2026, 3, 26), 1),
            "CARRY_FORWARD",
        ),
        (
            [
                ReportingSnapshotRow(
                    _portfolio("P1"),
                    _snapshot("SEC1", market_value="0", snapshot_date=date(2026, 3, 26)),
                    None,
                )
            ],
            SnapshotPresence(date(2026, 3, 26), 1),
            "CARRY_FORWARD",
        ),
        (
            [ReportingSnapshotRow(_portfolio("P1"), _snapshot("SEC1", market_value="10"), None)],
            SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=2),
            "UNAVAILABLE",
        ),
        (
            [
                ReportingSnapshotRow(
                    _portfolio("P1"),
                    _snapshot("SEC1", market_value="10", snapshot_date=date(2026, 3, 27)),
                    None,
                ),
                ReportingSnapshotRow(
                    _portfolio("P1"),
                    _snapshot("SEC2", market_value="5", snapshot_date=date(2026, 3, 26)),
                    None,
                ),
            ],
            SnapshotPresence(date(2026, 3, 27), 2, expected_open_count=2),
            "CARRY_FORWARD",
        ),
    ],
)
async def test_aum_coverage_state_preserves_source_presence_and_zero_semantics(
    rows: list[ReportingSnapshotRow],
    presence: SnapshotPresence | None,
    expected: str,
) -> None:
    assert (
        _aum_coverage_state(
            rows=rows,
            presence=presence,
            resolved_as_of_date=date(2026, 3, 27),
        )
        == expected
    )


async def test_get_assets_under_management_publishes_presence_for_empty_portfolio() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = []
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(snapshot_date=date(2026, 3, 26), row_count=2)
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_assets_under_management(
            AssetsUnderManagementQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
            )
        )

    summary = response.portfolios[0]
    assert summary.aum_reporting_currency == Decimal("0")
    assert summary.position_count == 0
    assert summary.snapshot_found is True
    assert summary.snapshot_date == date(2026, 3, 26)
    assert summary.coverage_state == "LOADED_EMPTY"


async def test_get_assets_under_management_converts_snapshot_rows_sequentially() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2"),
        ),
    ]
    call_order: list[Decimal] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(amount)
        assert from_currency == "USD"
        assert to_currency == "SGD"
        assert as_of_date == date(2026, 3, 27)
        return amount * Decimal("1.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._convert_amount = AsyncMock(side_effect=convert_amount)  # type: ignore[method-assign]
        response = await service.get_assets_under_management(
            AssetsUnderManagementQueryRequest(
                scope=ReportingScope(portfolio_ids=["P1"]),
                reporting_currency="SGD",
            )
        )

    assert response.totals.aum_reporting_currency == Decimal("225.0")
    assert call_order == [Decimal("100"), Decimal("50")]


async def test_get_asset_allocation_groups_requested_dimensions_with_fx_conversion() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1", asset_class="EQUITY", sector="TECH", currency="USD"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="40"),
            instrument=_instrument("SEC2", asset_class="BOND", sector="RATES", currency="EUR"),
        ),
    ]
    repo.get_latest_fx_rate.side_effect = lambda **kwargs: Decimal("1.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_asset_allocation(
            AssetAllocationQueryRequest(
                scope=ReportingScope(portfolio_ids=["P1"]),
                reporting_currency="SGD",
                dimensions=["asset_class", "currency"],
            )
        )

    assert response.reporting_currency == "SGD"
    assert response.total_market_value_reporting_currency == Decimal("210")
    asset_class_view = next(view for view in response.views if view.dimension == "asset_class")
    equity_bucket = next(
        bucket for bucket in asset_class_view.buckets if bucket.dimension_value == "EQUITY"
    )
    bond_bucket = next(
        bucket for bucket in asset_class_view.buckets if bucket.dimension_value == "BOND"
    )
    assert equity_bucket.market_value_reporting_currency == Decimal("150")
    assert bond_bucket.market_value_reporting_currency == Decimal("60")
    assert equity_bucket.contributor_count == 1
    assert equity_bucket.contributors[0].contributor_type == "direct_position"
    assert equity_bucket.contributors[0].portfolio_id == "P1"
    assert equity_bucket.contributors[0].security_id == "SEC1"
    assert equity_bucket.contributors[0].booked_security_id == "SEC1"
    assert equity_bucket.contributors[0].source_snapshot_id == 1
    assert equity_bucket.omitted_market_value_reporting_currency == Decimal("0")
    assert response.calculation_lineage.algorithm_id == "PORTFOLIO_ALLOCATION"
    assert response.calculation_lineage.intermediate_precision == 28


async def test_get_portfolio_summary_returns_historical_restated_totals() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency=" usd ")
    portfolio.portfolio_type = "DISCRETIONARY"
    portfolio.objective = "Growth"
    portfolio.risk_exposure = "BALANCED"
    portfolio.status = "ACTIVE"
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "CASH_USD",
                market_value="200",
                quantity="1",
                snapshot_date=date(2026, 3, 26),
            ),
            instrument=_instrument(
                "CASH_USD",
                name="USD Cash",
                currency=" usd ",
                asset_class="CASH",
                sector="CASH",
                product_type="CASH",
            ),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "SEC1",
                market_value="800",
                quantity="10",
                valuation_status=" unvalued ",
                snapshot_date=date(2026, 3, 27),
            ),
            instrument=_instrument("SEC1", asset_class="EQUITY"),
        ),
    ]
    repo.list_cash_account_masters.return_value = [
        SimpleNamespace(
            cash_account_id="CASH-ACC-USD-001",
            security_id="CASH_USD",
            display_name="USD Operating Cash",
            account_currency=" usd ",
        )
    ]
    repo.get_latest_cash_account_ids.return_value = {}
    repo.get_latest_fx_rate.return_value = Decimal("1.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_portfolio_summary(
            PortfolioSummaryQueryRequest(portfolio_id="P1", reporting_currency=" sgd ")
        )

    assert response.portfolio_currency == "USD"
    assert response.reporting_currency == "SGD"
    assert response.totals.total_market_value_portfolio_currency == Decimal("1000")
    assert response.totals.cash_balance_portfolio_currency == Decimal("200")
    assert response.totals.invested_market_value_reporting_currency == Decimal("1200.0")
    assert response.snapshot_metadata.snapshot_date == date(2026, 3, 27)
    assert response.snapshot_metadata.cash_account_count == 1
    assert response.snapshot_metadata.valued_position_count == 1
    assert response.snapshot_metadata.unvalued_position_count == 1


async def test_get_portfolio_summary_converts_snapshot_rows_sequentially() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    portfolio.portfolio_type = "DISCRETIONARY"
    portfolio.objective = "Growth"
    portfolio.risk_exposure = "BALANCED"
    portfolio.status = "ACTIVE"
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_cash_account_masters.return_value = []
    repo.get_latest_cash_account_ids.return_value = {}
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="800"),
            instrument=_instrument("SEC1", asset_class="EQUITY"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="200"),
            instrument=_instrument("SEC2", asset_class="BOND"),
        ),
    ]
    call_order: list[Decimal] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(amount)
        assert from_currency == "USD"
        assert to_currency == "SGD"
        assert as_of_date == date(2026, 3, 27)
        return amount * Decimal("1.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._convert_amount = AsyncMock(side_effect=convert_amount)  # type: ignore[method-assign]
        response = await service.get_portfolio_summary(
            PortfolioSummaryQueryRequest(portfolio_id="P1", reporting_currency="SGD")
        )

    assert response.totals.total_market_value_reporting_currency == Decimal("1500.0")
    assert response.snapshot_metadata.valued_position_count == 2
    assert call_order == [Decimal("800"), Decimal("200")]


async def test_get_portfolio_summary_reads_cash_accounts_and_reporting_values_sequentially() -> (
    None
):
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    portfolio.portfolio_type = "DISCRETIONARY"
    portfolio.objective = "Growth"
    portfolio.risk_exposure = "BALANCED"
    portfolio.status = "ACTIVE"
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="800"),
            instrument=_instrument("SEC1", asset_class="EQUITY"),
        )
    ]
    call_order: list[str] = []

    async def build_cash_account_balance_records(**_kwargs):
        call_order.append("cash")
        return []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append("reporting")
        assert amount == Decimal("800")
        assert from_currency == "USD"
        assert to_currency == "SGD"
        assert as_of_date == date(2026, 3, 27)
        return Decimal("1200.0")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._cash_balance_resolver.build_cash_account_balance_records = AsyncMock(
            side_effect=build_cash_account_balance_records
        )
        service._convert_amount = AsyncMock(side_effect=convert_amount)  # type: ignore[method-assign]
        response = await service.get_portfolio_summary(
            PortfolioSummaryQueryRequest(portfolio_id="P1", reporting_currency="SGD")
        )

    assert response.totals.total_market_value_reporting_currency == Decimal("1200.0")
    assert response.snapshot_metadata.cash_account_count == 0
    assert call_order == ["cash", "reporting"]


async def test_get_portfolio_summary_reads_portfolio_and_default_date_sequentially() -> None:
    repo = AsyncMock()
    call_order: list[str] = []
    repo.list_latest_snapshot_rows.return_value = []
    repo.list_cash_account_masters.return_value = []
    repo.get_latest_cash_account_ids.return_value = {}

    async def get_portfolio_by_id(portfolio_id: str):
        call_order.append("portfolio")
        portfolio = _portfolio(portfolio_id, base_currency="USD")
        portfolio.portfolio_type = "DISCRETIONARY"
        portfolio.objective = "Growth"
        portfolio.risk_exposure = "BALANCED"
        portfolio.status = "ACTIVE"
        return portfolio

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2026, 3, 27)

    repo.get_portfolio_by_id.side_effect = get_portfolio_by_id
    repo.get_latest_business_date.side_effect = get_latest_business_date

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_portfolio_summary(
            PortfolioSummaryQueryRequest(portfolio_id="P1")
        )

    assert response.resolved_as_of_date == date(2026, 3, 27)
    assert call_order == ["portfolio", "date"]


async def test_get_portfolio_summary_explicit_date_skips_default_date_lookup() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    portfolio.portfolio_type = "DISCRETIONARY"
    portfolio.objective = "Growth"
    portfolio.risk_exposure = "BALANCED"
    portfolio.status = "ACTIVE"
    repo.get_portfolio_by_id.return_value = portfolio
    repo.list_latest_snapshot_rows.return_value = []
    repo.list_cash_account_masters.return_value = []
    repo.get_latest_cash_account_ids.return_value = {}

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_portfolio_summary(
            PortfolioSummaryQueryRequest(
                portfolio_id="P1",
                as_of_date=date(2026, 3, 26),
            )
        )

    assert response.resolved_as_of_date == date(2026, 3, 26)
    repo.get_latest_business_date.assert_not_awaited()


async def test_get_portfolio_summary_raises_lookup_error_for_unknown_portfolio() -> None:
    repo = AsyncMock()
    repo.get_portfolio_by_id.return_value = None

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
            await service.get_portfolio_summary(PortfolioSummaryQueryRequest(portfolio_id="P404"))


async def test_bulk_portfolio_summary_request_is_bounded_and_deduplicated() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        BulkPortfolioSummaryQueryRequest(portfolio_ids=["P1", " P1 "])
    with pytest.raises(ValueError, match="required when more than one"):
        BulkPortfolioSummaryQueryRequest(portfolio_ids=["P1", "P2"])

    request = BulkPortfolioSummaryQueryRequest(portfolio_ids=[" P1 "], reporting_currency=" usd ")
    assert request.portfolio_ids == ["P1"]
    assert request.reporting_currency == " usd "


async def test_bulk_summary_batches_snapshot_read_and_aggregates_members() -> None:
    repo = AsyncMock()
    portfolios = [_portfolio("P1"), _portfolio("P2")]
    repo.list_portfolios.return_value = portfolios
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolios[0],
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1", asset_class="EQUITY"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolios[0],
            snapshot=_snapshot("CASH1", market_value="20"),
            instrument=_instrument("CASH1", asset_class="CASH"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolios[1],
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", asset_class="BOND"),
        ),
    ]
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(date(2026, 3, 27), 2, expected_open_count=2),
        "P2": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1),
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1", "P2"], reporting_currency="USD", as_of_date=date(2026, 3, 27)
            )
        )

    assert [item.portfolio_id for item in response.portfolios] == ["P1", "P2"]
    assert response.portfolios[0].totals is not None
    assert response.portfolios[0].totals.cash_balance_reporting_currency == Decimal("20")
    assert response.portfolios[1].totals is not None
    assert response.aggregate.coverage_state == "COMPLETE"
    assert response.aggregate.totals is not None
    assert response.aggregate.totals.total_market_value_reporting_currency == Decimal("170")
    repo.list_latest_snapshot_rows.assert_awaited_once_with(
        portfolio_ids=["P1", "P2"], as_of_date=date(2026, 3, 27), include_presence=True
    )
    repo.list_cash_account_masters.assert_not_awaited()


async def test_bulk_summary_keeps_native_aggregate_fields_null_for_mixed_currencies() -> None:
    repo = AsyncMock()
    portfolios = [_portfolio("P1", base_currency="USD"), _portfolio("P2", base_currency="SGD")]
    repo.list_portfolios.return_value = portfolios
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolios[0],
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolios[1],
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", currency="SGD"),
        ),
    ]
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1),
        "P2": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1),
    }
    repo.get_latest_fx_rate.return_value = Decimal("0.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1", "P2"], reporting_currency="USD", as_of_date=date(2026, 3, 27)
            )
        )

    assert response.aggregate.coverage_state == "COMPLETE"
    assert response.aggregate.totals is not None
    assert response.aggregate.totals.total_market_value_portfolio_currency is None
    assert response.aggregate.totals.cash_balance_portfolio_currency is None
    assert response.aggregate.totals.invested_market_value_portfolio_currency is None
    assert response.aggregate.totals.total_market_value_reporting_currency == Decimal("125")
    assert response.aggregate.totals.cash_balance_reporting_currency == Decimal("0")
    assert response.aggregate.totals.invested_market_value_reporting_currency == Decimal("125")


async def test_bulk_summary_fails_closed_when_cash_asset_classification_is_missing() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1")
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH1", market_value="20"),
            instrument=_instrument("CASH1", product_type="CASH", asset_class=None),
        )
    ]
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1),
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1"], reporting_currency="USD", as_of_date=date(2026, 3, 27)
            )
        )

    assert response.portfolios[0].coverage_state == "PARTIAL"
    assert response.portfolios[0].coverage_reason == "cash_classification_missing"
    assert response.portfolios[0].totals is None
    assert response.aggregate.coverage_state == "UNAVAILABLE"
    assert response.aggregate.totals is None


async def test_bulk_summary_caches_negative_fx_lookup_for_repeated_currency_pair() -> None:
    repo = AsyncMock()
    portfolios = [_portfolio("P1", base_currency="SGD"), _portfolio("P2", base_currency="SGD")]
    repo.list_portfolios.return_value = portfolios
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(f"SEC-{portfolio.portfolio_id}", market_value="10"),
            instrument=_instrument(f"SEC-{portfolio.portfolio_id}", currency="SGD"),
        )
        for portfolio in portfolios
    ]
    repo.list_snapshot_presence.return_value = {
        portfolio.portfolio_id: SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1)
        for portfolio in portfolios
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._convert_amount = AsyncMock(side_effect=ValueError("FX rate not found"))  # type: ignore[method-assign]
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1", "P2"], reporting_currency="USD", as_of_date=date(2026, 3, 27)
            )
        )

    assert [item.coverage_state for item in response.portfolios] == [
        "FX_UNAVAILABLE",
        "FX_UNAVAILABLE",
    ]
    assert service._convert_amount.await_count == 1


async def test_get_bulk_portfolio_summary_is_fail_closed_for_missing_partial_and_fx_members() -> (
    None
):
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.list_portfolios.return_value = [portfolio]
    missing_value = _snapshot("SEC1", market_value="10")
    missing_value.market_value = None
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=missing_value,
            instrument=_instrument("SEC1"),
        )
    ]
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=2)
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        partial = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1", "P404"], reporting_currency="SGD", as_of_date=date(2026, 3, 27)
            )
        )

    assert [item.coverage_state for item in partial.portfolios] == ["PARTIAL", "INVALID_PORTFOLIO"]
    assert all(item.totals is None for item in partial.portfolios)
    assert partial.aggregate.coverage_state == "UNAVAILABLE"
    assert partial.aggregate.totals is None


async def test_get_bulk_portfolio_summary_keeps_fx_failure_on_member_and_blocks_aggregate() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="10"),
            instrument=_instrument("SEC1"),
        )
    ]
    repo.list_snapshot_presence.return_value = {
        "P1": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1)
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))

        async def fail_fx(**_kwargs):
            raise ValueError("FX rate not found")

        service._convert_amount = AsyncMock(side_effect=fail_fx)  # type: ignore[method-assign]
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P1"], reporting_currency="SGD", as_of_date=date(2026, 3, 27)
            )
        )

    assert response.portfolios[0].coverage_state == "FX_UNAVAILABLE"
    assert response.portfolios[0].coverage_reason == "reporting_fx_unavailable"
    assert response.portfolios[0].totals is None
    assert response.aggregate.coverage_state == "UNAVAILABLE"
    assert response.aggregate.totals is None


async def test_get_bulk_portfolio_summary_distinguishes_zero_empty_and_no_snapshot() -> None:
    repo = AsyncMock()
    portfolios = [_portfolio("P0"), _portfolio("PE"), _portfolio("PN")]
    repo.list_portfolios.return_value = portfolios
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolios[0],
            snapshot=_snapshot("SEC0", market_value="0"),
            instrument=_instrument("SEC0"),
        )
    ]
    repo.list_snapshot_presence.return_value = {
        "P0": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1),
        "PE": SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=0),
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=["P0", "PE", "PN"],
                reporting_currency="USD",
                as_of_date=date(2026, 3, 27),
            )
        )

    assert [item.coverage_state for item in response.portfolios] == [
        "MEASURED_ZERO",
        "LOADED_EMPTY",
        "NO_SNAPSHOT",
    ]
    assert response.portfolios[0].totals is not None
    assert response.portfolios[1].totals is None
    assert response.aggregate.coverage_state == "PARTIAL"
    assert response.aggregate.totals is None


@pytest.mark.parametrize("member_count", [1, 25, 100])
async def test_bulk_summary_keeps_repository_reads_bounded_at_supported_sizes(
    member_count: int,
) -> None:
    repo = AsyncMock()
    portfolios = [_portfolio(f"P{index}") for index in range(member_count)]
    repo.list_portfolios.return_value = portfolios
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(f"SEC-{portfolio.portfolio_id}", market_value="1"),
            instrument=_instrument(f"SEC-{portfolio.portfolio_id}"),
        )
        for portfolio in portfolios
    ]
    repo.list_snapshot_presence.return_value = {
        portfolio.portfolio_id: SnapshotPresence(date(2026, 3, 27), 1, expected_open_count=1)
        for portfolio in portfolios
    }

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_bulk_portfolio_summary(
            BulkPortfolioSummaryQueryRequest(
                portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
                reporting_currency="USD",
                as_of_date=date(2026, 3, 27),
            )
        )

    assert len(response.portfolios) == member_count
    assert response.aggregate.coverage_state == "COMPLETE"
    repo.list_portfolios.assert_awaited_once_with(
        portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios]
    )
    repo.list_latest_snapshot_rows.assert_awaited_once_with(
        portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
        as_of_date=date(2026, 3, 27),
        include_presence=True,
    )
    repo.list_snapshot_presence.assert_awaited_once_with(
        portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
        as_of_date=date(2026, 3, 27),
    )
    repo.list_cash_account_masters.assert_not_awaited()


async def test_get_asset_allocation_applies_region_and_partial_lookthrough() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("PB_SG_GLOBAL_BAL_001", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("FUND1", market_value="100"),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", asset_class="EQUITY", country_of_risk="US"),
        ),
    ]
    repo.list_instrument_lookthrough_components.return_value = [
        InstrumentLookthroughComponentRow(
            parent_security_id="FUND1",
            component_security_id="ETF1",
            component_weight=Decimal("0.6"),
            component_instrument=_instrument("ETF1", asset_class="EQUITY", country_of_risk="US"),
            component_record_id=101,
            effective_from=date(2026, 1, 1),
            source_system="fund-master",
            source_record_id="FUND1-ETF1",
        ),
        InstrumentLookthroughComponentRow(
            parent_security_id="FUND1",
            component_security_id="ETF2",
            component_weight=Decimal("0.4"),
            component_instrument=_instrument("ETF2", asset_class="BOND", country_of_risk="DE"),
            component_record_id=102,
            effective_from=date(2026, 1, 1),
            source_system="fund-master",
            source_record_id="FUND1-ETF2",
        ),
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_asset_allocation(
            AssetAllocationQueryRequest(
                scope=ReportingScope(portfolio_id="PB_SG_GLOBAL_BAL_001"),
                dimensions=["region", "asset_class"],
                look_through_mode="prefer_look_through",
            )
        )

    assert response.look_through.applied_mode == "prefer_look_through"
    assert response.look_through.supported is True
    assert response.look_through.decomposed_position_count == 1
    assert "remaining positions" in response.look_through.limitation_reason
    region_view = next(view for view in response.views if view.dimension == "region")
    north_america_bucket = next(
        bucket for bucket in region_view.buckets if bucket.dimension_value == "North America"
    )
    europe_bucket = next(
        bucket for bucket in region_view.buckets if bucket.dimension_value == "Europe"
    )
    assert north_america_bucket.market_value_reporting_currency == Decimal("110.0")
    assert europe_bucket.market_value_reporting_currency == Decimal("40.0")
    assert [
        (item.contributor_type, item.booked_security_id, item.security_id)
        for item in north_america_bucket.contributors
    ] == [
        ("look_through_component", "FUND1", "ETF1"),
        ("direct_position", "SEC2", "SEC2"),
    ]
    assert {
        item.portfolio_id for bucket in region_view.buckets for item in bucket.contributors
    } == {"PB_SG_GLOBAL_BAL_001"}
    component = north_america_bucket.contributors[0]
    assert component.component_record_id == 101
    assert component.component_weight == Decimal("0.6")
    assert component.component_effective_from == date(2026, 1, 1)
    assert component.component_source_system == "fund-master"
    assert component.component_source_record_id == "FUND1-ETF1"
    assert sum(
        (item.market_value_reporting_currency for item in north_america_bucket.contributors),
        Decimal("0"),
    ) + north_america_bucket.omitted_market_value_reporting_currency == (
        north_america_bucket.market_value_reporting_currency
    )


async def test_get_asset_allocation_reports_lookthrough_capability_in_direct_mode() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("FUND1", market_value="100"),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        )
    ]
    repo.list_instrument_lookthrough_components.return_value = [
        InstrumentLookthroughComponentRow(
            parent_security_id="FUND1",
            component_security_id="ETF1",
            component_weight=Decimal("1"),
            component_instrument=_instrument("ETF1", asset_class="EQUITY", country_of_risk="US"),
            component_record_id=101,
            effective_from=date(2026, 1, 1),
        )
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_asset_allocation(
            AssetAllocationQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
                dimensions=["asset_class"],
            )
        )

    assert response.look_through.requested_mode == "direct_only"
    assert response.look_through.applied_mode == "direct_only"
    assert response.look_through.supported is True


async def test_get_asset_allocation_normalizes_lookthrough_parent_security_ids() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(" FUND1 ", market_value="100"),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("FUND1", market_value="100", snapshot_id=2),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        ),
    ]
    repo.list_instrument_lookthrough_components.return_value = [
        InstrumentLookthroughComponentRow(
            parent_security_id=" FUND1 ",
            component_security_id="ETF1",
            component_weight=Decimal("1"),
            component_instrument=_instrument("ETF1", asset_class="EQUITY", country_of_risk="US"),
            component_record_id=101,
            effective_from=date(2026, 1, 1),
        )
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_asset_allocation(
            AssetAllocationQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
                dimensions=["asset_class"],
                look_through_mode="prefer_look_through",
            )
        )

    assert response.look_through.applied_mode == "prefer_look_through"
    assert response.look_through.decomposed_position_count == 2
    asset_class_view = next(view for view in response.views if view.dimension == "asset_class")
    buckets = [
        (bucket.dimension_value, bucket.market_value_reporting_currency)
        for bucket in asset_class_view.buckets
    ]
    assert buckets == [
        ("EQUITY", Decimal("200")),
    ]
    assert asset_class_view.buckets[0].position_count == 2
    assert asset_class_view.buckets[0].contributor_count == 2
    assert [item.source_snapshot_id for item in asset_class_view.buckets[0].contributors] == [1, 2]
    repo.list_instrument_lookthrough_components.assert_awaited_once_with(
        parent_security_ids=["FUND1"],
        as_of_date=date(2026, 3, 27),
    )


@pytest.mark.asyncio
async def test_resolve_allocation_rows_reuses_reporting_values_for_lookthrough() -> None:
    repo = AsyncMock()
    rows = [
        ReportingSnapshotRow(
            portfolio=_portfolio("P1", base_currency="USD"),
            snapshot=_snapshot(" FUND1 ", market_value="100"),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        ),
        ReportingSnapshotRow(
            portfolio=_portfolio("P1", base_currency="USD"),
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", asset_class="EQUITY", country_of_risk="US"),
        ),
    ]
    repo.list_instrument_lookthrough_components.return_value = [
        InstrumentLookthroughComponentRow(
            parent_security_id="FUND1",
            component_security_id="ETF1",
            component_weight=Decimal("1"),
            component_instrument=_instrument("ETF1", asset_class="EQUITY", country_of_risk="US"),
            component_record_id=101,
            effective_from=date(2026, 1, 1),
        )
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._convert_amount = AsyncMock(side_effect=lambda *, amount, **_: amount)
        allocation_rows, lookthrough = await service._resolve_allocation_rows(
            rows=rows,
            requested_mode="prefer_look_through",
            as_of_date=date(2026, 3, 27),
            reporting_currency="SGD",
        )

    assert service._convert_amount.await_count == len(rows)
    assert lookthrough.applied_mode == "prefer_look_through"
    assert [row.market_value_reporting_currency for row in allocation_rows] == [
        Decimal("100"),
        Decimal("50"),
    ]
    assert allocation_rows[0].instrument is (
        repo.list_instrument_lookthrough_components.return_value[0].component_instrument
    )
    assert allocation_rows[0].snapshot.security_id == "ETF1"
    assert allocation_rows[0].contributor is not None
    assert allocation_rows[0].contributor.contributor_type == "look_through_component"
    assert allocation_rows[0].contributor.booked_security_id == "FUND1"
    assert allocation_rows[0].contributor.component_record_id == 101
    assert allocation_rows[1].instrument is rows[1].instrument
    assert allocation_rows[1].snapshot is rows[1].snapshot
    assert allocation_rows[1].contributor is not None
    assert allocation_rows[1].contributor.contributor_type == "direct_position"


@pytest.mark.asyncio
async def test_resolve_allocation_rows_reads_conversions_and_components_sequentially() -> None:
    repo = AsyncMock()
    rows = [
        ReportingSnapshotRow(
            portfolio=_portfolio("P1", base_currency="USD"),
            snapshot=_snapshot(" FUND1 ", market_value="100"),
            instrument=_instrument("FUND1", asset_class="FUND", country_of_risk="LU"),
        ),
        ReportingSnapshotRow(
            portfolio=_portfolio("P1", base_currency="USD"),
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", asset_class="EQUITY", country_of_risk="US"),
        ),
    ]
    call_order: list[str] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(f"convert:{amount}")
        assert from_currency == "USD"
        assert to_currency == "SGD"
        assert as_of_date == date(2026, 3, 27)
        return amount

    async def list_components(
        *,
        parent_security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentLookthroughComponentRow]:
        call_order.append("components")
        assert parent_security_ids == ["FUND1", "SEC2"]
        assert as_of_date == date(2026, 3, 27)
        return []

    repo.list_instrument_lookthrough_components.side_effect = list_components

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        service._convert_amount = AsyncMock(side_effect=convert_amount)  # type: ignore[method-assign]
        allocation_rows, lookthrough = await service._resolve_allocation_rows(
            rows=rows,
            requested_mode="direct_only",
            as_of_date=date(2026, 3, 27),
            reporting_currency="SGD",
        )

    assert [row.snapshot.security_id for row in allocation_rows] == [" FUND1 ", "SEC2"]
    assert lookthrough.applied_mode == "direct_only"
    assert call_order == ["convert:100", "convert:50", "components"]


@pytest.mark.asyncio
async def test_reporting_service_can_decompose_position_requires_complete_weights() -> None:
    assert ReportingService._can_decompose_position([]) is False
    assert (
        ReportingService._can_decompose_position(
            [
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF1",
                    component_weight=Decimal("0.7"),
                    component_instrument=_instrument("ETF1"),
                ),
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF2",
                    component_weight=Decimal("0.2"),
                    component_instrument=_instrument("ETF2"),
                ),
            ]
        )
        is False
    )
    assert (
        ReportingService._can_decompose_position(
            [
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="SHORT_COMPONENT",
                    component_weight=Decimal("-0.25"),
                    component_instrument=_instrument("SHORT_COMPONENT"),
                ),
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="LEVERAGED_COMPONENT",
                    component_weight=Decimal("1.25"),
                    component_instrument=_instrument("LEVERAGED_COMPONENT"),
                ),
            ]
        )
        is False
    )
    assert (
        ReportingService._can_decompose_position(
            [
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF1",
                    component_weight=" ",
                    component_instrument=_instrument("ETF1"),
                ),
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF2",
                    component_weight=Decimal("1"),
                    component_instrument=_instrument("ETF2"),
                ),
            ]
        )
        is False
    )
    assert (
        ReportingService._can_decompose_position(
            [
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF1",
                    component_weight=Decimal("0.6"),
                    component_instrument=_instrument("ETF1"),
                ),
                InstrumentLookthroughComponentRow(
                    parent_security_id="FUND1",
                    component_security_id="ETF2",
                    component_weight=Decimal("0.4"),
                    component_instrument=_instrument("ETF2"),
                ),
            ]
        )
        is True
    )


@pytest.mark.asyncio
async def test_reporting_service_resolve_scope_requires_business_date() -> None:
    repo = AsyncMock()
    repo.get_latest_business_date.return_value = None

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="No business date is available"):
            await service._resolve_scope_portfolios_and_date(
                ReportingScope(portfolio_id="P1"),
                None,
            )


@pytest.mark.asyncio
async def test_reporting_service_resolve_scope_requires_matching_portfolios() -> None:
    repo = AsyncMock()
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = []

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="No portfolios matched"):
            await service._resolve_scope_portfolios_and_date(
                ReportingScope(portfolio_id="P1"),
                None,
            )


@pytest.mark.asyncio
async def test_reporting_service_resolve_scope_reads_default_date_and_portfolios_sequentially() -> (
    None
):
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    call_order: list[str] = []

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2026, 3, 27)

    async def list_portfolios(**_: object) -> list[object]:
        call_order.append("portfolios")
        return [portfolio]

    repo.get_latest_business_date.side_effect = get_latest_business_date
    repo.list_portfolios.side_effect = list_portfolios

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        portfolios, resolved_as_of_date = await service._resolve_scope_portfolios_and_date(
            ReportingScope(portfolio_id="P1"),
            None,
        )

    assert portfolios == [portfolio]
    assert resolved_as_of_date == date(2026, 3, 27)
    assert call_order == ["date", "portfolios"]


@pytest.mark.asyncio
async def test_reporting_service_resolve_reporting_currency_covers_scope_rules() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency=" usd ")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        assert (
            await service._resolve_reporting_currency(
                scope=ReportingScope(portfolio_id="P1"),
                portfolios=[portfolio],
                requested_reporting_currency=" sgd ",
            )
            == "SGD"
        )
        assert (
            await service._resolve_reporting_currency(
                scope=ReportingScope(portfolio_id="P1"),
                portfolios=[portfolio],
                requested_reporting_currency=None,
            )
            == "USD"
        )
        with pytest.raises(ValueError, match="reporting_currency is required"):
            await service._resolve_reporting_currency(
                scope=ReportingScope(portfolio_ids=["P1", "P2"]),
                portfolios=[portfolio],
                requested_reporting_currency=None,
            )


@pytest.mark.asyncio
async def test_reporting_service_get_fx_rate_uses_cache_and_raises_for_missing_rate() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.side_effect = [Decimal("1.25"), None]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        same_currency = await service._convert_amount(
            amount=Decimal("10"),
            from_currency=" usd ",
            to_currency="USD",
            as_of_date=date(2026, 3, 27),
        )
        first = await service._get_fx_rate(" eur ", " usd ", date(2026, 3, 27))
        second = await service._get_fx_rate("EUR", "USD", date(2026, 3, 27))
        assert same_currency == Decimal("10")
        assert first == Decimal("1.25")
        assert second == Decimal("1.25")
        assert repo.get_latest_fx_rate.await_count == 1
        repo.get_latest_fx_rate.assert_awaited_once_with(
            from_currency="EUR",
            to_currency="USD",
            as_of_date=date(2026, 3, 27),
        )
        with pytest.raises(ValueError, match="FX rate not found"):
            await service._get_fx_rate(" chf ", " usd ", date(2026, 3, 27))
