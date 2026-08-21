"""Exact production-method plan evidence for reconciliation control reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.application.holdings_reconciliation import (
    HoldingsReconciliationScope,
)
from src.services.query_service.app.repositories.position_repository import PositionRepository

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_single_production_statement, explain_captured_statement


async def measure_reconciliation_estate_scan(
    session: AsyncSession,
    *,
    portfolio_id: str,
    scopes: tuple[HoldingsReconciliationScope, ...],
    scenario: HotPathScenario,
) -> HotPathPlanResult:
    """Measure exact-scope reconciliation SQL emitted by the production repository."""

    repository = PositionRepository(session)
    statement = await capture_single_production_statement(
        session,
        lambda: repository.get_holdings_reconciliation_controls(
            portfolio_id=portfolio_id,
            scopes=scopes,
        ),
    )
    plan = await explain_captured_statement(session, statement)
    return evaluate_hot_path_plan(scenario, plan)
