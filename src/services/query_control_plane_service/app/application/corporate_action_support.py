"""Serve bounded corporate-action operational evidence through a read port."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Literal, cast

from ..contracts.corporate_action_support import (
    CorporateActionEventSupportItem,
    CorporateActionEventSupportListResponse,
    CorporateActionExecutionReleaseSupport,
    CorporateActionManifestSupport,
    CorporateActionReadinessSupport,
)
from ..domain.corporate_action_support import CorporateActionEventEvidence
from ..ports.corporate_action_support import CorporateActionSupportReader

READINESS_STATUSES = frozenset(
    {
        "AWAITING_MANIFEST",
        "AWAITING_COMPLETION",
        "AWAITING_CHILDREN",
        "INVALID",
        "READY",
    }
)
EXECUTION_STATUSES = frozenset({"PENDING", "PROCESSING", "COMPLETE", "FAILED", "SUPERSEDED"})


class CorporateActionSupportService:
    """Validate scope and map persistence-independent evidence to public contracts."""

    def __init__(
        self,
        *,
        reader: CorporateActionSupportReader,
        clock: Callable[[], datetime],
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def list_current(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        portfolio_id: str,
        corporate_action_event_id: str | None,
        readiness_status: str | None,
        execution_status: str | None,
        skip: int,
        limit: int,
    ) -> CorporateActionEventSupportListResponse:
        tenant_id = _required_text(tenant_id, "tenant_id")
        legal_book_id = _required_text(legal_book_id, "legal_book_id")
        portfolio_id = _required_text(portfolio_id, "portfolio_id")
        corporate_action_event_id = _optional_text(
            corporate_action_event_id, "corporate_action_event_id"
        )
        readiness_status = _optional_status(
            readiness_status, "readiness_status", READINESS_STATUSES
        )
        execution_status = _optional_status(
            execution_status, "execution_status", EXECUTION_STATUSES
        )
        if skip < 0 or not 1 <= limit <= 100:
            raise ValueError("corporate-action support paging is outside the governed bound")
        page = await self._reader.list_current(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            corporate_action_event_id=corporate_action_event_id,
            readiness_status=readiness_status,
            execution_status=execution_status,
            skip=skip,
            limit=limit,
        )
        if page.total == 0:
            raise LookupError("corporate-action support scope was not found")
        return CorporateActionEventSupportListResponse(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            generated_at_utc=self._clock(),
            total=page.total,
            skip=skip,
            limit=limit,
            items=[_event_contract(item) for item in page.items],
        )


def _event_contract(evidence: CorporateActionEventEvidence) -> CorporateActionEventSupportItem:
    manifest = evidence.current_manifest
    readiness = evidence.readiness
    release = evidence.execution_release
    return CorporateActionEventSupportItem(
        corporate_action_event_id=evidence.corporate_action_event_id,
        linked_transaction_group_id=evidence.linked_transaction_group_id,
        parent_event_reference=evidence.parent_event_reference,
        state_version=evidence.state_version,
        current_manifest_version=evidence.current_manifest_version,
        readiness_status=cast(ReadinessStatus, evidence.readiness_status),
        last_observation_sequence=evidence.last_observation_sequence,
        event_created_at=evidence.event_created_at,
        event_updated_at=evidence.event_updated_at,
        current_manifest=(
            CorporateActionManifestSupport(**asdict(manifest)) if manifest is not None else None
        ),
        readiness=CorporateActionReadinessSupport(
            through_observation_sequence=readiness.through_observation_sequence,
            manifest_content_hash=readiness.manifest_content_hash,
            execution_plan_content_hash=readiness.execution_plan_content_hash,
            ordered_member_count=readiness.ordered_member_count,
            finding_count=len(readiness.finding_reason_codes),
            finding_reason_codes=list(readiness.finding_reason_codes),
            correlation_id=readiness.correlation_id,
            evaluated_at=readiness.evaluated_at,
        ),
        execution_release=(
            CorporateActionExecutionReleaseSupport(
                release_id=release.release_id,
                release_authority_hash=release.release_authority_hash,
                status=cast(ExecutionStatus, release.status),
                member_count=release.member_count,
                completed_member_count=release.completed_member_count,
                attempt_count=release.attempt_count,
                fence_token=release.fence_token,
                lease_state=cast(LeaseState, release.lease_state),
                lease_expires_at=release.lease_expires_at,
                terminal_reason_code=release.terminal_reason_code,
                created_at=release.created_at,
                updated_at=release.updated_at,
                completed_at=release.completed_at,
            )
            if release is not None
            else None
        ),
    )


ReadinessStatus = Literal[
    "AWAITING_MANIFEST",
    "AWAITING_COMPLETION",
    "AWAITING_CHILDREN",
    "INVALID",
    "READY",
]
ExecutionStatus = Literal["PENDING", "PROCESSING", "COMPLETE", "FAILED", "SUPERSEDED"]
LeaseState = Literal["NONE", "ACTIVE", "EXPIRED"]


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    return None if value is None else _required_text(value, field_name)


def _optional_status(
    value: str | None,
    field_name: str,
    allowed: frozenset[str],
) -> str | None:
    if value is None:
        return None
    normalized = _required_text(value, field_name).upper()
    if normalized not in allowed:
        raise ValueError(f"{field_name} is not a supported status")
    return normalized
