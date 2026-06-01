from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import Instrument, PositionHistory, PositionState

from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.services.position_holdings import (
    effective_holdings_as_of_date,
    fallback_valuation_security_ids,
    holdings_response_as_of_date,
    merge_snapshot_and_history_position_rows,
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
