"""Exact production-method plan evidence for latest-position reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.position_repository import PositionRepository

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_single_production_statement, explain_captured_statement


async def measure_latest_position_snapshot(
    session: AsyncSession,
    *,
    portfolio_id: str,
    scenario: HotPathScenario,
) -> HotPathPlanResult:
    """Measure latest-position SQL emitted by the production repository."""

    repository = PositionRepository(session)
    statement = await capture_single_production_statement(
        session,
        lambda: repository.get_latest_positions_by_portfolio(portfolio_id),
    )
    plan = await explain_captured_statement(session, statement)
    return evaluate_hot_path_plan(scenario, plan)
