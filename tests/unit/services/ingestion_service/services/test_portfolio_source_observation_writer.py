"""Native callback/control proof with simulated SQL I/O; not PostgreSQL ACID proof."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_source_observation_models import (
    CashAvailabilityObservationHead,
    CashAvailabilityObservationRow,
)
from sqlalchemy.dialects import sqlite

from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
)
from src.services.ingestion_service.app.services.portfolio_source_observation_writer import (
    PortfolioSourceObservationWriter,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


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
async def test_overlap_executes_nullable_half_open_predicate(
    existing_from, existing_to, new_from, new_to, overlaps
):
    # SQLite evaluates the actual SQL predicate; native PostgreSQL proof is separate.
    row_model, head_model = CashAvailabilityObservationRow, CashAvailabilityObservationHead
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            f"CREATE TABLE {row_model.__tablename__} (observation_id TEXT, content_hash TEXT, "
            "tenant_id TEXT, portfolio_id TEXT, producer_id TEXT, coverage_scope TEXT, "
            "source_record_id TEXT, effective_from TEXT, effective_to TEXT)"
        )
        connection.execute(
            f"CREATE TABLE {head_model.__tablename__} (observation_id TEXT, content_hash TEXT)"
        )
        connection.execute(
            f"INSERT INTO {row_model.__tablename__} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "old",
                "hash",
                "tenant",
                "portfolio",
                "producer",
                "scope",
                "old",
                existing_from.isoformat(),
                existing_to.isoformat() if existing_to else None,
            ),
        )
        connection.execute(f"INSERT INTO {head_model.__tablename__} VALUES ('old', 'hash')")

        class Session:
            async def scalar(self, statement):
                sql = statement.compile(
                    dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
                )
                row = connection.execute(str(sql)).fetchone()
                return row[0] if row else None

        fact = SimpleNamespace(
            envelope=SimpleNamespace(
                tenant_id="tenant",
                portfolio_id="portfolio",
                producer_id="producer",
                coverage_scope="scope",
                source_record_id="new",
                effective_from=new_from,
                effective_to=new_to,
            )
        )
        writer = PortfolioSourceObservationWriter(Session())
        if overlaps:
            with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_AMBIGUOUS_OVERLAP"):
                await writer._refuse_competing_interval(row_model, head_model, fact)
        else:
            await writer._refuse_competing_interval(row_model, head_model, fact)


class _Begin:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.before = list(self.session.rows)
        self.session.active = True

    async def __aexit__(self, kind, error, traceback):
        if kind:
            self.session.rows[:] = self.before
            self.session.rollbacks += 1
        else:
            self.session.commits += 1
        self.session.active = False


class _Session:
    def __init__(self):
        self.rows = []
        self.info = {}
        self.active = False
        self.commits = self.rollbacks = 0

    def begin(self):
        return _Begin(self)

    async def scalar(self, statement):
        return self.rows[0] if self.rows else None

    async def execute(self, statement, params=None):
        assert self.active

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        for row in self.rows:
            row.submitted_at = row.submitted_at or datetime.now(UTC)
            row.retry_count = row.retry_count or 0


async def _create(session, callback):
    async def sessions():
        yield session

    return await create_or_get_job_result(
        job_id="synthetic-observation-job",
        tenant_id="tenant-synthetic",
        endpoint="/ingest/portfolio-cash-availability-observations",
        entity_type="portfolio_cash_availability_observation",
        accepted_count=1,
        idempotency_key="synthetic-idempotency",
        correlation_id="correlation",
        request_id="request",
        trace_id="trace",
        request_payload={
            "observations": [
                {
                    "source_system": "producer-synthetic",
                    "source_record_id": "record-synthetic",
                    "source_version": 1,
                    "observed_at": "2026-01-01T00:00:00Z",
                    "available_amount": "0",
                }
            ]
        },
        fingerprint_key_id="synthetic-key",
        fingerprint_hmac_secret="synthetic-secret",
        fingerprint_previous_keys={},
        session_factory=sessions,
        on_created=callback,
    )


async def test_native_creation_hook_uses_same_active_transaction_and_replay_skips_hook():
    session = _Session()
    callbacks = []

    async def callback(db, row):
        assert db is session and db.active
        assert db.info["portfolio_source_observation_creation_row"] is row
        assert row in db.rows
        callbacks.append(row.job_id)

    created = await _create(session, callback)
    replay = await _create(session, callback)
    assert created.created and not replay.created
    assert created.job.job_id == replay.job.job_id
    assert len(session.rows) == 1
    assert callbacks == ["synthetic-observation-job"]
    assert session.commits == 2 and session.rollbacks == 0
    assert session.info == {}
    assert session.rows[0].request_payload is None  # Fingerprint-only durable evidence.


async def test_native_callback_failure_rolls_back_new_receipt_and_clears_creation_token():
    session = _Session()

    async def callback(db, row):
        assert db.active and row in db.rows
        raise ValueError("synthetic append/CAS refusal")

    with pytest.raises(ValueError, match="append/CAS refusal"):
        await _create(session, callback)
    assert session.rows == []
    assert session.rollbacks == 1 and session.commits == 0
    assert session.info == {}
