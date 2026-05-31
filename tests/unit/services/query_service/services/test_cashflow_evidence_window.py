import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.repositories.cashflow_repository import CashflowSeriesEvidence
from src.services.query_service.app.services.cashflow_evidence_window import (
    read_cashflow_evidence_window,
)

pytestmark = pytest.mark.asyncio


async def test_read_cashflow_evidence_window_reads_booked_and_projected_concurrently() -> None:
    repo = AsyncMock()
    booked_started = asyncio.Event()
    projected_started = asyncio.Event()

    async def booked_evidence(
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> CashflowSeriesEvidence:
        booked_started.set()
        await asyncio.wait_for(projected_started.wait(), timeout=1)
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 4, 5)
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("10"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
        )

    async def projected_evidence(
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> CashflowSeriesEvidence:
        projected_started.set()
        await asyncio.wait_for(booked_started.wait(), timeout=1)
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 4, 5)
        return CashflowSeriesEvidence(
            rows=[(end_date, Decimal("-5"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, tzinfo=UTC),
        )

    repo.get_portfolio_cashflow_series_with_evidence.side_effect = booked_evidence
    repo.get_projected_settlement_cashflow_series_with_evidence.side_effect = projected_evidence

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 4, 5),
        include_projected=True,
    )

    assert window.booked_rows == [(date(2026, 3, 27), Decimal("10"))]
    assert window.projected_rows == [(date(2026, 4, 5), Decimal("-5"))]
    assert window.latest_evidence_timestamp == datetime(2026, 3, 27, 10, tzinfo=UTC)
    assert booked_started.is_set()
    assert projected_started.is_set()


async def test_read_cashflow_evidence_window_skips_projected_read_for_booked_only() -> None:
    repo = AsyncMock()
    repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), Decimal("10"))],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
    )

    window = await read_cashflow_evidence_window(
        repo=repo,
        portfolio_id="P1",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 3, 27),
        include_projected=False,
    )

    repo.get_projected_settlement_cashflow_series_with_evidence.assert_not_awaited()
    assert window.booked_rows == [(date(2026, 3, 27), Decimal("10"))]
    assert window.projected_rows == []
    assert window.latest_evidence_timestamp == datetime(2026, 3, 27, 9, tzinfo=UTC)
