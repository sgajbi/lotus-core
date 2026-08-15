from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

from ..repositories.instrument_reprocessing_conversion_repository import (
    InstrumentReprocessingConversionRepository,
)
from ..repositories.valuation_repository import ValuationRepository


@dataclass(frozen=True)
class ValuationSchedulerRepositoryFactory:
    """Repository construction boundary for valuation scheduler DB steps."""

    valuation_repository_factory: Callable[[Any], ValuationRepository]
    valuation_job_repository_factory: Callable[[Any], ValuationJobRepository]
    position_state_repository_factory: Callable[[Any], PositionStateRepository]
    instrument_reprocessing_conversion_repository_factory: Callable[
        [Any], InstrumentReprocessingConversionRepository
    ]

    def valuation_repository(self, db: Any) -> ValuationRepository:
        return self.valuation_repository_factory(db)

    def valuation_job_repository(self, db: Any) -> ValuationJobRepository:
        return self.valuation_job_repository_factory(db)

    def position_state_repository(self, db: Any) -> PositionStateRepository:
        return self.position_state_repository_factory(db)

    def instrument_reprocessing_conversion_repository(
        self, db: Any
    ) -> InstrumentReprocessingConversionRepository:
        return self.instrument_reprocessing_conversion_repository_factory(db)
