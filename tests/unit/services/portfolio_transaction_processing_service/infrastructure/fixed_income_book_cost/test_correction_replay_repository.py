"""Verify bounded SQL selection and transactional staging for correction replay."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotBookCostAuthorityScope,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost.correction_replay_repository import (  # noqa: E501
    SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository,
    _earliest_affected_disposal_statement,
)


def _scope() -> LotBookCostAuthorityScope:
    return LotBookCostAuthorityScope(
        tenant_id="tenant-1",
        legal_book_id="book-1",
        portfolio_id="portfolio-1",
        security_id="security-1",
        lot_id="lot-1",
    )


def _intent() -> FixedIncomeBookCostCorrectionReplayIntent:
    return FixedIncomeBookCostCorrectionReplayIntent(
        scope=_scope(),
        earliest_affected_date=date(2026, 1, 1),
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
        ),
        source_authority_event_content_hash="a" * 64,
        profile_decisions=(
            FixedIncomeBookCostProfileDecisionEvidence(
                effective_date=date(2026, 1, 1),
                profile_id="profile-1",
                profile_version=2,
                authority_content_hash="b" * 64,
                eligibility_reason=None,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_finds_earliest_affected_disposal_anchor() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = SimpleNamespace(
        transaction_id="sell-1",
        transaction_date=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
    )
    session.execute.return_value = result
    repository = SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository(
        session,
        topic="fixed_income.book_cost.disposal_replay.requested",
    )

    anchor = await repository.find_earliest_affected_disposal(
        _scope(),
        effective_date=date(2026, 1, 1),
    )

    assert anchor == AffectedLotDisposalReplayAnchor(
        transaction_id="sell-1",
        transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
    )
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_none_when_no_current_disposal_uses_source_lot() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute.return_value = result
    repository = SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository(
        session,
        topic="fixed_income.book_cost.disposal_replay.requested",
    )

    assert (
        await repository.find_earliest_affected_disposal(
            _scope(),
            effective_date=date(2026, 1, 1),
        )
        is None
    )


def test_anchor_query_is_latest_active_exact_scope_ordered_and_bounded() -> None:
    statement = _earliest_affected_disposal_statement(
        _scope(),
        effective_date=date(2026, 1, 1),
    )

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "max(lot_disposal_receipts.receipt_version)" in sql
    assert "lot_disposal_receipts.status = 'ACTIVE'" in sql
    assert "portfolios.tenant_id = 'tenant-1'" in sql
    assert "portfolios.legal_book_id = 'book-1'" in sql
    assert "lot_disposal_allocations.source_lot_id = 'lot-1'" in sql
    assert "transactions.transaction_date >= '2026-01-01 00:00:00+00:00'" in sql
    assert "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_stages_one_source_lot_keyed_outbox_event() -> None:
    session = AsyncMock()
    outbox = AsyncMock(spec=OutboxRepository)
    repository = SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository(
        session,
        topic=" fixed_income.book.cost.replay ",
        outbox_repository=outbox,
    )
    intent = _intent()

    await repository.stage_replay_intent(
        intent,
        correlation_id="correlation-1",
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
    )

    outbox.create_outbox_event.assert_awaited_once()
    call = outbox.create_outbox_event.await_args.kwargs
    assert call["aggregate_id"] == intent.command_id
    assert call["event_type"] == "fixed_income.book_cost.disposal_replay.requested"
    assert call["topic"] == "fixed_income.book.cost.replay"
    assert call["partition_key"] == "tenant-1|book-1|portfolio-1|security-1|lot-1"
    assert call["payload"]["command_id"] == intent.command_id
    assert call["correlation_id"] == "correlation-1"
