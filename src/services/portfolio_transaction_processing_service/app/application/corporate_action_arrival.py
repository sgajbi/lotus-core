"""Park manifest-governed children before any financial mutation can occur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ..domain import build_transaction_semantic_identity, corporate_action_manifest_child
from ..ports.corporate_action_event_graph import CorporateActionChildObservation
from .commands import ProcessTransactionCommand
from .corporate_action_event_graph import RegisterCorporateActionChildObservationUseCase
from .corporate_action_execution import (
    CorporateActionExecutionDisposition,
    CorporateActionExecutionPlan,
    resolve_corporate_action_execution_gate,
)


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


class RouteCorporateActionChildArrivalUseCase:
    """Persist governed child evidence and fail closed until the cohort is READY."""

    def __init__(
        self,
        register_observation: RegisterCorporateActionChildObservationUseCase,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._register_observation = register_observation
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
        decision = await self._register_observation.execute(observation)
        gate = resolve_corporate_action_execution_gate(observation, decision)
        if gate.disposition is CorporateActionExecutionDisposition.READY:
            if gate.plan is None:
                raise ValueError("ready corporate-action gate is missing its execution plan")
            return CorporateActionArrivalResult(
                CorporateActionArrivalDisposition.RELEASE_READY,
                plan=gate.plan,
            )
        return CorporateActionArrivalResult(
            CorporateActionArrivalDisposition(gate.disposition.value)
        )
