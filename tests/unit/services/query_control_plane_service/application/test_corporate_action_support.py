"""Specify bounded mapping and validation for corporate-action support evidence."""

from datetime import UTC, datetime, timedelta

import pytest

from src.services.query_control_plane_service.app.application.corporate_action_support import (
    CorporateActionSupportService,
)
from src.services.query_control_plane_service.app.domain.corporate_action_support import (
    CorporateActionEventEvidence,
    CorporateActionEventEvidencePage,
    CorporateActionExecutionReleaseEvidence,
    CorporateActionManifestEvidence,
    CorporateActionReadinessEvidence,
)

NOW = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)


class _Reader:
    def __init__(self, page: CorporateActionEventEvidencePage) -> None:
        self.page = page
        self.requests = []

    async def list_current(self, **kwargs):
        self.requests.append(kwargs)
        return self.page


def _evidence() -> CorporateActionEventEvidence:
    return CorporateActionEventEvidence(
        corporate_action_event_id="CA-EVENT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        state_version=4,
        current_manifest_version=2,
        readiness_status="READY",
        last_observation_sequence=3,
        event_created_at=NOW - timedelta(minutes=5),
        event_updated_at=NOW,
        current_manifest=CorporateActionManifestEvidence(
            manifest_version=2,
            corporate_action_type="DEMERGER",
            completion_declared=True,
            expected_node_count=2,
            expected_edge_count=1,
            opened_observation_sequence=1,
            source_system="custodian-ca",
            source_record_id="SOURCE-001",
            source_revision="2",
            source_content_hash="a" * 64,
            manifest_content_hash="b" * 64,
            source_observed_at=NOW - timedelta(minutes=4),
        ),
        readiness=CorporateActionReadinessEvidence(
            through_observation_sequence=3,
            manifest_content_hash="b" * 64,
            execution_plan_content_hash="c" * 64,
            ordered_member_count=2,
            finding_count=0,
            finding_reason_codes=(),
            correlation_id="QCP:correlation-001",
            evaluated_at=NOW - timedelta(minutes=3),
        ),
        execution_release=CorporateActionExecutionReleaseEvidence(
            release_id=41,
            release_authority_hash="d" * 64,
            status="PROCESSING",
            member_count=2,
            completed_member_count=1,
            attempt_count=2,
            fence_token=2,
            lease_state="ACTIVE",
            lease_expires_at=NOW + timedelta(minutes=1),
            terminal_reason_code=None,
            created_at=NOW - timedelta(minutes=2),
            updated_at=NOW,
            completed_at=None,
        ),
    )


@pytest.mark.asyncio
async def test_service_returns_compact_current_authority_without_lease_secrets() -> None:
    reader = _Reader(CorporateActionEventEvidencePage(total=1, items=(_evidence(),)))
    service = CorporateActionSupportService(reader=reader, clock=lambda: NOW)

    response = await service.list_current(
        tenant_id=" TENANT-SG ",
        legal_book_id=" PB-SG-01 ",
        portfolio_id=" PORT-001 ",
        corporate_action_event_id=None,
        readiness_status="ready",
        execution_status="processing",
        skip=0,
        limit=50,
    )

    assert response.total == 1
    assert response.items[0].execution_release is not None
    assert response.items[0].execution_release.completed_member_count == 1
    assert reader.requests[0]["readiness_status"] == "READY"
    payload = response.model_dump(mode="json")
    serialized = str(payload)
    for denied in ("lease_token", "lease_owner", "manifest_payload", "transaction_payload"):
        assert denied not in serialized


@pytest.mark.asyncio
async def test_service_fails_closed_for_unsupported_status_and_page_size() -> None:
    service = CorporateActionSupportService(
        reader=_Reader(CorporateActionEventEvidencePage(total=1, items=(_evidence(),))),
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match="readiness_status"):
        await service.list_current(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            portfolio_id="PORT-001",
            corporate_action_event_id=None,
            readiness_status="UNKNOWN",
            execution_status=None,
            skip=0,
            limit=50,
        )
    with pytest.raises(ValueError, match="paging"):
        await service.list_current(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            portfolio_id="PORT-001",
            corporate_action_event_id=None,
            readiness_status=None,
            execution_status=None,
            skip=0,
            limit=101,
        )
    with pytest.raises(ValueError, match="paging"):
        await service.list_current(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            portfolio_id="PORT-001",
            corporate_action_event_id=None,
            readiness_status=None,
            execution_status=None,
            skip=10_001,
            limit=50,
        )


@pytest.mark.asyncio
async def test_service_uses_non_enumerating_not_found_for_empty_scope() -> None:
    service = CorporateActionSupportService(
        reader=_Reader(
            CorporateActionEventEvidencePage(total=0, items=(), scope_exists=False)
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(LookupError, match="scope was not found"):
        await service.list_current(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            portfolio_id="PORT-404",
            corporate_action_event_id="CA-404",
            readiness_status=None,
            execution_status=None,
            skip=0,
            limit=50,
        )


@pytest.mark.asyncio
async def test_service_returns_empty_page_for_valid_scope_without_matching_events() -> None:
    service = CorporateActionSupportService(
        reader=_Reader(CorporateActionEventEvidencePage(total=0, items=())),
        clock=lambda: NOW,
    )

    response = await service.list_current(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="PORT-001",
        corporate_action_event_id=None,
        readiness_status=None,
        execution_status="FAILED",
        skip=0,
        limit=50,
    )

    assert response.total == 0
    assert response.items == []
