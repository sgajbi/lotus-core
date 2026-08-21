"""Rollback-safe plan evidence for valuation stale-job recovery."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_and_explain_rolled_back_statement


async def measure_valuation_stale_recovery(
    session: AsyncSession,
    *,
    scan_scenario: HotPathScenario,
    reset_scenario: HotPathScenario,
    reset_job_ids: tuple[int, ...],
) -> tuple[HotPathPlanResult, HotPathPlanResult]:
    """Measure exact stale selection and reset statements without retaining them."""

    scan_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ValuationRepository(evidence_session)._find_stale_job_rows(),
        statement_prefix="SELECT",
    )
    reset_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ValuationRepository(evidence_session)._reset_retryable_stale_jobs(
            list(reset_job_ids)
        ),
        statement_prefix="UPDATE",
    )
    return (
        evaluate_hot_path_plan(scan_scenario, scan_plan),
        evaluate_hot_path_plan(reset_scenario, reset_plan),
    )
