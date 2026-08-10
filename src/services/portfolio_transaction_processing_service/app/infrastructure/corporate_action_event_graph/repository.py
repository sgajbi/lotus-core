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
    CorporateActionReadinessEvaluationRecord,
    Portfolio,
)
from portfolio_common.database_models import (
    Transaction as TransactionRecord,
)
from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from sqlalchemy import and_, insert, or_, select, text, true, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...domain.transaction.corporate_action import (
    CorporateActionEventChild,
    CorporateActionEventGraph,
    CorporateActionEventStructuralPlan,
    CorporateActionEventStructuralStatus,
    CorporateActionManifestReadiness,
    CorporateActionManifestReadinessStatus,
    CorporateActionParentManifest,
    evaluate_corporate_action_manifest_readiness,
    resolve_corporate_action_event_graph,
)
from ...ports.corporate_action_event_graph import (
    ConflictingCorporateActionManifestError,
    ConflictingCorporateActionObservationError,
    CorporateActionBookScopeError,
    CorporateActionChildObservation,
    CorporateActionManifestAppendOutcome,
    CorporateActionObservationAppendOutcome,
    CorporateActionReadinessDecision,
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
        event = await self._resolve_event(
            manifest,
            conflict_error=ConflictingCorporateActionManifestError,
        )
        existing_outcome = await self._existing_manifest_outcome(event.id, manifest)
        if existing_outcome is not None:
            return existing_outcome

        expected_version = (event.current_manifest_version or 0) + 1
        if manifest.version != expected_version:
            raise ConflictingCorporateActionManifestError(
                "corporate-action manifest versions must append contiguously"
            )
        structural_plan = _validated_manifest_structural_plan(manifest)
        predecessor = await self._current_manifest(event)
        if predecessor is not None:
            await self._verify_manifest_chain(predecessor)
        opened_observation_sequence = (
            0 if manifest.version == 1 else event.last_observation_sequence
        )
        manifest_record_id = await self._insert_manifest(
            event=event,
            manifest=manifest,
            predecessor=predecessor,
            expected_edge_count=structural_plan.declared_edge_count,
            opened_observation_sequence=opened_observation_sequence,
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
            observed_children=await self._latest_observed_children(
                event.id,
                manifest_id=manifest_record_id,
                predecessor_manifest_id=predecessor.id if predecessor is not None else None,
                opened_observation_sequence=opened_observation_sequence,
            ),
        )
        next_state_version = event.state_version + 1
        await self._advance_event(
            event,
            manifest_version=manifest.version,
            readiness_status=readiness.status,
        )
        await self._insert_readiness_evaluation(
            event_id=event.id,
            state_version=next_state_version,
            manifest_id=manifest_record_id,
            through_observation_sequence=event.last_observation_sequence,
            readiness=readiness,
            correlation_id=None,
        )
        return CorporateActionManifestAppendOutcome.APPENDED

    async def observe_child(
        self,
        observation: CorporateActionChildObservation,
    ) -> CorporateActionReadinessDecision:
        _validate_child_observation(observation)
        await self._acquire_event_locks(observation)
        async with self._session.begin_nested():
            return await self._observe_child_locked(observation)

    async def _observe_child_locked(
        self,
        observation: CorporateActionChildObservation,
    ) -> CorporateActionReadinessDecision:
        event = await self._resolve_event(
            observation,
            conflict_error=ConflictingCorporateActionObservationError,
        )
        await self._require_observed_transaction_scope(observation)

        existing_delivery = await self._observation_by_delivery(
            event.id,
            observation.delivery_event_id,
        )
        if existing_delivery is not None:
            _require_same_observation(existing_delivery, observation)
            return await self._current_readiness_decision(
                event,
                CorporateActionObservationAppendOutcome.UNCHANGED,
            )
        semantic_retry = await self._observation_by_semantic_identity(event, observation)
        if semantic_retry is not None:
            return await self._current_readiness_decision(
                event,
                CorporateActionObservationAppendOutcome.UNCHANGED,
            )
        latest_observation = await self._latest_transaction_observation(
            event.id, observation.child.transaction_id
        )
        if latest_observation is not None and (
            observation.transaction_epoch < latest_observation.transaction_epoch
            or (
                observation.transaction_epoch == latest_observation.transaction_epoch
                and observation.child.content_hash != latest_observation.observed_content_hash
            )
        ):
            raise ConflictingCorporateActionObservationError(
                "corporate-action child correction epoch must increase monotonically"
            )

        next_observation_sequence = event.last_observation_sequence + 1
        await self._insert_observation(
            event.id,
            next_observation_sequence,
            observation,
        )
        readiness, manifest_record = await self._evaluate_current_event(event)
        next_state_version = event.state_version + 1
        await self._advance_observation_state(
            event,
            observation_sequence=next_observation_sequence,
            readiness_status=readiness.status,
        )
        await self._insert_readiness_evaluation(
            event_id=event.id,
            state_version=next_state_version,
            manifest_id=manifest_record.id if manifest_record is not None else None,
            through_observation_sequence=next_observation_sequence,
            readiness=readiness,
            correlation_id=observation.correlation_id,
        )
        return _readiness_decision(
            CorporateActionObservationAppendOutcome.APPENDED,
            readiness,
            state_version=next_state_version,
            through_observation_sequence=next_observation_sequence,
        )

    async def _resolve_event(
        self,
        identity: CorporateActionParentManifest | CorporateActionChildObservation,
        *,
        conflict_error: type[ValueError],
    ) -> CorporateActionEventRecord:
        candidates = await self._event_candidates(identity)
        event = next(
            (candidate for candidate in candidates if _same_event_identity(candidate, identity)),
            None,
        )
        if event is not None:
            return event
        if candidates:
            raise conflict_error(
                "corporate-action event or parent identity is already bound differently"
            )
        return await self._create_event(identity)

    async def _existing_manifest_outcome(
        self,
        event_id: int,
        manifest: CorporateActionParentManifest,
    ) -> CorporateActionManifestAppendOutcome | None:
        candidates = await self._manifest_candidates(event_id, manifest)
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
        return None

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

    async def _acquire_event_locks(
        self,
        identity: CorporateActionParentManifest | CorporateActionChildObservation,
    ) -> None:
        lock_identities = sorted(
            (
                "corporate-action-event-id:"
                f"{identity.portfolio_id}:{identity.corporate_action_event_id}",
                "corporate-action-parent:"
                f"{identity.portfolio_id}:{identity.linked_transaction_group_id}:"
                f"{identity.parent_event_reference}",
            )
        )
        for lock_identity in lock_identities:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"),
                {"lock_identity": lock_identity},
            )

    async def _event_candidates(
        self,
        identity: CorporateActionParentManifest | CorporateActionChildObservation,
    ) -> Sequence[CorporateActionEventRecord]:
        return cast(
            Sequence[CorporateActionEventRecord],
            (
                await self._session.scalars(
                    select(CorporateActionEventRecord).where(
                        CorporateActionEventRecord.portfolio_id == identity.portfolio_id,
                        or_(
                            CorporateActionEventRecord.corporate_action_event_id
                            == identity.corporate_action_event_id,
                            and_(
                                CorporateActionEventRecord.linked_transaction_group_id
                                == identity.linked_transaction_group_id,
                                CorporateActionEventRecord.parent_event_reference
                                == identity.parent_event_reference,
                            ),
                        ),
                    )
                )
            ).all(),
        )

    async def _create_event(
        self,
        identity: CorporateActionParentManifest | CorporateActionChildObservation,
    ) -> CorporateActionEventRecord:
        book_scope = (
            await self._session.execute(
                select(Portfolio.tenant_id, Portfolio.legal_book_id).where(
                    Portfolio.portfolio_id == identity.portfolio_id
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
                portfolio_id=identity.portfolio_id,
                corporate_action_event_id=identity.corporate_action_event_id,
                linked_transaction_group_id=identity.linked_transaction_group_id,
                parent_event_reference=identity.parent_event_reference,
            )
            .returning(CorporateActionEventRecord)
        )
        return inserted.scalar_one()

    async def _latest_observed_children(
        self,
        event_id: int,
        *,
        manifest_id: int,
        predecessor_manifest_id: int | None,
        opened_observation_sequence: int,
    ) -> tuple[CorporateActionEventChild, ...]:
        observation = CorporateActionChildObservationRecord
        current_node = aliased(CorporateActionManifestNodeRecord)
        predecessor_node = aliased(CorporateActionManifestNodeRecord)
        reusable_transaction_ids = (
            select(current_node.transaction_id)
            .join(
                predecessor_node,
                predecessor_node.transaction_id == current_node.transaction_id,
            )
            .where(
                current_node.manifest_id == manifest_id,
                predecessor_node.manifest_id == predecessor_manifest_id,
            )
        )
        records = (
            await self._session.scalars(
                select(observation)
                .where(
                    observation.event_id == event_id,
                    or_(
                        observation.observation_sequence > opened_observation_sequence,
                        observation.transaction_id.in_(reusable_transaction_ids),
                    ),
                )
                .distinct(observation.transaction_id)
                .order_by(
                    observation.transaction_id,
                    observation.transaction_epoch.desc(),
                    observation.observation_sequence.desc(),
                )
            )
        ).all()
        return tuple(_child_from_observation(record) for record in records)

    async def _require_observed_transaction_scope(
        self,
        observation: CorporateActionChildObservation,
    ) -> None:
        portfolio_id = await self._session.scalar(
            select(TransactionRecord.portfolio_id).where(
                TransactionRecord.transaction_id == observation.child.transaction_id
            )
        )
        if portfolio_id != observation.portfolio_id:
            raise CorporateActionBookScopeError(
                "corporate-action child observation transaction is outside event portfolio"
            )

    async def _observation_by_delivery(
        self,
        event_id: int,
        delivery_event_id: str,
    ) -> CorporateActionChildObservationRecord | None:
        return await self._session.scalar(
            select(CorporateActionChildObservationRecord).where(
                CorporateActionChildObservationRecord.event_id == event_id,
                CorporateActionChildObservationRecord.delivery_event_id == delivery_event_id,
            )
        )

    async def _observation_by_semantic_identity(
        self,
        event: CorporateActionEventRecord,
        observation: CorporateActionChildObservation,
    ) -> CorporateActionChildObservationRecord | None:
        current_manifest = await self._current_manifest(event)
        reusable_for_current_manifest = true()
        if current_manifest is not None:
            current_node = aliased(CorporateActionManifestNodeRecord)
            predecessor_node = aliased(CorporateActionManifestNodeRecord)
            reusable_transaction_ids = (
                select(current_node.transaction_id)
                .join(
                    predecessor_node,
                    predecessor_node.transaction_id == current_node.transaction_id,
                )
                .where(
                    current_node.manifest_id == current_manifest.id,
                    predecessor_node.manifest_id == current_manifest.previous_manifest_id,
                )
            )
            reusable_for_current_manifest = or_(
                CorporateActionChildObservationRecord.observation_sequence
                > current_manifest.opened_observation_sequence,
                CorporateActionChildObservationRecord.transaction_id.in_(
                    reusable_transaction_ids
                ),
            )
        return await self._session.scalar(
            select(CorporateActionChildObservationRecord).where(
                CorporateActionChildObservationRecord.event_id == event.id,
                CorporateActionChildObservationRecord.transaction_id
                == observation.child.transaction_id,
                CorporateActionChildObservationRecord.transaction_epoch
                == observation.transaction_epoch,
                CorporateActionChildObservationRecord.observed_content_hash
                == observation.child.content_hash,
                reusable_for_current_manifest,
            )
        )

    async def _latest_transaction_observation(
        self,
        event_id: int,
        transaction_id: str,
    ) -> CorporateActionChildObservationRecord | None:
        return await self._session.scalar(
            select(CorporateActionChildObservationRecord)
            .where(
                CorporateActionChildObservationRecord.event_id == event_id,
                CorporateActionChildObservationRecord.transaction_id == transaction_id,
            )
            .order_by(
                CorporateActionChildObservationRecord.transaction_epoch.desc(),
                CorporateActionChildObservationRecord.observation_sequence.desc(),
            )
            .limit(1)
        )

    async def _insert_observation(
        self,
        event_id: int,
        observation_sequence: int,
        observation: CorporateActionChildObservation,
    ) -> None:
        await self._session.execute(
            insert(CorporateActionChildObservationRecord).values(
                event_id=event_id,
                observation_sequence=observation_sequence,
                transaction_id=observation.child.transaction_id,
                transaction_epoch=observation.transaction_epoch,
                delivery_event_id=observation.delivery_event_id,
                correlation_id=observation.correlation_id,
                observed_content_hash=observation.child.content_hash,
                observed_payload=observation.child.lineage_payload(),
                observed_at=observation.observed_at,
            )
        )

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
        opened_observation_sequence: int,
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
                opened_observation_sequence=opened_observation_sequence,
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

    async def _advance_observation_state(
        self,
        event: CorporateActionEventRecord,
        *,
        observation_sequence: int,
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
                    CorporateActionEventRecord.last_observation_sequence
                    == event.last_observation_sequence,
                    current_manifest_predicate,
                )
                .values(
                    last_observation_sequence=observation_sequence,
                    readiness_status=readiness_status.value,
                    state_version=event.state_version + 1,
                )
            ),
        )
        if result.rowcount != 1:
            raise ConflictingCorporateActionObservationError(
                "corporate-action event state changed during child observation"
            )

    async def _evaluate_current_event(
        self,
        event: CorporateActionEventRecord,
    ) -> tuple[
        CorporateActionManifestReadiness,
        CorporateActionManifestVersionRecord | None,
    ]:
        manifest_record = await self._current_manifest(event)
        if manifest_record is None:
            return (
                evaluate_corporate_action_manifest_readiness(
                    manifest=None,
                    observed_children=(),
                ),
                None,
            )
        manifest = await self._manifest_from_record(manifest_record, event.portfolio_id)
        observed_children = await self._latest_observed_children(
            event.id,
            manifest_id=manifest_record.id,
            predecessor_manifest_id=manifest_record.previous_manifest_id,
            opened_observation_sequence=manifest_record.opened_observation_sequence,
        )
        return (
            evaluate_corporate_action_manifest_readiness(
                manifest=manifest,
                observed_children=observed_children,
            ),
            manifest_record,
        )

    async def _current_readiness_decision(
        self,
        event: CorporateActionEventRecord,
        observation_outcome: CorporateActionObservationAppendOutcome,
    ) -> CorporateActionReadinessDecision:
        readiness, _manifest_record = await self._evaluate_current_event(event)
        return _readiness_decision(
            observation_outcome,
            readiness,
            state_version=event.state_version,
            through_observation_sequence=event.last_observation_sequence,
        )

    async def _insert_readiness_evaluation(
        self,
        *,
        event_id: int,
        state_version: int,
        manifest_id: int | None,
        through_observation_sequence: int,
        readiness: CorporateActionManifestReadiness,
        correlation_id: str | None,
    ) -> None:
        ordered_transaction_ids = tuple(
            child.transaction_id for child in readiness.ordered_children
        )
        await self._session.execute(
            insert(CorporateActionReadinessEvaluationRecord).values(
                event_id=event_id,
                state_version=state_version,
                manifest_id=manifest_id,
                through_observation_sequence=through_observation_sequence,
                readiness_status=readiness.status.value,
                manifest_content_hash=readiness.manifest_content_hash,
                execution_plan_content_hash=(
                    _execution_plan_content_hash(
                        readiness.manifest_content_hash,
                        ordered_transaction_ids,
                    )
                    if readiness.status is CorporateActionManifestReadinessStatus.READY
                    else None
                ),
                findings=_readiness_findings_payload(readiness),
                ordered_transaction_ids=list(ordered_transaction_ids),
                correlation_id=correlation_id,
            )
        )

    async def _manifest_from_record(
        self,
        record: CorporateActionManifestVersionRecord,
        portfolio_id: str,
    ) -> CorporateActionParentManifest:
        await self._verify_manifest_chain(record)
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

    async def _verify_manifest_chain(
        self,
        record: CorporateActionManifestVersionRecord,
    ) -> None:
        history = (
            await self._session.scalars(
                select(CorporateActionManifestVersionRecord)
                .where(
                    CorporateActionManifestVersionRecord.event_id == record.event_id,
                    CorporateActionManifestVersionRecord.manifest_version
                    <= record.manifest_version,
                )
                .order_by(CorporateActionManifestVersionRecord.manifest_version)
            )
        ).all()
        _require_valid_manifest_chain(record, history)

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


def _same_event_identity(
    event: CorporateActionEventRecord,
    identity: CorporateActionParentManifest | CorporateActionChildObservation,
) -> bool:
    return bool(
        event.corporate_action_event_id == identity.corporate_action_event_id
        and event.linked_transaction_group_id == identity.linked_transaction_group_id
        and event.parent_event_reference == identity.parent_event_reference
    )


def _validated_manifest_structural_plan(
    manifest: CorporateActionParentManifest,
) -> CorporateActionEventStructuralPlan:
    plan = resolve_corporate_action_event_graph(
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
        plan.status is not CorporateActionEventStructuralStatus.STRUCTURALLY_VALID
        and not incomplete_empty_manifest
    ):
        raise ConflictingCorporateActionManifestError(
            "corporate-action manifest graph must be structurally valid before normalization"
        )
    return plan


def _validate_child_observation(observation: CorporateActionChildObservation) -> None:
    if not isinstance(observation, CorporateActionChildObservation):
        raise TypeError("observation must be a CorporateActionChildObservation")
    for field_name in (
        "corporate_action_event_id",
        "portfolio_id",
        "linked_transaction_group_id",
        "parent_event_reference",
        "delivery_event_id",
    ):
        _require_canonical_text(getattr(observation, field_name), field_name)
    if not isinstance(observation.child, CorporateActionEventChild):
        raise TypeError("child must be a CorporateActionEventChild")
    _require_nonnegative_integer(observation.transaction_epoch, "transaction_epoch")
    if observation.correlation_id is not None:
        _require_canonical_text(observation.correlation_id, "correlation_id")
    if (
        not isinstance(observation.observed_at, datetime)
        or observation.observed_at.utcoffset() is None
    ):
        raise ValueError("observed_at must be timezone-aware")


def _require_canonical_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-empty text")


def _require_nonnegative_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_same_observation(
    record: CorporateActionChildObservationRecord,
    observation: CorporateActionChildObservation,
) -> None:
    if (
        record.transaction_id != observation.child.transaction_id
        or record.transaction_epoch != observation.transaction_epoch
        or record.observed_content_hash != observation.child.content_hash
        or record.observed_payload != observation.child.lineage_payload()
        or record.correlation_id != observation.correlation_id
        or record.observed_at.astimezone(UTC) != observation.observed_at.astimezone(UTC)
    ):
        raise ConflictingCorporateActionObservationError(
            "corporate-action child delivery identity already exists with different evidence"
        )


def _execution_plan_content_hash(
    manifest_content_hash: str | None,
    ordered_transaction_ids: tuple[str, ...],
) -> str:
    if manifest_content_hash is None:
        raise ValueError("READY execution plan requires a manifest content hash")
    return cast(
        str,
        canonical_content_hash(
            {
                "canonical_payload_version": 1,
                "manifest_content_hash": manifest_content_hash,
                "ordered_transaction_ids": list(ordered_transaction_ids),
            }
        ),
    )


def _readiness_findings_payload(
    readiness: CorporateActionManifestReadiness,
) -> list[dict[str, object]]:
    return [
        {
            "reason": finding.reason.value,
            "transaction_ids": list(finding.transaction_ids),
            "graph_findings": [
                {
                    "reason": graph_finding.reason.value,
                    "transaction_ids": list(graph_finding.transaction_ids),
                    "dependency_transaction_ids": list(graph_finding.dependency_transaction_ids),
                }
                for graph_finding in finding.graph_findings
            ],
        }
        for finding in readiness.findings
    ]


def _readiness_decision(
    observation_outcome: CorporateActionObservationAppendOutcome,
    readiness: CorporateActionManifestReadiness,
    *,
    state_version: int,
    through_observation_sequence: int,
) -> CorporateActionReadinessDecision:
    return CorporateActionReadinessDecision(
        observation_outcome=observation_outcome,
        readiness_status=readiness.status,
        ordered_transaction_ids=tuple(child.transaction_id for child in readiness.ordered_children),
        findings=readiness.findings,
        state_version=state_version,
        through_observation_sequence=through_observation_sequence,
    )


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
    if child.transaction_id != record.transaction_id:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action child observation identity is inconsistent"
        )
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
    _require_persisted_manifest_counts(record, nodes, edges)
    structural_plan = _persisted_manifest_structural_plan(manifest)
    _require_persisted_manifest_node_evidence(nodes, manifest, structural_plan)
    _require_persisted_manifest_content(record, manifest)


def _require_persisted_manifest_counts(
    record: CorporateActionManifestVersionRecord,
    nodes: Sequence[CorporateActionManifestNodeRecord],
    edges: Sequence[CorporateActionManifestEdgeRecord],
) -> None:
    if len(nodes) != record.expected_node_count:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest node count is inconsistent"
        )
    if len(edges) != record.expected_edge_count:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest edge count is inconsistent"
        )


def _persisted_manifest_structural_plan(
    manifest: CorporateActionParentManifest,
) -> CorporateActionEventStructuralPlan:
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
    return structural_plan


def _require_persisted_manifest_node_evidence(
    nodes: Sequence[CorporateActionManifestNodeRecord],
    manifest: CorporateActionParentManifest,
    structural_plan: CorporateActionEventStructuralPlan,
) -> None:
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


def _require_persisted_manifest_content(
    record: CorporateActionManifestVersionRecord,
    manifest: CorporateActionParentManifest,
) -> None:
    if record.manifest_content_hash != manifest.content_hash:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest content hash is inconsistent"
        )
    if record.manifest_payload != _manifest_json_payload(manifest):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest payload is not canonical"
        )


def _require_valid_manifest_chain(
    record: CorporateActionManifestVersionRecord,
    history: Sequence[CorporateActionManifestVersionRecord],
) -> None:
    _require_manifest_chain_head(record, history)
    _require_manifest_chain_versions(record, history)
    _require_manifest_chain_root(history[0])
    _require_manifest_chain_links(history)


def _require_manifest_chain_head(
    record: CorporateActionManifestVersionRecord,
    history: Sequence[CorporateActionManifestVersionRecord],
) -> None:
    if not history or len(history) != record.manifest_version or history[-1].id != record.id:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest predecessor chain is not contiguous"
        )


def _require_manifest_chain_versions(
    record: CorporateActionManifestVersionRecord,
    history: Sequence[CorporateActionManifestVersionRecord],
) -> None:
    if tuple(item.manifest_version for item in history) != tuple(
        range(1, record.manifest_version + 1)
    ):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest predecessor chain is not contiguous"
        )


def _require_manifest_chain_root(root: CorporateActionManifestVersionRecord) -> None:
    if root.previous_manifest_id is not None or root.previous_manifest_content_hash is not None:
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest predecessor chain has an invalid root"
        )


def _require_manifest_chain_links(
    history: Sequence[CorporateActionManifestVersionRecord],
) -> None:
    if any(
        current.previous_manifest_id != predecessor.id
        or current.previous_manifest_content_hash != predecessor.manifest_content_hash
        for predecessor, current in zip(history, history[1:])
    ):
        raise ConflictingCorporateActionManifestError(
            "persisted corporate-action manifest predecessor chain is inconsistent"
        )
