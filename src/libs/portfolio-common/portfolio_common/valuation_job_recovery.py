"""Tenant and lease fences for stale and failed-dispatch valuation recovery."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, tuple_, update

from .database_models import PortfolioValuationJob
from .valuation_job_contracts import ValuationJobClaim


@dataclass(frozen=True)
class _StaleValuationJobGroups:
    superseded_job_scopes: list[tuple[str, int]]
    failed_job_scopes: list[tuple[str, int]]
    reset_job_scopes: list[tuple[str, int]]


def _classify_stale_valuation_jobs(
    stale_rows: list[Any],
    max_attempts: int,
) -> _StaleValuationJobGroups:
    superseded_job_scopes = _superseded_stale_job_scopes(stale_rows)
    retryable_rows = _retryable_stale_rows(stale_rows, superseded_job_scopes)
    return _StaleValuationJobGroups(
        superseded_job_scopes=superseded_job_scopes,
        failed_job_scopes=_over_limit_stale_job_scopes(retryable_rows, max_attempts),
        reset_job_scopes=_resettable_stale_job_scopes(retryable_rows, max_attempts),
    )


def _superseded_stale_job_scopes(stale_rows: list[Any]) -> list[tuple[str, int]]:
    return [(row.tenant_id, row.id) for row in stale_rows if _has_newer_epoch(row)]


def _retryable_stale_rows(
    stale_rows: list[Any], superseded_job_scopes: list[tuple[str, int]]
) -> list[Any]:
    return [row for row in stale_rows if (row.tenant_id, row.id) not in superseded_job_scopes]


def _over_limit_stale_job_scopes(stale_rows: list[Any], max_attempts: int) -> list[tuple[str, int]]:
    return [
        (row.tenant_id, row.id)
        for row in stale_rows
        if row.attempt_count >= max_attempts and not _requeue_requested(row)
    ]


def _resettable_stale_job_scopes(stale_rows: list[Any], max_attempts: int) -> list[tuple[str, int]]:
    return [
        (row.tenant_id, row.id)
        for row in stale_rows
        if row.attempt_count < max_attempts or _requeue_requested(row)
    ]


def _has_newer_epoch(stale_row: Any) -> bool:
    return bool(getattr(stale_row, "has_newer_epoch", False))


def _requeue_requested(stale_row: Any) -> bool:
    return getattr(stale_row, "requeue_requested", False) is True


def _superseded_stale_jobs_update_stmt(
    superseded_job_scopes: list[tuple[str, int]],
):
    return (
        _stale_jobs_update_stmt(superseded_job_scopes)
        .values(
            status="SKIPPED_SUPERSEDED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason="Superseded by newer valuation epoch.",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _failed_stale_jobs_update_stmt(
    failed_job_scopes: list[tuple[str, int]],
):
    return (
        _stale_jobs_update_stmt(failed_job_scopes)
        .values(
            status="FAILED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason="Expired valuation claim lease exceeded max attempts",
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _reset_stale_jobs_update_stmt(
    reset_job_scopes: list[tuple[str, int]],
):
    return (
        _stale_jobs_update_stmt(reset_job_scopes)
        .values(
            status="PENDING",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            updated_at=func.now(),
        )
        .returning(PortfolioValuationJob.id)
    )


def _stale_jobs_update_stmt(job_scopes: list[tuple[str, int]]):
    return update(PortfolioValuationJob).where(
        tuple_(PortfolioValuationJob.tenant_id, PortfolioValuationJob.id).in_(job_scopes),
        PortfolioValuationJob.status == "PROCESSING",
        PortfolioValuationJob.valuation_lease_expires_at <= func.clock_timestamp(),
    )


def _dispatch_failed_valuation_jobs_update_stmt(
    *,
    job_claims: list[ValuationJobClaim],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_valuation_jobs_update_stmt(job_claims)
        .where(
            PortfolioValuationJob.attempt_count >= max_attempts,
            PortfolioValuationJob.requeue_requested.is_(False),
        )
        .values(
            status="FAILED",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason=failure_reason,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _dispatch_retryable_valuation_jobs_update_stmt(
    *,
    job_claims: list[ValuationJobClaim],
    max_attempts: int,
    failure_reason: str,
):
    return (
        _dispatch_recovery_valuation_jobs_update_stmt(job_claims)
        .where(
            or_(
                PortfolioValuationJob.attempt_count < max_attempts,
                PortfolioValuationJob.requeue_requested.is_(True),
            )
        )
        .values(
            status="PENDING",
            requeue_requested=False,
            valuation_lease_owner=None,
            valuation_claim_token=None,
            valuation_lease_expires_at=None,
            failure_reason=failure_reason,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )


def _dispatch_recovery_valuation_jobs_update_stmt(job_claims: list[ValuationJobClaim]):
    return update(PortfolioValuationJob).where(
        tuple_(
            PortfolioValuationJob.tenant_id,
            PortfolioValuationJob.id,
            PortfolioValuationJob.valuation_claim_token,
        ).in_([(claim.tenant_id.value, claim.job_id, claim.claim_token) for claim in job_claims]),
        PortfolioValuationJob.status == "PROCESSING",
        PortfolioValuationJob.valuation_lease_expires_at > func.clock_timestamp(),
    )
