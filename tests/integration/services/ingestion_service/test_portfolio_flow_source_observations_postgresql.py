"""Owning PostgreSQL controls, collected only until Root admits database execution."""

import asyncio
import runpy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.page_tokens import PageTokenCodec
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationRow,
    FlowSourceCutRow,
)
from portfolio_common.portfolio_source_observation_models import CashAvailabilityObservationRow
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAdmission,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from src.services.ingestion_service.app.infrastructure import (
    portfolio_source_observation_unit_of_work as observation_uow,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
)
from src.services.query_control_plane_service.app.application import (
    portfolio_flow_source_observations as flow_application,
)
from src.services.query_control_plane_service.app.contracts import (
    portfolio_flow_source_observations as flow_contracts,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_flow_source_observation_sources as flow_sources,
)
from tests.integration.services.ingestion_service import (
    test_portfolio_source_observation_admission_postgresql as source_tests,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, dated_event, event, pin

observation_lease = source_tests.observation_lease
observation_schema = source_tests.observation_schema

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


def migration(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    module = runpy.run_path(
        str(root / "alembic/versions/c187b2c3d548_portfolio_flow_source_observations.py")
    )
    assert module["down_revision"] == "c186b2c3d547"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def apply_migration(owned, action="upgrade"):
    engine, _, schema, _ = owned
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        migration(connection)[action]()


def fact_for(lease, name="a", *, business_date=None, **changes):
    fact = (
        dated_event(name, business_date, **changes)
        if business_date is not None
        else event(name, **changes)
    )
    return replace(
        fact, envelope=replace(fact.envelope, tenant_id=lease.tenant, portfolio_id=lease.portfolio)
    )


def manifest_for(lease, *facts, **changes):
    return cut(*facts, tenant_id=lease.tenant, portfolio_id=lease.portfolio, **changes)


async def create(lease, value, *, is_cut=False, idempotency=None, callback=None):
    tenant = value.tenant_id if is_cut else value.envelope.tenant_id
    producer = value.source_system if is_cut else value.envelope.producer_id
    from portfolio_common.domain.portfolio_source_observations import ObservationFamily

    admission = UnqualifiedProducerAdmission(
        ProducerSubmissionGrant(
            tenant,
            lease.portfolio,
            producer,
            ObservationFamily.FLOW_EVENT,
        )
    )
    stager = observation_uow.PortfolioFlowSourceObservationStager(
        (value,), (admission,), datetime.now(UTC), is_cut
    )

    async def sessions():
        async with lease.sessions() as session:
            yield session

    return await create_or_get_job_result(
        job_id=str(uuid4()),
        tenant_id=tenant,
        endpoint="/ingest/portfolio-flow-source-cuts"
        if is_cut
        else "/ingest/portfolio-flow-event-observations",
        entity_type="portfolio_flow_source_cut" if is_cut else "portfolio_flow_event_observation",
        accepted_count=1,
        idempotency_key=idempotency or str(uuid4()),
        correlation_id="synthetic-correlation",
        request_id="synthetic-request",
        trace_id="synthetic-trace",
        request_payload={
            "cuts" if is_cut else "observations": [{"content_hash": value.content_hash}]
        },
        fingerprint_key_id="synthetic-key",
        fingerprint_hmac_secret="synthetic-secret",
        fingerprint_previous_keys={},
        session_factory=sessions,
        on_created=callback or stager.stage,
    )


async def counts(lease):
    async with lease.sessions() as session:
        return tuple(
            [
                await session.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == lease.tenant)
                )
                for model in (IngestionJob, FlowEventObservationRow, FlowSourceCutRow)
            ]
        )


@pytest.mark.parametrize("case", ["same-window", "prior-window", "multi-hop"])
async def test_populated_upgrade_keeps_legacy_and_retains_original_corrected_and_reversal(
    observation_lease, observation_schema, case
):
    lease = observation_lease
    old = lease.cash()
    receipt = await lease.create(old)
    async with lease.sessions() as session:
        legacy = await session.get(CashAvailabilityObservationRow, old.content_hash)
        preserved = (legacy.content_hash, legacy.received_at, legacy.receipt_job_id)
    apply_migration(observation_schema)
    original_date = {
        "same-window": date(2026, 1, 2),
        "prior-window": date(2025, 12, 15),
        "multi-hop": date(2025, 11, 15),
    }[case]
    original = fact_for(lease, business_date=original_date)
    admitted = await create(lease, original, idempotency="response-lost")
    retry = await create(lease, original, idempotency="response-lost")
    assert retry.job.job_id == admitted.job.job_id and not retry.created
    first = manifest_for(
        lease,
        original,
        coverage_from=original.envelope.effective_from,
        coverage_to=original.envelope.effective_to - timedelta(days=1),
    )
    await create(lease, first, is_cut=True)
    correction = replace(
        original,
        posting_state="CANCELLED",
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    await create(lease, correction)
    reversal_date = date(2025, 12, 15) if case == "multi-hop" else date(2026, 1, 2)
    reversal = fact_for(
        lease,
        "b",
        business_date=reversal_date,
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="a",
        reversal_target=pin(original),
    )
    await create(lease, reversal)
    dependencies = (original,)
    if case == "multi-hop":
        january = fact_for(
            lease,
            "c",
            classification="REVERSAL",
            reversal_state="REVERSES",
            reverses_source_record_id="b",
            reversal_target=pin(reversal),
        )
        await create(lease, january)
        dependencies += (reversal,)
        reversal = january
    if case == "same-window":
        second = manifest_for(
            lease,
            correction,
            reversal,
            cut_revision=2,
            predecessor_cut_hash=first.content_hash,
            expected_head_hash=first.content_hash,
            dependency_pins=tuple(pin(f) for f in dependencies),
        )
        expected_second = ["CANCELLED", "POSTED"]
    else:
        second = manifest_for(
            lease,
            reversal,
            source_cut_id="january-cut",
            dependency_pins=tuple(pin(f) for f in dependencies),
        )
        expected_second = ["POSTED"]
    before = await counts(lease)
    missing = replace(
        second,
        source_cut_id="refused-cut",
        cut_revision=1,
        predecessor_cut_hash=None,
        expected_head_hash=None,
        dependency_pins=(),
    )
    with pytest.raises(ObservationConflict, match="INVALID_MEMBERSHIP"):
        await create(lease, missing, is_cut=True)
    assert await counts(lease) == before
    await create(lease, second, is_cut=True)
    async with lease.sessions() as session:
        legacy = await session.get(CashAvailabilityObservationRow, old.content_hash)
        assert legacy.receipt_job_id == receipt.job.job_id
        assert (legacy.content_hash, legacy.received_at, legacy.receipt_job_id) == preserved
        reader = flow_sources.SqlAlchemyPortfolioFlowObservationReader(session)
        service = flow_application.PortfolioFlowObservationsService(
            reader, PageTokenCodec(secret="synthetic-page")
        )
        for manifest, expected in ((first, ["POSTED"]), (second, expected_second)):
            request = flow_contracts.PortfolioFlowObservationsRequest.model_validate(
                {
                    "source_system": manifest.source_system,
                    "source_cut_id": manifest.source_cut_id,
                    "cut_revision": manifest.cut_revision,
                    "manifest_hash": manifest.content_hash,
                    "currency": manifest.currency,
                    "window": {
                        "from_date": manifest.coverage_from,
                        "to_date": manifest.coverage_to,
                    },
                    "page": {"page_size": 100},
                }
            )
            result = await service.query(
                tenant_id=lease.tenant, portfolio_id=lease.portfolio, request=request
            )
            assert [e.posting_state for e in result.events] == expected
            assert result.source_fields_available and not result.authoritative_use_available
            assert result.pagination.total_count == len(expected)
            if manifest is first:
                assert result.events[0].receipt_job_id == admitted.job.job_id
                assert result.reversal_dependencies == []
            else:
                assert len(result.reversal_dependencies) == len(dependencies)
                assert result.reversal_dependencies[0].observation_id == original.content_hash
                assert result.reversal_dependencies[0].flow_source_record_revision == 1
                assert all(e.business_date.month == 1 for e in result.events)
                assert (
                    result.events[-1].reversal_target.observation_id
                    == reversal.reversal_target.observation_id
                )
    with pytest.raises(RuntimeError, match="nonempty"):
        apply_migration(observation_schema, "downgrade")


async def test_cas_race_and_rollback_leave_one_correction_and_no_orphan_receipt(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    original = fact_for(lease)
    await create(lease, original)
    correction = replace(
        original,
        posting_state="CANCELLED",
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    divergent = replace(correction, classification="INTERNAL_TRANSFER")
    results = await asyncio.gather(
        create(lease, correction), create(lease, divergent), return_exceptions=True
    )
    assert sum(isinstance(r, ObservationConflict) for r in results) == 1
    assert await counts(lease) == (2, 2, 0)
    from src.services.ingestion_service.app.services import (
        portfolio_flow_source_observation_writer as flow_writer,
    )

    orphan = fact_for(lease, "orphan")

    async def crash(session, receipt):
        admission = UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                lease.tenant, lease.portfolio, orphan.envelope.producer_id, orphan.family
            )
        )
        await flow_writer.PortfolioFlowSourceObservationWriter(session).append(
            (orphan,), (admission,), receipt_job_id=receipt.job_id, received_at=datetime.now(UTC)
        )
        raise RuntimeError("simulated crash before terminal receipt")

    with pytest.raises(RuntimeError, match="simulated crash"):
        await create(lease, orphan, callback=crash)
    assert await counts(lease) == (2, 2, 0)
    await create(lease, orphan)
    assert await counts(lease) == (3, 3, 0)


async def test_empty_upgrade_round_trip_and_append_only_guards(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    apply_migration(observation_schema, "downgrade")
    apply_migration(observation_schema)
    original = fact_for(lease)
    await create(lease, original)
    await create(lease, manifest_for(lease, original), is_cut=True)
    for table in ("portfolio_flow_event_observations", "portfolio_flow_source_cuts"):
        for statement in (
            f"DELETE FROM {table}",
            f"UPDATE {table} SET receipt_job_id=receipt_job_id",
            f"TRUNCATE {table}",
        ):
            with pytest.raises(DBAPIError):
                async with lease.sessions.begin() as session:
                    await session.execute(text(statement))
    assert await counts(lease) == (2, 1, 1)


async def test_concurrent_arrival_is_visible_after_publication_lock_wait(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    original, arrival = fact_for(lease), fact_for(lease, "late-arrival")
    await create(lease, original)
    manifest = manifest_for(lease, original)
    wrote, release = asyncio.Event(), asyncio.Event()
    cut_pid = asyncio.get_running_loop().create_future()
    from portfolio_common.domain.portfolio_source_observations import ObservationFamily

    admission = UnqualifiedProducerAdmission(
        ProducerSubmissionGrant(
            lease.tenant,
            lease.portfolio,
            original.envelope.producer_id,
            ObservationFamily.FLOW_EVENT,
        )
    )

    async def arrival_callback(session, receipt):
        await observation_uow.PortfolioFlowSourceObservationStager(
            (arrival,),
            (admission,),
            datetime.now(UTC),
            False,
        ).stage(session, receipt)
        wrote.set()
        await release.wait()

    async def cut_callback(session, receipt):
        cut_pid.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
        await observation_uow.PortfolioFlowSourceObservationStager(
            (manifest,),
            (admission,),
            datetime.now(UTC),
            True,
        ).stage(session, receipt)

    arrival_task = asyncio.create_task(create(lease, arrival, callback=arrival_callback))
    cut_task = None
    try:
        await asyncio.wait_for(wrote.wait(), timeout=5)
        cut_task = asyncio.create_task(create(lease, manifest, is_cut=True, callback=cut_callback))
        pid = await asyncio.wait_for(cut_pid, timeout=5)

        async def blocked():
            while True:
                async with lease.sessions() as session:
                    if await session.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
                    ):
                        return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(blocked(), timeout=5)
        assert not cut_task.done()
    finally:
        release.set()
        tasks = [arrival_task] + ([cut_task] if cut_task is not None else [])
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert not isinstance(results[0], Exception)
    assert isinstance(results[1], ObservationConflict)
    assert "INVALID_MEMBERSHIP" in str(results[1])
    assert await counts(lease) == (2, 2, 0)
    await create(lease, manifest_for(lease, original, arrival), is_cut=True)
    assert await counts(lease) == (3, 2, 1)


async def test_retained_empty_cut_replay_survives_late_arrival_without_rewriting_receipt(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    empty = manifest_for(lease)
    original_receipt = await create(lease, empty, is_cut=True)
    async with lease.sessions() as session:
        retained = await session.get(FlowSourceCutRow, empty.content_hash)
        first_time = retained.received_at
    await create(lease, fact_for(lease))
    await create(lease, empty, is_cut=True)
    async with lease.sessions() as session:
        retained = await session.get(FlowSourceCutRow, empty.content_hash)
        assert retained.event_pins == []
        assert (
            retained.received_at == first_time
            and retained.receipt_job_id == original_receipt.job.job_id
        )
    assert await counts(lease) == (3, 1, 1)
