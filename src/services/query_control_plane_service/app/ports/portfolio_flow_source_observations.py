"""Immutable bounded evidence at the query application boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowSourceCut,
)

from ..contracts.portfolio_flow_source_observations import PortfolioFlowObservationsRequest


@dataclass(frozen=True, slots=True)
class PersistedFlowEvent:
    fact: FlowEventObservation
    received_at: datetime
    receipt_job_id: str


@dataclass(frozen=True, slots=True)
class PersistedFlowCut:
    cut: FlowSourceCut
    received_at: datetime
    receipt_job_id: str
    events: tuple[PersistedFlowEvent, ...]
    dependencies: tuple[PersistedFlowEvent, ...] = ()


class PortfolioFlowObservationReader(Protocol):
    async def read_cut(
        self, *, tenant_id: str, portfolio_id: str, request: PortfolioFlowObservationsRequest
    ) -> PersistedFlowCut | None: ...

    async def read_event(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        source_system: str,
        source_record_id: str,
        flow_source_record_revision: int,
    ) -> PersistedFlowEvent | None: ...
