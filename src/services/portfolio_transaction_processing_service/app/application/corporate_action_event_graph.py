"""Commit parent manifests and child readiness evidence in lightweight UoWs."""

from __future__ import annotations

from ..domain.transaction.corporate_action import CorporateActionParentManifest
from ..ports.corporate_action_event_graph import (
    CorporateActionChildObservation,
    CorporateActionEventGraphUnitOfWorkFactory,
    CorporateActionManifestAppendOutcome,
    CorporateActionReadinessDecision,
)


class RegisterCorporateActionManifestUseCase:
    """Persist one source-owned manifest without coupling it to financial mutation."""

    def __init__(self, unit_of_work_factory: CorporateActionEventGraphUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome:
        async with self._unit_of_work_factory() as unit_of_work:
            outcome = await unit_of_work.event_graph.append_manifest(manifest)
            await unit_of_work.commit()
        return outcome


class RegisterCorporateActionChildObservationUseCase:
    """Persist one child arrival and its deterministic readiness evaluation."""

    def __init__(self, unit_of_work_factory: CorporateActionEventGraphUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(
        self,
        observation: CorporateActionChildObservation,
    ) -> CorporateActionReadinessDecision:
        async with self._unit_of_work_factory() as unit_of_work:
            decision = await unit_of_work.event_graph.observe_child(observation)
            await unit_of_work.commit()
        return decision
