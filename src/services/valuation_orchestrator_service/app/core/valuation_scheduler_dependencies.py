from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

from ..repositories.valuation_repository import ValuationRepository


@dataclass(frozen=True)
class ValuationSchedulerRepositoryFactory:
    """Repository construction boundary for valuation scheduler DB steps."""

    valuation_repository_factory: Callable[[Any], ValuationRepository]
    valuation_job_repository_factory: Callable[[Any], ValuationJobRepository]
    position_state_repository_factory: Callable[[Any], PositionStateRepository]
    reprocessing_job_repository_factory: Callable[[Any], ReprocessingJobRepository]

    def valuation_repository(self, db: Any) -> ValuationRepository:
        return self.valuation_repository_factory(db)

    def valuation_job_repository(self, db: Any) -> ValuationJobRepository:
        return self.valuation_job_repository_factory(db)

    def position_state_repository(self, db: Any) -> PositionStateRepository:
        return self.position_state_repository_factory(db)

    def reprocessing_job_repository(self, db: Any) -> ReprocessingJobRepository:
        return self.reprocessing_job_repository_factory(db)
