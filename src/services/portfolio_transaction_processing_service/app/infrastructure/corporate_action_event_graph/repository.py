"""SQLAlchemy adapter for source-versioned corporate-action parent graphs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from portfolio_common.database_models import (
    CorporateActionChildObservationRecord,
    CorporateActionEventRecord,
    CorporateActionManifestEdgeRecord,
    CorporateActionManifestNodeRecord,
    CorporateActionManifestVersionRecord,
    Portfolio,
)
from portfolio_common.domain.calculation_lineage import FinancialSourceReference
from sqlalchemy import and_, insert, or_, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.transaction.corporate_action import (
    CorporateActionEventChild,
    CorporateActionEventGraph,
    CorporateActionEventStructuralStatus,
    CorporateActionManifestReadinessStatus,
    CorporateActionParentManifest,
    evaluate_corporate_action_manifest_readiness,
    resolve_corporate_action_event_graph,
)
from ...ports.corporate_action_event_graph import (
    ConflictingCorporateActionManifestError,
    CorporateActionBookScopeError,
    CorporateActionManifestAppendOutcome,
)


class SqlAlchemyCorporateActionEventGraphRepository:
    """Persist immutable manifests within the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_manifest(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome:
        if not isinstance(manifest, CorporateActionParentManifest):
            raise TypeError("manifest must be a CorporateActionParentManifest")
        await self._acquire_event_locks(manifest)
        async with self._session.begin_nested():
            return await self._append_locked(manifest)

    async def _append_locked(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome:
        events = await self._event_candidates(manifest)
        event = next(
            (
                candidate
                for candidate in events
                if candidate.corporate_action_event_id == manifest.corporate_action_event_id
                and candidate.linked_transaction_group_id == manifest.linked_transaction_group_id
                and candidate.parent_event_reference == manifest.parent_event_reference
            ),
            None,
        )
        if event is None and events:
            raise ConflictingCorporateActionManifestError(
                "corporate-action event or parent identity is already bound differently"
            )
        if event is None:
            event = await self._create_event(manifest)

        candidates = await self._manifest_candidates(event.id, manifest)
        matching_version = next(
            (
                candidate
                for candidate in candidates
                if candidate.manifest_version == manifest.version
            ),
            None,
        )
        if matching_version is not None:
            persisted = await self._manifest_from_record(matching_version, manifest.portfolio_id)
            if persisted.lineage_payload() == manifest.lineage_payload():
                return CorporateActionManifestAppendOutcome.UNCHANGED
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest version already exists with different content"
            )
        if candidates:
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest source identity or content is already bound "
                "to a different version"
            )

        expected_version = (event.current_manifest_version or 0) + 1
        if manifest.version != expected_version:
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest versions must append contiguously"
            )
        structural_plan = resolve_corporate_action_event_graph(
            CorporateActionEventGraph(
                corporate_action_event_id=manifest.corporate_action_event_id,
                linked_transaction_group_id=manifest.linked_transaction_group_id,
                parent_event_reference=manifest.parent_event_reference,
                version=manifest.version,
                children=manifest.expected_children,
            )
        )
        incomplete_empty_manifest = (
            not manifest.completion_declared and not manifest.expected_children
        )
        if (
            structural_plan.status is not CorporateActionEventStructuralStatus.STRUCTURALLY_VALID
            and not incomplete_empty_manifest
        ):
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest graph must be structurally valid before normalization"
            )
        predecessor = await self._current_manifest(event)
        manifest_record_id = await self._insert_manifest(
            event=event,
            manifest=manifest,
            predecessor=predecessor,
            expected_edge_count=structural_plan.declared_edge_count,
        )
        ordinal_by_transaction_id = {
            child.transaction_id: ordinal
            for ordinal, child in enumerate(structural_plan.ordered_children)
        }
        await self._insert_nodes(
            manifest_record_id,
            manifest.expected_children,
            ordinal_by_transaction_id,
        )
        await self._insert_edges(manifest_record_id, manifest.expected_children)
        readiness = evaluate_corporate_action_manifest_readiness(
            manifest=manifest,
            observed_children=await self._latest_observed_children(event.id),
        )
        await self._advance_event(
            event,
            manifest_version=manifest.version,
            readiness_status=readiness.status,
        )
        return CorporateActionManifestAppendOutcome.APPENDED

    async def load_current_manifest(
        self,
        *,
        portfolio_id: str,
        corporate_action_event_id: str,
    ) -> CorporateActionParentManifest | None:
        event = await self._session.scalar(
            select(CorporateActionEventRecord).where(
                CorporateActionEventRecord.portfolio_id == portfolio_id,
                CorporateActionEventRecord.corporate_action_event_id == corporate_action_event_id,
            )
        )
        if event is None or event.current_manifest_version is None:
            return None
        record = await self._manifest_version(event.id, event.current_manifest_version)
        if record is None:
            raise ConflictingCorporateActionManifestError(
                "corporate-action event current manifest pointer is unresolved"
            )
        return await self._manifest_from_record(record, portfolio_id)

    async def _acquire_event_locks(self, manifest: CorporateActionParentManifest) -> None:
        lock_identities = sorted(
            (
                "corporate-action-event-id:"
                f"{manifest.portfolio_id}:{manifest.corporate_action_event_id}",
                "corporate-action-parent:"
                f"{manifest.portfolio_id}:{manifest.linked_transaction_group_id}:"
                f"{manifest.parent_event_reference}",
            )
        )
        for lock_identity in lock_identities:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"),
                {"lock_identity": lock_identity},
            )

    async def _event_candidates(
        self,
        manifest: CorporateActionParentManifest,
    ) -> Sequence[CorporateActionEventRecord]:
        return cast(
            Sequence[CorporateActionEventRecord],
            (
                await self._session.scalars(
                    select(CorporateActionEventRecord).where(
                        CorporateActionEventRecord.portfolio_id == manifest.portfolio_id,
                        or_(
                            CorporateActionEventRecord.corporate_action_event_id
                            == manifest.corporate_action_event_id,
                            and_(
                                CorporateActionEventRecord.linked_transaction_group_id
                                == manifest.linked_transaction_group_id,
                                CorporateActionEventRecord.parent_event_reference
                                == manifest.parent_event_reference,
                            ),
                        ),
                    )
                )
            ).all(),
        )

    async def _create_event(
        self,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionEventRecord:
        book_scope = (
            await self._session.execute(
                select(Portfolio.tenant_id, Portfolio.legal_book_id).where(
                    Portfolio.portfolio_id == manifest.portfolio_id
                )
            )
        ).one_or_none()
        if book_scope is None or not book_scope.tenant_id or not book_scope.legal_book_id:
            raise CorporateActionBookScopeError(
                "corporate-action manifest portfolio has no complete governed book scope"
            )
        inserted = await self._session.execute(
            insert(CorporateActionEventRecord)
            .values(
                tenant_id=book_scope.tenant_id,
                legal_book_id=book_scope.legal_book_id,
                portfolio_id=manifest.portfolio_id,
                corporate_action_event_id=manifest.corporate_action_event_id,
                linked_transaction_group_id=manifest.linked_transaction_group_id,
                parent_event_reference=manifest.parent_event_reference,
            )
            .returning(CorporateActionEventRecord)
        )
        return inserted.scalar_one()

    async def _latest_observed_children(
        self,
        event_id: int,
    ) -> tuple[CorporateActionEventChild, ...]:
        records = (
            await self._session.scalars(
                select(CorporateActionChildObservationRecord)
                .where(CorporateActionChildObservationRecord.event_id == event_id)
                .distinct(CorporateActionChildObservationRecord.transaction_id)
                .order_by(
                    CorporateActionChildObservationRecord.transaction_id,
                    CorporateActionChildObservationRecord.transaction_epoch.desc(),
                    CorporateActionChildObservationRecord.observation_sequence.desc(),
                )
            )
        ).all()
        return tuple(_child_from_observation(record) for record in records)

    async def _manifest_version(
        self,
        event_id: int,
        manifest_version: int,
    ) -> CorporateActionManifestVersionRecord | None:
        return await self._session.scalar(
            select(CorporateActionManifestVersionRecord).where(
                CorporateActionManifestVersionRecord.event_id == event_id,
                CorporateActionManifestVersionRecord.manifest_version == manifest_version,
            )
        )

    async def _manifest_candidates(
        self,
        event_id: int,
        manifest: CorporateActionParentManifest,
    ) -> Sequence[CorporateActionManifestVersionRecord]:
        record = CorporateActionManifestVersionRecord
        return cast(
            Sequence[CorporateActionManifestVersionRecord],
            (
                await self._session.scalars(
                    select(record).where(
                        record.event_id == event_id,
                        or_(
                            record.manifest_version == manifest.version,
                            record.manifest_content_hash == manifest.content_hash,
                            and_(
                                record.source_system == manifest.source_reference.source_system,
                                record.source_record_id
                                == manifest.source_reference.source_record_id,
                                record.source_revision == manifest.source_reference.source_revision,
                            ),
                        ),
                    )
                )
            ).all(),
        )

    async def _current_manifest(
        self,
        event: CorporateActionEventRecord,
    ) -> CorporateActionManifestVersionRecord | None:
        if event.current_manifest_version is None:
            return None
        predecessor = await self._manifest_version(event.id, event.current_manifest_version)
        if predecessor is None:
            raise ConflictingCorporateActionManifestError(
                "corporate-action event current manifest pointer is unresolved"
            )
        return predecessor

    async def _insert_manifest(
        self,
        *,
        event: CorporateActionEventRecord,
        manifest: CorporateActionParentManifest,
        predecessor: CorporateActionManifestVersionRecord | None,
        expected_edge_count: int,
    ) -> int:
        result = await self._session.execute(
            insert(CorporateActionManifestVersionRecord)
            .values(
                event_id=event.id,
                manifest_version=manifest.version,
                corporate_action_type=manifest.corporate_action_type,
                completion_declared=manifest.completion_declared,
                source_system=manifest.source_reference.source_system,
                source_record_id=manifest.source_reference.source_record_id,
                source_revision=manifest.source_reference.source_revision,
                source_content_hash=manifest.source_reference.source_content_hash,
                source_observed_at=manifest.source_reference.observed_at,
                manifest_content_hash=manifest.content_hash,
                previous_manifest_id=predecessor.id if predecessor is not None else None,
                previous_manifest_content_hash=(
                    predecessor.manifest_content_hash if predecessor is not None else None
                ),
                expected_node_count=len(manifest.expected_children),
                expected_edge_count=expected_edge_count,
                opened_observation_sequence=event.last_observation_sequence,
                manifest_payload=_manifest_json_payload(manifest),
            )
            .returning(CorporateActionManifestVersionRecord.id)
        )
        return cast(int, result.scalar_one())

    async def _insert_nodes(
        self,
        manifest_id: int,
        children: tuple[CorporateActionEventChild, ...],
        ordinal_by_transaction_id: dict[str, int],
    ) -> None:
        if not children:
            return
        await self._session.execute(
            insert(CorporateActionManifestNodeRecord),
            [
                {
                    "manifest_id": manifest_id,
                    "transaction_id": child.transaction_id,
                    "transaction_type": child.transaction_type,
                    "child_role": child.child_role,
                    "child_sequence_hint": child.child_sequence_hint,
                    "instrument_id": child.instrument_id,
                    "source_instrument_id": child.source_instrument_id,
                    "target_instrument_id": child.target_instrument_id,
                    "child_content_hash": child.content_hash,
                    "resolved_execution_ordinal": ordinal_by_transaction_id[child.transaction_id],
                }
                for child in children
            ],
        )

    async def _insert_edges(
        self,
        manifest_id: int,
        children: tuple[CorporateActionEventChild, ...],
    ) -> None:
        edges = [
            {
                "manifest_id": manifest_id,
                "predecessor_transaction_id": predecessor,
                "successor_transaction_id": child.transaction_id,
            }
            for child in children
            for predecessor in child.dependency_transaction_ids
        ]
        if edges:
            await self._session.execute(insert(CorporateActionManifestEdgeRecord), edges)

    async def _advance_event(
        self,
        event: CorporateActionEventRecord,
        *,
        manifest_version: int,
        readiness_status: CorporateActionManifestReadinessStatus,
    ) -> None:
        current_manifest_predicate = (
            CorporateActionEventRecord.current_manifest_version.is_(None)
            if event.current_manifest_version is None
            else CorporateActionEventRecord.current_manifest_version
            == event.current_manifest_version
        )
        result = cast(
            CursorResult[tuple[object, ...]],
            await self._session.execute(
                update(CorporateActionEventRecord)
                .where(
                    CorporateActionEventRecord.id == event.id,
                    CorporateActionEventRecord.state_version == event.state_version,
                    current_manifest_predicate,
                )
                .values(
                    current_manifest_version=manifest_version,
                    readiness_status=readiness_status.value,
                    state_version=event.state_version + 1,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConflictingCorporateActionManifestError(
                "corporate-action event state changed during manifest append"
            )

    async def _manifest_from_record(
        self,
        record: CorporateActionManifestVersionRecord,
        portfolio_id: str,
    ) -> CorporateActionParentManifest:
        nodes = (
            await self._session.scalars(
                select(CorporateActionManifestNodeRecord)
                .where(CorporateActionManifestNodeRecord.manifest_id == record.id)
                .order_by(CorporateActionManifestNodeRecord.transaction_id)
            )
        ).all()
        edges = (
            await self._session.scalars(
                select(CorporateActionManifestEdgeRecord)
                .where(CorporateActionManifestEdgeRecord.manifest_id == record.id)
                .order_by(
                    CorporateActionManifestEdgeRecord.successor_transaction_id,
                    CorporateActionManifestEdgeRecord.predecessor_transaction_id,
                )
            )
        ).all()
        predecessors_by_successor: defaultdict[str, list[str]] = defaultdict(list)
        for edge in edges:
            predecessors_by_successor[edge.successor_transaction_id].append(
                edge.predecessor_transaction_id
            )
        event = await self._event_identity(record.event_id)
        if event.portfolio_id != portfolio_id:
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest event portfolio is inconsistent"
            )
        manifest = CorporateActionParentManifest(
            corporate_action_event_id=event.corporate_action_event_id,
            portfolio_id=portfolio_id,
            linked_transaction_group_id=event.linked_transaction_group_id,
            parent_event_reference=event.parent_event_reference,
            corporate_action_type=record.corporate_action_type,
            version=record.manifest_version,
            completion_declared=record.completion_declared,
            expected_children=tuple(
                CorporateActionEventChild(
                    transaction_id=node.transaction_id,
                    transaction_type=node.transaction_type,
                    child_role=node.child_role,
                    dependency_transaction_ids=tuple(
                        predecessors_by_successor[node.transaction_id]
                    ),
                    child_sequence_hint=node.child_sequence_hint,
                    instrument_id=node.instrument_id,
                    source_instrument_id=node.source_instrument_id,
                    target_instrument_id=node.target_instrument_id,
                )
                for node in nodes
            ),
            source_reference=FinancialSourceReference(
                source_system=record.source_system,
                source_record_id=record.source_record_id,
                source_revision=record.source_revision,
                source_content_hash=record.source_content_hash,
                observed_at=record.source_observed_at,
            ),
        )
        _verify_persisted_manifest(record, nodes, edges, manifest)
        return manifest

    async def _event_identity(self, event_id: int) -> CorporateActionEventRecord:
        event = await self._session.get(CorporateActionEventRecord, event_id)
        if event is None:
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest references a missing event"
            )
        return event


def _manifest_json_payload(manifest: CorporateActionParentManifest) -> dict[str, object]:
    payload = manifest.lineage_payload()
    source = dict(cast(dict[str, object], payload["source_reference"]))
    observed_at = source["observed_at"]
    if not isinstance(observed_at, datetime):
        raise TypeError("manifest source observed_at must be a datetime")
    source["observed_at"] = observed_at.astimezone(UTC).isoformat()
    payload["source_reference"] = source
    return cast(dict[str, object], payload)


def _child_from_observation(
    record: CorporateActionChildObservationRecord,
) -> CorporateActionEventChild:
    payload = record.observed_payload
    if not isinstance(payload, dict) or payload.get("canonical_payload_version") != 1:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action child observation payload version is unsupported"
        )
    dependencies = payload.get("dependency_transaction_ids")
    if not isinstance(dependencies, list):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action child observation dependencies are invalid"
        )
    try:
        child = CorporateActionEventChild(
            transaction_id=cast(str, payload["transaction_id"]),
            transaction_type=cast(str, payload["transaction_type"]),
            child_role=cast(str, payload["child_role"]),
            dependency_transaction_ids=tuple(cast(list[str], dependencies)),
            child_sequence_hint=cast(int | None, payload.get("child_sequence_hint")),
            instrument_id=cast(str | None, payload.get("instrument_id")),
            source_instrument_id=cast(str | None, payload.get("source_instrument_id")),
            target_instrument_id=cast(str | None, payload.get("target_instrument_id")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action child observation payload is invalid"
        ) from exc
    if child.content_hash != record.observed_content_hash:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action child observation hash is inconsistent"
        )
    return child


def _verify_persisted_manifest(
    record: CorporateActionManifestVersionRecord,
    nodes: Sequence[CorporateActionManifestNodeRecord],
    edges: Sequence[CorporateActionManifestEdgeRecord],
    manifest: CorporateActionParentManifest,
) -> None:
    if len(nodes) != record.expected_node_count:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest node count is inconsistent"
        )
    if len(edges) != record.expected_edge_count:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest edge count is inconsistent"
        )
    structural_plan = resolve_corporate_action_event_graph(
        CorporateActionEventGraph(
            corporate_action_event_id=manifest.corporate_action_event_id,
            linked_transaction_group_id=manifest.linked_transaction_group_id,
            parent_event_reference=manifest.parent_event_reference,
            version=manifest.version,
            children=manifest.expected_children,
        )
    )
    incomplete_empty_manifest = not manifest.completion_declared and not manifest.expected_children
    if (
        structural_plan.status is not CorporateActionEventStructuralStatus.STRUCTURALLY_VALID
        and not incomplete_empty_manifest
    ):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest graph is structurally inconsistent"
        )
    ordinal_by_transaction_id = {
        child.transaction_id: ordinal
        for ordinal, child in enumerate(structural_plan.ordered_children)
    }
    if any(
        node.resolved_execution_ordinal != ordinal_by_transaction_id[node.transaction_id]
        for node in nodes
    ):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest execution order is inconsistent"
        )
    expected_by_transaction_id = {
        child.transaction_id: child for child in manifest.expected_children
    }
    if any(
        node.child_content_hash != expected_by_transaction_id[node.transaction_id].content_hash
        for node in nodes
    ):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest child hash is inconsistent"
        )
    if record.manifest_content_hash != manifest.content_hash:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest content hash is inconsistent"
        )
    if record.manifest_payload != _manifest_json_payload(manifest):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest payload is not canonical"
        )
