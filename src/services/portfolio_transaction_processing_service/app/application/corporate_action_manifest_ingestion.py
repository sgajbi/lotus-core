"""Map and register source-owned corporate-action manifest events."""

from __future__ import annotations

from portfolio_common.domain.calculation_lineage import FinancialSourceReference
from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent

from ..domain.transaction.corporate_action import (
    CorporateActionEventChild,
    CorporateActionParentManifest,
)
from ..ports.corporate_action_event_graph import CorporateActionManifestAppendOutcome
from .corporate_action_event_graph import RegisterCorporateActionManifestUseCase


def map_corporate_action_manifest_event(
    event: CorporateActionManifestReceivedEvent,
) -> CorporateActionParentManifest:
    """Translate the normalized transport fact into domain-owned authority."""

    return CorporateActionParentManifest(
        corporate_action_event_id=event.corporate_action_event_id,
        portfolio_id=event.portfolio_id,
        linked_transaction_group_id=event.linked_transaction_group_id,
        parent_event_reference=event.parent_event_reference,
        corporate_action_type=event.corporate_action_type,
        version=event.version,
        completion_declared=event.completion_declared,
        expected_children=tuple(
            CorporateActionEventChild(
                transaction_id=child.transaction_id,
                transaction_type=child.transaction_type,
                child_role=child.child_role,
                dependency_transaction_ids=child.dependency_transaction_ids,
                child_sequence_hint=child.child_sequence_hint,
                instrument_id=child.instrument_id,
                source_instrument_id=child.source_instrument_id,
                target_instrument_id=child.target_instrument_id,
            )
            for child in event.expected_children
        ),
        source_reference=FinancialSourceReference(
            source_system=event.source.source_system,
            source_record_id=event.source.source_record_id,
            source_revision=event.source.source_revision,
            source_content_hash=event.source.source_content_hash,
            observed_at=event.source.observed_at,
        ),
    )


class HandleCorporateActionManifestEventUseCase:
    """Keep transport mapping outside the manifest persistence boundary."""

    def __init__(self, register_manifest: RegisterCorporateActionManifestUseCase) -> None:
        self._register_manifest = register_manifest

    async def execute(
        self,
        event: CorporateActionManifestReceivedEvent,
    ) -> CorporateActionManifestAppendOutcome:
        return await self._register_manifest.execute(map_corporate_action_manifest_event(event))
