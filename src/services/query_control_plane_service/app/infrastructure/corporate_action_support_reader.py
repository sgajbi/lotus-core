"""SQLAlchemy adapter for bounded current corporate-action supportability."""

from typing import Any

from portfolio_common.database_models import (
    CorporateActionEventRecord,
    CorporateActionExecutionReleaseRecord,
    CorporateActionManifestVersionRecord,
    CorporateActionReadinessEvaluationRecord,
    Portfolio,
)
from sqlalchemy import Select, case, cast, exists, func, select
from sqlalchemy.dialects.postgresql import JSONPATH
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
        query_arguments = dict(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            corporate_action_event_id=corporate_action_event_id,
            readiness_status=readiness_status,
            execution_status=execution_status,
        )
        scope_count = (await self._db.execute(_scope_and_count(**query_arguments))).one()
        total = int(scope_count.event_count or 0)
        scope_exists = bool(scope_count.scope_exists)
        if total == 0:
            return CorporateActionEventEvidencePage(
                total=0,
                items=(),
                scope_exists=scope_exists,
            )
        filtered = _current_projection(**query_arguments)
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
            scope_exists=scope_exists,
        )


def _scope_and_count(
    *,
    tenant_id: str,
    legal_book_id: str,
    portfolio_id: str,
    corporate_action_event_id: str | None,
    readiness_status: str | None,
    execution_status: str | None,
) -> Select[Any]:
    scope_exists = exists(
        select(Portfolio.id).where(
            Portfolio.tenant_id == tenant_id,
            Portfolio.legal_book_id == legal_book_id,
            Portfolio.portfolio_id == portfolio_id,
        )
    ).label("scope_exists")
    event_count = (
        _current_projection(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            corporate_action_event_id=corporate_action_event_id,
            readiness_status=readiness_status,
            execution_status=execution_status,
            count=True,
        )
        .scalar_subquery()
        .label("event_count")
    )
    return select(scope_exists, event_count)


def _current_projection(
    *,
    tenant_id: str,
    legal_book_id: str,
    portfolio_id: str,
    corporate_action_event_id: str | None,
    readiness_status: str | None,
    execution_status: str | None,
    count: bool = False,
) -> Select[Any]:
    event = CorporateActionEventRecord
    manifest = CorporateActionManifestVersionRecord
    readiness = CorporateActionReadinessEvaluationRecord
    release = CorporateActionExecutionReleaseRecord
    if count:
        projection = (func.count(event.id).label("event_count"),)
    else:
        projection = (
            event.corporate_action_event_id,
            event.linked_transaction_group_id,
            event.parent_event_reference,
            event.state_version,
            event.current_manifest_version,
            event.readiness_status,
            event.last_observation_sequence,
            event.created_at.label("event_created_at"),
            event.updated_at.label("event_updated_at"),
            manifest.manifest_version,
            manifest.corporate_action_type,
            manifest.completion_declared,
            manifest.expected_node_count,
            manifest.expected_edge_count,
            manifest.opened_observation_sequence,
            manifest.source_system,
            manifest.source_record_id,
            manifest.source_revision,
            manifest.source_content_hash,
            manifest.manifest_content_hash.label("current_manifest_content_hash"),
            manifest.source_observed_at,
            readiness.through_observation_sequence,
            readiness.manifest_content_hash.label("readiness_manifest_content_hash"),
            readiness.execution_plan_content_hash,
            func.jsonb_array_length(readiness.ordered_transaction_ids).label(
                "ordered_member_count"
            ),
            func.jsonb_array_length(readiness.findings).label("finding_count"),
            func.jsonb_path_query_array(
                readiness.findings,
                cast("$.**.reason", JSONPATH),
            ).label("finding_reason_codes"),
            readiness.correlation_id,
            readiness.created_at.label("evaluated_at"),
            release.id.label("release_id"),
            release.release_authority_hash,
            release.status.label("execution_status"),
            release.member_count,
            release.next_execution_ordinal.label("completed_member_count"),
            release.attempt_count,
            release.fence_token,
            case(
                (release.lease_expires_at.is_(None), "NONE"),
                (release.lease_expires_at <= func.clock_timestamp(), "EXPIRED"),
                else_="ACTIVE",
            ).label("lease_state"),
            release.lease_expires_at,
            release.terminal_reason.label("terminal_reason_code"),
            release.created_at.label("release_created_at"),
            release.updated_at.label("release_updated_at"),
            release.completed_at,
        )
    statement = (
        select(*projection)
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


def _event_evidence(row: Any) -> CorporateActionEventEvidence:
    return CorporateActionEventEvidence(
        corporate_action_event_id=row.corporate_action_event_id,
        linked_transaction_group_id=row.linked_transaction_group_id,
        parent_event_reference=row.parent_event_reference,
        state_version=row.state_version,
        current_manifest_version=row.current_manifest_version,
        readiness_status=row.readiness_status,
        last_observation_sequence=row.last_observation_sequence,
        event_created_at=row.event_created_at,
        event_updated_at=row.event_updated_at,
        current_manifest=_manifest_evidence(row),
        readiness=_readiness_evidence(row),
        execution_release=_release_evidence(row),
    )


def _manifest_evidence(row: Any) -> CorporateActionManifestEvidence | None:
    if row.manifest_version is None:
        return None
    return CorporateActionManifestEvidence(
        manifest_version=row.manifest_version,
        corporate_action_type=row.corporate_action_type,
        completion_declared=row.completion_declared,
        expected_node_count=row.expected_node_count,
        expected_edge_count=row.expected_edge_count,
        opened_observation_sequence=row.opened_observation_sequence,
        source_system=row.source_system,
        source_record_id=row.source_record_id,
        source_revision=row.source_revision,
        source_content_hash=row.source_content_hash,
        manifest_content_hash=row.current_manifest_content_hash,
        source_observed_at=row.source_observed_at,
    )


def _readiness_evidence(row: Any) -> CorporateActionReadinessEvidence:
    reason_codes = tuple(sorted({str(reason) for reason in row.finding_reason_codes if reason}))
    return CorporateActionReadinessEvidence(
        through_observation_sequence=row.through_observation_sequence,
        manifest_content_hash=row.readiness_manifest_content_hash,
        execution_plan_content_hash=row.execution_plan_content_hash,
        ordered_member_count=row.ordered_member_count,
        finding_count=row.finding_count,
        finding_reason_codes=reason_codes,
        correlation_id=row.correlation_id,
        evaluated_at=row.evaluated_at,
    )


def _release_evidence(row: Any) -> CorporateActionExecutionReleaseEvidence | None:
    if row.release_id is None:
        return None
    return CorporateActionExecutionReleaseEvidence(
        release_id=row.release_id,
        release_authority_hash=row.release_authority_hash,
        status=row.execution_status,
        member_count=row.member_count,
        completed_member_count=row.completed_member_count,
        attempt_count=row.attempt_count,
        fence_token=row.fence_token,
        lease_state=row.lease_state,
        lease_expires_at=row.lease_expires_at,
        terminal_reason_code=row.terminal_reason_code,
        created_at=row.release_created_at,
        updated_at=row.release_updated_at,
        completed_at=row.completed_at,
    )
