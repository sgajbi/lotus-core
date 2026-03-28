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


@pytest.mark.asyncio
async def test_upsert_cash_account_masters_uses_cash_account_id_conflict_key() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_cash_account_masters(
        [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "PORT_001",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "lifecycle_status": "ACTIVE",
            }
        ]
    )

    compiled = str(db.execute.await_args.args[0].compile())
    assert "cash_account_masters" in compiled
    assert "ON CONFLICT (cash_account_id)" in compiled
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_lookthrough_components_uses_effective_key_conflict() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_instrument_lookthrough_components(
        [
            {
                "parent_security_id": "FUND_001",
                "component_security_id": "ETF_001",
                "effective_from": "2026-01-01",
                "component_weight": "0.6000000000",
            }
        ]
    )

    compiled = str(db.execute.await_args.args[0].compile())
    assert "instrument_lookthrough_components" in compiled
    assert "ON CONFLICT (parent_security_id, component_security_id, effective_from)" in compiled
    db.commit.assert_awaited_once()
