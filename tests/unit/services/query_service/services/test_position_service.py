# tests/unit/services/query_service/services/test_position_service.py
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PositionHistory,
    PositionState,
)

from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.dtos.valuation_dto import ValuationData
from src.services.query_service.app.repositories.position_repository import PositionRepository
from src.services.query_service.app.services.position_history import (
    portfolio_position_history_response_data,
    position_history_record_data,
)
from src.services.query_service.app.services.position_holdings import (
    apply_held_since_dates,
    assign_position_weights,
    fallback_valuation_security_ids,
    holdings_response_as_of_date,
    market_price_freshness_security_ids,
    merge_snapshot_and_history_position_rows,
    portfolio_positions_response_data,
    position_held_since_requests,
    position_requires_market_price_freshness,
    position_response_data,
    position_valuation_data,
    position_weight_base_value,
    should_fetch_fallback_valuation_map,
)
from src.services.query_service.app.services.position_service import PositionService

pytestmark = pytest.mark.asyncio


async def test_merge_snapshot_and_history_position_rows_preserves_snapshot_authority() -> None:
    snapshot_row = PositionHistory(security_id=" SEC_A ", position_date=date(2025, 1, 1))
    duplicate_history_row = PositionHistory(security_id="SEC_A", position_date=date(2025, 1, 2))
    history_only_row = PositionHistory(security_id=" sec_b ", position_date=date(2025, 1, 2))
    snapshot_instrument = Instrument(name="Snapshot Instrument")
    duplicate_instrument = Instrument(name="Duplicate History Instrument")
    history_instrument = Instrument(name="History Instrument")
    snapshot_state = PositionState(status="CURRENT")
    duplicate_state = PositionState(status="CURRENT")
    history_state = PositionState(status="CURRENT")

    merged, history_supplements, snapshot_security_ids = merge_snapshot_and_history_position_rows(
        snapshot_results=[(snapshot_row, snapshot_instrument, snapshot_state)],
        history_results=[
            (duplicate_history_row, duplicate_instrument, duplicate_state),
            (history_only_row, history_instrument, history_state),
        ],
    )

    assert [row.security_id for row, _instrument, _state in merged] == [" SEC_A ", " sec_b "]
    assert [instrument.name for _row, instrument, _state in merged] == [
        "Snapshot Instrument",
        "History Instrument",
    ]
    assert history_supplements == [(history_only_row, history_instrument, history_state)]
    assert snapshot_security_ids == {"SEC_A"}


async def test_fallback_valuation_security_ids_normalizes_history_supplements() -> None:
    first_row = PositionHistory(security_id=" SEC_B ", position_date=date(2025, 1, 2))
    duplicate_row = PositionHistory(security_id="SEC_B", position_date=date(2025, 1, 3))
    blank_row = PositionHistory(security_id="   ", position_date=date(2025, 1, 4))
    second_row = PositionHistory(security_id="SEC_A", position_date=date(2025, 1, 5))

    security_ids = fallback_valuation_security_ids(
        [
            (first_row, None, None),
            (duplicate_row, None, None),
            (blank_row, None, None),
            (second_row, None, None),
        ]
    )

    assert security_ids == ["SEC_A", "SEC_B"]


async def test_should_fetch_fallback_valuation_map_for_history_or_history_only_scope() -> None:
    row = PositionHistory(security_id="SEC_A", position_date=date(2025, 1, 2))
    db_results = [(row, None, None)]

    assert (
        should_fetch_fallback_valuation_map(
            db_results=[],
            history_supplements=[],
            snapshot_security_ids=set(),
        )
        is False
    )
    assert (
        should_fetch_fallback_valuation_map(
            db_results=db_results,
            history_supplements=[],
            snapshot_security_ids={"SEC_A"},
        )
        is False
    )
    assert (
        should_fetch_fallback_valuation_map(
            db_results=db_results,
            history_supplements=[],
            snapshot_security_ids=set(),
        )
        is True
    )
    assert (
        should_fetch_fallback_valuation_map(
            db_results=db_results,
            history_supplements=db_results,
            snapshot_security_ids={"SEC_A"},
        )
        is True
    )


async def test_holdings_response_as_of_date_prefers_effective_as_of_date() -> None:
    positions = [
        Position(
            security_id="SEC_A",
            quantity=Decimal("1"),
            cost_basis=Decimal("100"),
            position_date=date(2025, 1, 3),
            instrument_name="Later",
        )
    ]

    assert holdings_response_as_of_date(
        effective_as_of_date=date(2025, 1, 1),
        positions=positions,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 1)


async def test_holdings_response_as_of_date_uses_latest_position_date() -> None:
    positions = [
        Position(
            security_id="SEC_A",
            quantity=Decimal("1"),
            cost_basis=Decimal("100"),
            position_date=date(2025, 1, 2),
            instrument_name="First",
        ),
        Position(
            security_id="SEC_B",
            quantity=Decimal("1"),
            cost_basis=Decimal("200"),
            position_date=date(2025, 1, 4),
            instrument_name="Second",
        ),
    ]

    assert holdings_response_as_of_date(
        effective_as_of_date=None,
        positions=positions,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 4)


async def test_holdings_response_as_of_date_uses_today_when_positions_empty() -> None:
    assert holdings_response_as_of_date(
        effective_as_of_date=None,
        positions=[],
        today=date(2025, 1, 9),
    ) == date(2025, 1, 9)


async def test_portfolio_positions_response_data_adds_runtime_metadata() -> None:
    evidence_timestamp = datetime(2025, 1, 1, 10, 5, tzinfo=UTC)
    position = Position(
        security_id="SEC_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Instrument",
    )

    response = portfolio_positions_response_data(
        portfolio_id="P1",
        positions=[position],
        response_as_of_date=date(2025, 1, 1),
        data_quality_status="COMPLETE",
        latest_evidence_timestamp=evidence_timestamp,
    )

    assert response.portfolio_id == "P1"
    assert response.positions == [position]
    assert response.product_name == "HoldingsAsOf"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2025, 1, 1)
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == evidence_timestamp
    assert response.restatement_version == "current"
    assert response.reconciliation_status == "UNKNOWN"
    assert response.correlation_id is None
    assert response.generated_at.tzinfo is not None


async def test_position_valuation_data_maps_snapshot_row_values() -> None:
    position_row = DailyPositionSnapshot(
        market_price=Decimal("10.25"),
        market_value=Decimal("1025"),
        unrealized_gain_loss=Decimal("25"),
        market_value_local=Decimal("1025"),
        unrealized_gain_loss_local=Decimal("25"),
    )

    valuation = position_valuation_data(
        position_row=position_row,
        is_snapshot_row=True,
        fallback_valuation=None,
    )

    assert valuation.market_price == Decimal("10.25")
    assert valuation.market_value == Decimal("1025")
    assert valuation.unrealized_gain_loss == Decimal("25")


async def test_position_valuation_data_uses_latest_snapshot_fallback() -> None:
    position_row = PositionHistory(cost_basis=Decimal("900"), cost_basis_local=Decimal("900"))

    valuation = position_valuation_data(
        position_row=position_row,
        is_snapshot_row=False,
        fallback_valuation={
            "market_price": Decimal("101.5"),
            "market_value": Decimal("5582.5"),
            "unrealized_gain_loss": Decimal("82.5"),
            "market_value_local": Decimal("5582.5"),
            "unrealized_gain_loss_local": Decimal("82.5"),
        },
    )

    assert valuation.market_price == Decimal("101.5")
    assert valuation.market_value == Decimal("5582.5")
    assert valuation.unrealized_gain_loss == Decimal("82.5")


async def test_position_valuation_data_preserves_cost_basis_when_backfill_missing() -> None:
    position_row = PositionHistory(
        cost_basis=Decimal("123.45"),
        cost_basis_local=Decimal("120.00"),
    )

    valuation = position_valuation_data(
        position_row=position_row,
        is_snapshot_row=False,
        fallback_valuation=None,
    )

    assert valuation.market_price is None
    assert valuation.market_value == Decimal("123.45")
    assert valuation.unrealized_gain_loss == Decimal("0")
    assert valuation.market_value_local == Decimal("120.00")
    assert valuation.unrealized_gain_loss_local == Decimal("0")


async def test_position_response_data_maps_snapshot_instrument_fields() -> None:
    valuation = ValuationData(market_value=Decimal("1025"))
    position = position_response_data(
        position_row=DailyPositionSnapshot(
            security_id=" SEC_A ",
            quantity=Decimal("100"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("995"),
            date=date(2025, 1, 2),
        ),
        instrument=Instrument(
            name="Apple Inc.",
            isin="US0378331005",
            currency="USD",
            asset_class="Equity",
            product_type="Equity",
            sector="Technology",
            country_of_risk="US",
            rating="AA+",
            liquidity_tier="L1",
        ),
        pos_state=PositionState(status="CURRENT"),
        is_snapshot_row=True,
        valuation=valuation,
    )

    assert position.security_id == "SEC_A"
    assert position.position_date == date(2025, 1, 2)
    assert position.instrument_name == "Apple Inc."
    assert position.asset_class == "Equity"
    assert position.isin == "US0378331005"
    assert position.currency == "USD"
    assert position.sector == "Technology"
    assert position.country_of_risk == "US"
    assert position.product_type == "Equity"
    assert position.rating == "AA+"
    assert position.liquidity_tier == "L1"
    assert position.valuation is valuation
    assert position.reprocessing_status == "CURRENT"


async def test_position_response_data_maps_history_date_and_missing_instrument() -> None:
    position = position_response_data(
        position_row=PositionHistory(
            security_id=" HIST_A ",
            quantity=Decimal("3"),
            cost_basis=Decimal("300"),
            cost_basis_local=Decimal("297"),
            position_date=date(2025, 1, 3),
        ),
        instrument=None,
        pos_state=None,
        is_snapshot_row=False,
        valuation=ValuationData(market_value=Decimal("300")),
    )

    assert position.security_id == "HIST_A"
    assert position.position_date == date(2025, 1, 3)
    assert position.instrument_name == "N/A"
    assert position.asset_class is None
    assert position.isin is None
    assert position.currency is None
    assert position.reprocessing_status is None


async def test_assign_position_weights_uses_market_value_share() -> None:
    first = Position(
        security_id="S1",
        quantity=Decimal("1"),
        cost_basis=Decimal("75"),
        position_date=date(2025, 1, 1),
        instrument_name="First",
        valuation=ValuationData(market_value=Decimal("100")),
    )
    second = Position(
        security_id="S2",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Second",
        valuation=ValuationData(market_value=Decimal("300")),
    )

    assign_position_weights([first, second])

    assert first.weight == Decimal("0.25")
    assert second.weight == Decimal("0.75")


async def test_assign_position_weights_falls_back_to_cost_basis() -> None:
    valued = Position(
        security_id="S1",
        quantity=Decimal("1"),
        cost_basis=Decimal("75"),
        position_date=date(2025, 1, 1),
        instrument_name="Valued",
        valuation=ValuationData(market_value=Decimal("100")),
    )
    unvalued = Position(
        security_id="S2",
        quantity=Decimal("1"),
        cost_basis=Decimal("300"),
        position_date=date(2025, 1, 1),
        instrument_name="Unvalued",
        valuation=ValuationData(market_value=None),
    )

    assign_position_weights([valued, unvalued])

    assert valued.weight == Decimal("0.25")
    assert unvalued.weight == Decimal("0.75")


async def test_assign_position_weights_sets_zero_when_no_positive_base_value() -> None:
    first = Position(
        security_id="S1",
        quantity=Decimal("1"),
        cost_basis=Decimal("0"),
        position_date=date(2025, 1, 1),
        instrument_name="First",
        valuation=ValuationData(market_value=Decimal("0")),
    )
    second = Position(
        security_id="S2",
        quantity=Decimal("1"),
        cost_basis=Decimal("0"),
        position_date=date(2025, 1, 1),
        instrument_name="Second",
        valuation=ValuationData(market_value=None),
    )

    assign_position_weights([first, second])

    assert first.weight == Decimal("0")
    assert second.weight == Decimal("0")


async def test_position_held_since_requests_sets_default_when_epoch_missing() -> None:
    row = PositionHistory(security_id=" SEC_A ", position_date=date(2025, 1, 2))
    position = Position(
        security_id="SEC_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 2),
        instrument_name="No epoch",
    )

    requests = position_held_since_requests(
        db_results=[(row, None, PositionState(status="CURRENT", epoch=None))],
        positions=[position],
    )

    assert requests == []
    assert position.held_since_date == date(2025, 1, 2)


async def test_position_held_since_requests_normalizes_epoch_requests() -> None:
    first_row = PositionHistory(security_id=" SEC_A ", position_date=date(2025, 1, 2))
    second_row = PositionHistory(security_id=" SEC_B ", position_date=date(2025, 1, 3))
    first_position = Position(
        security_id="SEC_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 2),
        instrument_name="First",
    )
    second_position = Position(
        security_id="SEC_B",
        quantity=Decimal("1"),
        cost_basis=Decimal("200"),
        position_date=date(2025, 1, 3),
        instrument_name="Second",
    )

    requests = position_held_since_requests(
        db_results=[
            (first_row, None, PositionState(status="CURRENT", epoch=2)),
            (second_row, None, PositionState(status="CURRENT", epoch=3)),
        ],
        positions=[first_position, second_position],
    )

    assert requests == [
        (0, "SEC_A", 2, date(2025, 1, 2)),
        (1, "SEC_B", 3, date(2025, 1, 3)),
    ]
    assert first_position.held_since_date is None
    assert second_position.held_since_date is None


async def test_apply_held_since_dates_uses_default_when_map_missing() -> None:
    first = Position(
        security_id="SEC_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 2),
        instrument_name="First",
    )
    second = Position(
        security_id="SEC_B",
        quantity=Decimal("1"),
        cost_basis=Decimal("200"),
        position_date=date(2025, 1, 3),
        instrument_name="Second",
    )

    apply_held_since_dates(
        positions=[first, second],
        held_since_requests=[
            (0, "SEC_A", 2, date(2025, 1, 2)),
            (1, "SEC_B", 3, date(2025, 1, 3)),
        ],
        held_since_map={("SEC_A", 2): date(2024, 12, 31)},
    )

    assert first.held_since_date == date(2024, 12, 31)
    assert second.held_since_date == date(2025, 1, 3)


async def test_market_price_freshness_security_ids_filters_cash_and_unpriced_rows() -> None:
    equity = Position(
        security_id=" EQ_A ",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Equity",
        asset_class="Equity",
        valuation=ValuationData(market_price=Decimal("10")),
    )
    cash = Position(
        security_id="CASH_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Cash",
        asset_class="Cash",
        valuation=ValuationData(market_price=Decimal("1")),
    )
    unpriced_bond = Position(
        security_id="BOND_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Bond",
        asset_class="Bond",
        valuation=ValuationData(market_price=None),
    )

    assert position_requires_market_price_freshness(equity) is True
    assert position_requires_market_price_freshness(cash) is False
    assert position_requires_market_price_freshness(unpriced_bond) is False
    assert market_price_freshness_security_ids([cash, equity, unpriced_bond]) == ["EQ_A"]


async def test_position_history_record_data_maps_history_fields() -> None:
    history = PositionHistory(
        transaction_id="T-HIST",
        position_date=date(2025, 1, 2),
        quantity=Decimal("4"),
        cost_basis=Decimal("400"),
        cost_basis_local=Decimal("397"),
    )

    record = position_history_record_data(
        position_history_obj=history,
        reprocessing_status="REPROCESSING",
    )

    assert record.position_date == date(2025, 1, 2)
    assert record.transaction_id == "T-HIST"
    assert record.quantity == Decimal("4")
    assert record.cost_basis == Decimal("400")
    assert record.cost_basis_local == Decimal("397")
    assert record.valuation is None
    assert record.reprocessing_status == "REPROCESSING"


async def test_portfolio_position_history_response_data_preserves_scope_and_status() -> None:
    first = PositionHistory(
        transaction_id="T1",
        position_date=date(2025, 1, 1),
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("99"),
    )
    second = PositionHistory(
        transaction_id="T2",
        position_date=date(2025, 1, 2),
        quantity=Decimal("2"),
        cost_basis=Decimal("200"),
        cost_basis_local=Decimal("198"),
    )

    response = portfolio_position_history_response_data(
        portfolio_id="P1",
        security_id="SEC_A",
        db_results=[(first, "CURRENT"), (second, None)],
    )

    assert response.portfolio_id == "P1"
    assert response.security_id == "SEC_A"
    assert [record.transaction_id for record in response.positions] == ["T1", "T2"]
    assert [record.reprocessing_status for record in response.positions] == ["CURRENT", None]


@pytest.fixture
def mock_position_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.portfolio_exists.return_value = True

    mock_history_obj = PositionHistory(
        transaction_id="T1",
        position_date=date(2025, 1, 1),
        quantity=1,
        cost_basis=1,
        cost_basis_local=1,
    )
    repo.get_position_history_by_security.return_value = [(mock_history_obj, "CURRENT")]

    mock_snapshot = DailyPositionSnapshot(
        security_id="S1",
        quantity=Decimal(100),
        cost_basis=Decimal(1000),
        market_price=Decimal("10"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("1000"),
        unrealized_gain_loss=Decimal("0"),
        unrealized_gain_loss_local=Decimal("0"),
        date=date(2025, 1, 1),
        created_at=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
    )
    mock_instrument = Instrument(
        name="Test Instrument",
        isin="ISIN123",
        currency="USD",
        asset_class="Equity",
        product_type="Equity",
        sector="Technology",
        country_of_risk="US",
        rating="AA+",
        liquidity_tier="L2",
    )
    mock_state = PositionState(
        status="CURRENT",
        epoch=1,
        created_at=datetime(2025, 1, 1, 8, 30, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
    )

    repo.get_latest_positions_by_portfolio.return_value = [
        (mock_snapshot, mock_instrument, mock_state)
    ]
    repo.get_latest_business_date.return_value = date(2025, 1, 1)
    repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (mock_snapshot, mock_instrument, mock_state)
    ]
    repo.get_held_since_dates.return_value = {("S1", 1): date(2024, 12, 31)}
    repo.get_latest_position_history_by_portfolio.return_value = []
    repo.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    repo.get_latest_snapshot_valuation_map.return_value = {}
    repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {}
    repo.get_latest_market_price_dates.return_value = {"S1": date(2025, 1, 1)}
    return repo


async def test_get_position_history(mock_position_repo: AsyncMock):
    """Tests the position history service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        params = {
            "portfolio_id": "P1",
            "security_id": " S1 ",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response = await service.get_position_history(**params)

        # ASSERT
        mock_position_repo.get_position_history_by_security.assert_awaited_once_with(
            portfolio_id="P1",
            security_id="S1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert response.security_id == "S1"
        assert len(response.positions) == 1
        assert response.positions[0].transaction_id == "T1"
        assert response.positions[0].valuation is None
        assert response.positions[0].reprocessing_status == "CURRENT"


async def test_get_latest_positions(mock_position_repo: AsyncMock):
    """Tests the latest portfolio positions service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())

        # ACT
        response = await service.get_portfolio_positions(portfolio_id="P1")

        # ASSERT
        mock_position_repo.get_latest_business_date.assert_awaited_once()
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P1", date(2025, 1, 1)
        )
        assert len(response.positions) == 1
        assert response.positions[0].security_id == "S1"
        assert response.positions[0].instrument_name == "Test Instrument"
        assert response.positions[0].reprocessing_status == "CURRENT"
        assert response.positions[0].asset_class == "Equity"
        assert response.positions[0].isin == "ISIN123"
        assert response.positions[0].currency == "USD"
        assert response.positions[0].sector == "Technology"
        assert response.positions[0].country_of_risk == "US"
        assert response.positions[0].product_type == "Equity"
        assert response.positions[0].rating == "AA+"
        assert response.positions[0].liquidity_tier == "L2"
        assert response.positions[0].held_since_date == date(2024, 12, 31)
        assert response.positions[0].weight == Decimal("1")
        assert response.product_name == "HoldingsAsOf"
        assert response.product_version == "v1"
        assert response.as_of_date == date(2025, 1, 1)
        assert response.generated_at.tzinfo is not None
        assert response.restatement_version == "current"
        assert response.reconciliation_status == "UNKNOWN"
        assert response.data_quality_status == "COMPLETE"
        assert response.latest_evidence_timestamp == datetime(2025, 1, 1, 10, 5, tzinfo=UTC)
        assert response.correlation_id is None


async def test_get_latest_positions_reads_snapshot_and_history_sequentially(
    mock_position_repo: AsyncMock,
):
    call_order: list[str] = []
    snapshot_rows = mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value

    async def _snapshot_rows(portfolio_id: str, as_of_date: date):
        call_order.append("snapshot")
        return snapshot_rows

    async def _history_rows(portfolio_id: str, as_of_date: date):
        call_order.append("history")
        return []

    mock_position_repo.get_latest_positions_by_portfolio_as_of_date.side_effect = _snapshot_rows
    mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.side_effect = (
        _history_rows
    )

    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(
            portfolio_id="P1",
            as_of_date=date(2025, 1, 1),
        )

    assert len(response.positions) == 1
    assert response.positions[0].security_id == "S1"
    assert call_order == ["snapshot", "history"]


async def test_get_latest_positions_reads_support_evidence_sequentially(
    mock_position_repo: AsyncMock,
) -> None:
    call_order: list[str] = []

    async def get_held_since_dates(
        *,
        portfolio_id: str,
        security_epoch_pairs: list[tuple[str, int]],
    ) -> dict[tuple[str, int], date]:
        call_order.append("held_since")
        assert portfolio_id == "P1"
        assert security_epoch_pairs == [("S1", 1)]
        return {("S1", 1): date(2024, 12, 31)}

    async def get_latest_market_price_dates(
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> dict[str, date]:
        call_order.append("price_dates")
        assert security_ids == ["S1"]
        assert as_of_date == date(2025, 1, 1)
        return {"S1": date(2025, 1, 1)}

    mock_position_repo.get_held_since_dates.side_effect = get_held_since_dates
    mock_position_repo.get_latest_market_price_dates.side_effect = get_latest_market_price_dates

    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(
            portfolio_id="P1",
            as_of_date=date(2025, 1, 1),
        )

    assert response.positions[0].held_since_date == date(2024, 12, 31)
    assert call_order == ["held_since", "price_dates"]


async def test_get_latest_positions_reads_portfolio_exists_and_default_date_sequentially(
    mock_position_repo: AsyncMock,
) -> None:
    call_order: list[str] = []

    async def portfolio_exists(portfolio_id: str) -> bool:
        call_order.append("portfolio")
        assert portfolio_id == "P1"
        return True

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2025, 1, 1)

    mock_position_repo.portfolio_exists.side_effect = portfolio_exists
    mock_position_repo.get_latest_business_date.side_effect = get_latest_business_date

    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(portfolio_id="P1")

    assert response.as_of_date == date(2025, 1, 1)
    assert call_order == ["portfolio", "date"]


async def test_get_latest_positions_explicit_date_skips_default_date_lookup(
    mock_position_repo: AsyncMock,
) -> None:
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(
            portfolio_id="P1",
            as_of_date=date(2025, 1, 1),
        )

    assert response.as_of_date == date(2025, 1, 1)
    mock_position_repo.get_latest_business_date.assert_not_awaited()


async def test_get_latest_positions_falls_back_to_position_history(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
        mock_history_obj = PositionHistory(
            security_id="S2",
            quantity=Decimal("55"),
            cost_basis=Decimal("5500"),
            cost_basis_local=Decimal("5500"),
            position_date=date(2025, 1, 2),
            transaction_id="T2",
        )
        mock_instrument = Instrument(
            name="Fallback Instrument",
            isin="ISIN456",
            currency="USD",
            asset_class="Bond",
            product_type="Bond",
            sector="N/A",
            country_of_risk="US",
            rating="A",
            liquidity_tier="L3",
        )
        mock_state = PositionState(status="CURRENT", epoch=1)
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (mock_history_obj, mock_instrument, mock_state)
        ]
        mock_position_repo.get_held_since_dates.return_value = {("S2", 1): date(2024, 1, 1)}
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {
            "S2": {
                "market_price": Decimal("101.5"),
                "market_value": Decimal("5582.5"),
                "unrealized_gain_loss": Decimal("82.5"),
                "market_value_local": Decimal("5582.5"),
                "unrealized_gain_loss_local": Decimal("82.5"),
            }
        }

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(portfolio_id="P2")

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1)
        )
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1)
        )
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1), security_ids=["S2"]
        )
        assert len(response.positions) == 1
        assert response.positions[0].security_id == "S2"
        assert response.positions[0].position_date == date(2025, 1, 2)
        assert response.positions[0].instrument_name == "Fallback Instrument"
        assert response.positions[0].product_type == "Bond"
        assert response.positions[0].rating == "A"
        assert response.positions[0].liquidity_tier == "L3"
        assert response.positions[0].asset_class == "Bond"
        assert response.positions[0].valuation is not None
        assert response.positions[0].valuation.market_value == Decimal("5582.5")
        assert response.positions[0].held_since_date == date(2024, 1, 1)
        assert response.positions[0].weight == Decimal("1")


async def test_get_position_history_raises_when_portfolio_missing(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.portfolio_exists.return_value = False
        service = PositionService(AsyncMock())

        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
            await service.get_position_history(portfolio_id="P404", security_id="S1")


async def test_get_portfolio_positions_raises_when_portfolio_missing(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.portfolio_exists.return_value = False
        service = PositionService(AsyncMock())

        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
            await service.get_portfolio_positions("P404")


async def test_holdings_data_quality_status_does_not_infer_missing_state():
    assert (
        PositionService._holdings_data_quality_status(
            positions=[
                Position(
                    security_id="S1",
                    quantity=Decimal("1"),
                    cost_basis=Decimal("10"),
                    position_date=date(2025, 1, 1),
                    instrument_name="Missing state",
                    reprocessing_status=None,
                )
            ],
            history_supplements=[],
            response_as_of_date=date(2025, 1, 1),
            latest_market_price_dates={},
        )
        == "UNKNOWN"
    )


async def test_get_latest_positions_fallback_without_snapshot_valuation_uses_cost_basis(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
        mock_history_obj = PositionHistory(
            security_id="S9",
            quantity=Decimal("10"),
            cost_basis=Decimal("123.45"),
            cost_basis_local=Decimal("123.45"),
            position_date=date(2025, 1, 3),
            transaction_id="T9",
        )
        mock_instrument = Instrument(
            name="No Valuation",
            isin="ISIN999",
            currency="USD",
            asset_class="Equity",
            sector="Tech",
            country_of_risk="US",
        )
        mock_state = PositionState(status="CURRENT", epoch=1)
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (mock_history_obj, mock_instrument, mock_state)
        ]
        mock_position_repo.get_held_since_dates.return_value = {}
        mock_position_repo.get_latest_snapshot_valuation_map.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P9")

        assert response.positions[0].valuation is not None
        assert response.positions[0].valuation.market_price is None
        assert response.positions[0].valuation.market_value == Decimal("123.45")
        assert response.positions[0].valuation.unrealized_gain_loss == Decimal("0")
        assert response.positions[0].held_since_date == date(2025, 1, 3)
        assert response.as_of_date == date(2025, 1, 1)
        assert response.data_quality_status == "PARTIAL"


async def test_get_latest_positions_marks_stale_when_market_prices_are_not_current(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_market_price_dates.return_value = {"S1": date(2024, 12, 30)}
        service = PositionService(AsyncMock())

        response = await service.get_portfolio_positions(portfolio_id="P1")

        mock_position_repo.get_latest_market_price_dates.assert_awaited_once_with(
            security_ids=["S1"],
            as_of_date=date(2025, 1, 1),
        )
        assert response.data_quality_status == "STALE"


async def test_get_latest_positions_supplements_missing_snapshot_rows_from_history(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        snapshot_row = DailyPositionSnapshot(
            security_id="SNAP_ONLY",
            quantity=Decimal("100"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
            market_price=Decimal("10"),
            market_value=Decimal("1000"),
            market_value_local=Decimal("1000"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 1),
        )
        history_row = PositionHistory(
            security_id="HIST_ONLY",
            quantity=Decimal("310"),
            cost_basis=Decimal("57195"),
            cost_basis_local=Decimal("57195"),
            position_date=date(2025, 1, 1),
            transaction_id="T-HIST",
        )
        instrument = Instrument(
            name="Apple Inc.",
            isin="US0378331005",
            currency="USD",
            asset_class="Equity",
            product_type="Equity",
            sector="Technology",
            country_of_risk="US",
            rating=None,
            liquidity_tier="L1",
        )
        state = PositionState(status="REPROCESSING", epoch=2)

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (snapshot_row, instrument, state)
        ]
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (snapshot_row, instrument, state),
            (history_row, instrument, state),
        ]
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {
            "HIST_ONLY": {
                "market_price": Decimal("209.1627"),
                "market_value": Decimal("64840.437"),
                "unrealized_gain_loss": Decimal("7645.437"),
                "market_value_local": Decimal("64840.437"),
                "unrealized_gain_loss_local": Decimal("7645.437"),
            }
        }
        mock_position_repo.get_held_since_dates.return_value = {
            ("SNAP_ONLY", 2): date(2024, 12, 31),
            ("HIST_ONLY", 2): date(2024, 4, 3),
        }

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1", as_of_date=date(2025, 1, 1))

        assert {position.security_id for position in response.positions} == {
            "SNAP_ONLY",
            "HIST_ONLY",
        }
        history_position = next(
            position for position in response.positions if position.security_id == "HIST_ONLY"
        )
        assert history_position.quantity == Decimal("310")
        assert history_position.position_date == date(2025, 1, 1)
        assert history_position.valuation is not None
        assert history_position.valuation.market_value == Decimal("64840.437")
        assert history_position.reprocessing_status == "REPROCESSING"
        assert response.data_quality_status == "STALE"
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.assert_awaited_once_with(
            "P1", date(2025, 1, 1), security_ids=["HIST_ONLY"]
        )


async def test_get_latest_positions_normalizes_security_ids_for_holdings_assembly(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        snapshot_row = DailyPositionSnapshot(
            security_id=" SNAP_ONLY ",
            quantity=Decimal("100"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
            market_price=Decimal("10"),
            market_value=Decimal("1000"),
            market_value_local=Decimal("1000"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 1),
        )
        matching_history_row = PositionHistory(
            security_id="SNAP_ONLY",
            quantity=Decimal("100"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
            position_date=date(2025, 1, 1),
            transaction_id="T-SNAP",
        )
        history_row = PositionHistory(
            security_id=" HIST_ONLY ",
            quantity=Decimal("310"),
            cost_basis=Decimal("57195"),
            cost_basis_local=Decimal("57195"),
            position_date=date(2025, 1, 1),
            transaction_id="T-HIST",
        )
        instrument = Instrument(
            name="Apple Inc.",
            isin="US0378331005",
            currency="USD",
            asset_class="Equity",
            product_type="Equity",
            sector="Technology",
            country_of_risk="US",
        )
        state = PositionState(status="CURRENT", epoch=2)

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (snapshot_row, instrument, state)
        ]
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (matching_history_row, instrument, state),
            (history_row, instrument, state),
        ]
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {
            "HIST_ONLY": {
                "market_price": Decimal("209.1627"),
                "market_value": Decimal("64840.437"),
                "unrealized_gain_loss": Decimal("7645.437"),
                "market_value_local": Decimal("64840.437"),
                "unrealized_gain_loss_local": Decimal("7645.437"),
            }
        }
        mock_position_repo.get_held_since_dates.return_value = {
            ("SNAP_ONLY", 2): date(2024, 12, 31),
            ("HIST_ONLY", 2): date(2024, 4, 3),
        }
        mock_position_repo.get_latest_market_price_dates.return_value = {
            "SNAP_ONLY": date(2025, 1, 1),
            "HIST_ONLY": date(2025, 1, 1),
        }

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1", as_of_date=date(2025, 1, 1))

        assert [position.security_id for position in response.positions] == [
            "SNAP_ONLY",
            "HIST_ONLY",
        ]
        assert response.positions[0].held_since_date == date(2024, 12, 31)
        assert response.positions[1].held_since_date == date(2024, 4, 3)
        assert response.positions[1].valuation is not None
        assert response.positions[1].valuation.market_value == Decimal("64840.437")
        mock_position_repo.get_held_since_dates.assert_awaited_once_with(
            portfolio_id="P1",
            security_epoch_pairs=[("SNAP_ONLY", 2), ("HIST_ONLY", 2)],
        )
        mock_position_repo.get_latest_market_price_dates.assert_awaited_once_with(
            security_ids=["HIST_ONLY", "SNAP_ONLY"],
            as_of_date=date(2025, 1, 1),
        )
        assert response.data_quality_status == "PARTIAL"


async def test_get_latest_positions_include_projected_uses_unbounded_latest(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())

        await service.get_portfolio_positions(portfolio_id="P1", include_projected=True)

        mock_position_repo.get_latest_business_date.assert_not_awaited()
        mock_position_repo.get_latest_positions_by_portfolio.assert_awaited_once_with("P1")


async def test_get_latest_positions_defaults_to_today_when_business_date_absent(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_business_date.return_value = None
        service = PositionService(AsyncMock())

        await service.get_portfolio_positions(portfolio_id="P1")

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P1", date.today()
        )


async def test_get_latest_positions_weight_zero_when_all_values_zero(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        zero_snapshot = DailyPositionSnapshot(
            security_id="S0",
            quantity=Decimal("1"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_value=Decimal("0"),
            market_value_local=Decimal("0"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 1),
        )
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (zero_snapshot, None, PositionState(status="CURRENT", epoch=1))
        ]
        mock_position_repo.get_held_since_dates.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1")

        assert len(response.positions) == 1
        assert response.positions[0].weight == Decimal(0)
        assert response.positions[0].held_since_date == date(2025, 1, 1)


async def test_weight_base_value_prefers_market_value_and_falls_back_to_cost_basis() -> None:
    valued_position = Position(
        security_id="S1",
        quantity=Decimal("1"),
        cost_basis=Decimal("75"),
        position_date=date(2025, 1, 1),
        instrument_name="Valued",
        valuation=ValuationData(market_value=Decimal("100")),
    )
    unvalued_position = Position(
        security_id="S2",
        quantity=Decimal("1"),
        cost_basis=Decimal("75"),
        position_date=date(2025, 1, 1),
        instrument_name="Unvalued",
        valuation=ValuationData(market_value=None),
    )

    assert position_weight_base_value(valued_position) == Decimal("100")
    assert position_weight_base_value(unvalued_position) == Decimal("75")


async def test_get_latest_positions_uses_default_held_since_when_map_missing(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        snapshot = DailyPositionSnapshot(
            security_id="S3",
            quantity=Decimal("2"),
            cost_basis=Decimal("20"),
            cost_basis_local=Decimal("20"),
            market_value=Decimal("20"),
            market_value_local=Decimal("20"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 2),
        )
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (snapshot, None, PositionState(status="CURRENT", epoch=3))
        ]
        mock_position_repo.get_held_since_dates.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1")

        assert response.positions[0].held_since_date == date(2025, 1, 2)
