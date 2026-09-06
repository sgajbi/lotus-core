"""PostgreSQL contracts for corporate-action parent-manifest persistence."""

from __future__ import annotations

import asyncio
import runpy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    CorporateActionChildObservationRecord,
    CorporateActionEventRecord,
    CorporateActionExecutionMemberRecord,
    CorporateActionExecutionReleaseRecord,
    CorporateActionManifestEdgeRecord,
    CorporateActionManifestNodeRecord,
    CorporateActionManifestVersionRecord,
    CorporateActionReadinessEvaluationRecord,
)
from portfolio_common.database_models import Transaction as TransactionRecord
from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from portfolio_common.events import TransactionEvent
from sqlalchemy import Engine, func, insert, inspect, select, text, update
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application import (
    ConflictingCorporateActionExecutionReleaseError,
    CorporateActionExecutionLeaseRequest,
    CorporateActionExecutionPlan,
    CorporateActionReleaseMaterializationOutcome,
    CorporateActionReleaseProgressOutcome,
    CorporateActionReleaseWorkerStatus,
    ProcessNextCorporateActionReleaseUseCase,
    ProcessTransactionCommand,
    ProcessTransactionResult,
    RouteCorporateActionChildArrivalUseCase,
    StaleCorporateActionExecutionPlanError,
    TransactionEventMetadata,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    build_transaction_semantic_identity,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_event_graph import (  # noqa: E501
    SqlAlchemyCorporateActionEventGraphRepository,
    SqlAlchemyCorporateActionEventGraphUnitOfWork,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_execution import (  # noqa: E501
    SqlAlchemyCorporateActionExecutionReleaseRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping.booked_transaction import (  # noqa: E501
    to_booked_transaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    ConflictingCorporateActionManifestError,
    ConflictingCorporateActionObservationError,
    CorporateActionBookScopeError,
    CorporateActionChildObservation,
    CorporateActionManifestAppendOutcome,
    CorporateActionObservationAppendOutcome,
    CorporateActionReadinessDecision,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c152b2c3d519_feat_add_corporate_action_event_graph.py"
)

RELEASE_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c153b2c3d520_feat_add_corporate_action_execution_releases.py"
)
SUPPORT_INDEX_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c154b2c3d521_perf_index_corporate_action_support.py"
)
AUTHORITY_FIX_FORWARD_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c155b2c3d522_fix_forward_corporate_action_authority.py"
)


async def test_manifest_append_retry_conflict_chain_and_reconstruction(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    first = _manifest()
    second = replace(
        first,
        version=2,
        source_reference=replace(
            first.source_reference,
            source_revision="2",
            source_content_hash="b" * 64,
            observed_at=datetime(
                2026,
                8,
                9,
                10,
                tzinfo=timezone(timedelta(hours=8)),
            ),
        ),
    )

    assert await repository.append_manifest(first) is CorporateActionManifestAppendOutcome.APPENDED
    assert (
        await repository.append_manifest(
            replace(first, expected_children=tuple(reversed(first.expected_children)))
        )
        is CorporateActionManifestAppendOutcome.UNCHANGED
    )
    with pytest.raises(ConflictingCorporateActionManifestError, match="different content"):
        await repository.append_manifest(
            replace(
                first,
                source_reference=replace(first.source_reference, source_revision="conflict"),
            )
        )
    with pytest.raises(ConflictingCorporateActionManifestError, match="contiguously"):
        await repository.append_manifest(replace(second, version=3))
    with pytest.raises(ConflictingCorporateActionManifestError, match="source identity"):
        await repository.append_manifest(replace(second, source_reference=first.source_reference))
    with pytest.raises(ConflictingCorporateActionManifestError, match="already bound"):
        await repository.append_manifest(replace(first, corporate_action_event_id="CA-EVENT-ALIAS"))
    assert await async_db_session.scalar(text("SELECT 1")) == 1

    assert await repository.append_manifest(second) is CorporateActionManifestAppendOutcome.APPENDED
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    async with AsyncSession(bind=bind, expire_on_commit=False) as restarted_session:
        restarted_repository = SqlAlchemyCorporateActionEventGraphRepository(restarted_session)
        current = await restarted_repository.load_current_manifest(
            portfolio_id=first.portfolio_id,
            corporate_action_event_id=first.corporate_action_event_id,
        )
        assert current is not None
        assert current.lineage_payload() == second.lineage_payload()
        assert (
            await restarted_repository.append_manifest(second)
            is CorporateActionManifestAppendOutcome.UNCHANGED
        )
    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.current_manifest_version == 2
    assert event.state_version == 2
    assert event.readiness_status == "AWAITING_CHILDREN"
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestVersionRecord)
        )
        == 2
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestNodeRecord)
        )
        == 4
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestEdgeRecord)
        )
        == 2
    )

    manifest_record = await async_db_session.scalar(
        select(CorporateActionManifestVersionRecord).where(
            CorporateActionManifestVersionRecord.manifest_version == 2
        )
    )
    assert manifest_record is not None
    manifest_record_id = manifest_record.id
    await async_db_session.execute(
        text(
            "ALTER TABLE corporate_action_manifest_versions "
            "DISABLE TRIGGER trg_ca_manifest_version_immutable"
        )
    )

    await async_db_session.execute(
        text(
            "ALTER TABLE corporate_action_manifest_versions "
            "DISABLE TRIGGER trg_ca_manifest_predecessor"
        )
    )
    try:
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_versions "
                "SET expected_edge_count = expected_edge_count + 1 WHERE id = :manifest_id"
            ),
            {"manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
        with pytest.raises(ConflictingCorporateActionManifestError, match="edge count"):
            await repository.load_current_manifest(
                portfolio_id=first.portfolio_id,
                corporate_action_event_id=first.corporate_action_event_id,
            )
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_versions "
                "SET expected_edge_count = expected_edge_count - 1 WHERE id = :manifest_id"
            ),
            {"manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_versions "
                "SET previous_manifest_content_hash = :incorrect_hash "
                "WHERE id = :manifest_id"
            ),
            {"incorrect_hash": "f" * 64, "manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
        with pytest.raises(ConflictingCorporateActionManifestError, match="predecessor chain"):
            await repository.load_current_manifest(
                portfolio_id=first.portfolio_id,
                corporate_action_event_id=first.corporate_action_event_id,
            )
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_versions "
                "SET previous_manifest_content_hash = :expected_hash "
                "WHERE id = :manifest_id"
            ),
            {"expected_hash": first.content_hash, "manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
    finally:
        await async_db_session.execute(
            text(
                "ALTER TABLE corporate_action_manifest_versions "
                "ENABLE TRIGGER trg_ca_manifest_predecessor"
            )
        )
        await async_db_session.execute(
            text(
                "ALTER TABLE corporate_action_manifest_versions "
                "ENABLE TRIGGER trg_ca_manifest_version_immutable"
            )
        )

    await async_db_session.execute(
        text(
            "ALTER TABLE corporate_action_manifest_nodes "
            "DISABLE TRIGGER trg_ca_manifest_node_immutable"
        )
    )
    try:
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_nodes "
                "SET resolved_execution_ordinal = 7 "
                "WHERE manifest_id = :manifest_id AND transaction_id = 'CA-SOURCE-001'"
            ),
            {"manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
        with pytest.raises(ConflictingCorporateActionManifestError, match="execution order"):
            await repository.load_current_manifest(
                portfolio_id=first.portfolio_id,
                corporate_action_event_id=first.corporate_action_event_id,
            )
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_manifest_nodes "
                "SET resolved_execution_ordinal = 0 "
                "WHERE manifest_id = :manifest_id AND transaction_id = 'CA-SOURCE-001'"
            ),
            {"manifest_id": manifest_record_id},
        )
        async_db_session.expire_all()
    finally:
        await async_db_session.execute(
            text(
                "ALTER TABLE corporate_action_manifest_nodes "
                "ENABLE TRIGGER trg_ca_manifest_node_immutable"
            )
        )
    await async_db_session.commit()


async def test_legacy_manifest_reconstruction_preserves_durable_hash_authority(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await async_db_session.flush()
    record = await async_db_session.scalar(select(CorporateActionManifestVersionRecord))
    assert record is not None
    legacy_payload, legacy_hash = _legacy_manifest_authority(manifest)
    await async_db_session.execute(
        text(
            "ALTER TABLE corporate_action_manifest_versions "
            "DISABLE TRIGGER trg_ca_manifest_version_immutable"
        )
    )
    record.manifest_payload = legacy_payload
    record.manifest_content_hash = legacy_hash
    await async_db_session.flush()
    await async_db_session.execute(
        text(
            "ALTER TABLE corporate_action_manifest_versions "
            "ENABLE TRIGGER trg_ca_manifest_version_immutable"
        )
    )
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    async with AsyncSession(bind=bind, expire_on_commit=False) as restarted_session:
        restarted_repository = SqlAlchemyCorporateActionEventGraphRepository(restarted_session)
        reconstructed = await restarted_repository.load_current_manifest(
            portfolio_id=manifest.portfolio_id,
            corporate_action_event_id=manifest.corporate_action_event_id,
        )
        readiness = await restarted_repository.load_current_readiness(
            portfolio_id=manifest.portfolio_id,
            corporate_action_event_id=manifest.corporate_action_event_id,
        )

    assert reconstructed is not None
    assert reconstructed.lineage_payload() == manifest.lineage_payload()
    assert readiness.manifest_content_hash == legacy_hash


async def test_incomplete_empty_manifest_is_a_durable_awaiting_snapshot(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = replace(_manifest(), completion_declared=False, expected_children=())
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await async_db_session.commit()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.readiness_status == "AWAITING_COMPLETION"
    assert (
        await repository.load_current_manifest(
            portfolio_id=manifest.portfolio_id,
            corporate_action_event_id=manifest.corporate_action_event_id,
        )
        == manifest
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestNodeRecord)
        )
        == 0
    )


async def test_parent_alias_append_serializes_and_fails_with_typed_conflict(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    await async_db_session.commit()
    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    first = _manifest()
    alias = replace(first, corporate_action_event_id="CA-EVENT-ALIAS")

    contender_task: asyncio.Task[CorporateActionManifestAppendOutcome] | None = None
    async with session_factory() as owner, session_factory() as contender:
        try:
            owner_repository = SqlAlchemyCorporateActionEventGraphRepository(owner)
            contender_repository = SqlAlchemyCorporateActionEventGraphRepository(contender)
            assert (
                await owner_repository.append_manifest(first)
                is CorporateActionManifestAppendOutcome.APPENDED
            )
            contender_pid = await contender.scalar(text("SELECT pg_backend_pid()"))
            assert contender_pid is not None
            contender_task = asyncio.create_task(contender_repository.append_manifest(alias))
            await wait_for_postgres_advisory_lock_wait(
                contender_task,
                session_factory,
                backend_pid=contender_pid,
                timeout=2,
            )
            await owner.commit()
            with pytest.raises(ConflictingCorporateActionManifestError, match="already bound"):
                await asyncio.wait_for(contender_task, timeout=5)
            assert await contender.scalar(text("SELECT 1")) == 1
            await contender.commit()
        finally:
            await cancel_pending_tasks(contender_task)

    async with session_factory() as verification:
        assert (
            await verification.scalar(select(func.count()).select_from(CorporateActionEventRecord))
            == 1
        )


async def test_child_observations_before_manifest_restore_ready_state(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    for sequence, child in enumerate(manifest.expected_children, start=1):
        decision = await repository.observe_child(
            _observation(manifest, child, delivery_event_id=f"delivery-{sequence}")
        )
        assert decision.readiness_status == "AWAITING_MANIFEST"

    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    retry = await repository.observe_child(
        replace(
            _observation(
                manifest,
                manifest.expected_children[0],
                delivery_event_id="delivery-1",
            ),
            observed_at=manifest.source_reference.observed_at + timedelta(seconds=1),
        )
    )
    assert retry.observation_outcome is CorporateActionObservationAppendOutcome.UNCHANGED
    assert retry.readiness_status == "READY"
    assert retry.manifest_content_hash == manifest.content_hash
    assert retry.structural_plan_content_hash is not None
    with pytest.raises(ConflictingCorporateActionObservationError, match="different evidence"):
        await repository.observe_child(
            replace(
                _observation(
                    manifest,
                    manifest.expected_children[0],
                    delivery_event_id="delivery-1",
                ),
                correlation_id="conflicting-correlation",
            )
        )
    assert await async_db_session.scalar(text("SELECT 1")) == 1
    await async_db_session.commit()
    async_db_session.expire_all()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.readiness_status == "READY"
    assert event.last_observation_sequence == 2
    assert event.state_version == 3
    observed_fingerprints = tuple(
        await async_db_session.scalars(
            select(CorporateActionChildObservationRecord.transaction_payload_fingerprint).order_by(
                CorporateActionChildObservationRecord.observation_sequence
            )
        )
    )
    assert observed_fingerprints == tuple(
        f"sha256:{child.content_hash}" for child in manifest.expected_children
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionReadinessEvaluationRecord)
        )
        == 3
    )
    reconstructed = await repository.load_current_manifest(
        portfolio_id=manifest.portfolio_id,
        corporate_action_event_id=manifest.corporate_action_event_id,
    )
    assert reconstructed is not None
    assert reconstructed.lineage_payload() == manifest.lineage_payload()


async def test_first_manifest_rejects_rogue_pre_manifest_child(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    rogue = replace(
        manifest.expected_children[1],
        transaction_id="CA-ROGUE-001",
        instrument_id="ROGUE-SEC",
        target_instrument_id="ROGUE-SEC",
    )
    await _seed_transactions(async_db_session, (*manifest.expected_children, rogue))
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    for sequence, child in enumerate((*manifest.expected_children, rogue), start=1):
        await repository.observe_child(
            _observation(manifest, child, delivery_event_id=f"pre-manifest-{sequence}")
        )
    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await async_db_session.commit()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    evaluation = await async_db_session.scalar(
        select(CorporateActionReadinessEvaluationRecord).order_by(
            CorporateActionReadinessEvaluationRecord.state_version.desc()
        )
    )
    assert event is not None
    assert evaluation is not None
    assert event.readiness_status == "INVALID"
    assert evaluation.readiness_status == "INVALID"
    assert any(
        finding["reason"] == "CA_MANIFEST_UNEXPECTED_CHILD" for finding in evaluation.findings
    )


async def test_ready_release_materialization_freezes_payload_authority_and_replays_neutrally(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    await async_db_session.execute(
        text(
            """
            UPDATE transactions
            SET economic_event_id = :event_id,
                linked_transaction_group_id = :group_id,
                parent_event_reference = :parent_reference
            WHERE portfolio_id = :portfolio_id
            """
        ),
        {
            "event_id": manifest.corporate_action_event_id,
            "group_id": manifest.linked_transaction_group_id,
            "parent_reference": manifest.parent_event_reference,
            "portfolio_id": manifest.portfolio_id,
        },
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert await graph.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    decision = None
    for sequence, child in enumerate(manifest.expected_children, start=1):
        persisted = await async_db_session.scalar(
            select(TransactionRecord).where(
                TransactionRecord.transaction_id == child.transaction_id
            )
        )
        assert persisted is not None
        booked = replace(
            to_booked_transaction(TransactionEvent.model_validate(persisted)),
            epoch=1,
        )
        observation = replace(
            _observation(
                manifest,
                child,
                delivery_event_id=f"release-materialization-{sequence}",
            ),
            transaction_payload_fingerprint=(
                build_transaction_semantic_identity(booked).payload_fingerprint
            ),
        )
        decision = await graph.observe_child(observation)
    assert decision is not None
    assert decision.readiness_status == "READY"
    assert decision.manifest_content_hash is not None
    assert decision.structural_plan_content_hash is not None
    plan = CorporateActionExecutionPlan(
        corporate_action_event_id=manifest.corporate_action_event_id,
        portfolio_id=manifest.portfolio_id,
        linked_transaction_group_id=manifest.linked_transaction_group_id,
        parent_event_reference=manifest.parent_event_reference,
        manifest_content_hash=decision.manifest_content_hash,
        structural_plan_content_hash=decision.structural_plan_content_hash,
        readiness_state_version=decision.state_version,
        through_observation_sequence=decision.through_observation_sequence,
        ordered_transaction_ids=decision.ordered_transaction_ids,
    )
    releases = SqlAlchemyCorporateActionExecutionReleaseRepository(async_db_session)

    first = await releases.materialize(plan)
    replay = await releases.materialize(plan)
    await async_db_session.commit()

    assert first.outcome is CorporateActionReleaseMaterializationOutcome.APPENDED
    assert replay.outcome is CorporateActionReleaseMaterializationOutcome.UNCHANGED
    assert replay.release_id == first.release_id
    assert replay.release_authority_hash == first.release_authority_hash
    assert replay.member_count == len(manifest.expected_children)
    first_lease = CorporateActionExecutionLeaseRequest(
        owner="corporate-action-worker-01",
        token="a" * 64,
        duration_seconds=300,
    )
    claimed = await releases.claim_next(first_lease)
    assert claimed is not None
    assert claimed.fence_token == 1
    assert claimed.attempt_count == 1
    assert claimed.next_member.execution_ordinal == 0
    assert await releases.renew_lease(
        release_id=claimed.release_id,
        lease=first_lease,
        fence_token=claimed.fence_token,
    )
    loaded = await releases.load_owned_transaction(claimed)
    assert loaded.transaction_id == claimed.next_member.transaction_id
    assert loaded.tenant_id == manifest.tenant_id
    assert (
        build_transaction_semantic_identity(loaded).payload_fingerprint
        == claimed.next_member.transaction_payload_fingerprint
    )
    await async_db_session.commit()

    contender_lease = CorporateActionExecutionLeaseRequest(
        owner="corporate-action-worker-02",
        token="b" * 64,
        duration_seconds=300,
    )
    assert not await releases.renew_lease(
        release_id=claimed.release_id,
        lease=contender_lease,
        fence_token=claimed.fence_token,
    )
    assert await releases.claim_next(contender_lease) is None
    await async_db_session.execute(
        update(CorporateActionExecutionReleaseRecord)
        .where(CorporateActionExecutionReleaseRecord.id == first.release_id)
        .values(lease_expires_at=func.now() - text("INTERVAL '1 second'"))
    )
    await async_db_session.commit()
    reclaimed = await releases.claim_next(contender_lease)
    assert reclaimed is not None
    assert reclaimed.release_id == claimed.release_id
    assert reclaimed.fence_token == 2
    assert reclaimed.attempt_count == 2
    with pytest.raises(
        ConflictingCorporateActionExecutionReleaseError,
        match="lease ownership was lost",
    ):
        await releases.load_owned_transaction(claimed)
    assert (
        await releases.advance_member(
            release_id=claimed.release_id,
            expected_ordinal=claimed.next_member.execution_ordinal,
            lease_token=claimed.lease_token,
            fence_token=claimed.fence_token,
        )
        is CorporateActionReleaseProgressOutcome.LOST_OWNERSHIP
    )
    assert (
        await releases.advance_member(
            release_id=reclaimed.release_id,
            expected_ordinal=reclaimed.next_member.execution_ordinal,
            lease_token=reclaimed.lease_token,
            fence_token=reclaimed.fence_token,
        )
        is CorporateActionReleaseProgressOutcome.ADVANCED
    )
    await async_db_session.commit()
    next_member = await releases.load_owned_next(
        release_id=reclaimed.release_id,
        lease_token=reclaimed.lease_token,
        fence_token=reclaimed.fence_token,
    )
    assert next_member is not None
    assert next_member.next_member.execution_ordinal == 1
    assert (
        await releases.advance_member(
            release_id=next_member.release_id,
            expected_ordinal=next_member.next_member.execution_ordinal,
            lease_token=next_member.lease_token,
            fence_token=next_member.fence_token,
        )
        is CorporateActionReleaseProgressOutcome.COMPLETE
    )
    await async_db_session.commit()
    assert await releases.claim_next(contender_lease) is None
    with pytest.raises(StaleCorporateActionExecutionPlanError, match="current READY authority"):
        await releases.materialize(
            replace(plan, readiness_state_version=plan.readiness_state_version + 1)
        )
    await async_db_session.execute(
        update(TransactionRecord)
        .where(TransactionRecord.transaction_id == decision.ordered_transaction_ids[0])
        .values(quantity=2)
    )
    with pytest.raises(StaleCorporateActionExecutionPlanError, match="payload differs"):
        await releases.materialize(plan)
    release = await async_db_session.get(
        CorporateActionExecutionReleaseRecord,
        first.release_id,
    )
    assert release is not None
    members = tuple(
        await async_db_session.scalars(
            select(CorporateActionExecutionMemberRecord)
            .where(CorporateActionExecutionMemberRecord.release_id == first.release_id)
            .order_by(CorporateActionExecutionMemberRecord.execution_ordinal)
        )
    )
    assert tuple(member.transaction_id for member in members) == decision.ordered_transaction_ids
    assert all(member.transaction_payload_fingerprint.startswith("sha256:") for member in members)


async def test_corrected_generation_waits_for_owned_prior_generation(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    """One economic event must never execute two manifest generations concurrently."""

    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    first_manifest = _manifest()
    await _seed_transactions(async_db_session, first_manifest.expected_children)
    await async_db_session.execute(
        update(TransactionRecord)
        .where(TransactionRecord.portfolio_id == first_manifest.portfolio_id)
        .values(
            economic_event_id=first_manifest.corporate_action_event_id,
            linked_transaction_group_id=first_manifest.linked_transaction_group_id,
            parent_event_reference=first_manifest.parent_event_reference,
        )
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    releases = SqlAlchemyCorporateActionExecutionReleaseRepository(async_db_session)
    assert (
        await graph.append_manifest(first_manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    for sequence, child in enumerate(first_manifest.expected_children, start=1):
        await graph.observe_child(
            await _persisted_observation(
                async_db_session,
                first_manifest,
                child,
                delivery_event_id=f"generation-one-{sequence}",
            )
        )
    first_decision = await graph.load_current_readiness(
        portfolio_id=first_manifest.portfolio_id,
        corporate_action_event_id=first_manifest.corporate_action_event_id,
    )
    first_release = await releases.materialize(_execution_plan(first_manifest, first_decision))
    first_lease = CorporateActionExecutionLeaseRequest(
        owner="generation-one-worker",
        token="c" * 64,
        duration_seconds=300,
    )
    first_claim = await releases.claim_next(first_lease)
    assert first_claim is not None
    await async_db_session.commit()

    second_manifest = replace(
        first_manifest,
        version=2,
        source_reference=replace(
            first_manifest.source_reference,
            source_revision="2",
            source_content_hash="d" * 64,
        ),
    )
    assert (
        await graph.append_manifest(second_manifest)
        is CorporateActionManifestAppendOutcome.APPENDED
    )
    second_decision = await graph.load_current_readiness(
        portfolio_id=second_manifest.portfolio_id,
        corporate_action_event_id=second_manifest.corporate_action_event_id,
    )
    assert second_decision.readiness_status == "READY"
    second_release = await releases.materialize(_execution_plan(second_manifest, second_decision))
    await async_db_session.commit()
    assert second_release.release_id != first_release.release_id

    contender = CorporateActionExecutionLeaseRequest(
        owner="generation-two-worker",
        token="e" * 64,
        duration_seconds=300,
    )
    assert await releases.claim_next(contender) is None

    await async_db_session.execute(
        update(CorporateActionExecutionReleaseRecord)
        .where(CorporateActionExecutionReleaseRecord.id == first_release.release_id)
        .values(lease_expires_at=func.now() - text("INTERVAL '1 second'"))
    )
    await async_db_session.commit()
    recovered = await releases.claim_next(contender)
    assert recovered is not None
    assert recovered.release_id == first_release.release_id
    while True:
        progress = await releases.advance_member(
            release_id=recovered.release_id,
            expected_ordinal=recovered.next_member.execution_ordinal,
            lease_token=recovered.lease_token,
            fence_token=recovered.fence_token,
        )
        await async_db_session.commit()
        if progress is CorporateActionReleaseProgressOutcome.COMPLETE:
            break
        next_member = await releases.load_owned_next(
            release_id=recovered.release_id,
            lease_token=recovered.lease_token,
            fence_token=recovered.fence_token,
        )
        assert next_member is not None
        recovered = next_member

    second_claim = await releases.claim_next(contender)
    assert second_claim is not None
    assert second_claim.release_id == second_release.release_id


async def test_real_postgres_worker_drains_release_without_lease_expiry_wait(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    """The deployable use case must process every member under its current lease."""

    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    await async_db_session.execute(
        update(TransactionRecord)
        .where(TransactionRecord.portfolio_id == manifest.portfolio_id)
        .values(
            economic_event_id=manifest.corporate_action_event_id,
            linked_transaction_group_id=manifest.linked_transaction_group_id,
            parent_event_reference=manifest.parent_event_reference,
        )
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert await graph.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    for sequence, child in enumerate(manifest.expected_children, start=1):
        await graph.observe_child(
            await _persisted_observation(
                async_db_session,
                manifest,
                child,
                delivery_event_id=f"worker-drain-{sequence}",
            )
        )
    decision = await graph.load_current_readiness(
        portfolio_id=manifest.portfolio_id,
        corporate_action_event_id=manifest.corporate_action_event_id,
    )
    release = await SqlAlchemyCorporateActionExecutionReleaseRepository(
        async_db_session
    ).materialize(_execution_plan(manifest, decision))
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    process = AsyncMock()
    process.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="corporate-action-member",
    )
    worker = ProcessNextCorporateActionReleaseUseCase(  # type: ignore[arg-type]
        unit_of_work_factory=lambda: SqlAlchemyCorporateActionEventGraphUnitOfWork(session_factory),
        process_transaction=process,
        lease_owner="real-postgres-worker",
        lease_duration_seconds=300,
        token_factory=lambda: "f" * 64,
    )

    result = await worker.execute()

    assert result.status is CorporateActionReleaseWorkerStatus.COMPLETE
    assert result.processed_member_count == len(manifest.expected_children)
    assert process.execute.await_count == len(manifest.expected_children)
    assert [call.args[0].metadata.event_id for call in process.execute.await_args_list] == [
        f"corporate-action-release:{release.release_authority_hash}:{ordinal}"
        for ordinal in range(len(manifest.expected_children))
    ]
    async_db_session.expire_all()
    persisted_release = await async_db_session.get(
        CorporateActionExecutionReleaseRecord,
        release.release_id,
    )
    assert persisted_release is not None
    assert persisted_release.status == "COMPLETE"
    assert persisted_release.attempt_count == 1
    assert persisted_release.next_execution_ordinal == len(manifest.expected_children)


async def test_release_progress_fence_uses_statement_time_after_transaction_ages(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    """Reject progress after expiry even when the worker transaction began beforehand."""

    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    await async_db_session.execute(
        update(TransactionRecord)
        .where(TransactionRecord.portfolio_id == manifest.portfolio_id)
        .values(
            economic_event_id=manifest.corporate_action_event_id,
            linked_transaction_group_id=manifest.linked_transaction_group_id,
            parent_event_reference=manifest.parent_event_reference,
        )
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert await graph.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    for sequence, child in enumerate(manifest.expected_children, start=1):
        await graph.observe_child(
            await _persisted_observation(
                async_db_session,
                manifest,
                child,
                delivery_event_id=f"aged-transaction-{sequence}",
            )
        )
    decision = await graph.load_current_readiness(
        portfolio_id=manifest.portfolio_id,
        corporate_action_event_id=manifest.corporate_action_event_id,
    )
    materialized = await SqlAlchemyCorporateActionExecutionReleaseRepository(
        async_db_session
    ).materialize(_execution_plan(manifest, decision))
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    async with session_factory() as worker_session:
        releases = SqlAlchemyCorporateActionExecutionReleaseRepository(worker_session)
        claim = await releases.claim_next(
            CorporateActionExecutionLeaseRequest(
                owner="aged-transaction-worker",
                token="e" * 64,
                duration_seconds=300,
            )
        )
        assert claim is not None
        assert claim.release_id == materialized.release_id
        await worker_session.commit()

        # Hold a transaction-start timestamp from before the control session shortens the lease.
        await worker_session.execute(select(func.now()))
        async with session_factory() as control_session:
            await control_session.execute(
                update(CorporateActionExecutionReleaseRecord)
                .where(CorporateActionExecutionReleaseRecord.id == claim.release_id)
                .values(lease_expires_at=func.clock_timestamp() + text("INTERVAL '1 second'"))
            )
            await control_session.commit()
        await worker_session.execute(select(func.pg_sleep(1.25)))

        outcome = await releases.advance_member(
            release_id=claim.release_id,
            expected_ordinal=claim.next_member.execution_ordinal,
            lease_token=claim.lease_token,
            fence_token=claim.fence_token,
        )
        await worker_session.commit()

        assert outcome is CorporateActionReleaseProgressOutcome.LOST_OWNERSHIP


async def test_ready_observation_rolls_back_when_release_authority_cannot_materialize(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    """Never commit READY graph state without its immutable execution release."""

    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    await async_db_session.execute(
        update(TransactionRecord)
        .where(TransactionRecord.portfolio_id == manifest.portfolio_id)
        .values(
            economic_event_id=manifest.corporate_action_event_id,
            linked_transaction_group_id=manifest.linked_transaction_group_id,
            parent_event_reference=manifest.parent_event_reference,
        )
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert await graph.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    first_child, final_child = manifest.expected_children
    await graph.observe_child(
        await _persisted_observation(
            async_db_session,
            manifest,
            first_child,
            delivery_event_id="atomic-ready-first",
        )
    )
    await async_db_session.commit()

    persisted = await async_db_session.scalar(
        select(TransactionRecord).where(
            TransactionRecord.transaction_id == final_child.transaction_id
        )
    )
    assert persisted is not None
    source_transaction = replace(
        to_booked_transaction(TransactionEvent.model_validate(persisted)),
        epoch=1,
    )
    drifted_arrival = replace(
        source_transaction,
        quantity=source_transaction.quantity + 1,
        child_role=final_child.child_role,
        child_sequence_hint=final_child.child_sequence_hint,
        dependency_reference_ids=final_child.dependency_transaction_ids,
        source_instrument_id=final_child.source_instrument_id,
        target_instrument_id=final_child.target_instrument_id,
    )
    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    route_arrival = RouteCorporateActionChildArrivalUseCase(
        lambda: SqlAlchemyCorporateActionEventGraphUnitOfWork(session_factory)
    )

    with pytest.raises(StaleCorporateActionExecutionPlanError, match="payload differs"):
        await route_arrival.execute(
            ProcessTransactionCommand(
                transaction=drifted_arrival,
                metadata=TransactionEventMetadata(event_id="atomic-ready-final"),
            )
        )

    async_db_session.expire_all()
    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.readiness_status == "AWAITING_CHILDREN"
    assert event.last_observation_sequence == 1
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionChildObservationRecord)
        )
        == 1
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionExecutionReleaseRecord)
        )
        == 0
    )


async def test_thousand_member_release_drains_with_bounded_progress_validation(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    """Prove the contractual maximum cohort without repeated full-release validation."""

    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _large_manifest(node_count=1_000, suffix="RELEASE-CAPACITY")
    await _seed_transactions(async_db_session, manifest.expected_children)
    await async_db_session.execute(
        update(TransactionRecord)
        .where(
            TransactionRecord.transaction_id.in_(
                child.transaction_id for child in manifest.expected_children
            )
        )
        .values(
            economic_event_id=manifest.corporate_action_event_id,
            linked_transaction_group_id=manifest.linked_transaction_group_id,
            parent_event_reference=manifest.parent_event_reference,
        )
    )
    graph = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert await graph.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    event = await async_db_session.scalar(
        select(CorporateActionEventRecord).where(
            CorporateActionEventRecord.corporate_action_event_id
            == manifest.corporate_action_event_id
        )
    )
    assert event is not None
    await _seed_observations(async_db_session, event.id, manifest)
    readiness, manifest_record = await graph._evaluate_current_event(event)
    assert readiness.status == "READY"
    assert manifest_record is not None
    state_version = event.state_version + 1
    through_observation_sequence = len(manifest.expected_children)
    await async_db_session.execute(
        update(CorporateActionEventRecord)
        .where(CorporateActionEventRecord.id == event.id)
        .values(
            state_version=state_version,
            last_observation_sequence=through_observation_sequence,
            readiness_status="READY",
        )
    )
    await graph._insert_readiness_evaluation(
        event_id=event.id,
        state_version=state_version,
        manifest_id=manifest_record.id,
        through_observation_sequence=through_observation_sequence,
        readiness=readiness,
        correlation_id="release-capacity-proof",
    )
    await async_db_session.flush()
    decision = await graph.load_current_readiness(
        portfolio_id=manifest.portfolio_id,
        corporate_action_event_id=manifest.corporate_action_event_id,
    )
    release = await SqlAlchemyCorporateActionExecutionReleaseRepository(
        async_db_session
    ).materialize(_execution_plan(manifest, decision))
    await async_db_session.commit()

    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    process = AsyncMock()
    process.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="corporate-action-capacity-member",
    )
    worker = ProcessNextCorporateActionReleaseUseCase(  # type: ignore[arg-type]
        unit_of_work_factory=lambda: SqlAlchemyCorporateActionEventGraphUnitOfWork(session_factory),
        process_transaction=process,
        lease_owner="capacity-worker",
        lease_duration_seconds=300,
        token_factory=lambda: "1" * 64,
    )

    statements: list[str] = []

    def record_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", record_statement)
    started = perf_counter()
    try:
        result = await asyncio.wait_for(worker.execute(), timeout=600)
    finally:
        elapsed_seconds = perf_counter() - started
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", record_statement)

    assert result.status is CorporateActionReleaseWorkerStatus.COMPLETE
    assert result.release_id == release.release_id
    assert result.processed_member_count == 1_000
    assert process.execute.await_count == 1_000
    assert len(statements) <= 7 * result.processed_member_count + 10
    readiness_authority_statement_count = sum(
        "corporate_action_readiness_evaluations" in statement for statement in statements
    )
    # Claiming performs one stale-readiness supersession and one candidate lookup.
    # Neither statement may be repeated for each release member.
    assert readiness_authority_statement_count == 2
    persisted_release = await async_db_session.get(
        CorporateActionExecutionReleaseRecord,
        release.release_id,
    )
    assert persisted_release is not None
    assert persisted_release.status == "COMPLETE"
    assert persisted_release.attempt_count == 1
    print(f"1,000-member release drain: {elapsed_seconds:.3f}s")


async def test_child_correction_epochs_are_monotonic_and_retries_are_neutral(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    for sequence, child in enumerate(manifest.expected_children, start=1):
        await repository.observe_child(
            _observation(manifest, child, delivery_event_id=f"initial-{sequence}")
        )

    with pytest.raises(ConflictingCorporateActionObservationError, match="increase monotonically"):
        await repository.observe_child(
            replace(
                _observation(
                    manifest,
                    manifest.expected_children[0],
                    delivery_event_id="same-epoch-different-payload",
                ),
                transaction_payload_fingerprint=f"sha256:{'f' * 64}",
            )
        )

    corrected_child = replace(manifest.expected_children[0], child_sequence_hint=99)
    corrected = await repository.observe_child(
        _observation(
            manifest,
            corrected_child,
            delivery_event_id="correction-2",
            transaction_epoch=2,
        )
    )
    assert corrected.observation_outcome is CorporateActionObservationAppendOutcome.APPENDED
    assert corrected.readiness_status == "INVALID"

    semantic_retry = await repository.observe_child(
        _observation(
            manifest,
            manifest.expected_children[0],
            delivery_event_id="semantic-retry",
        )
    )
    assert semantic_retry.observation_outcome is CorporateActionObservationAppendOutcome.UNCHANGED
    assert semantic_retry.readiness_status == "INVALID"

    with pytest.raises(ConflictingCorporateActionObservationError, match="increase monotonically"):
        await repository.observe_child(
            _observation(
                manifest,
                replace(manifest.expected_children[0], child_sequence_hint=7),
                delivery_event_id="stale-different-content",
            )
        )
    assert await async_db_session.scalar(text("SELECT 1")) == 1
    await async_db_session.commit()
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionChildObservationRecord)
        )
        == 3
    )


async def test_corrected_manifest_reuses_expected_epochs_and_ignores_removed_old_child(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    base = _manifest()
    source = next(
        child for child in base.expected_children if child.child_role == "SOURCE_POSITION_REDUCE"
    )
    extra_target = replace(
        next(
            child for child in base.expected_children if child.child_role == "TARGET_POSITION_ADD"
        ),
        transaction_id="CA-TARGET-002",
        instrument_id="TARGET-SEC-002",
        target_instrument_id="TARGET-SEC-002",
    )
    first = replace(base, expected_children=base.expected_children + (extra_target,))
    second = replace(
        base,
        version=2,
        source_reference=replace(
            base.source_reference,
            source_revision="2",
            source_content_hash="b" * 64,
        ),
    )
    await _seed_transactions(async_db_session, first.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    for sequence, child in enumerate(first.expected_children, start=1):
        await repository.observe_child(
            _observation(first, child, delivery_event_id=f"correction-delivery-{sequence}")
        )
    assert await repository.append_manifest(first) is CorporateActionManifestAppendOutcome.APPENDED
    assert await repository.append_manifest(second) is CorporateActionManifestAppendOutcome.APPENDED
    await async_db_session.commit()
    async_db_session.expire_all()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.current_manifest_version == 2
    assert event.readiness_status == "READY"
    assert event.last_observation_sequence == 3
    latest_evaluation = await async_db_session.scalar(
        select(CorporateActionReadinessEvaluationRecord).order_by(
            CorporateActionReadinessEvaluationRecord.state_version.desc()
        )
    )
    assert latest_evaluation is not None
    assert latest_evaluation.ordered_transaction_ids == [
        source.transaction_id,
        "CA-TARGET-001",
    ]


async def test_corrected_manifest_requires_newly_declared_child_after_opening_boundary(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    first = _manifest()
    extra_target = replace(
        next(
            child for child in first.expected_children if child.child_role == "TARGET_POSITION_ADD"
        ),
        transaction_id="CA-TARGET-002",
        instrument_id="TARGET-SEC-002",
        target_instrument_id="TARGET-SEC-002",
    )
    second = replace(
        first,
        version=2,
        expected_children=first.expected_children + (extra_target,),
        source_reference=replace(
            first.source_reference,
            source_revision="2",
            source_content_hash="b" * 64,
        ),
    )
    await _seed_transactions(async_db_session, second.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    for sequence, child in enumerate(second.expected_children, start=1):
        await repository.observe_child(
            _observation(first, child, delivery_event_id=f"pre-correction-{sequence}")
        )
    assert await repository.append_manifest(first) is CorporateActionManifestAppendOutcome.APPENDED
    assert await repository.append_manifest(second) is CorporateActionManifestAppendOutcome.APPENDED

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.current_manifest_version == 2
    assert event.readiness_status == "AWAITING_CHILDREN"

    decision = await repository.observe_child(
        _observation(
            second,
            extra_target,
            delivery_event_id="post-correction-extra-target",
        )
    )
    assert decision.observation_outcome is CorporateActionObservationAppendOutcome.APPENDED
    assert decision.readiness_status == "READY"

    third = replace(
        first,
        version=3,
        source_reference=replace(
            first.source_reference,
            source_revision="3",
            source_content_hash="c" * 64,
        ),
    )
    assert await repository.append_manifest(third) is CorporateActionManifestAppendOutcome.APPENDED
    removed_child_redelivery = await repository.observe_child(
        _observation(
            third,
            extra_target,
            delivery_event_id="post-removal-extra-target",
        )
    )
    assert (
        removed_child_redelivery.observation_outcome
        is CorporateActionObservationAppendOutcome.APPENDED
    )
    assert removed_child_redelivery.readiness_status == "INVALID"
    await async_db_session.commit()


async def test_consecutive_correction_does_not_reauthorize_pre_declaration_observation(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    first = _manifest()
    extra_target = replace(
        next(
            child for child in first.expected_children if child.child_role == "TARGET_POSITION_ADD"
        ),
        transaction_id="CA-TARGET-002",
        instrument_id="TARGET-SEC-002",
        target_instrument_id="TARGET-SEC-002",
    )
    second = replace(
        first,
        version=2,
        expected_children=first.expected_children + (extra_target,),
        source_reference=replace(
            first.source_reference,
            source_revision="2",
            source_content_hash="b" * 64,
        ),
    )
    third = replace(
        second,
        version=3,
        source_reference=replace(
            first.source_reference,
            source_revision="3",
            source_content_hash="c" * 64,
        ),
    )
    await _seed_transactions(async_db_session, second.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    for sequence, child in enumerate(second.expected_children, start=1):
        await repository.observe_child(
            _observation(first, child, delivery_event_id=f"pre-declaration-{sequence}")
        )
    assert await repository.append_manifest(first) is CorporateActionManifestAppendOutcome.APPENDED
    assert await repository.append_manifest(second) is CorporateActionManifestAppendOutcome.APPENDED
    assert await repository.append_manifest(third) is CorporateActionManifestAppendOutcome.APPENDED

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.current_manifest_version == 3
    assert event.readiness_status == "AWAITING_CHILDREN"

    decision = await repository.observe_child(
        _observation(third, extra_target, delivery_event_id="post-v3-extra-target")
    )
    assert decision.observation_outcome is CorporateActionObservationAppendOutcome.APPENDED
    assert decision.readiness_status == "READY"
    await async_db_session.commit()


async def test_concurrent_last_child_has_one_state_winner_and_neutral_retry(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    seed_repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert (
        await seed_repository.append_manifest(manifest)
        is CorporateActionManifestAppendOutcome.APPENDED
    )
    source = next(
        child
        for child in manifest.expected_children
        if child.child_role == "SOURCE_POSITION_REDUCE"
    )
    target = next(
        child for child in manifest.expected_children if child.child_role == "TARGET_POSITION_ADD"
    )
    await seed_repository.observe_child(
        _observation(manifest, source, delivery_event_id="source-delivery")
    )
    await async_db_session.commit()
    bind = async_db_session.bind
    assert bind is not None
    session_factory = async_sessionmaker(bind, expire_on_commit=False)

    contender_task: asyncio.Task[Any] | None = None
    async with session_factory() as owner, session_factory() as contender:
        try:
            owner_repository = SqlAlchemyCorporateActionEventGraphRepository(owner)
            contender_repository = SqlAlchemyCorporateActionEventGraphRepository(contender)
            owner_decision = await owner_repository.observe_child(
                _observation(manifest, target, delivery_event_id="target-owner")
            )
            assert owner_decision.readiness_status == "READY"
            contender_pid = await contender.scalar(text("SELECT pg_backend_pid()"))
            assert contender_pid is not None
            contender_task = asyncio.create_task(
                contender_repository.observe_child(
                    _observation(manifest, target, delivery_event_id="target-contender")
                )
            )
            await wait_for_postgres_advisory_lock_wait(
                contender_task,
                session_factory,
                backend_pid=contender_pid,
                timeout=2,
            )
            await owner.commit()
            contender_decision = await asyncio.wait_for(contender_task, timeout=5)
            assert (
                contender_decision.observation_outcome
                is CorporateActionObservationAppendOutcome.UNCHANGED
            )
            assert contender_decision.readiness_status == "READY"
            await contender.commit()
        finally:
            await cancel_pending_tasks(contender_task)

    async with session_factory() as verification:
        event = await verification.scalar(select(CorporateActionEventRecord))
        assert event is not None
        assert event.state_version == 3
        assert event.last_observation_sequence == 2
        assert (
            await verification.scalar(
                select(func.count()).select_from(CorporateActionReadinessEvaluationRecord)
            )
            == 3
        )


async def test_manifest_append_statement_count_is_constant_at_one_thousand_nodes(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    small_manifest = _large_manifest(node_count=10, suffix="SMALL")
    large_manifest = _large_manifest(node_count=1_000, suffix="LARGE")
    bind = async_db_session.bind
    assert bind is not None
    statements: list[str] = []

    def record_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", record_statement)
    try:
        before_small = len(statements)
        assert (
            await repository.append_manifest(small_manifest)
            is CorporateActionManifestAppendOutcome.APPENDED
        )
        small_statement_count = len(statements) - before_small
        before_large = len(statements)
        assert (
            await repository.append_manifest(large_manifest)
            is CorporateActionManifestAppendOutcome.APPENDED
        )
        large_statement_count = len(statements) - before_large
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", record_statement)

    assert small_statement_count == large_statement_count
    assert large_statement_count <= 15

    await _seed_transactions(
        async_db_session,
        (*small_manifest.expected_children, *large_manifest.expected_children),
    )
    events = {
        event.corporate_action_event_id: event
        for event in (await async_db_session.scalars(select(CorporateActionEventRecord))).all()
    }
    await _seed_observations(
        async_db_session,
        events[small_manifest.corporate_action_event_id].id,
        small_manifest,
    )
    await _seed_observations(
        async_db_session,
        events[large_manifest.corporate_action_event_id].id,
        large_manifest,
    )

    statements.clear()
    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", record_statement)
    try:
        before_small = len(statements)
        small_readiness, _ = await repository._evaluate_current_event(
            events[small_manifest.corporate_action_event_id]
        )
        small_read_statement_count = len(statements) - before_small
        before_large = len(statements)
        large_readiness, _ = await repository._evaluate_current_event(
            events[large_manifest.corporate_action_event_id]
        )
        large_read_statement_count = len(statements) - before_large
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", record_statement)

    assert small_readiness.status == "READY"
    assert large_readiness.status == "READY"
    assert small_read_statement_count == large_read_statement_count
    assert large_read_statement_count <= 6


async def test_observation_book_scope_fails_closed_in_repository_and_database(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await _seed_other_portfolio_and_transaction(async_db_session)
    foreign_child = replace(
        manifest.expected_children[0],
        transaction_id="CA-FOREIGN-001",
        instrument_id="FOREIGN-SEC",
        target_instrument_id="FOREIGN-SEC",
    )
    observation = _observation(
        manifest,
        foreign_child,
        delivery_event_id="foreign-delivery",
    )

    with pytest.raises(CorporateActionBookScopeError, match="outside event portfolio"):
        await repository.observe_child(observation)
    assert await async_db_session.scalar(text("SELECT 1")) == 1

    event_id = await async_db_session.scalar(select(CorporateActionEventRecord.id))
    assert event_id is not None
    with pytest.raises(IntegrityError, match="outside event portfolio"):
        async with async_db_session.begin_nested():
            await async_db_session.execute(
                insert(CorporateActionChildObservationRecord).values(
                    event_id=event_id,
                    observation_sequence=1,
                    transaction_id=foreign_child.transaction_id,
                    transaction_epoch=1,
                    delivery_event_id="foreign-direct",
                    correlation_id="correlation-001",
                    observed_content_hash=foreign_child.content_hash,
                    observed_payload=foreign_child.lineage_payload(),
                    observed_at=manifest.source_reference.observed_at,
                )
            )
    assert await async_db_session.scalar(text("SELECT 1")) == 1


async def test_cas_conflict_savepoint_prevents_stranded_graph_commit(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    first = _manifest()
    assert await repository.append_manifest(first) is CorporateActionManifestAppendOutcome.APPENDED
    await async_db_session.commit()
    original_advance = repository._advance_event

    async def force_cas_loss(event, *, manifest_version, readiness_status) -> None:
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_events "
                "SET state_version = state_version + 1 WHERE id = :event_id"
            ),
            {"event_id": event.id},
        )
        await original_advance(
            event,
            manifest_version=manifest_version,
            readiness_status=readiness_status,
        )

    repository._advance_event = force_cas_loss  # type: ignore[method-assign]
    second = replace(
        first,
        version=2,
        source_reference=replace(first.source_reference, source_revision="2"),
    )
    with pytest.raises(ConflictingCorporateActionManifestError, match="state changed"):
        await repository.append_manifest(second)
    await async_db_session.commit()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.current_manifest_version == 1
    assert event.state_version == 1
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestVersionRecord)
        )
        == 1
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestNodeRecord)
        )
        == 2
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionManifestEdgeRecord)
        )
        == 1
    )


async def test_observation_cas_conflict_rolls_back_observation_and_evaluation(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_migration(db_engine)
    await _seed_portfolio(async_db_session)
    manifest = _manifest()
    await _seed_transactions(async_db_session, manifest.expected_children)
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)
    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await async_db_session.commit()
    original_advance = repository._advance_observation_state

    async def force_cas_loss(event, *, observation_sequence, readiness_status) -> None:
        await async_db_session.execute(
            text(
                "UPDATE corporate_action_events "
                "SET state_version = state_version + 1 WHERE id = :event_id"
            ),
            {"event_id": event.id},
        )
        await original_advance(
            event,
            observation_sequence=observation_sequence,
            readiness_status=readiness_status,
        )

    repository._advance_observation_state = force_cas_loss  # type: ignore[method-assign]
    with pytest.raises(ConflictingCorporateActionObservationError, match="state changed"):
        await repository.observe_child(
            _observation(manifest, manifest.expected_children[0], delivery_event_id="cas-loss")
        )
    await async_db_session.commit()

    event = await async_db_session.scalar(select(CorporateActionEventRecord))
    assert event is not None
    assert event.state_version == 1
    assert event.last_observation_sequence == 0
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionChildObservationRecord)
        )
        == 0
    )
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(CorporateActionReadinessEvaluationRecord)
        )
        == 1
    )


def _manifest() -> corporate_action.CorporateActionParentManifest:
    source = corporate_action.CorporateActionEventChild(
        transaction_id="CA-SOURCE-001",
        transaction_type="DEMERGER_OUT",
        child_role="SOURCE_POSITION_REDUCE",
        instrument_id="SOURCE-SEC",
        source_instrument_id="SOURCE-SEC",
    )
    target = corporate_action.CorporateActionEventChild(
        transaction_id="CA-TARGET-001",
        transaction_type="DEMERGER_IN",
        child_role="TARGET_POSITION_ADD",
        dependency_transaction_ids=(source.transaction_id,),
        instrument_id="TARGET-SEC",
        source_instrument_id="SOURCE-SEC",
        target_instrument_id="TARGET-SEC",
    )
    return corporate_action.CorporateActionParentManifest(
        corporate_action_event_id="CA-EVENT-001",
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="CA-PORT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        corporate_action_type="DEMERGER",
        version=1,
        completion_declared=True,
        expected_children=(target, source),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id="SOURCE-CA-001",
            source_revision="1",
            source_content_hash="a" * 64,
            observed_at=datetime(
                2026,
                8,
                9,
                9,
                tzinfo=timezone(timedelta(hours=8)),
            ),
        ),
    )


def _legacy_manifest_authority(
    manifest: corporate_action.CorporateActionParentManifest,
) -> tuple[dict[str, object], str]:
    payload = cast(dict[str, object], manifest.lineage_payload())
    payload.pop("tenant_id")
    payload.pop("legal_book_id")
    content_hash = canonical_content_hash(payload)
    source = dict(cast(dict[str, object], payload["source_reference"]))
    source["observed_at"] = manifest.source_reference.observed_at.astimezone(
        timezone.utc
    ).isoformat()
    payload["source_reference"] = source
    return payload, content_hash


def _observation(
    manifest: corporate_action.CorporateActionParentManifest,
    child: corporate_action.CorporateActionEventChild,
    *,
    delivery_event_id: str,
    transaction_epoch: int = 1,
) -> CorporateActionChildObservation:
    return CorporateActionChildObservation(
        corporate_action_event_id=manifest.corporate_action_event_id,
        portfolio_id=manifest.portfolio_id,
        linked_transaction_group_id=manifest.linked_transaction_group_id,
        parent_event_reference=manifest.parent_event_reference,
        child=child,
        transaction_epoch=transaction_epoch,
        transaction_payload_fingerprint=f"sha256:{child.content_hash}",
        delivery_event_id=delivery_event_id,
        correlation_id="correlation-001",
        observed_at=manifest.source_reference.observed_at,
    )


async def _persisted_observation(
    session: AsyncSession,
    manifest: corporate_action.CorporateActionParentManifest,
    child: corporate_action.CorporateActionEventChild,
    *,
    delivery_event_id: str,
) -> CorporateActionChildObservation:
    persisted = await session.scalar(
        select(TransactionRecord).where(TransactionRecord.transaction_id == child.transaction_id)
    )
    assert persisted is not None
    booked = replace(to_booked_transaction(TransactionEvent.model_validate(persisted)), epoch=1)
    return replace(
        _observation(manifest, child, delivery_event_id=delivery_event_id),
        transaction_payload_fingerprint=(
            build_transaction_semantic_identity(booked).payload_fingerprint
        ),
    )


def _execution_plan(
    manifest: corporate_action.CorporateActionParentManifest,
    decision: CorporateActionReadinessDecision,
) -> CorporateActionExecutionPlan:
    assert decision.readiness_status == "READY"
    assert decision.manifest_content_hash is not None
    assert decision.structural_plan_content_hash is not None
    return CorporateActionExecutionPlan(
        corporate_action_event_id=manifest.corporate_action_event_id,
        portfolio_id=manifest.portfolio_id,
        linked_transaction_group_id=manifest.linked_transaction_group_id,
        parent_event_reference=manifest.parent_event_reference,
        manifest_content_hash=decision.manifest_content_hash,
        structural_plan_content_hash=decision.structural_plan_content_hash,
        readiness_state_version=decision.state_version,
        through_observation_sequence=decision.through_observation_sequence,
        ordered_transaction_ids=decision.ordered_transaction_ids,
    )


def _large_manifest(
    *,
    node_count: int,
    suffix: str,
) -> corporate_action.CorporateActionParentManifest:
    if node_count < 2:
        raise ValueError("node_count must include one source and at least one target")
    source = corporate_action.CorporateActionEventChild(
        transaction_id=f"CA-SOURCE-{suffix}",
        transaction_type="DEMERGER_OUT",
        child_role="SOURCE_POSITION_REDUCE",
        instrument_id=f"SOURCE-{suffix}",
        source_instrument_id=f"SOURCE-{suffix}",
    )
    targets = tuple(
        corporate_action.CorporateActionEventChild(
            transaction_id=f"CA-TARGET-{suffix}-{index:04d}",
            transaction_type="DEMERGER_IN",
            child_role="TARGET_POSITION_ADD",
            dependency_transaction_ids=(source.transaction_id,),
            instrument_id=f"TARGET-{suffix}-{index:04d}",
            source_instrument_id=source.instrument_id,
            target_instrument_id=f"TARGET-{suffix}-{index:04d}",
        )
        for index in range(1, node_count)
    )
    return corporate_action.CorporateActionParentManifest(
        corporate_action_event_id=f"CA-EVENT-{suffix}",
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="CA-PORT-001",
        linked_transaction_group_id=f"CA-GROUP-{suffix}",
        parent_event_reference=f"CA-PARENT-{suffix}",
        corporate_action_type="DEMERGER",
        version=1,
        completion_declared=True,
        expected_children=(source, *targets),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id=f"SOURCE-CA-{suffix}",
            source_revision="1",
            source_content_hash="c" * 64,
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        ),
    )


async def _seed_portfolio(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id,
                tenant_id,
                legal_book_id,
                base_currency,
                open_date,
                risk_exposure,
                investment_time_horizon,
                portfolio_type,
                booking_center_code,
                client_id,
                is_leverage_allowed,
                status
            ) VALUES (
                'CA-PORT-001',
                'TENANT-SG',
                'PB-SG-01',
                'USD',
                DATE '2026-01-01',
                'BALANCED',
                'LONG_TERM',
                'DISCRETIONARY',
                'SG',
                'CA-CLIENT-001',
                false,
                'ACTIVE'
            )
            """
        )
    )


async def _seed_transactions(
    session: AsyncSession,
    children: tuple[corporate_action.CorporateActionEventChild, ...],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id,
                portfolio_id,
                instrument_id,
                security_id,
                transaction_type,
                quantity,
                price,
                gross_transaction_amount,
                trade_currency,
                currency,
                transaction_date
            ) VALUES (
                :transaction_id,
                'CA-PORT-001',
                :instrument_id,
                :instrument_id,
                :transaction_type,
                1,
                1,
                1,
                'USD',
                'USD',
                TIMESTAMPTZ '2026-08-09 01:00:00+00'
            )
            """
        ),
        [
            {
                "transaction_id": child.transaction_id,
                "instrument_id": child.instrument_id,
                "transaction_type": child.transaction_type,
            }
            for child in children
        ],
    )


async def _seed_observations(
    session: AsyncSession,
    event_id: int,
    manifest: corporate_action.CorporateActionParentManifest,
) -> None:
    transaction_records = (
        await session.scalars(
            select(TransactionRecord).where(
                TransactionRecord.transaction_id.in_(
                    child.transaction_id for child in manifest.expected_children
                )
            )
        )
    ).all()
    fingerprints = {
        record.transaction_id: build_transaction_semantic_identity(
            replace(
                to_booked_transaction(TransactionEvent.model_validate(record)),
                epoch=1,
            )
        ).payload_fingerprint
        for record in transaction_records
    }
    assert len(fingerprints) == len(manifest.expected_children)
    await session.execute(
        insert(CorporateActionChildObservationRecord),
        [
            {
                "event_id": event_id,
                "observation_sequence": sequence,
                "transaction_id": child.transaction_id,
                "transaction_epoch": 1,
                "delivery_event_id": f"capacity-{manifest.corporate_action_event_id}-{sequence}",
                "correlation_id": "capacity-correlation",
                "observed_content_hash": child.content_hash,
                "transaction_payload_fingerprint": fingerprints[child.transaction_id],
                "observed_payload": child.lineage_payload(),
                "observed_at": manifest.source_reference.observed_at,
            }
            for sequence, child in enumerate(manifest.expected_children, start=1)
        ],
    )


async def _seed_other_portfolio_and_transaction(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id,
                tenant_id,
                legal_book_id,
                base_currency,
                open_date,
                risk_exposure,
                investment_time_horizon,
                portfolio_type,
                booking_center_code,
                client_id,
                is_leverage_allowed,
                status
            ) VALUES (
                'CA-PORT-OTHER',
                'TENANT-SG',
                'PB-SG-02',
                'USD',
                DATE '2026-01-01',
                'BALANCED',
                'LONG_TERM',
                'DISCRETIONARY',
                'SG',
                'CA-CLIENT-OTHER',
                false,
                'ACTIVE'
            )
            """
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id,
                portfolio_id,
                instrument_id,
                security_id,
                transaction_type,
                quantity,
                price,
                gross_transaction_amount,
                trade_currency,
                currency,
                transaction_date
            ) VALUES (
                'CA-FOREIGN-001',
                'CA-PORT-OTHER',
                'FOREIGN-SEC',
                'FOREIGN-SEC',
                'DEMERGER_IN',
                1,
                1,
                1,
                'USD',
                'USD',
                TIMESTAMPTZ '2026-08-09 01:00:00+00'
            )
            """
        )
    )


def _apply_migration(db_engine: Engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    release_migration: dict[str, Any] = runpy.run_path(str(RELEASE_MIGRATION))
    support_index_migration: dict[str, Any] = runpy.run_path(str(SUPPORT_INDEX_MIGRATION))
    authority_fix_forward_migration: dict[str, Any] = runpy.run_path(
        str(AUTHORITY_FIX_FORWARD_MIGRATION)
    )
    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        inspector = inspect(connection)
        if "corporate_action_events" not in inspector.get_table_names():
            migration["upgrade"].__globals__["op"] = operations
            migration["upgrade"]()
            inspector = inspect(connection)
        observation_columns = {
            column["name"]
            for column in inspector.get_columns("corporate_action_child_observations")
        }
        if "transaction_payload_fingerprint" not in observation_columns:
            release_migration["upgrade"].__globals__["op"] = operations
            release_migration["upgrade"]()
            inspector = inspect(connection)
        if "ix_ca_event_book_scope_updated" not in {
            index["name"] for index in inspector.get_indexes("corporate_action_events")
        }:
            support_index_migration["upgrade"].__globals__["op"] = operations
            support_index_migration["upgrade"]()
        if (
            connection.scalar(
                text("SELECT to_regprocedure('enforce_ca_manifest_payload_book_scope()')")
            )
            is None
        ):
            authority_fix_forward_migration["upgrade"].__globals__["op"] = operations
            authority_fix_forward_migration["upgrade"]()
