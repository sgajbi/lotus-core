"""Domain-focused tests for durable FX replay execution."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.services.valuation_orchestrator_service.app.application.process_fx_revaluation_job import (
    ProcessFxRevaluationJob,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    DirectCurrencyPair,
    PositionValuationKey,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.domain]


async def test_replay_resets_only_resolved_direct_pair_keys() -> None:
    repository = AsyncMock()
    watermarks = AsyncMock()
    repository.find_affected_position_keys.return_value = [
        PositionValuationKey("P-SGD", "USD-BOND", 2),
        PositionValuationKey("P-SGD", "USD-EQUITY", 0),
    ]
    watermarks.update_watermarks_if_older.return_value = 2
    handler = ProcessFxRevaluationJob(repository=repository, watermarks=watermarks)

    result = await handler.execute(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
    )

    watermarks.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P-SGD", "USD-BOND"), ("P-SGD", "USD-EQUITY")],
        new_watermark_date=date(2026, 4, 9),
    )
    assert result.targeted_key_count == 2
    assert result.updated_key_count == 2
    assert result.requeue_required is False


async def test_replay_remains_pending_during_position_readiness_race() -> None:
    repository = AsyncMock()
    watermarks = AsyncMock()
    repository.find_affected_position_keys.return_value = []
    handler = ProcessFxRevaluationJob(repository=repository, watermarks=watermarks)

    result = await handler.execute(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
    )

    assert result.requeue_required is True
    watermarks.update_watermarks_if_older.assert_not_awaited()
