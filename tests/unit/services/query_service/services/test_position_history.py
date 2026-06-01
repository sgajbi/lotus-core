from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import PositionHistory

from src.services.query_service.app.services.position_history import (
    portfolio_position_history_response_data,
    position_history_record_data,
)

pytestmark = pytest.mark.asyncio


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
