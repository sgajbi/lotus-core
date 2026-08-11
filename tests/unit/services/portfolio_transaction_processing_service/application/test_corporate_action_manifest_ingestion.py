"""Verify transport-to-domain corporate-action manifest mapping."""

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent

from src.services.portfolio_transaction_processing_service.app.application.corporate_action_manifest_ingestion import (  # noqa: E501
    HandleCorporateActionManifestEventUseCase,
    map_corporate_action_manifest_event,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionManifestAppendOutcome,
    CorporateActionObservationAppendOutcome,
    CorporateActionReadinessDecision,
)


def _event() -> CorporateActionManifestReceivedEvent:
    return CorporateActionManifestReceivedEvent.model_validate(
        {
            "corporate_action_event_id": "EVENT_001",
            "tenant_id": "TENANT_SG",
            "legal_book_id": "BOOK_SG_PB",
            "portfolio_id": "PORTFOLIO_001",
            "linked_transaction_group_id": "GROUP_001",
            "parent_event_reference": "PARENT_001",
            "corporate_action_type": "SPIN_OFF",
            "version": 1,
            "completion_declared": True,
            "expected_children": [
                {
                    "transaction_id": "TX_SOURCE",
                    "transaction_type": "SPIN_OFF",
                    "child_role": "SOURCE_POSITION_REDUCE",
                    "instrument_id": "SECURITY_SOURCE",
                    "source_instrument_id": "SECURITY_SOURCE",
                    "target_instrument_id": "SECURITY_TARGET",
                },
                {
                    "transaction_id": "TX_TARGET",
                    "transaction_type": "SPIN_IN",
                    "child_role": "TARGET_POSITION_ADD",
                    "dependency_transaction_ids": ["TX_SOURCE"],
                    "instrument_id": "SECURITY_TARGET",
                    "source_instrument_id": "SECURITY_SOURCE",
                    "target_instrument_id": "SECURITY_TARGET",
                },
            ],
            "source": {
                "source_system": "corporate-actions-master",
                "source_record_id": "EVENT_001",
                "source_revision": "revision-1",
                "source_content_hash": "a" * 64,
                "observed_at": "2026-08-11T02:15:00Z",
            },
        }
    )


def test_mapping_preserves_complete_domain_and_source_authority() -> None:
    event = _event()

    manifest = map_corporate_action_manifest_event(event)

    assert manifest.corporate_action_event_id == "EVENT_001"
    assert manifest.tenant_id == "TENANT_SG"
    assert manifest.legal_book_id == "BOOK_SG_PB"
    assert manifest.portfolio_id == "PORTFOLIO_001"
    assert manifest.linked_transaction_group_id == "GROUP_001"
    assert manifest.corporate_action_type == "SPIN_OFF"
    assert tuple(child.transaction_id for child in manifest.expected_children) == (
        "TX_SOURCE",
        "TX_TARGET",
    )
    assert manifest.expected_children[1].dependency_transaction_ids == ("TX_SOURCE",)
    assert manifest.source_reference.source_content_hash == "a" * 64
    assert manifest.source_reference.observed_at == event.source.observed_at


class _EventGraph:
    def __init__(self, decision: CorporateActionReadinessDecision) -> None:
        self.decision = decision
        self.manifests = []

    async def append_manifest(self, manifest):
        self.manifests.append(manifest)
        return CorporateActionManifestAppendOutcome.APPENDED

    async def load_current_readiness(self, **_identity):
        return self.decision


class _Releases:
    def __init__(self) -> None:
        self.plans = []

    async def materialize(self, plan):
        self.plans.append(plan)


class _UnitOfWork:
    def __init__(self, decision: CorporateActionReadinessDecision) -> None:
        self.event_graph = _EventGraph(decision)
        self.releases = _Releases()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def commit(self) -> None:
        self.committed = True


def _decision(*, ready: bool) -> CorporateActionReadinessDecision:
    return CorporateActionReadinessDecision(
        observation_outcome=CorporateActionObservationAppendOutcome.UNCHANGED,
        readiness_status=(
            corporate_action.CorporateActionManifestReadinessStatus.READY
            if ready
            else corporate_action.CorporateActionManifestReadinessStatus.AWAITING_CHILDREN
        ),
        manifest_content_hash=canonical_content_hash({"manifest": 1}) if ready else None,
        structural_plan_content_hash=(canonical_content_hash({"plan": 1}) if ready else None),
        ordered_transaction_ids=("TX_SOURCE", "TX_TARGET") if ready else (),
        findings=(),
        state_version=3,
        through_observation_sequence=2,
    )


@pytest.mark.asyncio
async def test_handler_registers_exact_mapped_manifest_atomically() -> None:
    unit_of_work = _UnitOfWork(_decision(ready=False))
    handler = HandleCorporateActionManifestEventUseCase(  # type: ignore[arg-type]
        lambda: unit_of_work
    )

    result = await handler.execute(_event())

    assert result is CorporateActionManifestAppendOutcome.APPENDED
    registered = unit_of_work.event_graph.manifests[0]
    assert registered.content_hash == map_corporate_action_manifest_event(_event()).content_hash
    assert unit_of_work.releases.plans == []
    assert unit_of_work.committed


@pytest.mark.asyncio
async def test_handler_materializes_children_before_manifest_ready_generation() -> None:
    unit_of_work = _UnitOfWork(_decision(ready=True))
    handler = HandleCorporateActionManifestEventUseCase(  # type: ignore[arg-type]
        lambda: unit_of_work
    )

    await handler.execute(_event())

    assert len(unit_of_work.releases.plans) == 1
    assert unit_of_work.releases.plans[0].ordered_transaction_ids == (
        "TX_SOURCE",
        "TX_TARGET",
    )
    assert unit_of_work.committed
