"""Park manifest-governed children before any financial mutation can occur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ..domain import build_transaction_semantic_identity, corporate_action_manifest_child
from ..ports.corporate_action_event_graph import (
    CorporateActionChildObservation,
    CorporateActionEventGraphUnitOfWorkFactory,
)
from .commands import ProcessTransactionCommand
from .corporate_action_execution import (
    CorporateActionExecutionDisposition,
    CorporateActionExecutionPlan,
    resolve_corporate_action_execution_gate,
)
from .corporate_action_release import CorporateActionReleaseMaterialization


class CorporateActionArrivalDisposition(StrEnum):
    """Classify live intake without conflating parking with financial execution."""

    ORDINARY = "ORDINARY"
    PARKED = "PARKED"
    INVALID = "INVALID"
    RELEASE_READY = "RELEASE_READY"


@dataclass(frozen=True, slots=True)
class CorporateActionArrivalResult:
    """Return the route and optional authenticated release plan."""

    disposition: CorporateActionArrivalDisposition
    plan: CorporateActionExecutionPlan | None = None
    release: CorporateActionReleaseMaterialization | None = None


class RouteCorporateActionChildArrivalUseCase:
    """Persist governed child evidence and fail closed until the cohort is READY."""

    def __init__(
        self,
        unit_of_work_factory: CorporateActionEventGraphUnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(self, command: ProcessTransactionCommand) -> CorporateActionArrivalResult:
        if not isinstance(command, ProcessTransactionCommand):
            raise TypeError("command must be a ProcessTransactionCommand")
        transaction = command.transaction
        child = corporate_action_manifest_child(transaction)
        if child is None:
            return CorporateActionArrivalResult(CorporateActionArrivalDisposition.ORDINARY)

        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("corporate-action arrival clock must be timezone-aware")
        observation = CorporateActionChildObservation(
            corporate_action_event_id=str(transaction.economic_event_id),
            portfolio_id=transaction.portfolio_id,
            linked_transaction_group_id=str(transaction.linked_transaction_group_id),
            parent_event_reference=str(transaction.parent_event_reference),
            child=child,
            transaction_epoch=transaction.epoch or 0,
            transaction_payload_fingerprint=(
                build_transaction_semantic_identity(transaction).payload_fingerprint
            ),
            delivery_event_id=command.metadata.event_id,
            correlation_id=command.metadata.correlation_id,
            observed_at=observed_at,
        )
        async with self._unit_of_work_factory() as unit_of_work:
            decision = await unit_of_work.event_graph.observe_child(observation)
            gate = resolve_corporate_action_execution_gate(observation, decision)
            if gate.disposition is CorporateActionExecutionDisposition.READY:
                if gate.plan is None:
                    raise ValueError("ready corporate-action gate is missing its execution plan")
                release = await unit_of_work.releases.materialize(gate.plan)
                await unit_of_work.commit()
                return CorporateActionArrivalResult(
                    CorporateActionArrivalDisposition.RELEASE_READY,
                    plan=gate.plan,
                    release=release,
                )
            await unit_of_work.commit()
            return CorporateActionArrivalResult(
                CorporateActionArrivalDisposition(gate.disposition.value)
            )
