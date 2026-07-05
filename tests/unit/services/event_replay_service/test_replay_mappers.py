from fastapi import HTTPException

from src.services.event_replay_service.app.application.replay_command_errors import (
    ReplayCommandError,
)
from src.services.event_replay_service.app.routers.replay_mappers import command_error_to_http


def test_command_error_to_http_preserves_status_and_detail() -> None:
    exc = command_error_to_http(
        ReplayCommandError(
            status_code=409,
            detail={"code": "REPLAY_BLOCKED", "message": "Replay blocked."},
        )
    )

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 409
    assert exc.detail == {"code": "REPLAY_BLOCKED", "message": "Replay blocked."}
