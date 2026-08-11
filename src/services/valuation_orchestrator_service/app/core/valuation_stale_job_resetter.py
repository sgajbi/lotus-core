from ..repositories.valuation_repository import ValuationRepository


class ValuationStaleJobResetter:
    """Resets valuation jobs whose authoritative claim lease has expired."""

    def __init__(self, *, max_attempts: int) -> None:
        self._max_attempts = max_attempts

    async def reset_stale_jobs(self, *, repo: ValuationRepository) -> None:
        await repo.find_and_reset_stale_jobs(
            max_attempts=self._max_attempts,
        )
