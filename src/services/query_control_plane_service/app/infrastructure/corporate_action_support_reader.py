"""SQLAlchemy adapter for bounded current corporate-action supportability."""

from collections.abc import Sequence
from typing import Any

from portfolio_common.database_models import (
    CorporateActionEventRecord,
    CorporateActionExecutionReleaseRecord,
    CorporateActionManifestVersionRecord,
    CorporateActionReadinessEvaluationRecord,
)
from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.corporate_action_support import (
    CorporateActionEventEvidence,
    CorporateActionEventEvidencePage,
    CorporateActionExecutionReleaseEvidence,
    CorporateActionManifestEvidence,
    CorporateActionReadinessEvidence,
)


class SqlAlchemyCorporateActionSupportReader:
    """Read exactly one tenant/book/portfolio page in two database statements."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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
    ) -> CorporateActionEventEvidencePage:
        filtered = _current_projection(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            corporate_action_event_id=corporate_action_event_id,
            readiness_status=readiness_status,
            execution_status=execution_status,
        )
        total = int(
            (await self._db.scalar(select(func.count()).select_from(filtered.subquery()))) or 0
        )
        if total == 0:
            return CorporateActionEventEvidencePage(total=0, items=())
        rows = (
            await self._db.execute(
                filtered.order_by(
                    CorporateActionEventRecord.updated_at.desc(),
                    CorporateActionEventRecord.id.desc(),
                )
                .offset(skip)
                .limit(limit)
            )
        ).all()
        return CorporateActionEventEvidencePage(
            total=total,
            items=tuple(_event_evidence(row) for row in rows),
        )


def _current_projection(
    *,
    tenant_id: str,
    legal_book_id: str,
    portfolio_id: str,
    corporate_action_event_id: str | None,
    readiness_status: str | None,
    execution_status: str | None,
) -> Select[Any]:
    event = CorporateActionEventRecord
    manifest = CorporateActionManifestVersionRecord
    readiness = CorporateActionReadinessEvaluationRecord
    release = CorporateActionExecutionReleaseRecord
    lease_state = case(
        (release.lease_expires_at.is_(None), "NONE"),
        (release.lease_expires_at <= func.now(), "EXPIRED"),
        else_="ACTIVE",
    ).label("lease_state")
    statement = (
        select(event, manifest, readiness, release, lease_state)
        .outerjoin(
            manifest,
            (manifest.event_id == event.id)
            & (manifest.manifest_version == event.current_manifest_version),
        )
        .join(
            readiness,
            (readiness.event_id == event.id) & (readiness.state_version == event.state_version),
        )
        .outerjoin(release, release.readiness_evaluation_id == readiness.id)
        .where(
            event.tenant_id == tenant_id,
            event.legal_book_id == legal_book_id,
            event.portfolio_id == portfolio_id,
        )
    )
    if corporate_action_event_id is not None:
        statement = statement.where(event.corporate_action_event_id == corporate_action_event_id)
    if readiness_status is not None:
        statement = statement.where(event.readiness_status == readiness_status)
    if execution_status is not None:
        statement = statement.where(release.status == execution_status)
    return statement


def _event_evidence(row: Sequence[Any]) -> CorporateActionEventEvidence:
    event, manifest, readiness, release, lease_state = row
    return CorporateActionEventEvidence(
        corporate_action_event_id=event.corporate_action_event_id,
        linked_transaction_group_id=event.linked_transaction_group_id,
        parent_event_reference=event.parent_event_reference,
        state_version=event.state_version,
        current_manifest_version=event.current_manifest_version,
        readiness_status=event.readiness_status,
        last_observation_sequence=event.last_observation_sequence,
        event_created_at=event.created_at,
        event_updated_at=event.updated_at,
        current_manifest=_manifest_evidence(manifest),
        readiness=_readiness_evidence(readiness),
        execution_release=_release_evidence(release, lease_state),
    )


def _manifest_evidence(record: Any | None) -> CorporateActionManifestEvidence | None:
    if record is None:
        return None
    return CorporateActionManifestEvidence(
        manifest_version=record.manifest_version,
        corporate_action_type=record.corporate_action_type,
        completion_declared=record.completion_declared,
        expected_node_count=record.expected_node_count,
        expected_edge_count=record.expected_edge_count,
        opened_observation_sequence=record.opened_observation_sequence,
        source_system=record.source_system,
        source_record_id=record.source_record_id,
        source_revision=record.source_revision,
        source_content_hash=record.source_content_hash,
        manifest_content_hash=record.manifest_content_hash,
        source_observed_at=record.source_observed_at,
    )


def _readiness_evidence(record: Any) -> CorporateActionReadinessEvidence:
    reason_codes = tuple(
        sorted(
            {
                str(finding["reason"])
                for finding in record.findings
                if isinstance(finding, dict) and finding.get("reason")
            }
        )
    )
    return CorporateActionReadinessEvidence(
        through_observation_sequence=record.through_observation_sequence,
        manifest_content_hash=record.manifest_content_hash,
        execution_plan_content_hash=record.execution_plan_content_hash,
        ordered_member_count=len(record.ordered_transaction_ids),
        finding_reason_codes=reason_codes,
        correlation_id=record.correlation_id,
        evaluated_at=record.created_at,
    )


def _release_evidence(
    record: Any | None,
    lease_state: str,
) -> CorporateActionExecutionReleaseEvidence | None:
    if record is None:
        return None
    return CorporateActionExecutionReleaseEvidence(
        release_id=record.id,
        release_authority_hash=record.release_authority_hash,
        status=record.status,
        member_count=record.member_count,
        completed_member_count=record.next_execution_ordinal,
        attempt_count=record.attempt_count,
        fence_token=record.fence_token,
        lease_state=lease_state,
        lease_expires_at=record.lease_expires_at,
        terminal_reason_code=record.terminal_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )
