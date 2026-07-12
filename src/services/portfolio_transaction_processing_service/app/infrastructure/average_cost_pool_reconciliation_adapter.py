from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from portfolio_common.database_models import Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cost_calculator_service.app.cost_calculation_workflow import (
    LOT_OPENING_BEHAVIORS,
    CostCalculationWorkflow,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    AverageCostPoolPersistedSummary,
    CostCalculatorRepository,
)

from ..domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)

logger = logging.getLogger(__name__)

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
        workflow: CostCalculationWorkflow,
        repository_factory: Callable[[AsyncSession], CostCalculatorRepository] = (
            CostCalculatorRepository
        ),
    ) -> None:
        self._session_factory = session_factory
        self._workflow = workflow
        self._repository_factory = repository_factory

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
                    await repository.acquire_cost_basis_processing_lock(
                        key.portfolio_id,
                        key.security_id,
                    )
                    plan = await self._workflow.build_average_cost_pool_rebuild_plan(
                        portfolio_id=key.portfolio_id,
                        security_id=key.security_id,
                        repo=repository,
                    )
                    expected_source_count = len(plan.source_transactions)
                    expected_quantity = plan.checkpoint.quantity
                    expected_cost_local = plan.checkpoint.cost_local
                    expected_cost_base = plan.checkpoint.cost_base
                    persisted_before = await repository.get_average_cost_pool_persisted_summary(
                        portfolio_id=key.portfolio_id,
                        security_id=key.security_id,
                    )
                    if _summary_matches_plan(
                        persisted_before,
                        expected_source_count=expected_source_count,
                        expected_quantity=expected_quantity,
                        expected_cost_local=expected_cost_local,
                        expected_cost_base=expected_cost_base,
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
                            ),
                        )

                    await repository.apply_average_cost_pool_rebuild(plan)
                    persisted_after = await repository.get_average_cost_pool_persisted_summary(
                        portfolio_id=key.portfolio_id,
                        security_id=key.security_id,
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
        pool_quantity=None,
        pool_cost_local=None,
        pool_cost_base=None,
    )


def _summary_matches_plan(
    summary: AverageCostPoolPersistedSummary,
    *,
    expected_source_count: int,
    expected_quantity: Decimal,
    expected_cost_local: Decimal,
    expected_cost_base: Decimal,
) -> bool:
    return bool(
        summary.source_count == expected_source_count
        and summary.source_quantity == expected_quantity
        and summary.source_cost_local == expected_cost_local
        and summary.source_cost_base == expected_cost_base
        and summary.pool_quantity == expected_quantity
        and summary.pool_cost_local == expected_cost_local
        and summary.pool_cost_base == expected_cost_base
    )


def _drift_reason(
    summary: AverageCostPoolPersistedSummary,
    *,
    expected_source_count: int,
) -> str:
    if summary.pool_quantity is None:
        return "pool_state_missing"
    if summary.source_count != expected_source_count:
        return "source_count_mismatch"
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
