from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)


@pytest.mark.asyncio
async def test_upsert_portfolio_benchmark_assignments_defaults_assignment_recorded_at() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_portfolio_benchmark_assignments(
        [
            {
                "portfolio_id": "PORT_001",
                "benchmark_id": "BMK_001",
                "effective_from": "2026-01-01",
                "assignment_source": "benchmark_policy_engine",
                "assignment_status": "active",
                "source_system": "lotus-manage",
                "assignment_recorded_at": None,
            }
        ]
    )

    db.execute.assert_awaited_once()
    compiled_params = db.execute.await_args.args[0].compile().params
    assert isinstance(compiled_params["assignment_recorded_at_m0"], datetime)
    db.commit.assert_awaited_once()
