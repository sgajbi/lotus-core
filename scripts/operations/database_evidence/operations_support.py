"""Exact production-method plan evidence for operations support paging."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.operations.repository import (
    OperationsRepository,
)

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_single_production_statement, explain_captured_statement


async def measure_operations_support_page(
    session: AsyncSession,
    *,
    portfolio_id: str,
    reference_now: datetime,
    scenario: HotPathScenario,
) -> HotPathPlanResult:
    """Measure valuation-job support SQL emitted by the production repository."""

    repository = OperationsRepository(session)
    statement = await capture_single_production_statement(
        session,
        lambda: repository.get_valuation_jobs(
            portfolio_id,
            skip=0,
            limit=scenario.max_root_actual_rows,
            reference_now=reference_now,
        ),
    )
    plan = await explain_captured_statement(session, statement)
    return evaluate_hot_path_plan(scenario, plan)
