"""Rollback-safe production-method plan evidence for valuation job claiming."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_and_explain_rolled_back_mutation


async def measure_valuation_job_claim(
    session: AsyncSession,
    *,
    scenario: HotPathScenario,
) -> HotPathPlanResult:
    """Measure exact claim SQL without retaining either mutation execution."""

    plan = await capture_and_explain_rolled_back_mutation(
        session,
        lambda evidence_session: ValuationRepository(evidence_session).find_and_claim_eligible_jobs(
            batch_size=scenario.max_root_actual_rows,
            lease_owner="database-hot-path-evidence",
        ),
    )
    return evaluate_hot_path_plan(scenario, plan)
