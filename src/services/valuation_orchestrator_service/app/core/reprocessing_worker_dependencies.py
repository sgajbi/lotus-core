"""Repository construction boundary for isolated reprocessing job transactions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

from ..infrastructure.repositories.fx_revaluation_repository import (
    SqlAlchemyFxRevaluationRepository,
)
from ..repositories.valuation_repository import ValuationRepository


@dataclass(frozen=True, slots=True)
class ReprocessingWorkerRepositoryFactory:
    """Construct transaction-scoped adapters without coupling orchestration to SQLAlchemy."""

    reprocessing_job_repository_factory: Callable[[Any], ReprocessingJobRepository]
    position_state_repository_factory: Callable[[Any], PositionStateRepository]
    valuation_repository_factory: Callable[[Any], ValuationRepository]
    fx_revaluation_repository_factory: Callable[[Any], SqlAlchemyFxRevaluationRepository]

    def reprocessing_jobs(self, db: Any) -> ReprocessingJobRepository:
        return self.reprocessing_job_repository_factory(db)

    def position_states(self, db: Any) -> PositionStateRepository:
        return self.position_state_repository_factory(db)

    def valuations(self, db: Any) -> ValuationRepository:
        return self.valuation_repository_factory(db)

    def fx_revaluations(self, db: Any) -> SqlAlchemyFxRevaluationRepository:
        return self.fx_revaluation_repository_factory(db)
