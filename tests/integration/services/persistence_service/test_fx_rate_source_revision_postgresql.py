"""Actual migrated FX cut/revision transactions; no Kafka or provider certification."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from portfolio_common.fx_source_admission import FxSourceAdmission
from portfolio_common.fx_source_models import FxRateSourceCut, FxRateSourceRevision
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.services.persistence_service.app.repositories.fx_source_repository import (
    FxSourceConflict,
    FxSourceRepository,
)
from src.services.query_control_plane_service.app.domain.market_fx import (
    FxSourceSelection,
    FxSourceSelectionRejected,
)
from src.services.query_control_plane_service.app.infrastructure.retained_fx_sources import (
    read_retained_fx_rates,
)
from tests.test_support import fx_source_database as fx_db_fixtures
from tests.test_support.fx_source_fixtures import (
    CALENDAR_VERSION,
    OBSERVED,
    PRINCIPAL,
    synthetic_cut,
    synthetic_revision,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
fx_source_schema = fx_db_fixtures.fx_source_schema
fx_source_database = fx_db_fixtures.fx_source_database
fx_source_migration = fx_db_fixtures.fx_source_migration


def revision(database, **changes):
    return synthetic_revision(scope=database.scope, **changes)


async def rates(database, *, source_as_of, known_as_of, cut_id=None, scope=None):
    async with database.sessions() as session:
        return await read_retained_fx_rates(
            session,
            selection=FxSourceSelection(scope or database.scope, source_as_of, known_as_of, cut_id),
            from_currency="USD",
            to_currency="SGD",
            start_date=OBSERVED.date(),
            end_date=OBSERVED.date(),
        )


async def test_exact_replay_conflicting_version_and_prior_revision_preserved(fx_source_database):
    database = fx_source_database
    original = revision(database)
    cut = synthetic_cut(original)
    retained = await database.retain(cut)
    replay = await database.retain(cut)
    assert not retained.replayed and replay.replayed
    assert replay.row.accepted_at == retained.row.accepted_at
    with pytest.raises(FxSourceConflict, match="CUT_VERSION_CONFLICT"):
        await database.retain(synthetic_cut(replace(original, rate=Decimal("1.36"))))
    with pytest.raises(FxSourceConflict, match="REVISION_VERSION_CONFLICT"):
        await database.retain(
            synthetic_cut(replace(original, rate=Decimal("1.36")), version="another-cut")
        )
    assert await database.counts() == (1, 1, 0, 0)
    async with database.sessions() as session:
        row = await session.get(FxRateSourceRevision, original.revision_id)
        assert row.rate == Decimal("1.35") and row.content_hash == original.content_hash


async def test_distinct_observation_knowledge_boundaries_and_fixed_cut(fx_source_database):
    database = fx_source_database
    original = revision(database)
    first = await database.retain(synthetic_cut(original))
    corrected = replace(
        original,
        source_revision="2",
        predecessor_revision_id=original.revision_id,
        source_observed_at=OBSERVED + timedelta(seconds=30),
        rate=Decimal("1.36"),
    )
    second = await database.retain(synthetic_cut(corrected, version="2"))
    assert second.row.accepted_at > first.row.accepted_at
    before = await rates(
        database,
        source_as_of=OBSERVED,
        known_as_of=first.row.accepted_at - timedelta(microseconds=1),
    )
    assert before == []
    equal = await rates(database, source_as_of=OBSERVED, known_as_of=first.row.accepted_at)
    assert len(equal) == 1 and equal[0].source.revision_id == original.revision_id
    historical = await rates(
        database, source_as_of=corrected.source_observed_at, known_as_of=first.row.accepted_at
    )
    assert historical[0].rate == Decimal("1.35")
    late_source = await rates(database, source_as_of=OBSERVED, known_as_of=second.row.accepted_at)
    assert late_source[0].rate == Decimal("1.35")
    current = await rates(
        database, source_as_of=corrected.source_observed_at, known_as_of=second.row.accepted_at
    )
    assert current[0].source.revision_id == corrected.revision_id
    fixed = await rates(
        database,
        source_as_of=corrected.source_observed_at,
        known_as_of=second.row.accepted_at,
        cut_id=first.row.cut_id,
    )
    assert fixed[0].source.revision_id == original.revision_id
    foreign = replace(database.scope, tenant_id="SYNTHETIC_FOREIGN")
    assert (
        await rates(
            database, source_as_of=OBSERVED, known_as_of=second.row.accepted_at, scope=foreign
        )
        == []
    )
    with pytest.raises(FxSourceSelectionRejected, match="CUT_UNAVAILABLE"):
        await rates(
            database,
            source_as_of=OBSERVED,
            known_as_of=second.row.accepted_at,
            cut_id=first.row.cut_id,
            scope=foreign,
        )


async def test_independent_same_pair_chains_refuse_ambiguity(fx_source_database):
    database = fx_source_database
    await database.retain(synthetic_cut(revision(database)))
    other = revision(database, source_record_id="SYNTHETIC_OTHER_FIXING", rate=Decimal("1.37"))
    second = await database.retain(synthetic_cut(other, reference="SYNTHETIC_OTHER_CUT"))
    with pytest.raises(FxSourceSelectionRejected, match="PAIR_DATE_AMBIGUOUS"):
        await rates(database, source_as_of=OBSERVED, known_as_of=second.row.accepted_at)


async def test_overlapping_pg_corrections_wait_on_actual_lock_and_refuse_stale(fx_source_database):
    database = fx_source_database
    original = revision(database)
    await database.retain(synthetic_cut(original))
    first = replace(original, source_revision="2", predecessor_revision_id=original.revision_id)
    second = replace(first, source_revision="3", rate=Decimal("1.37"))
    first_cut, second_cut = synthetic_cut(first, version="2"), synthetic_cut(second, version="3")
    started = asyncio.Event()
    second_pid = None

    async def competing_write():
        nonlocal second_pid
        async with database.sessions.begin() as session:
            second_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            return await FxSourceRepository(session).retain_admitted_cut(
                FxSourceAdmission(
                    second_cut,
                    datetime.now(UTC),
                    PRINCIPAL,
                    "SYNTHETIC_ENROLLMENT_V1",
                    CALENDAR_VERSION,
                ),
                attestation_sha256="b" * 64,
            )

    async with database.sessions() as held:
        async with held.begin():
            await FxSourceRepository(held).retain_admitted_cut(
                FxSourceAdmission(
                    first_cut,
                    datetime.now(UTC),
                    PRINCIPAL,
                    "SYNTHETIC_ENROLLMENT_V1",
                    CALENDAR_VERSION,
                ),
                attestation_sha256="a" * 64,
            )
            task = asyncio.create_task(competing_write())
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                async with asyncio.timeout(5):
                    while True:
                        async with database.sessions() as observer:
                            blocked = await observer.scalar(
                                text("""
                                    SELECT EXISTS (SELECT 1 FROM pg_locks
                                    WHERE pid=:pid AND locktype='advisory' AND NOT granted)
                                """),
                                {"pid": second_pid},
                            )
                        if blocked:
                            break
                        assert not task.done(), "Competing write did not reach the owning lock"
                        await asyncio.sleep(0.01)
                assert not task.done()
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
        with pytest.raises(FxSourceConflict, match="STALE_PREDECESSOR"):
            await asyncio.wait_for(task, timeout=5)
    assert await database.counts() == (2, 2, 0, 0)


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
async def test_populated_authority_refuses_mutation(fx_source_database, operation):
    database = fx_source_database
    cut = synthetic_cut(revision(database))
    await database.retain(cut)
    statement = {
        "UPDATE": "UPDATE fx_rate_source_revisions SET rate=1.4",
        "DELETE": "DELETE FROM fx_rate_source_cuts",
        "TRUNCATE": "TRUNCATE fx_rate_source_cuts, fx_rate_source_revisions",
    }[operation]
    with pytest.raises(DBAPIError, match="FX_SOURCE_"):
        async with database.sessions.begin() as session:
            await session.execute(text(statement))
    assert await database.counts() == (1, 1, 0, 0)
    async with database.sessions() as session:
        row = await session.get(FxRateSourceCut, cut.cut_id)
        assert row.content_hash == cut.content_hash


async def test_populated_downgrade_refuses_without_losing_history(fx_source_database):
    database = fx_source_database
    await database.retain(synthetic_cut(revision(database)))
    with pytest.raises(DBAPIError, match="DOWNGRADE_WOULD_LOSE_AUTHORITY"):
        async with database.sessions.begin() as session:
            connection = await session.connection()
            await connection.run_sync(lambda bind: fx_source_migration(bind)["downgrade"]())
    assert await database.counts() == (1, 1, 0, 0)


async def test_empty_downgrade_upgrade_preserves_populated_legacy(fx_source_database, monkeypatch):
    from portfolio_common.database_models import FxRate, IngestionJob
    from portfolio_common.events import FxRateEvent

    from src.services.persistence_service.app.consumers import base_consumer
    from src.services.persistence_service.app.consumers.fx_rate_consumer import FxRateConsumer

    database = fx_source_database
    async with database.sessions.begin() as session:
        session.add(
            FxRate(
                from_currency="USD",
                to_currency="SGD",
                rate_date=OBSERVED.date(),
                rate=Decimal("1.31"),
            )
        )
        for status in ("accepted", "queued"):
            session.add(
                IngestionJob(
                    tenant_id=database.scope.tenant_id,
                    job_id=f"synthetic-legacy-{status}",
                    endpoint="/ingest/fx-rates",
                    entity_type="fx_rate",
                    status=status,
                    accepted_count=1,
                    correlation_id="synthetic-legacy",
                    request_id=f"synthetic-{status}",
                    trace_id="a" * 32,
                    request_payload_policy_version="synthetic-legacy-v1",
                    request_payload_classification="legacy_unclassified",
                    request_payload_representation="legacy_redacted",
                    request_payload_replay_eligible=False,
                    request_payload_partial_replay_eligible=False,
                    request_payload_retention_authority="synthetic-existing-legacy",
                )
            )
    async with database.sessions() as session:
        before = (await session.execute(text("SELECT to_jsonb(t) FROM fx_rates t"))).scalars().all()
        jobs_before = (
            (
                await session.execute(
                    text("SELECT to_jsonb(t) FROM ingestion_jobs t ORDER BY job_id")
                )
            )
            .scalars()
            .all()
        )
    async with database.sessions.begin() as session:
        connection = await session.connection()
        await connection.run_sync(lambda bind: fx_source_migration(bind)["downgrade"]())
        await connection.run_sync(lambda bind: fx_source_migration(bind)["upgrade"]())
    async with database.sessions() as session:
        after = (await session.execute(text("SELECT to_jsonb(t) FROM fx_rates t"))).scalars().all()
        jobs_after = (
            (
                await session.execute(
                    text("SELECT to_jsonb(t) FROM ingestion_jobs t ORDER BY job_id")
                )
            )
            .scalars()
            .all()
        )
    assert after == before and await database.counts() == (0, 0, 0, 0)
    assert jobs_after == jobs_before and {job["status"] for job in jobs_after} == {
        "accepted",
        "queued",
    }

    # A legacy event already in transit remains interpretable after upgrade.
    # Direct registered consumer execution is not broker delivery/job completion.
    async def sessions():
        async with database.sessions() as session:
            yield session

    monkeypatch.setattr(base_consumer, "get_async_db_session", sessions)
    consumer = FxRateConsumer(
        bootstrap_servers="synthetic-transport",
        topic="raw-fx-rates",
        group_id="synthetic-legacy-compatibility",
        dlq_topic=None,
    )
    event = FxRateEvent(
        from_currency="USD", to_currency="SGD", rate_date=OBSERVED.date(), rate=Decimal("1.32")
    )
    message = MagicMock()
    message.value.return_value = json.dumps(event.model_dump(mode="json")).encode()
    message.topic.return_value = "raw-fx-rates"
    message.partition.return_value = 0
    message.offset.return_value = 1
    message.headers.return_value = []
    await consumer.process_message(message)
    assert await database.counts() == (0, 0, 1, 1)
    async with database.sessions() as session:
        assert (await session.execute(text("SELECT rate FROM fx_rates"))).scalar_one() == Decimal(
            "1.32"
        )
        assert (
            await session.execute(text("SELECT to_jsonb(t) FROM ingestion_jobs t ORDER BY job_id"))
        ).scalars().all() == jobs_before
    assert await rates(database, source_as_of=OBSERVED, known_as_of=datetime.now(UTC)) == [], (
        "Legacy rate presence must not acquire canonical provenance"
    )


async def test_deferred_missing_members_refuse_commit_and_leave_no_cut(fx_source_database):
    database = fx_source_database
    cut = synthetic_cut(revision(database))
    with pytest.raises(DBAPIError, match="MEMBERS_NOT_RETAINED"):
        async with database.sessions.begin() as session:
            session.add(
                FxRateSourceCut(
                    cut_id=cut.cut_id,
                    **cut.scope.content(),
                    source_cut_reference=cut.source_cut_reference,
                    source_cut_revision=cut.source_cut_revision,
                    source_observed_cutoff=cut.source_observed_cutoff,
                    member_count=1,
                    members=[
                        {
                            "revision_id": cut.revisions[0].revision_id,
                            "content_hash": cut.revisions[0].content_hash,
                        }
                    ],
                    membership_hash=cut.declared_membership_hash,
                    content_hash=cut.content_hash,
                    admission_receipt={"synthetic": True},
                )
            )
            await session.flush()
    assert await database.counts() == (0, 0, 0, 0)
