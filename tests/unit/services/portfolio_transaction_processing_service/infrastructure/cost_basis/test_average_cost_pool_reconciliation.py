"""Verify SQLAlchemy AVCO reconciliation adapter behavior and transaction ownership."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    AverageCostPoolRebuildPlanner,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    build_average_cost_pool_rebuild_lineage,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.state_lineage import (  # noqa: E501
    build_cost_basis_state_lineage,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.average_cost_pool_reconciliation import (  # noqa: E501
    SqlAlchemyAverageCostPoolReconciliationAdapter,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AverageCostPoolPersistedSummary,
    CostBasisAverageCostPoolPort,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
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
    replay_revision: str = "1",
    lineage_algorithm_id: str = "average-cost-pool-rebuild",
    source_lineage_valid: bool = True,
    source_original_quantities: tuple[tuple[str, Decimal], ...] | None = None,
) -> AverageCostPoolPersistedSummary:
    plan = _plan(replay_revision=replay_revision)
    pool_lineage = build_average_cost_pool_rebuild_lineage(
        replay_lineage=plan.replay_lineage,
        checkpoint=plan.checkpoint,
    )
    if lineage_algorithm_id != "average-cost-pool-rebuild":
        output_payload = {
            "cost_base": Decimal(cost_base),
            "cost_local": Decimal(cost_local),
            "instrument_id": plan.checkpoint.instrument_id,
            "portfolio_id": plan.checkpoint.portfolio_id,
            "quantity": Decimal(quantity),
            "representative_source_transaction_id": (
                plan.checkpoint.representative_source_transaction_id
            ),
            "security_id": plan.checkpoint.security_id,
            "state_version": plan.checkpoint.state_version,
        }
        if lineage_algorithm_id != "average-cost-pool-processing-rebuild":
            output_payload["calculation_lineage"] = None
        pool_lineage = build_cost_basis_state_lineage(
            algorithm_id=lineage_algorithm_id,
            input_payload={"repository_owned_evidence": "latest-transition"},
            output_payload=output_payload,
        )
    return AverageCostPoolPersistedSummary(
        source_count=source_count,
        source_quantity=Decimal(quantity),
        source_cost_local=Decimal(cost_local),
        source_cost_base=Decimal(cost_base),
        source_lineage_valid=source_lineage_valid,
        source_original_quantities=(
            source_original_quantities
            if source_original_quantities is not None
            else (("BUY-1", Decimal("10")), ("BUY-2", Decimal("5")))
        ),
        pool_quantity=Decimal(quantity) if pool_present else None,
        pool_cost_local=Decimal(cost_local) if pool_present else None,
        pool_cost_base=Decimal(cost_base) if pool_present else None,
        pool_instrument_id=plan.checkpoint.instrument_id if pool_present else None,
        pool_representative_source_transaction_id=(
            plan.checkpoint.representative_source_transaction_id if pool_present else None
        ),
        pool_state_version=plan.checkpoint.state_version if pool_present else None,
        pool_calculation_lineage=(pool_lineage if pool_present else None),
    )


def _plan(*, replay_revision: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        source_transactions=(
            SimpleNamespace(
                transaction_id="BUY-1",
                source_lot_original_quantity=None,
                source_lot_order_quantity=None,
                quantity=Decimal("10"),
            ),
            SimpleNamespace(
                transaction_id="BUY-2",
                source_lot_original_quantity=None,
                source_lot_order_quantity=None,
                quantity=Decimal("5"),
            ),
        ),
        source_states={
            "BUY-1": SimpleNamespace(original_quantity=Decimal("10")),
            "BUY-2": SimpleNamespace(original_quantity=Decimal("5")),
        },
        processing_checkpoint=SimpleNamespace(latest_transaction_id="SELL-AVCO-1"),
        checkpoint=SimpleNamespace(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id="BUY-2",
            quantity=Decimal("15"),
            cost_local=Decimal("180"),
            cost_base=Decimal("195"),
            state_version="avco-pool-v1",
        ),
        replay_lineage=build_cost_basis_state_lineage(
            algorithm_id="test-average-cost-pool-replay",
            input_payload={"replay_revision": replay_revision},
            output_payload={"quantity": Decimal("15")},
        ),
    )


def _adapter(
    *,
    session: MagicMock,
    rebuild_planner: AsyncMock | None = None,
    repository: AsyncMock | None = None,
) -> tuple[SqlAlchemyAverageCostPoolReconciliationAdapter, AsyncMock, AsyncMock, AsyncMock]:
    resolved_rebuild_planner = rebuild_planner or AsyncMock(spec=AverageCostPoolRebuildPlanner)
    resolved_repository = repository or AsyncMock(spec=CostBasisAverageCostPoolPort)
    history_repository = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    return (
        SqlAlchemyAverageCostPoolReconciliationAdapter(
            session_factory=MagicMock(return_value=session),
            rebuild_planner=resolved_rebuild_planner,
            repository_factory=MagicMock(return_value=history_repository),
            average_cost_pool_factory=MagicMock(return_value=resolved_repository),
            processing_state_factory=MagicMock(return_value=processing_state),
        ),
        resolved_rebuild_planner,
        resolved_repository,
        processing_state,
    )


async def test_candidate_listing_uses_ordered_bounded_avco_lot_source_keys() -> None:
    session = _session()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(portfolio_id="P1", security_id="S2"),
        SimpleNamespace(portfolio_id="P2", security_id="S1"),
    ]
    session.execute.return_value = result
    adapter, _, _, _ = _adapter(session=session)

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
    adapter, rebuild_planner, repository, processing_state = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(pool_present=False)

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=False)

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "pool_state_missing"
    assert assessment.expected_quantity == Decimal("15")
    processing_state.acquire_cost_basis_processing_lock.assert_awaited_once_with("P1", "S1")
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()


async def test_apply_commits_only_after_post_write_exact_reconciliation() -> None:
    session = _session()
    adapter, rebuild_planner, repository, processing_state = _adapter(session=session)
    plan = _plan()
    rebuild_planner.build.return_value = plan
    repository.get_average_cost_pool_persisted_summary.side_effect = [
        _summary(quantity="14", cost_local="168", cost_base="182"),
        _summary(),
    ]

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.RECONCILED
    repository.apply_average_cost_pool_rebuild.assert_awaited_once_with(plan)
    processing_state.upsert_cost_basis_processing_checkpoint.assert_awaited_once_with(
        plan.processing_checkpoint
    )
    assert repository.get_average_cost_pool_persisted_summary.await_count == 2
    session.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_equal_economics_refresh_changed_replay_evidence_then_reconcile_current() -> None:
    session = _session()
    adapter, rebuild_planner, repository, processing_state = _adapter(session=session)
    plan = _plan(replay_revision="2")
    rebuild_planner.build.return_value = plan
    repository.get_average_cost_pool_persisted_summary.side_effect = [
        _summary(replay_revision="1"),
        _summary(replay_revision="2"),
        _summary(replay_revision="2"),
    ]

    refreshed = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)
    current = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert refreshed.status is AverageCostPoolReconciliationStatus.RECONCILED
    assert current.status is AverageCostPoolReconciliationStatus.CURRENT
    repository.apply_average_cost_pool_rebuild.assert_awaited_once_with(plan)
    processing_state.upsert_cost_basis_processing_checkpoint.assert_awaited_once_with(
        plan.processing_checkpoint
    )


@pytest.mark.parametrize(
    "lineage_algorithm_id",
    [
        "average-cost-pool-transition",
        "average-cost-pool-checkpoint-materialization",
        "average-cost-pool-processing-rebuild",
    ],
)
async def test_equal_economics_accept_governed_incremental_pool_lineage_without_rebuild(
    lineage_algorithm_id: str,
) -> None:
    session = _session()
    adapter, rebuild_planner, repository, processing_state = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(
        lineage_algorithm_id=lineage_algorithm_id
    )

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.CURRENT
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()
    processing_state.upsert_cost_basis_processing_checkpoint.assert_not_awaited()


async def test_dry_run_rejects_stale_source_original_quantity_with_equal_aggregates() -> None:
    session = _session()
    adapter, rebuild_planner, repository, processing_state = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(
        source_original_quantities=(("BUY-1", Decimal("5")), ("BUY-2", Decimal("10")))
    )

    assessment = await adapter.reconcile(
        key=AverageCostPoolKey("P1", "S1"),
        apply=False,
    )

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "source_original_quantity_mismatch"
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()
    processing_state.upsert_cost_basis_processing_checkpoint.assert_not_awaited()


async def test_equal_economics_reject_unknown_pool_lineage_algorithm() -> None:
    session = _session()
    adapter, rebuild_planner, repository, _ = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(
        lineage_algorithm_id="unowned-pool-writer"
    )

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=False)

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "checkpoint_replay_evidence_mismatch"


async def test_equal_economics_reject_invalid_source_lineage_evidence() -> None:
    session = _session()
    adapter, rebuild_planner, repository, _ = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    repository.get_average_cost_pool_persisted_summary.return_value = _summary(
        source_lineage_valid=False
    )

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=False)

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "source_lineage_evidence_mismatch"


async def test_equal_economics_reject_incremental_receipt_not_bound_to_checkpoint() -> None:
    session = _session()
    adapter, rebuild_planner, repository, _ = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
    summary = _summary(lineage_algorithm_id="average-cost-pool-transition")
    copied_lineage = build_cost_basis_state_lineage(
        algorithm_id="average-cost-pool-transition",
        input_payload={"repository_owned_evidence": "copied"},
        output_payload={"quantity": Decimal("15")},
    )
    repository.get_average_cost_pool_persisted_summary.return_value = replace(
        summary,
        pool_calculation_lineage=copied_lineage,
    )

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=False)

    assert assessment.status is AverageCostPoolReconciliationStatus.DRIFTED
    assert assessment.reason_code == "checkpoint_replay_evidence_mismatch"


async def test_apply_rolls_back_and_reports_failure_when_post_write_state_does_not_reconcile() -> (
    None
):
    session = _session()
    adapter, rebuild_planner, repository, _ = _adapter(session=session)
    rebuild_planner.build.return_value = _plan()
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
    adapter, rebuild_planner, repository, _ = _adapter(session=session)
    rebuild_planner.build.side_effect = ValueError("invalid history")

    assessment = await adapter.reconcile(key=AverageCostPoolKey("P1", "S1"), apply=True)

    assert assessment.status is AverageCostPoolReconciliationStatus.FAILED
    assert assessment.reason_code == "average_cost_reconciliation_failed"
    repository.apply_average_cost_pool_rebuild.assert_not_awaited()
