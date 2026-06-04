from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import PositionHistory

from src.services.query_service.app.services.position_history_reads import (
    position_history_response,
)

pytestmark = pytest.mark.asyncio


async def test_position_history_response_normalizes_security_id_for_repository_read() -> None:
    repository = AsyncMock()
    repository.get_position_history_by_security.return_value = [
        (
            PositionHistory(
                transaction_id="T1",
                position_date=date(2025, 1, 2),
                quantity=Decimal("4"),
                cost_basis=Decimal("400"),
                cost_basis_local=Decimal("397"),
            ),
            "CURRENT",
        )
    ]

    response = await position_history_response(
        repository=repository,
        portfolio_id="P1",
        security_id=" SEC_A ",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    repository.get_position_history_by_security.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="SEC_A",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
    assert response.portfolio_id == "P1"
    assert response.security_id == "SEC_A"
    assert [record.transaction_id for record in response.positions] == ["T1"]
    assert [record.reprocessing_status for record in response.positions] == ["CURRENT"]
