"""Persistence boundary for source-owned corporate-action parent manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Callable, Protocol, Self

from ..domain.transaction.corporate_action import (
    CorporateActionEventChild,
    CorporateActionManifestFinding,
    CorporateActionManifestReadinessStatus,
    CorporateActionParentManifest,
)


class CorporateActionManifestAppendOutcome(StrEnum):
    """Observable outcome of one immutable manifest append."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


class CorporateActionObservationAppendOutcome(StrEnum):
    """Classify physical or semantic child-observation retries."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class CorporateActionChildObservation:
    """Carry one source child arrival and its governed event identity."""

    corporate_action_event_id: str
    portfolio_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    child: CorporateActionEventChild
    transaction_epoch: int
    delivery_event_id: str
    correlation_id: str | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CorporateActionReadinessDecision:
    """Return the durable event state produced by one child observation."""

    observation_outcome: CorporateActionObservationAppendOutcome
    readiness_status: CorporateActionManifestReadinessStatus
    manifest_content_hash: str | None
    structural_plan_content_hash: str | None
    ordered_transaction_ids: tuple[str, ...]
    findings: tuple[CorporateActionManifestFinding, ...]
    state_version: int
    through_observation_sequence: int


class ConflictingCorporateActionManifestError(ValueError):
    """Raised when an event or source version is reused with different content."""


class CorporateActionBookScopeError(ValueError):
    """Raised when a manifest portfolio lacks complete governed book ownership."""


class ConflictingCorporateActionObservationError(ValueError):
    """Raised when child delivery or epoch identity is reused incompatibly."""


class CorporateActionEventGraphPort(Protocol):
    """Append and reconstruct source-versioned corporate-action manifests."""

    async def append_manifest(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome: ...

    async def load_current_manifest(
        self,
        *,
        portfolio_id: str,
        corporate_action_event_id: str,
    ) -> CorporateActionParentManifest | None: ...

    async def observe_child(
        self,
        observation: CorporateActionChildObservation,
    ) -> CorporateActionReadinessDecision: ...


class CorporateActionEventGraphUnitOfWork(Protocol):
    """Own one lightweight parent-graph transaction."""

    @property
    def event_graph(self) -> CorporateActionEventGraphPort: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


CorporateActionEventGraphUnitOfWorkFactory = Callable[[], CorporateActionEventGraphUnitOfWork]
