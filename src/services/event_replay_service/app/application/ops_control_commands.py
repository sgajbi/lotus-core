from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

HTTP_UNPROCESSABLE_CONTENT = 422


class OpsControlCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "ops control failed"))))
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class OpsControlUpdateCommand:
    mode: str
    replay_window_start: datetime | None
    replay_window_end: datetime | None
    updated_by: str | None


@dataclass(frozen=True)
class OpsControlCommandService:
    ingestion_job_service: IngestionJobService

    async def update_ingestion_ops_control(self, command: OpsControlUpdateCommand) -> Any:
        self._assert_valid_replay_window(command)
        return await self.ingestion_job_service.update_ops_mode(
            mode=command.mode,
            replay_window_start=command.replay_window_start,
            replay_window_end=command.replay_window_end,
            updated_by=command.updated_by,
        )

    @staticmethod
    def _assert_valid_replay_window(command: OpsControlUpdateCommand) -> None:
        if (
            command.replay_window_start
            and command.replay_window_end
            and command.replay_window_start > command.replay_window_end
        ):
            raise OpsControlCommandError(
                HTTP_UNPROCESSABLE_CONTENT,
                {
                    "code": "INGESTION_INVALID_REPLAY_WINDOW",
                    "message": "replay_window_start must be before replay_window_end.",
                },
            )
