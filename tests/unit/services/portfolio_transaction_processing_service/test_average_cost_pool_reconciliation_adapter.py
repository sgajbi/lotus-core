from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculationWorkflow,
    CostCalculatorRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.average_cost_pool_reconciliation_adapter import (  # noqa: E501
    SqlAlchemyAverageCostPoolReconciliationAdapter,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AverageCostPoolPersistedSummary,
)

pytestmark = pytest.mark.asyncio


def _session() -> MagicMock:
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=transaction)
    transaction.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = transaction
    return session


def _summary(
    *,
    source_count: int = 2,
    quantity: str = "15",
    cost_local: str = "180",
    cost_base: str = "195",
    pool_present: bool = True,
) -> AverageCostPoolPersistedSummary:
    return AverageCostPoolPersistedSummary(
        source_count=source_count,
        source_quantity=Decimal(quantity),
        source_cost_local=Decimal(cost_local),
        source_cost_base=Decimal(cost_base),
        pool_quantity=Decimal(quantity) if pool_present else None,
        pool_cost_local=Decimal(cost_local) if pool_present else None,
        pool_cost_base=Decimal(cost_base) if pool_present else None,
    )


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        source_transactions=(SimpleNamespace(), SimpleNamespace()),
        checkpoint=SimpleNamespace(
            quantity=Decimal("15"),
            cost_local=Decimal("180"),
            cost_base=Decimal("195"),
        ),
    )


def _adapter(
    *,
    session: MagicMock,
    workflow: AsyncMock | None = None,
    repository: AsyncMock | None = None,
) -> tuple[SqlAlchemyAverageCostPoolReconciliationAdapter, AsyncMock, AsyncMock]:
    resolved_workflow = workflow or AsyncMock(spec=CostCalculationWorkflow)
    resolved_repository = repository or AsyncMock(spec=CostCalculatorRepository)
    return (
        SqlAlchemyAverageCostPoolReconciliationAdapter(
            session_factory=MagicMock(return_value=session),
            workflow=resolved_workflow,
            repository_factory=MagicMock(return_value=resolved_repository),
        ),
        resolved_workflow,
        resolved_repository,
    )


async def test_candidate_listing_uses_ordered_bounded_avco_lot_source_keys() -> None:
    session = _session()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(portfolio_id="P1", security_id="S2"),
        SimpleNamespace(portfolio_id="P2", security_id="S1"),
    ]
    session.execute.return_value = result
    adapter, _, _ = _adapter(session=session)

    keys = await adapter.list_candidates(
        portfolio_id="P1",
        after=AverageCostPoolKey("P1", "S1"),
        limit=25,
    )

    assert keys == (AverageCostPoolKey("P1", "S2"), AverageCostPoolKey("P2", "S1"))
    query = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "upper(trim(portfolios.cost_basis_method)) = 'AVCO'" in query
    assert "upper(trim(transactions.transaction_type)) IN" in query
    assert "trim(transactions.portfolio_id) = 'P1'" in query
    assert "trim(transactions.security_id) > 'S1'" in query
    assert "ORDER BY trim(transactions.portfolio_id) ASC" in query
    assert "LIMIT 25" in query


async def test_dry_run_reports_replay_proven_drift_without_writes() -> None:
    session = _session()
    adapter, workflow, repository = _adapter(session=session)
    workflow.build_average_cost_pool_rebuild_plan.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(pool_present=False)

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=False)

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "pool_state_missing"
    assert assessment.expected_quantity == Decimal("15")
    repository.acquire_cost_basis_processing_lock.assert_awaited_once_with("P1", "S1")
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()


async def test_apply_commits_only_after_post_write_exact_reconciliation() -> None:
    session = _session()
    adapter, workflow, repository = _adapter(session=session)
    plan = _plan()
    workflow.build_average_cost_pool_rebuild_plan.return_value = plan
    repository.get_average_cost_pool_persisted_summary.side_effect = [
        _summary(quantity="14", cost_local="168", cost_base="182"),
        _summary(),
    ]

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.RECONCILED
    repository.apply_average_cost_pool_rebuild.assert_awaited_once_with(plan)
    assert repository.get_average_cost_pool_persisted_summary.await_count == 2
    session.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_apply_rolls_back_and_reports_failure_when_post_write_state_does_not_reconcile() -> (
    None
):
    session = _session()
    adapter, workflow, repository = _adapter(session=session)
    workflow.build_average_cost_pool_rebuild_plan.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.side_effect = [
        _summary(quantity="14", cost_local="168", cost_base="182"),
        _summary(quantity="13", cost_local="156", cost_base="169"),
    ]

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.FAILED
    assert assessment.reason_code == "average_cost_reconciliation_failed"
    assert assessment.source_quantity == Decimal("14")
    exit_call = session.begin.return_value.__aexit__.await_args
    assert exit_call.args[0] is ValueError


async def test_replay_failure_is_isolated_as_bounded_key_failure() -> None:
    session = _session()
    adapter, workflow, repository = _adapter(session=session)
    workflow.build_average_cost_pool_rebuild_plan.side_effect = ValueError("invalid history")

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.FAILED
    assert assessment.reason_code == "average_cost_reconciliation_failed"
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()
