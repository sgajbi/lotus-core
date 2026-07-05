from ..repositories.valuation_repository import ValuationRepository


class ValuationStaleJobResetter:
    """Resets valuation jobs that were claimed but not completed within the timeout."""

    def __init__(self, *, stale_timeout_minutes: int, max_attempts: int) -> None:
        self._stale_timeout_minutes = stale_timeout_minutes
        self._max_attempts = max_attempts

    async def reset_stale_jobs(self, *, repo: ValuationRepository) -> None:
        await repo.find_and_reset_stale_jobs(
            timeout_minutes=self._stale_timeout_minutes,
            max_attempts=self._max_attempts,
        )
