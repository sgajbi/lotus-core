from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.ops_control_commands import (
    OpsControlCommandError,
    OpsControlCommandService,
    OpsControlUpdateCommand,
)


def _ops_control_service(
    *,
    ingestion_job_service: MagicMock | None = None,
) -> OpsControlCommandService:
    return OpsControlCommandService(ingestion_job_service=ingestion_job_service or MagicMock())


@pytest.mark.asyncio
async def test_ops_control_update_delegates_valid_replay_window_to_service() -> None:
    response = SimpleNamespace(mode="paused", updated_by="ops_automation")
    ingestion_job_service = MagicMock()
    ingestion_job_service.update_ops_mode = AsyncMock(return_value=response)
    replay_window_start = datetime(2026, 3, 6, 0, 0, tzinfo=timezone.utc)
    replay_window_end = datetime(2026, 3, 6, 6, 0, tzinfo=timezone.utc)

    result = await _ops_control_service(
        ingestion_job_service=ingestion_job_service
    ).update_ingestion_ops_control(
        OpsControlUpdateCommand(
            mode="paused",
            replay_window_start=replay_window_start,
            replay_window_end=replay_window_end,
            updated_by="ops_automation",
        )
    )

    assert result is response
    ingestion_job_service.update_ops_mode.assert_awaited_once_with(
        mode="paused",
        replay_window_start=replay_window_start,
        replay_window_end=replay_window_end,
        updated_by="ops_automation",
    )


@pytest.mark.asyncio
async def test_ops_control_update_rejects_invalid_replay_window() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.update_ops_mode = AsyncMock()

    with pytest.raises(OpsControlCommandError) as exc_info:
        await _ops_control_service(
            ingestion_job_service=ingestion_job_service
        ).update_ingestion_ops_control(
            OpsControlUpdateCommand(
                mode="paused",
                replay_window_start=datetime(2026, 3, 6, 6, 0, tzinfo=timezone.utc),
                replay_window_end=datetime(2026, 3, 6, 0, 0, tzinfo=timezone.utc),
                updated_by="ops_automation",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {
        "code": "INGESTION_INVALID_REPLAY_WINDOW",
        "message": "replay_window_start must be before replay_window_end.",
    }
    ingestion_job_service.update_ops_mode.assert_not_awaited()
