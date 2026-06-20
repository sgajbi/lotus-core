from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Awaitable

from portfolio_common.database_models import IngestionOpsControl as DBIngestionOpsControl
from sqlalchemy import select

from ..DTOs.ingestion_job_dto import IngestionOpsModeResponse

SessionFactory = Callable[[], AsyncIterator[object]]

_MODE_STATE_VALUE = {"normal": 0, "paused": 1, "drain": 2}


def to_ops_mode_response(row: DBIngestionOpsControl) -> IngestionOpsModeResponse:
    return IngestionOpsModeResponse(
        mode=row.mode,  # type: ignore[arg-type]
        replay_window_start=row.replay_window_start,
        replay_window_end=row.replay_window_end,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


async def load_ops_mode_response(
    *,
    session_factory: SessionFactory,
) -> IngestionOpsModeResponse:
    async for db in session_factory():
        row = await db.scalar(
            select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
        )
        if row is None:
            row = DBIngestionOpsControl(
                id=1,
                mode="normal",
                replay_window_start=None,
                replay_window_end=None,
                updated_by="system_bootstrap",
            )
            async with db.begin():
                db.add(row)
                await db.flush()
        return to_ops_mode_response(row)
    raise RuntimeError("Unable to read ingestion ops mode.")


async def update_ops_mode_response(
    *,
    mode: str,
    replay_window_start: datetime | None,
    replay_window_end: datetime | None,
    updated_by: str | None,
    session_factory: SessionFactory,
) -> IngestionOpsModeResponse:
    async for db in session_factory():
        async with db.begin():
            row = await db.scalar(
                select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
            )
            if row is None:
                row = DBIngestionOpsControl(id=1, mode="normal")
                db.add(row)
                await db.flush()
            row.mode = mode
            row.replay_window_start = replay_window_start
            row.replay_window_end = replay_window_end
            row.updated_by = updated_by
            row.updated_at = datetime.now(UTC)
        return to_ops_mode_response(row)
    raise RuntimeError("Unable to update ingestion ops mode.")


async def assert_ingestion_writable_mode(
    *,
    ops_mode_loader: Callable[[], Awaitable[IngestionOpsModeResponse]],
    mode_state_metric: object,
) -> None:
    mode = await ops_mode_loader()
    mode_state_metric.set(_MODE_STATE_VALUE[mode.mode])
    if mode.mode in {"paused", "drain"}:
        raise PermissionError(
            f"Ingestion is currently in '{mode.mode}' mode and not accepting new requests."
        )
