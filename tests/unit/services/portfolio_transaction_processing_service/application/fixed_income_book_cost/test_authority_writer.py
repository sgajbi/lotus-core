"""Verify deterministic fixed-income book-cost authority writes."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    ConflictingLotAmortizedCostAuthorityBatchError,
    PersistLotAmortizedCostAuthorityUseCase,
)
from services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostAuthorityAppendOutcome,
    LotAmortizedCostAuthorityPort,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


@pytest.mark.asyncio
async def test_writer_deduplicates_exact_retries_and_reports_outcomes() -> None:
    port = AsyncMock(spec=LotAmortizedCostAuthorityPort)
    port.append.side_effect = [
        LotAmortizedCostAuthorityAppendOutcome.APPENDED,
        LotAmortizedCostAuthorityAppendOutcome.UNCHANGED,
    ]
    resolved = resolved_fixed_income_book_cost_inputs()

    result = await PersistLotAmortizedCostAuthorityUseCase(port).execute(
        [resolved.assignment, resolved.assignment, resolved.basis_fact]
    )

    assert result.submitted_count == 3
    assert result.unique_count == 2
    assert result.appended_count == 1
    assert result.unchanged_count == 1
    assert port.append.await_count == 2


@pytest.mark.asyncio
async def test_writer_rejects_conflicting_batch_before_any_write() -> None:
    port = AsyncMock(spec=LotAmortizedCostAuthorityPort)
    assignment = resolved_fixed_income_book_cost_inputs().assignment
    conflict = replace(assignment, assignment_reason="Conflicting treatment")

    with pytest.raises(
        ConflictingLotAmortizedCostAuthorityBatchError,
        match="conflicting payloads",
    ):
        await PersistLotAmortizedCostAuthorityUseCase(port).execute([assignment, conflict])

    port.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_orders_corrections_by_source_version() -> None:
    port = AsyncMock(spec=LotAmortizedCostAuthorityPort)
    port.append.return_value = LotAmortizedCostAuthorityAppendOutcome.APPENDED
    first = resolved_fixed_income_book_cost_inputs().basis_fact
    second = replace(
        first,
        source=replace(first.source, fact_version=2, source_revision="revision-2"),
        initial_clean_cost_local=first.initial_clean_cost_local + 1,
    )

    await PersistLotAmortizedCostAuthorityUseCase(port).execute([second, first])

    written = [call.args[0] for call in port.append.await_args_list]
    assert written == [first, second]
