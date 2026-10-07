"""One snapshot read port for two independent tenant-scoped observation families."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from portfolio_common.domain.portfolio_source_observations import PortfolioSourceObservation

from ..contracts.portfolio_source_observations import PortfolioSourceObservationsRequest


@dataclass(frozen=True, slots=True)
class PersistedSourceObservation:
    fact: PortfolioSourceObservation
    observation_id: str
    received_at: datetime
    receipt_job_id: str
    qualification: str


class PortfolioSourceObservationReader(Protocol):
    async def read_snapshot(
        self, *, tenant_id: str, portfolio_id: str, request: PortfolioSourceObservationsRequest
    ) -> tuple[PersistedSourceObservation | None, PersistedSourceObservation | None]: ...
