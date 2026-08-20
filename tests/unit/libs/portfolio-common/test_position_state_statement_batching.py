from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.infrastructure.persistence.statement_batching import (
    POSTGRES_BIND_PARAMETER_BUDGET,
)
from portfolio_common.position_state_repository import (
    PositionStateRepository,
    _normalize_state_updates,
)
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.asyncio


def _state_update(index: int) -> dict[str, object]:
    return {
        "portfolio_id": f"P-{index:05d}",
        "security_id": f"S-{index:05d}",
        "expected_epoch": 1,
        "watermark_date": date(2026, 8, 20),
        "status": "CURRENT",
    }


async def test_bulk_update_states_chunks_threshold_plus_one() -> None:
    db = AsyncMock()
    first_result = MagicMock(rowcount=1_000)
    second_result = MagicMock(rowcount=1)
    db.execute.side_effect = [first_result, second_result]

    updated = await PositionStateRepository(db).bulk_update_states(
        [_state_update(index) for index in reversed(range(1_001))]
    )

    assert updated == 1_001
    assert db.execute.await_count == 2


async def test_bulk_update_states_collapses_identical_duplicates() -> None:
    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=1)
    update = _state_update(1)

    updated = await PositionStateRepository(db).bulk_update_states([update, dict(update)])

    assert updated == 1
    db.execute.assert_awaited_once()


async def test_bulk_update_states_rejects_conflicting_duplicates_before_io() -> None:
    db = AsyncMock()
    first = _state_update(1)
    conflicting = {**first, "status": "REPROCESSING"}

    with pytest.raises(ValueError, match="conflicting position-state updates"):
        await PositionStateRepository(db).bulk_update_states([first, conflicting])

    db.execute.assert_not_awaited()


async def test_normalized_state_updates_snapshot_caller_owned_commands() -> None:
    update = _state_update(1)

    normalized = _normalize_state_updates([update])
    update["status"] = "MUTATED_AFTER_VALIDATION"

    assert normalized[0]["status"] == "CURRENT"


async def test_update_watermarks_chunks_unique_keys() -> None:
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchall.return_value = [(str(index),) for index in range(1_000)]
    second_result = MagicMock()
    second_result.fetchall.return_value = [("last",)]
    db.execute.side_effect = [first_result, second_result]
    keys = [(f"P-{index:05d}", f"S-{index:05d}") for index in reversed(range(1_001))]
    keys.append(keys[0])

    updated = await PositionStateRepository(db).update_watermarks_if_older(
        keys,
        date(2026, 8, 20),
    )

    assert updated == 1_001
    assert db.execute.await_count == 2


async def test_epoch_fenced_watermark_chunks_account_for_all_bind_parameters() -> None:
    db = AsyncMock()
    first_result = MagicMock()
    first_result.fetchall.return_value = []
    second_result = MagicMock()
    second_result.fetchall.return_value = []
    db.execute.side_effect = [first_result, second_result]
    keys = [(f"P-{index:05d}", f"S-{index:05d}") for index in range(1_001)]

    await PositionStateRepository(db).update_watermarks_if_older(
        keys,
        date(2026, 8, 20),
        expected_epoch=3,
    )

    parameter_counts = [
        len(
            call.args[0]
            .compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"render_postcompile": True},
            )
            .params
        )
        for call in db.execute.await_args_list
    ]
    assert parameter_counts == [2_004, 6]
    assert max(parameter_counts) <= POSTGRES_BIND_PARAMETER_BUDGET
