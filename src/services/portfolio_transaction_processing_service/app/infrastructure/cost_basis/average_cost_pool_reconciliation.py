"""Reconcile persisted AVCO state through SQLAlchemy transaction boundaries."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from portfolio_common.database_models import Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_binds_output,
)
from portfolio_common.domain.transaction.type_registry import TRANSACTION_TYPE_REGISTRY
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.cost_basis_processing import AverageCostPoolRebuildPlanner
from ...domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)
from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    AverageCostPoolCheckpoint,
    build_average_cost_pool_rebuild_lineage,
)
from ...domain.cost_basis.calculation.lot_state import resolve_source_lot_original_quantity
from ...domain.cost_basis.state_lineage import canonical_cost_basis_output_payload
from ...ports import (
    AverageCostPoolPersistedSummary,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
)
from .average_cost_pool_repository import SqlAlchemyAverageCostPoolRepository
from .fx_rate_repository import SqlAlchemyCostBasisFxRateRepository
from .processing_state_repository import SqlAlchemyCostBasisProcessingStateRepository
from .reference_data_repository import SqlAlchemyCostBasisReferenceDataRepository
from .transaction_repository import SqlAlchemyCostBasisTransactionRepository

logger = logging.getLogger(__name__)

_INCREMENTAL_POOL_LINEAGE_ALGORITHMS = frozenset(
    {
        "average-cost-pool-checkpoint-materialization",
        "average-cost-pool-processing-rebuild",
        "average-cost-pool-transition",
    }
)

AVERAGE_COST_SOURCE_TRANSACTION_TYPES = tuple(
    sorted(
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.lot_behavior in LOT_OPENING_BEHAVIORS
    )
)


class SqlAlchemyAverageCostPoolReconciliationAdapter:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        rebuild_planner: AverageCostPoolRebuildPlanner,
        repository_factory: Callable[[AsyncSession], CostBasisTransactionStatePort] = (
            SqlAlchemyCostBasisTransactionRepository
        ),
        average_cost_pool_factory: Callable[[AsyncSession], CostBasisAverageCostPoolPort] = (
            SqlAlchemyAverageCostPoolRepository
        ),
        reference_data_factory: Callable[[AsyncSession], CostBasisReferenceDataPort] = (
            SqlAlchemyCostBasisReferenceDataRepository
        ),
        fx_rate_factory: Callable[[AsyncSession], CostBasisFxRatePort] = (
            SqlAlchemyCostBasisFxRateRepository
        ),
        processing_state_factory: Callable[[AsyncSession], CostBasisProcessingStatePort] = (
            SqlAlchemyCostBasisProcessingStateRepository
        ),
    ) -> None:
        self._session_factory = session_factory
        self._rebuild_planner = rebuild_planner
        self._repository_factory = repository_factory
        self._average_cost_pool_factory = average_cost_pool_factory
        self._reference_data_factory = reference_data_factory
        self._fx_rate_factory = fx_rate_factory
        self._processing_state_factory = processing_state_factory

    async def list_candidates(
        self,
        *,
        portfolio_id: str | None,
        after: AverageCostPoolKey | None,
        limit: int,
    ) -> tuple[AverageCostPoolKey, ...]:
        portfolio_expr = func.trim(DBTransaction.portfolio_id)
        security_expr = func.trim(DBTransaction.security_id)
        stmt = (
            select(
                portfolio_expr.label("portfolio_id"),
                security_expr.label("security_id"),
            )
            .join(Portfolio, Portfolio.portfolio_id == portfolio_expr)
            .where(
                func.upper(func.trim(Portfolio.cost_basis_method)) == "AVCO",
                func.upper(func.trim(DBTransaction.transaction_type)).in_(
                    AVERAGE_COST_SOURCE_TRANSACTION_TYPES
                ),
            )
            .group_by(portfolio_expr, security_expr)
            .order_by(portfolio_expr.asc(), security_expr.asc())
            .limit(limit)
        )
        if portfolio_id is not None:
            stmt = stmt.where(portfolio_expr == portfolio_id)
        if after is not None:
            stmt = stmt.where(
                or_(
                    portfolio_expr > after.portfolio_id,
                    and_(
                        portfolio_expr == after.portfolio_id,
                        security_expr > after.security_id,
                    ),
                )
            )

        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(AverageCostPoolKey(row.portfolio_id, row.security_id) for row in rows)

    async def reconcile(
        self,
        *,
        key: AverageCostPoolKey,
        apply: bool,
    ) -> AverageCostPoolReconciliationAssessment:
        expected_source_count = 0
        expected_quantity = Decimal(0)
        expected_cost_local = Decimal(0)
        expected_cost_base = Decimal(0)
        persisted_before = _empty_summary()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repository = self._repository_factory(session)
                    average_cost_pools = self._average_cost_pool_factory(session)
                    reference_data = self._reference_data_factory(session)
                    fx_rates = self._fx_rate_factory(session)
                    processing_state = self._processing_state_factory(session)
                    await processing_state.acquire_cost_basis_processing_lock(
                        key.portfolio_id,
                        key.security_id,
                    )
                    plan = await self._rebuild_planner.build(
                        portfolio_id=key.portfolio_id,
                        security_id=key.security_id,
                        transactions=repository,
                        reference_data=reference_data,
                        fx_rates=fx_rates,
                    )
                    expected_source_count = len(plan.source_transactions)
                    expected_quantity = plan.checkpoint.quantity
                    expected_cost_local = plan.checkpoint.cost_local
                    expected_cost_base = plan.checkpoint.cost_base
                    expected_source_original_quantities = tuple(
                        sorted(
                            (
                                source.transaction_id,
                                (
                                    plan.source_states[source.transaction_id].original_quantity
                                    if source.transaction_id in plan.source_states
                                    else resolve_source_lot_original_quantity(
                                        original_quantity=source.source_lot_original_quantity,
                                        order_quantity=source.source_lot_order_quantity,
                                        current_quantity=source.quantity,
                                    )
                                ),
                            )
                            for source in plan.source_transactions
                        )
                    )
                    expected_checkpoint_lineage = build_average_cost_pool_rebuild_lineage(
                        replay_lineage=plan.replay_lineage,
                        checkpoint=plan.checkpoint,
                    )
                    persisted_before = (
                        await average_cost_pools.get_average_cost_pool_persisted_summary(
                            portfolio_id=key.portfolio_id,
                            security_id=key.security_id,
                        )
                    )
                    if _summary_matches_plan(
                        persisted_before,
                        expected_source_count=expected_source_count,
                        expected_quantity=expected_quantity,
                        expected_cost_local=expected_cost_local,
                        expected_cost_base=expected_cost_base,
                        expected_source_original_quantities=(expected_source_original_quantities),
                        expected_checkpoint=plan.checkpoint,
                        expected_checkpoint_lineage=expected_checkpoint_lineage,
                    ):
                        return _assessment(
                            key=key,
                            status=AverageCostPoolReconciliationStatus.CURRENT,
                            expected_source_count=expected_source_count,
                            expected_quantity=expected_quantity,
                            expected_cost_local=expected_cost_local,
                            expected_cost_base=expected_cost_base,
                            observed=persisted_before,
                        )
                    if not apply:
                        return _assessment(
                            key=key,
                            status=AverageCostPoolReconciliationStatus.DRIFTED,
                            expected_source_count=expected_source_count,
                            expected_quantity=expected_quantity,
                            expected_cost_local=expected_cost_local,
                            expected_cost_base=expected_cost_base,
                            observed=persisted_before,
                            reason_code=_drift_reason(
                                persisted_before,
                                expected_source_count=expected_source_count,
                                expected_source_original_quantities=(
                                    expected_source_original_quantities
                                ),
                                expected_checkpoint=plan.checkpoint,
                                expected_checkpoint_lineage=expected_checkpoint_lineage,
                            ),
                        )

                    await average_cost_pools.apply_average_cost_pool_rebuild(plan)
                    await processing_state.upsert_cost_basis_processing_checkpoint(
                        plan.processing_checkpoint
                    )
                    persisted_after = (
                        await average_cost_pools.get_average_cost_pool_persisted_summary(
                            portfolio_id=key.portfolio_id,
                            security_id=key.security_id,
                        )
                    )
                    if not _summary_matches_plan(
                        persisted_after,
                        expected_source_count=expected_source_count,
                        expected_quantity=expected_quantity,
                        expected_cost_local=expected_cost_local,
                        expected_cost_base=expected_cost_base,
                        expected_source_original_quantities=(expected_source_original_quantities),
                        expected_checkpoint=plan.checkpoint,
                        expected_checkpoint_lineage=expected_checkpoint_lineage,
                    ):
                        post_write_reason = _drift_reason(
                            persisted_after,
                            expected_source_count=expected_source_count,
                            expected_source_original_quantities=(
                                expected_source_original_quantities
                            ),
                            expected_checkpoint=plan.checkpoint,
                            expected_checkpoint_lineage=expected_checkpoint_lineage,
                        )
                        raise ValueError(
                            "Average cost rebuild did not persist the expected state "
                            f"and replay evidence: {post_write_reason}"
                        )
                    return _assessment(
                        key=key,
                        status=AverageCostPoolReconciliationStatus.RECONCILED,
                        expected_source_count=expected_source_count,
                        expected_quantity=expected_quantity,
                        expected_cost_local=expected_cost_local,
                        expected_cost_base=expected_cost_base,
                        observed=persisted_after,
                    )
        except Exception:
            logger.exception(
                "Average cost pool reconciliation failed.",
                extra={
                    "portfolio_id": key.portfolio_id,
                    "security_id": key.security_id,
                },
            )
            return _assessment(
                key=key,
                status=AverageCostPoolReconciliationStatus.FAILED,
                expected_source_count=expected_source_count,
                expected_quantity=expected_quantity,
                expected_cost_local=expected_cost_local,
                expected_cost_base=expected_cost_base,
                observed=persisted_before,
                reason_code="average_cost_reconciliation_failed",
            )


def _empty_summary() -> AverageCostPoolPersistedSummary:
    return AverageCostPoolPersistedSummary(
        source_count=0,
        source_quantity=Decimal(0),
        source_cost_local=Decimal(0),
        source_cost_base=Decimal(0),
        source_lineage_valid=True,
        source_original_quantities=(),
        pool_quantity=None,
        pool_cost_local=None,
        pool_cost_base=None,
        pool_instrument_id=None,
        pool_representative_source_transaction_id=None,
        pool_state_version=None,
        pool_calculation_lineage=None,
    )


def _summary_matches_plan(
    summary: AverageCostPoolPersistedSummary,
    *,
    expected_source_count: int,
    expected_quantity: Decimal,
    expected_cost_local: Decimal,
    expected_cost_base: Decimal,
    expected_source_original_quantities: tuple[tuple[str, Decimal], ...],
    expected_checkpoint: AverageCostPoolCheckpoint,
    expected_checkpoint_lineage: CalculationLineage,
) -> bool:
    return bool(
        summary.source_count == expected_source_count
        and summary.source_lineage_valid
        and summary.source_original_quantities == expected_source_original_quantities
        and summary.source_quantity == expected_quantity
        and summary.source_cost_local == expected_cost_local
        and summary.source_cost_base == expected_cost_base
        and summary.pool_quantity == expected_quantity
        and summary.pool_cost_local == expected_cost_local
        and summary.pool_cost_base == expected_cost_base
        and summary.pool_instrument_id == expected_checkpoint.instrument_id
        and summary.pool_representative_source_transaction_id
        == expected_checkpoint.representative_source_transaction_id
        and summary.pool_state_version == expected_checkpoint.state_version
        and _pool_lineage_matches_plan(
            summary.pool_calculation_lineage,
            expected_checkpoint=expected_checkpoint,
            expected_checkpoint_lineage=expected_checkpoint_lineage,
        )
    )


def _pool_lineage_matches_plan(
    persisted: CalculationLineage | None,
    *,
    expected_checkpoint: AverageCostPoolCheckpoint,
    expected_checkpoint_lineage: CalculationLineage,
) -> bool:
    """Accept replay-exact or governed incremental evidence for equal pool economics.

    Rebuild receipts bind the complete canonical replay and therefore must match exactly.
    Ordinary processing receipts bind the latest valid state transition instead; their input
    hashes cannot equal a full replay receipt.  For those repository-owned writers, validate
    the governed calculation semantics while the caller independently proves the complete
    persisted source and pool aggregates.
    """

    if persisted is None:
        return False
    if persisted.algorithm_id == expected_checkpoint_lineage.algorithm_id:
        return bool(persisted == expected_checkpoint_lineage)
    semantics_match = all(
        (
            persisted.algorithm_id in _INCREMENTAL_POOL_LINEAGE_ALGORITHMS,
            persisted.algorithm_version == expected_checkpoint_lineage.algorithm_version,
            persisted.intermediate_precision == expected_checkpoint_lineage.intermediate_precision,
            persisted.numeric_output_policy == expected_checkpoint_lineage.numeric_output_policy,
        )
    )
    if not semantics_match:
        return False
    output_payload = {
        "cost_base": expected_checkpoint.cost_base,
        "cost_local": expected_checkpoint.cost_local,
        "instrument_id": expected_checkpoint.instrument_id,
        "portfolio_id": expected_checkpoint.portfolio_id,
        "quantity": expected_checkpoint.quantity,
        "representative_source_transaction_id": (
            expected_checkpoint.representative_source_transaction_id
        ),
        "security_id": expected_checkpoint.security_id,
        "state_version": expected_checkpoint.state_version,
    }
    if persisted.algorithm_id != "average-cost-pool-processing-rebuild":
        output_payload["calculation_lineage"] = None
    return bool(
        calculation_lineage_binds_output(
            persisted,
            output_payload=canonical_cost_basis_output_payload(output_payload),
        )
    )


def _drift_reason(
    summary: AverageCostPoolPersistedSummary,
    *,
    expected_source_count: int,
    expected_source_original_quantities: tuple[tuple[str, Decimal], ...],
    expected_checkpoint: AverageCostPoolCheckpoint,
    expected_checkpoint_lineage: CalculationLineage,
) -> str:
    if summary.pool_quantity is None:
        return "pool_state_missing"
    if summary.source_count != expected_source_count:
        return "source_count_mismatch"
    if not summary.source_lineage_valid:
        return "source_lineage_evidence_mismatch"
    if summary.source_original_quantities != expected_source_original_quantities:
        return "source_original_quantity_mismatch"
    if not _pool_lineage_matches_plan(
        summary.pool_calculation_lineage,
        expected_checkpoint=expected_checkpoint,
        expected_checkpoint_lineage=expected_checkpoint_lineage,
    ):
        return "checkpoint_replay_evidence_mismatch"
    return "pool_or_source_aggregate_mismatch"


def _assessment(
    *,
    key: AverageCostPoolKey,
    status: AverageCostPoolReconciliationStatus,
    expected_source_count: int,
    expected_quantity: Decimal,
    expected_cost_local: Decimal,
    expected_cost_base: Decimal,
    observed: AverageCostPoolPersistedSummary,
    reason_code: str | None = None,
) -> AverageCostPoolReconciliationAssessment:
    return AverageCostPoolReconciliationAssessment(
        key=key,
        status=status,
        expected_source_count=expected_source_count,
        expected_quantity=expected_quantity,
        expected_cost_local=expected_cost_local,
        expected_cost_base=expected_cost_base,
        source_count=observed.source_count,
        pool_quantity=observed.pool_quantity,
        pool_cost_local=observed.pool_cost_local,
        pool_cost_base=observed.pool_cost_base,
        source_quantity=observed.source_quantity,
        source_cost_local=observed.source_cost_local,
        source_cost_base=observed.source_cost_base,
        reason_code=reason_code,
    )
