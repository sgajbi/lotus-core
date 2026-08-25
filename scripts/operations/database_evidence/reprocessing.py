"""Rollback-safe plan evidence for reprocessing claim and stale recovery."""

from __future__ import annotations

from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from .contract import HotPathPlanResult, HotPathScenario, evaluate_hot_path_plan
from .plan_capture import capture_and_explain_rolled_back_statement


async def measure_reprocessing_job_claim(
    session: AsyncSession,
    *,
    normalization_scenario: HotPathScenario,
    claim_scenario: HotPathScenario,
) -> tuple[HotPathPlanResult, HotPathPlanResult]:
    """Measure both RESET_WATERMARKS claim statements without retaining them."""

    normalization_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ReprocessingJobRepository(
            evidence_session
        ).normalize_pending_reset_watermarks_duplicates(),
        statement_prefix="WITH",
    )
    claim_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ReprocessingJobRepository(evidence_session).find_and_claim_jobs(
            "RESET_WATERMARKS",
            batch_size=claim_scenario.max_root_actual_rows,
        ),
        statement_prefix="WITH",
        statement_marker="WITH candidates AS MATERIALIZED",
    )
    return (
        evaluate_hot_path_plan(normalization_scenario, normalization_plan),
        evaluate_hot_path_plan(claim_scenario, claim_plan),
    )


async def measure_reprocessing_stale_recovery(
    session: AsyncSession,
    *,
    scan_scenario: HotPathScenario,
    reset_scenario: HotPathScenario,
    reset_job_ids: tuple[int, ...],
) -> tuple[HotPathPlanResult, HotPathPlanResult]:
    """Measure exact stale selection and reset statements without retaining them."""

    scan_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ReprocessingJobRepository(evidence_session)._find_stale_job_rows(),
        statement_prefix="SELECT",
    )
    reset_plan = await capture_and_explain_rolled_back_statement(
        session,
        lambda evidence_session: ReprocessingJobRepository(
            evidence_session
        )._reset_retryable_stale_jobs(list(reset_job_ids)),
        statement_prefix="UPDATE",
    )
    return (
        evaluate_hot_path_plan(scan_scenario, scan_plan),
        evaluate_hot_path_plan(reset_scenario, reset_plan),
    )
