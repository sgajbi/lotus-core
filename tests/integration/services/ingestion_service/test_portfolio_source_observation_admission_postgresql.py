"""Owned, migrated PostgreSQL lease only; no shared cleanup or runtime provisioning."""

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from portfolio_common.database_models import IngestionJob, Portfolio
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_async_database_engine
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
)
from portfolio_common.portfolio_source_observation_models import (
    CashAvailabilityObservationHead,
    CashAvailabilityObservationRow,
)
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAdmission,
)
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.ingestion_service.app.infrastructure import (
    portfolio_source_observation_unit_of_work as observation_uow,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
)
from src.services.ingestion_service.app.services.portfolio_source_observation_writer import (
    PortfolioSourceObservationWriter,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


@dataclass
class ObservationLease:
    sessions: async_sessionmaker
    tenant: str
    portfolio: str
    schema: str

    def cash(self, *, record="cash", scope="accounts", currency="SGD"):
        envelope = ObservationEnvelope(
            self.tenant,
            self.portfolio,
            "synthetic-source",
            record,
            1,
            "original-cut",
            "v1",
            date(2026, 1, 1),
            None,
            datetime(2026, 3, 1, tzinfo=UTC),
            datetime(2026, 3, 1, tzinfo=UTC),
            ObservationCoverage.COMPLETE,
            scope,
        )
        return CashAvailabilityObservation(envelope, currency, Decimal("10.00"), None, Decimal("0"))

    async def create(self, fact, *, idempotency=None, callback=None):
        async def sessions():
            async with self.sessions() as session:
                yield session

        admission = UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                self.tenant,
                self.portfolio,
                fact.envelope.producer_id,
                fact.family,
            )
        )
        stager = observation_uow.PortfolioSourceObservationStager((fact,), (admission,))
        return await create_or_get_job_result(
            job_id=str(uuid4()),
            tenant_id=self.tenant,
            endpoint=(
                "/ingest/portfolio-cash-availability-observations"
                if isinstance(fact, CashAvailabilityObservation)
                else "/ingest/portfolio-funding-investment-observations"
            ),
            entity_type=(
                "portfolio_cash_availability_observation"
                if isinstance(fact, CashAvailabilityObservation)
                else "portfolio_funding_investment_observation"
            ),
            accepted_count=1,
            idempotency_key=idempotency or str(uuid4()),
            correlation_id="synthetic-correlation",
            request_id="synthetic-request",
            trace_id="synthetic-trace",
            request_payload={
                "observations": [
                    {
                        "source_system": fact.envelope.producer_id,
                        "source_record_id": fact.envelope.source_record_id,
                        "source_version": fact.envelope.source_revision,
                        "observed_at": fact.envelope.observed_at.isoformat(),
                        "content_hash": fact.content_hash,
                    }
                ]
            },
            fingerprint_key_id="synthetic-key",
            fingerprint_hmac_secret="synthetic-secret",
            fingerprint_previous_keys={},
            session_factory=sessions,
            on_created=callback or stager.stage,
        )

    async def counts(self):
        async with self.sessions() as session:
            counts = []
            for model in (
                IngestionJob,
                CashAvailabilityObservationRow,
                CashAvailabilityObservationHead,
            ):
                counts.append(
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(
                            model.tenant_id == self.tenant,
                        )
                    )
                )
            return tuple(counts)


@pytest.fixture
def observation_schema(db_engine):
    """Adapt the native owned migration namespace pattern, never clean public."""
    from tests import conftest as harness
    from tests.test_support.db_cleanup import (
        authorize_database_cleanup,
        require_database_cleanup_authorization,
    )

    authorization = authorize_database_cleanup(runtime=harness._test_runtime, engine=db_engine)
    schema, marker = "core1227_" + uuid4().hex, "core1227-owned:" + uuid4().hex
    require_database_cleanup_authorization(authorization, engine=db_engine)
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT current_database()")) == authorization.target.database
        assert connection.scalar(text("SELECT session_user")) == authorization.target.username
        connection.execute(text(f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER'))
        connection.execute(text(f"""COMMENT ON SCHEMA "{schema}" IS '{marker}'"""))
        for table in ("portfolios", "ingestion_jobs", "ingestion_ops_control"):
            connection.execute(
                text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING CONSTRAINTS)')
            )
        # No shared defaults or sequences. These defaults belong solely to this
        # namespace and are necessary for the ACTUAL native receipt constructor.
        for table in ("portfolios", "ingestion_jobs"):
            connection.execute(
                text(
                    f'ALTER TABLE "{schema}".{table} ALTER COLUMN id '
                    "ADD GENERATED BY DEFAULT AS IDENTITY"
                )
            )
        for table, columns in (
            ("portfolios", "tenant_id, portfolio_id"),
            ("ingestion_jobs", "tenant_id, job_id"),
            ("ingestion_jobs", "job_id"),
            ("ingestion_ops_control", "id"),
        ):
            connection.execute(text(f'ALTER TABLE "{schema}".{table} ADD UNIQUE ({columns})'))
        for table, column in (
            ("ingestion_jobs", "submitted_at"),
            ("ingestion_ops_control", "updated_at"),
            ("portfolios", "created_at"),
            ("portfolios", "updated_at"),
        ):
            connection.execute(
                text(f'ALTER TABLE "{schema}".{table} ALTER COLUMN {column} SET DEFAULT now()')
            )
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        observation_migration(connection)["upgrade"]()
    owned = db_engine, authorization, schema, marker
    try:
        yield owned
    finally:
        # No inherited namespace, disabled trigger or public table teardown.
        require_database_cleanup_authorization(authorization, engine=db_engine)
        with db_engine.begin() as connection:
            identity = connection.execute(
                text("""
                SELECT current_database(), session_user, pg_get_userbyid(nspowner),
                       obj_description(oid, 'pg_namespace')
                FROM pg_namespace WHERE nspname=:schema
            """),
                {"schema": schema},
            ).one()
            assert tuple(identity) == (
                authorization.target.database,
                authorization.target.username,
                authorization.target.username,
                marker,
            )
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def observation_migration(connection):
    """Actual frozen migration functions with actual Alembic SQL operations."""
    import runpy
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[4] / "alembic/versions"
    module = runpy.run_path(str(path / "c178b2c3d539_add_portfolio_source_observations.py"))
    assert module["revision"] == "c178b2c3d539" and module["down_revision"] == "c177b2c3d538"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


@pytest_asyncio.fixture
async def observation_lease(observation_schema):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    db_engine, _, schema, _ = observation_schema
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=db_engine.url.render_as_string(hide_password=False),
        pool_mode=DatabasePoolMode.NULL,
    )

    class OwnedObservationSession(Session):
        pass

    def bind_owned_namespace(session, transaction, connection):
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))

    event.listen(OwnedObservationSession, "after_begin", bind_owned_namespace)
    sessions = async_sessionmaker(
        engine, expire_on_commit=False, sync_session_class=OwnedObservationSession
    )
    identity = uuid4().hex
    lease = ObservationLease(sessions, f"observation-{identity}", f"portfolio-{identity}", schema)
    try:
        async with sessions.begin() as session:
            assert await session.scalar(text("SELECT current_schema()")) == schema
            session.add(
                Portfolio(
                    portfolio_id=lease.portfolio,
                    tenant_id=lease.tenant,
                    legal_book_id="synthetic-book",
                    base_currency="SGD",
                    open_date=date(2020, 1, 1),
                    risk_exposure="MODERATE",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="DISCRETIONARY",
                    booking_center_code="SG",
                    client_id="synthetic-client",
                    status="ACTIVE",
                    is_leverage_allowed=False,
                )
            )
        yield lease
    finally:
        await engine.dispose()
        event.remove(OwnedObservationSession, "after_begin", bind_owned_namespace)


async def test_receipt_fact_head_commit_and_ambiguous_response_replay(observation_lease):
    lease = observation_lease
    fact = lease.cash()
    original = await lease.create(fact, idempotency="ambiguous-response")
    replay = await lease.create(fact, idempotency="ambiguous-response")
    assert original.created and not replay.created
    assert original.job.job_id == replay.job.job_id
    assert replay.job.status == "completed" and replay.job.completed_at is not None
    assert await lease.counts() == (1, 1, 1)
    async with lease.sessions() as session:
        receipt = await session.scalar(
            select(IngestionJob).where(
                IngestionJob.job_id == original.job.job_id,
            )
        )
        assert receipt.request_payload is None and not receipt.request_payload_replay_eligible
        head = await session.scalar(
            select(CashAvailabilityObservationHead).where(
                CashAvailabilityObservationHead.tenant_id == lease.tenant,
            )
        )
        assert head.observation_id == head.content_hash == fact.content_hash


@pytest.mark.parametrize("field", ["settled", "encumbered", "available"])
@pytest.mark.parametrize(
    "source,expected",
    [
        pytest.param("-0", "0", id="signed-zero"),
        pytest.param("-0.00", "0.00", id="scaled-signed-zero"),
        pytest.param("1E-7", "0.0000001", id="positive-tiny-control"),
        pytest.param("-1E-7", "-0.0000001", id="negative-tiny-control"),
        pytest.param("1E+3", "1000", id="positive-exponent"),
        pytest.param("0E+3", "0", id="zero-exponent"),
        pytest.param("-1E+3", "-1000", id="negative-integer-exponent"),
        pytest.param("0.00", "0.00", id="positive-zero-control"),
        pytest.param(
            "123456789012345678901234.1234567890123456789000",
            "123456789012345678901234.1234567890123456789000",
            id="positive-precision-control",
        ),
        pytest.param(
            "-123456789012345678901234.1234567890123456789000",
            "-123456789012345678901234.1234567890123456789000",
            id="negative-precision-control",
        ),
    ],
)
async def test_cash_numeric_representation_survives_persisted_read_and_cross_receipt_replay(
    observation_lease, field, source, expected
):
    from portfolio_common.portfolio_source_observation_models import observation_from_row

    lease = observation_lease
    fact = replace(lease.cash(), **{field: Decimal(source)})
    committed = await lease.create(fact, idempotency="signed-zero-original")
    assert committed.created and committed.job.status == "completed"
    assert await lease.counts() == (1, 1, 1)

    async def snapshot():
        async with lease.sessions() as session:
            return {
                table: (
                    await session.execute(
                        text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                    )
                )
                .scalars()
                .all()
                for table in (
                    "ingestion_jobs",
                    "portfolio_cash_availability_observations",
                    "portfolio_cash_availability_observation_heads",
                )
            }

    before = await snapshot()
    read_error = replay_error = None
    loaded = replay = None
    async with lease.sessions() as session:
        row = (await session.scalars(select(CashAvailabilityObservationRow))).one()
        stored = getattr(row, f"{field}_amount")
        assert stored.as_tuple() == Decimal(expected).as_tuple()
        try:
            loaded = observation_from_row(row)
        except ObservationConflict as error:
            read_error = str(error)
    try:
        replay = await lease.create(fact, idempotency="signed-zero-cross-receipt")
    except ObservationConflict as error:
        replay_error = str(error)
    after = await snapshot()
    if replay_error is not None:
        assert after == before, "failed cross-receipt replay must leave all durable rows unchanged"
    print(
        f"CASH_NUMERIC field={field} input={source} stored={stored} "
        f"read_error={read_error} replay_error={replay_error}"
    )
    assert read_error is None and replay_error is None
    assert loaded == fact and loaded.content_hash == fact.content_hash
    assert fact.content_hash == replace(fact, **{field: Decimal(expected)}).content_hash
    assert replay is not None and replay.created and replay.job.status == "completed"
    assert replay.job.job_id != committed.job.job_id
    assert await lease.counts() == (2, 1, 1)
    assert (
        after["portfolio_cash_availability_observations"]
        == before["portfolio_cash_availability_observations"]
    )
    assert (
        after["portfolio_cash_availability_observation_heads"]
        == before["portfolio_cash_availability_observation_heads"]
    )
    original_row = next(
        row for row in after["ingestion_jobs"] if row["job_id"] == committed.job.job_id
    )
    assert original_row == before["ingestion_jobs"][0]


async def _replay_identity_snapshot(lease):
    async with lease.sessions() as session:
        return {
            table: (
                await session.execute(
                    text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                )
            )
            .scalars()
            .all()
            for table in (
                "ingestion_jobs",
                "portfolio_cash_availability_observations",
                "portfolio_cash_availability_observation_heads",
                "portfolio_funding_investment_observations",
                "portfolio_funding_investment_observation_heads",
            )
        }


@pytest.mark.parametrize("field", ["settled", "encumbered", "available"])
@pytest.mark.parametrize("original,replayed", [("1.00", "1.0"), ("0.00", "0")])
async def test_existing_revision_scale_change_refuses_without_receipt_or_fact_mutation(
    observation_lease, field, original, replayed
):
    lease = observation_lease
    fact = replace(lease.cash(), **{field: Decimal(original)})
    divergent = replace(fact, **{field: Decimal(replayed)})
    assert fact == divergent and fact.content_hash != divergent.content_hash
    committed = await lease.create(fact, idempotency="scale-original")
    assert committed.created and committed.job.status == "completed"
    before = await _replay_identity_snapshot(lease)
    refusal = None
    try:
        await lease.create(divergent, idempotency="scale-divergent")
    except ObservationConflict as error:
        refusal = str(error)
    after = await _replay_identity_snapshot(lease)
    print(
        f"REPLAY_SCALE field={field} original={original} replay={replayed} "
        f"refusal={refusal} unchanged={before == after}"
    )
    assert refusal == "SOURCE_OBSERVATION_DIVERGENT_REPLAY"
    assert after == before
    assert await lease.counts() == (1, 1, 1)


@pytest.mark.parametrize("field", ["settled", "encumbered", "available"])
@pytest.mark.parametrize(
    "original,replayed",
    [
        ("1.00", "1.00"),
        ("-0.00", "0.00"),
        ("1E+3", "1000"),
        ("-12345678901234567890.12345678900", "-12345678901234567890.12345678900"),
    ],
)
async def test_existing_revision_hash_identity_accepts_exact_and_canonicalized_replay(
    observation_lease, field, original, replayed
):
    lease = observation_lease
    fact = replace(lease.cash(), **{field: Decimal(original)})
    equivalent = replace(fact, **{field: Decimal(replayed)})
    assert fact.content_hash == equivalent.content_hash
    committed = await lease.create(fact, idempotency="identity-original")
    before = await _replay_identity_snapshot(lease)
    replay = await lease.create(equivalent, idempotency="identity-replay")
    assert committed.created and replay.created
    assert replay.job.status == "completed" and replay.job.job_id != committed.job.job_id
    after = await _replay_identity_snapshot(lease)
    for table in before.keys() - {"ingestion_jobs"}:
        assert after[table] == before[table]
    assert len(after["ingestion_jobs"]) == 2
    assert (
        next(row for row in after["ingestion_jobs"] if row["job_id"] == committed.job.job_id)
        == before["ingestion_jobs"][0]
    )
    assert await lease.counts() == (2, 1, 1)


async def test_existing_revision_hash_identity_preserves_funding_replay_and_refusal(
    observation_lease,
):
    lease = observation_lease
    fact = FundingInvestmentObservation(
        replace(lease.cash().envelope, source_record_id="funding"), None, False
    )
    committed = await lease.create(fact, idempotency="funding-original")
    before = await _replay_identity_snapshot(lease)
    replay = await lease.create(fact, idempotency="funding-identical")
    assert committed.created and replay.created and replay.job.status == "completed"
    after = await _replay_identity_snapshot(lease)
    for table in before.keys() - {"ingestion_jobs"}:
        assert after[table] == before[table]
    assert len(after["ingestion_jobs"]) == 2
    assert (
        next(row for row in after["ingestion_jobs"] if row["job_id"] == committed.job.job_id)
        == before["ingestion_jobs"][0]
    )
    with pytest.raises(ObservationConflict, match="^SOURCE_OBSERVATION_DIVERGENT_REPLAY$"):
        await lease.create(replace(fact, funded=False), idempotency="funding-divergent")
    assert await _replay_identity_snapshot(lease) == after


async def test_actual_empty_downgrade_upgrade_preserves_parent_and_model_columns(observation_lease):
    lease = observation_lease
    async with lease.sessions.begin() as session:
        connection = await session.connection()
        before = await session.scalar(
            text("SELECT to_jsonb(p) FROM portfolios p WHERE portfolio_id=:p"),
            {"p": lease.portfolio},
        )
        await connection.run_sync(lambda c: observation_migration(c)["downgrade"]())
        assert (
            await session.scalar(
                text("SELECT to_regclass('portfolio_cash_availability_observations')")
            )
            is None
        )
    # Reopen the session to rule out transient in-session schema state.
    async with lease.sessions.begin() as session:
        connection = await session.connection()
        await connection.run_sync(lambda c: observation_migration(c)["upgrade"]())
        assert (
            await session.scalar(
                text("SELECT to_jsonb(p) FROM portfolios p WHERE portfolio_id=:p"),
                {"p": lease.portfolio},
            )
            == before
        )
        for model in (CashAvailabilityObservationRow, CashAvailabilityObservationHead):
            columns = set(
                (
                    await session.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema=:schema AND table_name=:table"
                        ),
                        {"schema": lease.schema, "table": model.__tablename__},
                    )
                ).scalars()
            )
            assert columns == set(model.__table__.columns.keys())


async def test_actual_nonempty_downgrade_refuses_and_keeps_history(observation_lease):
    lease = observation_lease
    await lease.create(lease.cash())
    with pytest.raises(RuntimeError, match="nonempty portfolio source observation history"):
        async with lease.sessions.begin() as session:
            connection = await session.connection()
            await connection.run_sync(lambda c: observation_migration(c)["downgrade"]())
    assert await lease.counts() == (1, 1, 1)


async def test_failure_after_fact_and_head_flush_rolls_back_receipt_too(observation_lease):
    lease = observation_lease
    fact = lease.cash()
    admission = UnqualifiedProducerAdmission(
        ProducerSubmissionGrant(
            lease.tenant,
            lease.portfolio,
            fact.envelope.producer_id,
            fact.family,
        )
    )

    async def fail_after_head(session, receipt):
        await PortfolioSourceObservationWriter(session).append(
            (fact,),
            (admission,),
            receipt_job_id=receipt.job_id,
            received_at=receipt.submitted_at,
        )
        raise RuntimeError("synthetic failure before receipt completion")

    with pytest.raises(RuntimeError, match="before receipt completion"):
        await lease.create(fact, callback=fail_after_head)
    assert await lease.counts() == (0, 0, 0)
    assert (await lease.create(fact)).job.status == "completed"
    assert await lease.counts() == (1, 1, 1)


async def test_two_competing_corrections_have_one_committed_winner(observation_lease):
    lease = observation_lease
    original = lease.cash()
    await lease.create(original)
    envelope = replace(
        original.envelope,
        source_revision=2,
        predecessor_id=original.content_hash,
        expected_head_hash=original.content_hash,
    )
    corrections = tuple(
        replace(original, envelope=envelope, available=Decimal(value)) for value in ("1", "2")
    )
    start = asyncio.Event()

    async def submit(fact):
        await start.wait()
        try:
            return await lease.create(fact)
        except ObservationConflict as error:
            return str(error)

    tasks = [asyncio.create_task(submit(fact)) for fact in corrections]
    start.set()
    outcomes = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert sum(not isinstance(result, str) for result in outcomes) == 1
    assert "SOURCE_OBSERVATION_DIVERGENT_REPLAY" in outcomes
    assert await lease.counts() == (2, 2, 1)
    # Original replay never rewinds the committed corrected head.
    await lease.create(original)
    async with lease.sessions() as session:
        head = await session.scalar(
            select(CashAvailabilityObservationHead).where(
                CashAvailabilityObservationHead.tenant_id == lease.tenant,
            )
        )
        assert head.observation_id in {fact.content_hash for fact in corrections}


@pytest.mark.parametrize("dimension", ["scope", "currency"])
async def test_same_portfolio_distinct_authority_keys_progress_while_other_transaction_open(
    observation_lease,
    dimension,
):
    lease = observation_lease
    holding, release = asyncio.Event(), asyncio.Event()
    first = lease.cash(record="first")
    second = lease.cash(
        record="second", **({"scope": "other"} if dimension == "scope" else {"currency": "USD"})
    )

    async def hold(session, receipt):
        admission = UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                lease.tenant,
                lease.portfolio,
                first.envelope.producer_id,
                first.family,
            )
        )
        await PortfolioSourceObservationWriter(session).append(
            (first,),
            (admission,),
            receipt_job_id=receipt.job_id,
            received_at=receipt.submitted_at,
        )
        holding.set()
        await release.wait()
        raise RuntimeError("synthetic held transaction rollback")

    task = asyncio.create_task(lease.create(first, callback=hold))
    try:
        await asyncio.wait_for(holding.wait(), timeout=5)
        result = await asyncio.wait_for(lease.create(second), timeout=5)
        assert result.job.status == "completed"  # Must finish BEFORE release.
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="held transaction rollback"):
            await task
    assert await lease.counts() == (1, 1, 1)


async def test_competing_same_scope_interval_refuses_without_orphan_receipt(observation_lease):
    lease = observation_lease
    await lease.create(lease.cash(record="first"))
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_AMBIGUOUS_OVERLAP"):
        await lease.create(lease.cash(record="second"))
    assert await lease.counts() == (1, 1, 1)


@pytest.mark.parametrize(
    "existing_from,existing_to,new_from,new_to,overlaps",
    [
        (date.max, None, date.max, None, True),
        (date.max, None, date(2026, 1, 1), None, True),
        (date(2026, 1, 1), None, date.max, None, True),
        (date(2026, 1, 1), date(2026, 2, 1), date(2026, 2, 1), None, False),
        (date(2026, 2, 1), None, date(2026, 1, 1), date(2026, 2, 1), False),
        (date(2026, 2, 1), None, date(2026, 1, 1), date(2026, 3, 1), True),
    ],
)
async def test_nullable_interval_boundary_admission_and_completed_replay(
    observation_lease, existing_from, existing_to, new_from, new_to, overlaps
):
    lease = observation_lease
    first = lease.cash(record="first")
    first = replace(
        first,
        envelope=replace(first.envelope, effective_from=existing_from, effective_to=existing_to),
    )
    original = await lease.create(first, idempotency="boundary-original")
    replay = await lease.create(first, idempotency="boundary-original")
    assert not replay.created and replay.job.job_id == original.job.job_id
    assert replay.job.status == "completed" and replay.job.completed_at is not None
    second = lease.cash(record="second")
    second = replace(
        second, envelope=replace(second.envelope, effective_from=new_from, effective_to=new_to)
    )
    if overlaps:
        with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_AMBIGUOUS_OVERLAP"):
            await lease.create(second)
        assert await lease.counts() == (1, 1, 1)
    else:
        assert (await lease.create(second)).job.status == "completed"
        assert await lease.counts() == (2, 2, 2)


async def test_concurrent_open_date_max_intervals_have_one_completed_receipt(observation_lease):
    lease = observation_lease
    facts = [
        replace(
            lease.cash(record=record),
            envelope=replace(lease.cash(record=record).envelope, effective_from=date.max),
        )
        for record in ("first", "second")
    ]
    results = await asyncio.gather(*(lease.create(fact) for fact in facts), return_exceptions=True)
    winners = [result for result in results if not isinstance(result, Exception)]
    refusals = [result for result in results if isinstance(result, Exception)]
    assert len(winners) == len(refusals) == 1
    assert winners[0].job.status == "completed"
    assert isinstance(refusals[0], ObservationConflict)
    assert "SOURCE_OBSERVATION_AMBIGUOUS_OVERLAP" in str(refusals[0])
    assert await lease.counts() == (1, 1, 1)


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE", "PARENT_TRUNCATE"])
async def test_database_refuses_fact_mutation_without_disabling_triggers(
    observation_lease,
    operation,
):
    lease = observation_lease
    fact = lease.cash()
    await lease.create(fact)
    table = "portfolio_cash_availability_observations"
    statements = {
        "UPDATE": f"UPDATE {table} SET available_amount=1 WHERE tenant_id=:tenant",
        "DELETE": f"DELETE FROM {table} WHERE tenant_id=:tenant",
        "TRUNCATE": f"TRUNCATE TABLE {table} CASCADE",
        "PARENT_TRUNCATE": "TRUNCATE TABLE portfolios RESTART IDENTITY CASCADE",
    }
    with pytest.raises(DBAPIError) as error:
        async with lease.sessions.begin() as session:
            await session.execute(text(statements[operation]), {"tenant": lease.tenant})
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    assert await lease.counts() == (1, 1, 1)
    async with lease.sessions() as session:
        assert (
            await session.get(CashAvailabilityObservationRow, fact.content_hash)
        ).available_amount == 0


async def test_empty_fixture_cascade_and_stale_snapshot_refusal(observation_lease):
    lease = observation_lease
    # This exact namespace is fresh. Use the existing fixture table inventory,
    # filtered to present owned parents, with its real CASCADE/RESTART behavior.
    # This is the observation-parent cleanup seam, not full-suite acceptance.
    from tests.conftest import TABLES_TO_TRUNCATE

    async with lease.sessions() as session:
        async with session.begin():
            assert await session.scalar(text("SHOW transaction_isolation")) == "read committed"
            existing = set(
                (
                    await session.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname=:schema"),
                        {"schema": lease.schema},
                    )
                ).scalars()
            )
            tables = [table for table in TABLES_TO_TRUNCATE if table in existing]
            await session.execute(
                text("TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
            )
            portfolio = await session.scalar(
                select(Portfolio).where(
                    Portfolio.tenant_id == lease.tenant,
                    Portfolio.portfolio_id == lease.portfolio,
                )
            )
            assert portfolio is None
            await session.rollback()
    # Establish a genuinely stale transaction-fixed snapshot before the other
    # session commits history. The guard must refuse, never mistake old zero for empty.
    async with lease.sessions() as stale:
        async with stale.begin():
            await stale.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            assert (
                await stale.scalar(select(func.count()).select_from(CashAvailabilityObservationRow))
                == 0
            )
            await lease.create(lease.cash())
            with pytest.raises(DBAPIError) as error:
                await stale.execute(
                    text("TRUNCATE TABLE portfolio_cash_availability_observations CASCADE")
                )
            assert getattr(error.value.orig, "sqlstate", None) == "23514"
            await stale.rollback()
    assert await lease.counts() == (1, 1, 1)


async def test_waiting_truncate_sees_insert_committed_after_statement_start(observation_lease):
    lease = observation_lease
    inserted, release, truncating = asyncio.Event(), asyncio.Event(), asyncio.Event()
    fact = lease.cash()
    pid = None

    async def hold_insert(session, receipt):
        admission = UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                lease.tenant,
                lease.portfolio,
                fact.envelope.producer_id,
                fact.family,
            )
        )
        await PortfolioSourceObservationWriter(session).append(
            (fact,),
            (admission,),
            receipt_job_id=receipt.job_id,
            received_at=receipt.submitted_at,
        )
        inserted.set()
        await release.wait()
        await observation_uow.complete_synchronous_observation_receipt(
            session,
            receipt,
            tenant_id=lease.tenant,
            job_id=receipt.job_id,
        )

    async def truncate():
        nonlocal pid
        async with lease.sessions.begin() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            truncating.set()
            await session.execute(
                text("TRUNCATE TABLE portfolio_cash_availability_observations CASCADE")
            )

    async def observed_lock_wait():
        while True:
            async with lease.sessions() as observer:
                waiting = await observer.scalar(
                    text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),
                    {"pid": pid},
                )
                if waiting:
                    return
            await asyncio.sleep(0.01)

    writer = asyncio.create_task(lease.create(fact, callback=hold_insert))
    truncate_task = None
    try:
        await asyncio.wait_for(inserted.wait(), timeout=5)
        truncate_task = asyncio.create_task(truncate())
        await asyncio.wait_for(truncating.wait(), timeout=5)
        await asyncio.wait_for(observed_lock_wait(), timeout=5)  # Actual PG barrier.
        release.set()
        assert (await asyncio.wait_for(writer, timeout=5)).job.status == "completed"
        with pytest.raises(DBAPIError) as error:
            await asyncio.wait_for(truncate_task, timeout=5)
        assert getattr(error.value.orig, "sqlstate", None) == "23514"
    finally:
        release.set()
        for task in (writer, truncate_task):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert await lease.counts() == (1, 1, 1)


async def test_actual_downgrade_waits_for_admission_then_refuses_committed_history(
    observation_lease,
):
    lease = observation_lease
    inserted, release, downgrading = asyncio.Event(), asyncio.Event(), asyncio.Event()
    fact = lease.cash()
    pid = None

    async def hold_insert(session, receipt):
        admission = UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                lease.tenant,
                lease.portfolio,
                fact.envelope.producer_id,
                fact.family,
            )
        )
        await PortfolioSourceObservationWriter(session).append(
            (fact,),
            (admission,),
            receipt_job_id=receipt.job_id,
            received_at=receipt.submitted_at,
        )
        inserted.set()
        await release.wait()
        await observation_uow.complete_synchronous_observation_receipt(
            session,
            receipt,
            tenant_id=lease.tenant,
            job_id=receipt.job_id,
        )

    async def downgrade():
        nonlocal pid
        async with lease.sessions.begin() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            downgrading.set()
            connection = await session.connection()
            await connection.run_sync(lambda c: observation_migration(c)["downgrade"]())

    async def wait_for_lock():
        while True:
            async with lease.sessions() as observer:
                if await observer.scalar(
                    text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),
                    {"pid": pid},
                ):
                    return
            await asyncio.sleep(0.01)

    writer = asyncio.create_task(lease.create(fact, callback=hold_insert))
    migration = None
    try:
        await asyncio.wait_for(inserted.wait(), timeout=5)
        migration = asyncio.create_task(downgrade())
        await asyncio.wait_for(downgrading.wait(), timeout=5)
        await asyncio.wait_for(wait_for_lock(), timeout=3)
        release.set()
        assert (await asyncio.wait_for(writer, timeout=5)).job.status == "completed"
        with pytest.raises(RuntimeError, match="nonempty portfolio source observation history"):
            await asyncio.wait_for(migration, timeout=5)
    finally:
        release.set()
        for task in (writer, migration):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert await lease.counts() == (1, 1, 1)


@pytest.mark.parametrize(
    "bad, sqlstate",
    [
        ("tenant", "23503"),
        ("portfolio", "23503"),
        ("receipt", "23503"),
        ("predecessor", "23503"),
        ("duplicate", "23505"),
        ("nan", "23514"),
        ("infinity", "23514"),
        ("qualification", "23514"),
    ],
)
async def test_actual_direct_constraints_refuse_bad_rows_and_accept_valid(
    observation_lease, bad, sqlstate
):
    lease = observation_lease
    original = lease.cash()
    await lease.create(original)
    async with lease.sessions() as session:
        row = (
            (await session.execute(select(CashAvailabilityObservationRow.__table__)))
            .mappings()
            .one()
        )
        values = dict(row)
    valid = lease.cash(record="direct-valid")
    values.update(
        source_record_id="direct-valid",
        observation_id=valid.content_hash,
        content_hash=valid.content_hash,
    )
    bad_values = dict(values)
    if bad == "tenant":
        bad_values["tenant_id"] = "foreign-tenant"
    elif bad == "portfolio":
        bad_values["portfolio_id"] = "foreign-portfolio"
    elif bad == "receipt":
        bad_values["receipt_job_id"] = "foreign-receipt"
    elif bad == "predecessor":
        bad_values.update(
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        )
    elif bad == "duplicate":
        bad_values = dict(row)
    elif bad == "nan":
        bad_values["available_amount"] = Decimal("NaN")
    elif bad == "infinity":
        bad_values["settled_amount"] = Decimal("Infinity")
    else:
        bad_values["qualification"] = "qualified"
    with pytest.raises(DBAPIError) as error:
        async with lease.sessions.begin() as session:
            if bad in {"nan", "infinity"}:
                # Fixed test SQL bypasses the ORM precision binder, exercising
                # PostgreSQL's constraint rather than binder rejection.
                columns = list(CashAvailabilityObservationRow.__table__.columns.keys())
                expressions = list(columns)
                expressions[columns.index("source_record_id")] = "'direct-valid'"
                for name in ("observation_id", "content_hash"):
                    expressions[columns.index(name)] = ":hash"
                column = "available_amount" if bad == "nan" else "settled_amount"
                expressions[columns.index(column)] = (
                    "'NaN'::numeric" if bad == "nan" else "'Infinity'::numeric"
                )
                await session.execute(
                    text(
                        "INSERT INTO portfolio_cash_availability_observations ("
                        + ",".join(columns)
                        + ") SELECT "
                        + ",".join(expressions)
                        + " FROM portfolio_cash_availability_observations"
                    ),
                    {"hash": valid.content_hash},
                )
            else:
                await session.execute(
                    insert(CashAvailabilityObservationRow.__table__).values(**bad_values)
                )
    assert getattr(error.value.orig, "sqlstate", None) == sqlstate
    assert await lease.counts() == (1, 1, 1)
    async with lease.sessions.begin() as session:
        await session.execute(insert(CashAvailabilityObservationRow.__table__).values(**values))
    assert await lease.counts() == (1, 2, 1)


async def test_actual_funding_immutability_and_head_owner_constraint(observation_lease):
    from portfolio_common.portfolio_source_observation_models import (
        FundingInvestmentObservationHead,
        FundingInvestmentObservationRow,
    )

    lease = observation_lease
    cash = lease.cash()
    fact = FundingInvestmentObservation(
        replace(cash.envelope, source_record_id="funding"), None, False
    )
    await lease.create(fact)
    for sql in (
        "UPDATE portfolio_funding_investment_observations SET funded=true",
        "DELETE FROM portfolio_funding_investment_observations",
        "TRUNCATE portfolio_funding_investment_observation_heads CASCADE",
    ):
        with pytest.raises(DBAPIError) as error:
            async with lease.sessions.begin() as session:
                await session.execute(text(sql))
        assert getattr(error.value.orig, "sqlstate", None) == "23514"
    with pytest.raises(DBAPIError) as error:
        async with lease.sessions.begin() as session:
            await session.execute(
                text(
                    "UPDATE portfolio_funding_investment_observation_heads SET tenant_id='foreign'"
                )
            )
    assert getattr(error.value.orig, "sqlstate", None) == "23503"
    async with lease.sessions() as session:
        row = (await session.scalars(select(FundingInvestmentObservationRow))).one()
        head = (await session.scalars(select(FundingInvestmentObservationHead))).one()
        assert row.funded is None and row.invested is False
        assert head.tenant_id == lease.tenant and head.observation_id == fact.content_hash


async def test_completed_receipt_is_nonactionable_in_native_operations(observation_lease):
    from src.services.ingestion_service.app.services.ingestion_backlog_breakdown import (
        load_backlog_breakdown_response,
    )
    from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
        get_job_response,
        mark_job_queued,
        mark_job_retried,
    )
    from src.services.ingestion_service.app.services.ingestion_retry_permissions import (
        count_backlog_jobs,
    )
    from src.services.ingestion_service.app.services.ingestion_stalled_jobs import (
        load_stalled_job_list_response,
    )

    lease = observation_lease
    completed = await lease.create(lease.cash())

    async def sessions():
        async with lease.sessions() as session:
            yield session

    response = await get_job_response(
        job_id=completed.job.job_id,
        tenant_id=lease.tenant,
        session_factory=sessions,
        reference_key_id="synthetic-key",
        reference_hmac_secret="synthetic-secret",
    )
    assert response.status == "completed" and response.completed_at is not None
    assert not response.request_payload_replay_eligible
    assert not await mark_job_queued(
        job_id=completed.job.job_id,
        tenant_id=lease.tenant,
        session_factory=sessions,
        expected_statuses=("completed",),
    )
    assert not await mark_job_retried(
        job_id=completed.job.job_id, tenant_id=lease.tenant, session_factory=sessions
    )
    # A real accepted control ensures the queries do not merely return empty unconditionally.
    async with lease.sessions.begin() as session:
        row = (await session.execute(select(IngestionJob.__table__))).mappings().one()
        values = dict(row)
        values.pop("id")
        values.update(
            job_id="accepted-control",
            idempotency_key="accepted-control",
            status="accepted",
            completed_at=None,
            submitted_at=datetime.now(UTC) - timedelta(seconds=2),
        )
        await session.execute(insert(IngestionJob.__table__).values(**values))
    now = datetime.now(UTC)
    assert await count_backlog_jobs(session_factory=sessions) == 1
    backlog = await load_backlog_breakdown_response(
        lookback_minutes=60, limit=10, session_factory=sessions, now=now
    )
    assert backlog.total_backlog_jobs == 1
    stalled = await load_stalled_job_list_response(
        threshold_seconds=1, limit=10, session_factory=sessions, now=now
    )
    assert [row.job_id for row in stalled.jobs] == ["accepted-control"]
    async with lease.sessions() as session:
        retained = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == completed.job.job_id)
        )
        assert retained.status == "completed" and retained.retry_count == 0


@pytest.mark.parametrize("scenario", ["mixed", "all_sync", "no_completion", "async_completed"])
async def test_native_queue_latency_excludes_synchronous_completed_receipts(
    observation_lease, scenario
):
    from src.services.ingestion_service.app.services.ingestion_slo_status import (
        _load_aggregate_slo_snapshot,
        slo_snapshot_from_jobs,
    )

    lease = observation_lease
    receipt = await lease.create(lease.cash())
    now = datetime.now(UTC)
    async with lease.sessions.begin() as session:
        original = (await session.execute(select(IngestionJob.__table__))).mappings().one()
        values = dict(original)
        values.pop("id")
        if scenario in ("mixed", "all_sync"):
            controls = [("completed", 2, 1)] * (1000 if scenario == "mixed" else 100)
        else:
            controls = []
        if scenario in ("mixed", "async_completed"):
            controls += [(status, 500, 100) for status in ("queued", "failed") for _ in range(5)]
        if scenario == "no_completion":
            controls += [(status, 500, None) for status in ("accepted", "queued", "failed")]
        for index, (status, submitted_age, completed_age) in enumerate(controls):
            await session.execute(
                insert(IngestionJob.__table__).values(
                    **{
                        **values,
                        "job_id": f"queue-control-{index}",
                        "idempotency_key": f"queue-control-{index}",
                        "status": status,
                        "submitted_at": now - timedelta(seconds=submitted_age),
                        "completed_at": None
                        if completed_age is None
                        else now - timedelta(seconds=completed_age),
                    }
                )
            )
    async with lease.sessions() as session:
        before = (
            (await session.execute(select(IngestionJob.__table__).order_by(IngestionJob.id)))
            .mappings()
            .all()
        )
        aggregate = await _load_aggregate_slo_snapshot(
            session, since=now - timedelta(hours=1), now=now
        )
        jobs = (await session.scalars(select(IngestionJob))).all()
        fallback = slo_snapshot_from_jobs(jobs=jobs, now=now)
        assert aggregate == fallback
        if scenario == "mixed":
            # Execute the predecessor expression against the same rows: fast synchronous
            # receipts really hide the queue's 400-second latency, not just a SQL-shape issue.
            diluted = await session.scalar(
                select(
                    func.percentile_cont(0.95).within_group(
                        func.extract("epoch", IngestionJob.completed_at - IngestionJob.submitted_at)
                    )
                ).where(IngestionJob.completed_at.is_not(None))
            )
            assert diluted == 1.0
        assert aggregate.total_jobs == sum(status != "completed" for status, _, _ in controls)
        assert aggregate.failed_jobs == (
            5 if scenario in ("mixed", "async_completed") else int(scenario == "no_completion")
        )
        assert aggregate.p95_latency_seconds == (
            400.0 if scenario in ("mixed", "async_completed") else 0.0
        )
        assert aggregate.backlog_age_seconds == (0.0 if scenario == "all_sync" else 500.0)
        after = (
            (await session.execute(select(IngestionJob.__table__).order_by(IngestionJob.id)))
            .mappings()
            .all()
        )
        assert after == before
        retained = next(row for row in after if row["job_id"] == receipt.job.job_id)
        assert retained["status"] == "completed" and retained["completed_at"] is not None


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("sync_count", [1, 100])
async def test_native_async_failure_cohort_is_invariant_to_sync_receipts(
    observation_lease, asynchronous, sync_count
):
    import logging

    from src.services.ingestion_service.app.services.ingestion_error_budget_status import (
        load_error_budget_status_response,
    )
    from src.services.ingestion_service.app.services.ingestion_slo_status import (
        _load_aggregate_slo_snapshot,
        _load_fallback_slo_snapshot,
        build_slo_status_response,
        slo_snapshot_from_jobs,
    )

    lease = observation_lease
    receipt = await lease.create(lease.cash())
    now = datetime.now(UTC)
    async with lease.sessions.begin() as session:
        await session.execute(
            text(
                f'CREATE TABLE "{lease.schema}".consumer_dlq_events '
                "(LIKE public.consumer_dlq_events INCLUDING CONSTRAINTS)"
            )
        )
        original = (await session.execute(select(IngestionJob.__table__))).mappings().one()
        template = dict(original)
        template.pop("id")
        controls = (
            [
                ("accepted", 500, None),
                ("queued", 500, 100),
                ("failed", 500, 100),
                ("queued", 5400, None),
            ]
            if asynchronous
            else []
        )
        for index, (status, age, completion) in enumerate(controls):
            await session.execute(
                insert(IngestionJob.__table__).values(
                    **{
                        **template,
                        "job_id": f"async-{index}",
                        "idempotency_key": f"async-{index}",
                        "status": status,
                        "submitted_at": now - timedelta(seconds=age),
                        "completed_at": None
                        if completion is None
                        else now - timedelta(seconds=completion),
                    }
                )
            )

    async def observed():
        async with lease.sessions() as session:
            aggregate = await _load_aggregate_slo_snapshot(
                session, since=now - timedelta(hours=1), now=now
            )
            jobs = (
                await session.scalars(
                    select(IngestionJob).where(
                        IngestionJob.submitted_at >= now - timedelta(hours=1)
                    )
                )
            ).all()
            assert aggregate == slo_snapshot_from_jobs(jobs=jobs, now=now)
            assert aggregate == await _load_fallback_slo_snapshot(
                session, since=now - timedelta(hours=1), now=now
            )

        async def sessions():
            async with lease.sessions() as session:
                yield session

        budget = await load_error_budget_status_response(
            lookback_minutes=60,
            failure_rate_threshold=Decimal("0.03"),
            backlog_growth_threshold=0,
            replay_max_backlog_jobs=10,
            dlq_budget_events_per_window=5,
            session_factory=sessions,
            logger=logging.getLogger(__name__),
        )
        return aggregate, budget

    baseline, baseline_budget = await observed()
    async with lease.sessions.begin() as session:
        for index in range(sync_count):
            for window, age in (("current", 2), ("previous", 5400)):
                await session.execute(
                    insert(IngestionJob.__table__).values(
                        **{
                            **template,
                            "job_id": f"sync-{window}-{index}",
                            "idempotency_key": f"sync-{window}-{index}",
                            "status": "completed",
                            "submitted_at": now - timedelta(seconds=age),
                            "completed_at": now,
                        }
                    )
                )
    before = await _replay_identity_snapshot(lease)
    aggregate, budget = await observed()
    assert aggregate == baseline and budget == baseline_budget
    assert budget.total_jobs == (3 if asynchronous else 0)
    assert budget.failed_jobs == int(asynchronous)
    assert budget.failure_rate == (Decimal(1) / Decimal(3) if asynchronous else Decimal(0))
    assert budget.remaining_error_budget == (Decimal(0) if asynchronous else Decimal("0.03"))
    assert budget.breach_failure_rate is asynchronous
    assert budget.backlog_jobs == (2 if asynchronous else 0)
    assert budget.previous_backlog_jobs == int(asynchronous)
    assert budget.backlog_growth == int(asynchronous)
    assert budget.replay_backlog_pressure_ratio == (Decimal("0.2") if asynchronous else Decimal(0))
    assert budget.dlq_events_in_window == 0 and budget.dlq_pressure_ratio == 0
    response = build_slo_status_response(
        lookback_minutes=60,
        snapshot=aggregate,
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=5.0,
        backlog_age_threshold_seconds=300.0,
    )
    assert response.failure_rate == budget.failure_rate
    assert response.breach_failure_rate is asynchronous
    assert response.p95_queue_latency_seconds == (400.0 if asynchronous else 0.0)
    assert response.backlog_age_seconds == (500.0 if asynchronous else 0.0)
    assert await _replay_identity_snapshot(lease) == before
    async with lease.sessions() as session:
        retained = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == receipt.job.job_id)
        )
        assert retained.status == "completed" and retained.completed_at is not None


async def test_complete_seeded_financial_fence_outbox_snapshots_unchanged(observation_lease):
    lease = observation_lease
    tables = (
        "transactions",
        "cashflows",
        "position_history",
        "cost_basis_processing_state",
        "processed_events",
        "outbox_events",
    )
    async with lease.sessions.begin() as session:
        for table in tables:
            await session.execute(
                text(
                    f'CREATE TABLE "{lease.schema}".{table} '
                    f"(LIKE public.{table} INCLUDING CONSTRAINTS)"
                )
            )
        params = {
            "portfolio": lease.portfolio,
            "tenant": lease.tenant,
            "fingerprint": "sha256:" + "a" * 64,
        }
        await session.execute(
            text("""
            INSERT INTO transactions(id,transaction_id,portfolio_id,instrument_id,security_id,
            transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency,
            transaction_date,created_at,updated_at,payload_fingerprint)
            VALUES(1,'economic-original',:portfolio,'SEC','SEC','BUY',1,20,20,'SGD','SGD',
            now(),now(),now(),:fingerprint)
        """),
            params,
        )
        await session.execute(
            text("""
            INSERT INTO cashflows(id,transaction_id,portfolio_id,security_id,cashflow_date,epoch,
            amount,currency,classification,timing,calculation_type,is_position_flow,is_portfolio_flow,
            created_at,updated_at) VALUES(1,'economic-original',:portfolio,'SEC',CURRENT_DATE,0,
            20,'SGD','INVESTMENT','EOD','NET',true,false,now(),now())
        """),
            params,
        )
        await session.execute(
            text("""
            INSERT INTO position_history(id,portfolio_id,security_id,transaction_id,position_date,
            epoch,quantity,cost_basis,cost_basis_local,created_at,updated_at)
            VALUES(1,:portfolio,'SEC','economic-original',CURRENT_DATE,0,1,20,20,now(),now())
        """),
            params,
        )
        await session.execute(
            text("""
            INSERT INTO cost_basis_processing_state(portfolio_id,security_id,cost_basis_method,
            latest_transaction_date,latest_dependency_rank,latest_cash_dependency_rank,
            latest_child_sequence,latest_target_instrument_id,latest_quantity,latest_transaction_id,
            engine_state_version,created_at,updated_at)
            VALUES(:portfolio,'SEC','FIFO',now(),0,0,0,'SEC',1,'economic-original','v1',now(),now())
        """),
            params,
        )
        await session.execute(
            text("""
            INSERT INTO processed_events(id,event_id,portfolio_id,service_name,tenant_id,
            correlation_id,processed_at) VALUES(1,'economic-fence',:portfolio,
            'portfolio-transaction-processing',:tenant,'synthetic-correlation',now())
        """),
            params,
        )
        await session.execute(
            text("""
            INSERT INTO outbox_events(id,aggregate_type,aggregate_id,partition_key,event_type,
            payload,topic,status,retry_count,created_at)
            VALUES(1,'Transaction','economic-original',:portfolio,'TransactionPersisted',
            '{"transaction_id":"economic-original"}','transactions.persisted','PENDING',0,now())
        """),
            params,
        )

    async def snapshot():
        async with lease.sessions() as session:
            return {
                table: (
                    await session.execute(
                        text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")
                    )
                )
                .scalars()
                .all()
                for table in tables
            }

    before = await snapshot()
    assert all(len(rows) == 1 for rows in before.values())
    cash = lease.cash()
    funding = FundingInvestmentObservation(
        replace(cash.envelope, source_record_id="funding"), None, False
    )
    for fact in (cash, funding):
        await lease.create(fact, idempotency=fact.content_hash)
        await lease.create(fact, idempotency=fact.content_hash)
        assert await snapshot() == before
    divergent = replace(cash, available=Decimal("5"))
    with pytest.raises(ObservationConflict):
        await lease.create(divergent)
    assert await snapshot() == before
