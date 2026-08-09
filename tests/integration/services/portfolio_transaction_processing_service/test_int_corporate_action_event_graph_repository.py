"""PostgreSQL contracts for corporate-action parent-manifest persistence."""

from __future__ import annotations

import asyncio
import runpy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    CorporateActionChildObservationRecord,
    CorporateActionEventRecord,
    CorporateActionManifestEdgeRecord,
    CorporateActionManifestNodeRecord,
    CorporateActionManifestVersionRecord,
)
from portfolio_common.domain.calculation_lineage import FinancialSourceReference
from sqlalchemy import Engine, func, insert, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_event_graph import (  # noqa: E501
    SqlAlchemyCorporateActionEventGraphRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    ConflictingCorporateActionManifestError,
    CorporateActionManifestAppendOutcome,
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
    / "c150b2c3d517_feat_add_corporate_action_event_graph.py"
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
    finally:
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
    event_id = (
        await async_db_session.execute(
            insert(CorporateActionEventRecord)
            .values(
                tenant_id="TENANT-SG",
                legal_book_id="PB-SG-01",
                portfolio_id=manifest.portfolio_id,
                corporate_action_event_id=manifest.corporate_action_event_id,
                linked_transaction_group_id=manifest.linked_transaction_group_id,
                parent_event_reference=manifest.parent_event_reference,
            )
            .returning(CorporateActionEventRecord.id)
        )
    ).scalar_one()
    await async_db_session.execute(
        insert(CorporateActionChildObservationRecord),
        [
            {
                "event_id": event_id,
                "observation_sequence": sequence,
                "transaction_id": child.transaction_id,
                "transaction_epoch": 1,
                "delivery_event_id": f"delivery-{sequence}",
                "observed_content_hash": child.content_hash,
                "observed_payload": child.lineage_payload(),
                "observed_at": manifest.source_reference.observed_at,
            }
            for sequence, child in enumerate(manifest.expected_children, start=1)
        ],
    )
    await async_db_session.execute(
        update(CorporateActionEventRecord)
        .where(CorporateActionEventRecord.id == event_id)
        .values(last_observation_sequence=len(manifest.expected_children))
    )
    repository = SqlAlchemyCorporateActionEventGraphRepository(async_db_session)

    assert (
        await repository.append_manifest(manifest) is CorporateActionManifestAppendOutcome.APPENDED
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    event = await async_db_session.get(CorporateActionEventRecord, event_id)
    assert event is not None
    assert event.readiness_status == "READY"
    reconstructed = await repository.load_current_manifest(
        portfolio_id=manifest.portfolio_id,
        corporate_action_event_id=manifest.corporate_action_event_id,
    )
    assert reconstructed is not None
    assert reconstructed.lineage_payload() == manifest.lineage_payload()


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


def _apply_migration(db_engine: Engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        if "corporate_action_events" in inspect(connection).get_table_names():
            return
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration["upgrade"]()
