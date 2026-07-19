"""PostgreSQL integration tests for reconciliation control evidence persistence."""

from datetime import date

import pytest
from portfolio_common.database_models import PipelineStageState
from portfolio_common.reconciliation_quality import FINANCIAL_RECONCILIATION_STAGE
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.financial_reconciliation_service.app.domain.reconciliation_control import (
    FinancialReconciliationCompletion,
)
from src.services.financial_reconciliation_service.app.infrastructure import (
    reconciliation_control_evidence_repository as control_evidence_repository,
)

pytestmark = pytest.mark.asyncio


def _completion(
    *,
    portfolio_id: str,
    epoch: int,
    outcome_status: str,
    aggregation_revision: int = 1,
) -> FinancialReconciliationCompletion:
    return FinancialReconciliationCompletion(
        portfolio_id=portfolio_id,
        business_date=date(2026, 3, 7),
        epoch=epoch,
        aggregation_revision=aggregation_revision,
        outcome_status=outcome_status,
        reconciliation_types=("transaction_cashflow",),
        blocking_reconciliation_types=("transaction_cashflow",)
        if outcome_status != "COMPLETED"
        else (),
        run_ids={"transaction_cashflow": f"run-{epoch}"},
        error_count=0,
        warning_count=0,
        requested_by="system_pipeline",
        trigger_stage="portfolio_day.aggregation.completed",
    )


async def test_newer_aggregation_revision_replaces_prior_control_status(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    repository = control_evidence_repository.SqlAlchemyReconciliationControlEvidenceRepository(
        async_db_session
    )

    first = await repository.record_completion(
        _completion(
            portfolio_id="PORT-CTRL-1",
            epoch=2,
            outcome_status="REQUIRES_REPLAY",
        )
    )
    second = await repository.record_completion(
        _completion(
            portfolio_id="PORT-CTRL-1",
            epoch=2,
            aggregation_revision=2,
            outcome_status="COMPLETED",
        )
    )
    await async_db_session.commit()

    persisted = await async_db_session.scalar(
        select(PipelineStageState).where(
            PipelineStageState.stage_name == FINANCIAL_RECONCILIATION_STAGE,
            PipelineStageState.portfolio_id == "PORT-CTRL-1",
            PipelineStageState.epoch == 2,
        )
    )
    assert first.status == "REQUIRES_REPLAY"
    assert first.accepted_revision is True
    assert second.status == "COMPLETED"
    assert second.accepted_revision is True
    assert persisted is not None
    assert persisted.status == "COMPLETED"
    assert persisted.aggregation_revision == 2


async def test_duplicate_aggregation_revision_is_a_durable_noop(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    repository = control_evidence_repository.SqlAlchemyReconciliationControlEvidenceRepository(
        async_db_session
    )

    first = await repository.record_completion(
        _completion(portfolio_id="PORT-CTRL-2", epoch=2, outcome_status="COMPLETED")
    )
    duplicate = await repository.record_completion(
        _completion(portfolio_id="PORT-CTRL-2", epoch=2, outcome_status="COMPLETED")
    )
    await async_db_session.commit()

    assert first.accepted_revision is True
    assert duplicate.accepted_revision is False
    assert duplicate.status == "COMPLETED"


async def test_conflicting_outcome_for_same_revision_fails_closed(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    repository = control_evidence_repository.SqlAlchemyReconciliationControlEvidenceRepository(
        async_db_session
    )
    await repository.record_completion(
        _completion(portfolio_id="PORT-CTRL-CONFLICT", epoch=2, outcome_status="COMPLETED")
    )

    with pytest.raises(ValueError, match="Conflicting reconciliation outcomes"):
        await repository.record_completion(
            _completion(portfolio_id="PORT-CTRL-CONFLICT", epoch=2, outcome_status="FAILED")
        )


async def test_older_aggregation_revision_cannot_overwrite_newer_control(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    repository = control_evidence_repository.SqlAlchemyReconciliationControlEvidenceRepository(
        async_db_session
    )
    await repository.record_completion(
        _completion(
            portfolio_id="PORT-CTRL-ORDERED",
            epoch=2,
            aggregation_revision=3,
            outcome_status="COMPLETED",
        )
    )

    stale = await repository.record_completion(
        _completion(
            portfolio_id="PORT-CTRL-ORDERED",
            epoch=2,
            aggregation_revision=2,
            outcome_status="REQUIRES_REPLAY",
        )
    )

    assert stale.accepted_revision is False
    assert stale.status == "COMPLETED"


async def test_record_completion_returns_latest_portfolio_day_epoch(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    repository = control_evidence_repository.SqlAlchemyReconciliationControlEvidenceRepository(
        async_db_session
    )

    await repository.record_completion(
        _completion(portfolio_id="PORT-CTRL-3", epoch=4, outcome_status="COMPLETED")
    )
    stale = await repository.record_completion(
        _completion(
            portfolio_id="PORT-CTRL-3",
            epoch=2,
            outcome_status="REQUIRES_REPLAY",
        )
    )
    await async_db_session.commit()

    assert stale.latest_epoch == 4
