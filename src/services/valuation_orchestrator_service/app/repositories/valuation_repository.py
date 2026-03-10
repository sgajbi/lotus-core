from portfolio_common.monitoring import (
    observe_valuation_worker_jobs_claimed,
    observe_valuation_worker_stale_resets,
)
from portfolio_common.valuation_repository_base import ValuationRepositoryBase


class ValuationRepository(ValuationRepositoryBase):
    """Service-local wrapper preserving valuation orchestrator metrics/import paths."""

    def _observe_jobs_claimed(self, claimed_count: int) -> None:
        observe_valuation_worker_jobs_claimed(claimed_count)

    def _observe_stale_resets(self, reset_count: int) -> None:
        observe_valuation_worker_stale_resets(reset_count)
