"""Verify transport-to-domain corporate-action manifest mapping."""

from unittest.mock import AsyncMock

import pytest
from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent

from src.services.portfolio_transaction_processing_service.app.application.corporate_action_manifest_ingestion import (  # noqa: E501
    HandleCorporateActionManifestEventUseCase,
    map_corporate_action_manifest_event,
)
from src.services.portfolio_transaction_processing_service.app.ports.corporate_action_event_graph import (  # noqa: E501
    CorporateActionManifestAppendOutcome,
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


@pytest.mark.asyncio
async def test_handler_registers_exact_mapped_manifest() -> None:
    register_manifest = AsyncMock()
    register_manifest.execute.return_value = CorporateActionManifestAppendOutcome.APPENDED
    handler = HandleCorporateActionManifestEventUseCase(register_manifest)

    result = await handler.execute(_event())

    assert result is CorporateActionManifestAppendOutcome.APPENDED
    registered = register_manifest.execute.await_args.args[0]
    assert registered.content_hash == map_corporate_action_manifest_event(_event()).content_hash
    register_manifest.execute.assert_awaited_once()
