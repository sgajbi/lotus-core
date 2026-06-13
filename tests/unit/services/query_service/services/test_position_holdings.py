from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PositionHistory,
    PositionState,
)

from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.dtos.valuation_dto import ValuationData
from src.services.query_service.app.services.position_holdings import (
    apply_held_since_dates,
    assign_position_weights,
    effective_holdings_as_of_date,
    fallback_valuation_security_ids,
    held_since_security_epoch_pairs,
    holdings_data_quality_status,
    holdings_response_as_of_date,
    latest_holdings_evidence_timestamp,
    market_price_freshness_security_ids,
    merge_snapshot_and_history_position_rows,
    portfolio_position_rows_data,
    portfolio_positions_response_data,
    position_held_since_requests,
    position_requires_market_price_freshness,
    position_response_data,
    position_valuation_data,
    position_weight_base_value,
    should_fetch_fallback_valuation_map,
    should_use_default_holdings_as_of_date,
)

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


async def test_merge_snapshot_and_history_position_rows_uses_history_for_basis_mismatch() -> None:
    reconciled_snapshot = DailyPositionSnapshot(
        security_id="SEC_OK",
        quantity=Decimal("5"),
        cost_basis=Decimal("500"),
        cost_basis_local=None,
        date=date(2025, 1, 2),
    )
    reconciled_history = PositionHistory(
        security_id="SEC_OK",
        quantity=Decimal("5"),
        cost_basis=Decimal("500"),
        cost_basis_local=None,
        position_date=date(2025, 1, 2),
    )
    stale_snapshot = DailyPositionSnapshot(
        security_id="SEC_STALE",
        quantity=Decimal("60"),
        cost_basis=Decimal("-6600"),
        cost_basis_local=Decimal("-6000"),
        date=date(2025, 8, 15),
    )
    authoritative_history = PositionHistory(
        security_id="SEC_STALE",
        quantity=Decimal("60"),
        cost_basis=Decimal("9900"),
        cost_basis_local=Decimal("9000"),
        position_date=date(2025, 8, 15),
    )
    snapshot_instrument = Instrument(name="Snapshot Instrument")
    history_instrument = Instrument(name="History Instrument")
    state = PositionState(status="CURRENT")

    merged, history_supplements, snapshot_security_ids = merge_snapshot_and_history_position_rows(
        snapshot_results=[
            (reconciled_snapshot, snapshot_instrument, state),
            (stale_snapshot, snapshot_instrument, state),
        ],
        history_results=[
            (reconciled_history, history_instrument, state),
            (authoritative_history, history_instrument, state),
        ],
    )

    assert [row.security_id for row, _instrument, _state in merged] == [
        "SEC_OK",
        "SEC_STALE",
    ]
    assert merged[0] == (reconciled_snapshot, snapshot_instrument, state)
    assert merged[1] == (authoritative_history, history_instrument, state)
    assert history_supplements == [(authoritative_history, history_instrument, state)]
    assert snapshot_security_ids == {"SEC_OK"}


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


async def test_should_use_default_holdings_as_of_date_only_for_booked_latest_reads() -> None:
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=None,
            include_projected=False,
        )
        is True
    )
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=date(2025, 1, 1),
            include_projected=False,
        )
        is False
    )
    assert (
        should_use_default_holdings_as_of_date(
            requested_as_of_date=None,
            include_projected=True,
        )
        is False
    )


async def test_effective_holdings_as_of_date_resolves_requested_latest_or_unbounded_scope() -> None:
    assert effective_holdings_as_of_date(
        requested_as_of_date=date(2025, 1, 5),
        latest_business_date=None,
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 5)
    assert effective_holdings_as_of_date(
        requested_as_of_date=None,
        latest_business_date=date(2025, 1, 4),
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 4)
    assert effective_holdings_as_of_date(
        requested_as_of_date=None,
        latest_business_date=None,
        include_projected=False,
        today=date(2025, 1, 9),
    ) == date(2025, 1, 9)
    assert (
        effective_holdings_as_of_date(
            requested_as_of_date=None,
            latest_business_date=None,
            include_projected=True,
            today=date(2025, 1, 9),
        )
        is None
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


async def test_portfolio_position_rows_data_applies_snapshot_and_fallback_valuation_policy() -> (
    None
):
    snapshot_row = DailyPositionSnapshot(
        security_id=" SNAP_A ",
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
        security_id=" HIST_A ",
        quantity=Decimal("20"),
        cost_basis=Decimal("200"),
        cost_basis_local=Decimal("198"),
        position_date=date(2025, 1, 2),
    )
    instrument = Instrument(name="Mapped Instrument", asset_class="Equity")

    positions = portfolio_position_rows_data(
        db_results=[
            (snapshot_row, instrument, PositionState(status="CURRENT")),
            (history_row, None, PositionState(status="REPROCESSING")),
        ],
        snapshot_security_ids={"SNAP_A"},
        fallback_valuation_map={
            "HIST_A": {
                "market_price": Decimal("11"),
                "market_value": Decimal("220"),
                "unrealized_gain_loss": Decimal("20"),
                "market_value_local": Decimal("218"),
                "unrealized_gain_loss_local": Decimal("20"),
            }
        },
    )

    assert [position.security_id for position in positions] == ["SNAP_A", "HIST_A"]
    assert positions[0].position_date == date(2025, 1, 1)
    assert positions[0].valuation is not None
    assert positions[0].valuation.market_value == Decimal("1000")
    assert positions[1].instrument_name == "N/A"
    assert positions[1].position_date == date(2025, 1, 2)
    assert positions[1].valuation is not None
    assert positions[1].valuation.market_value == Decimal("220")
    assert positions[1].reprocessing_status == "REPROCESSING"


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


async def test_held_since_security_epoch_pairs_drops_request_indexes_and_defaults() -> None:
    assert held_since_security_epoch_pairs(
        [
            (1, "SEC_B", 3, date(2025, 1, 3)),
            (0, "SEC_A", 2, date(2025, 1, 2)),
        ]
    ) == [("SEC_B", 3), ("SEC_A", 2)]


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


async def test_holdings_data_quality_status_does_not_infer_missing_state() -> None:
    assert (
        holdings_data_quality_status(
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


async def test_holdings_data_quality_status_marks_history_supplement_partial() -> None:
    position = Position(
        security_id="SEC_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="History supplement",
        reprocessing_status="CURRENT",
    )

    assert (
        holdings_data_quality_status(
            positions=[position],
            history_supplements=[(PositionHistory(security_id="SEC_A"), None, None)],
            response_as_of_date=date(2025, 1, 1),
            latest_market_price_dates={},
        )
        == "PARTIAL"
    )


async def test_latest_holdings_evidence_timestamp_uses_latest_row_or_state_timestamp() -> None:
    position_row = DailyPositionSnapshot(
        security_id="SEC_A",
        date=date(2025, 1, 1),
        created_at=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
    )
    state = PositionState(
        created_at=datetime(2025, 1, 1, 8, 30, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
    )

    assert latest_holdings_evidence_timestamp([(position_row, None, state)]) == datetime(
        2025, 1, 1, 10, 5, tzinfo=UTC
    )
