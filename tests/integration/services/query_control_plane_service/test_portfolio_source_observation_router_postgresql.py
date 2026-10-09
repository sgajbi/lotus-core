"""Actual included write/read handlers with synthetic admission on an owned PG lease."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
from time import time

import httpx
import pytest
from portfolio_common.database_models import IngestionOpsControl
from portfolio_common.db import get_async_db_session
from portfolio_common.domain.portfolio_source_observations import FundingInvestmentObservation
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
)
from sqlalchemy import text

from src.services.ingestion_service.app.dependencies import (
    get_portfolio_source_observation_commands,
)
from src.services.ingestion_service.app.infrastructure.workflow_stores import (
    SqlAlchemyIngestionJobStore,
)
from src.services.ingestion_service.app.main import app as write_app
from src.services.ingestion_service.app.services import ingestion_job_service as jobs
from src.services.ingestion_service.app.services.portfolio_source_observation_commands import (
    PortfolioSourceObservationCommands,
)
from src.services.query_control_plane_service.app.main import app as read_app
from tests.integration.services.ingestion_service import (
    test_portfolio_source_observation_admission_postgresql as admission_proof,
)
from tests.test_support.portfolio_source_test_schema import fact_verification_migration

observation_lease = admission_proof.observation_lease
preverification_observation_schema = admission_proof.observation_schema


@pytest.fixture
def observation_schema(preverification_observation_schema):
    """Current read adapters require the complete receipt dependency, even empty."""
    engine, _, schema, _ = preverification_observation_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        fact_verification_migration(connection)["upgrade"]()
    return preverification_observation_schema


pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
WRITE_CAP = "ingestion.portfolio_cash_availability_observations.write"
FUNDING_CAP = "ingestion.portfolio_funding_investment_observations.write"
READ_CAP = "source_data.portfolio_financial_source_observations.read"

# Two separately exited Python service processes prove reconstruction from durable
# SQL, not a fresh session in one cached app. DSN stays transient on stdin.
_RESTART_QUERY = """
import asyncio, json, os, sys
from portfolio_common.db import create_async_database_engine
from portfolio_common.database_runtime_profile import DatabasePoolMode
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.services.query_control_plane_service.app.application.portfolio_source_observations import (
    PortfolioSourceObservationsService,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_source_observation_sources as sources,
)
from src.services.query_control_plane_service.app.contracts.portfolio_source_observations import (
    PortfolioSourceObservationsRequest,
)

async def main():
    inputs = json.load(sys.stdin)
    engine = create_async_database_engine(runtime_identity='lotus-core-test',
        database_url=inputs['database_url'], pool_mode=DatabasePoolMode.NULL)
    class OwnedSession(Session):
        pass
    def bind_namespace(session, transaction, connection):
        connection.execute(text('SET LOCAL search_path TO "' + inputs['schema'] + '", pg_temp'))
    event.listen(OwnedSession, 'after_begin', bind_namespace)
    sessions = async_sessionmaker(engine, expire_on_commit=False, sync_session_class=OwnedSession)
    try:
        outputs = []
        for request in inputs['requests']:
            async with sessions() as session:
                service = PortfolioSourceObservationsService(
                    sources.SqlAlchemyPortfolioSourceObservationReader(session))
                response = await service.query(
                    tenant_id=inputs['tenant'], portfolio_id=inputs['portfolio'],
                    request=PortfolioSourceObservationsRequest.model_validate(request))
                outputs.append(response.model_dump(mode='json'))
        print('OWNED_QUERY=' + json.dumps({'pid': os.getpid(), 'responses': outputs}))
    finally:
        await engine.dispose()
        event.remove(OwnedSession, 'after_begin', bind_namespace)
asyncio.run(main())
"""


def _pin(fact):
    return {
        "producer_id": fact.envelope.producer_id,
        "source_record_id": fact.envelope.source_record_id,
        "observation_id": fact.content_hash,
        "content_hash": fact.content_hash,
        "source_cut_id": fact.envelope.source_cut_id,
        "source_version": fact.envelope.source_revision,
    }


async def _query_restarted_process(lease, requests):
    inputs = {
        "database_url": lease.sessions.kw["bind"].url.render_as_string(hide_password=False),
        "schema": lease.schema,
        "tenant": lease.tenant,
        "portfolio": lease.portfolio,
        "requests": requests,
    }
    completed = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "scripts/development/repository_python.py", "-c", _RESTART_QUERY],
        input=json.dumps(inputs),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # Do not expose the transient connection envelope on failures.
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    lines = [line for line in completed.stdout.splitlines() if line.startswith("OWNED_QUERY=")]
    assert len(lines) == 1
    return json.loads(lines[0].removeprefix("OWNED_QUERY="))


async def test_actual_query_service_process_restart_preserves_both_original_pins(observation_lease):
    lease = observation_lease
    cash = lease.cash()
    funding = FundingInvestmentObservation(
        replace(cash.envelope, source_record_id="funding"), None, False
    )
    await lease.create(cash)
    await lease.create(funding)
    original_request = {
        "as_of_date": "2026-01-15",
        "cash": _pin(cash),
        "funding_investment": _pin(funding),
    }
    first = await _query_restarted_process(lease, [original_request])
    corrected = []
    for fact in (cash, funding):
        envelope = replace(
            fact.envelope,
            source_revision=2,
            source_cut_id="corrected-cut",
            predecessor_id=fact.content_hash,
            expected_head_hash=fact.content_hash,
        )
        correction = (
            replace(fact, envelope=envelope, available=Decimal("3"))
            if fact is cash
            else replace(fact, envelope=envelope, funded=False, invested=None)
        )
        await lease.create(correction)
        corrected.append(correction)
    latest_request = {"as_of_date": "2026-01-15"}
    for name, fact in zip(("cash", "funding_investment"), (cash, funding), strict=True):
        latest_request[name] = {
            "producer_id": fact.envelope.producer_id,
            "source_record_id": fact.envelope.source_record_id,
            "latest_restated": True,
        }
    second = await _query_restarted_process(lease, [original_request, latest_request])
    assert len({os.getpid(), first["pid"], second["pid"]}) == 3
    before, reloaded = first["responses"][0], second["responses"][0]
    for response in (before, reloaded, second["responses"][1]):
        assert response["authoritative_state"] == response["compatibility"] == "UNAVAILABLE"
    # Entire family projections, including receipt and timestamps, survive restart.
    assert reloaded["cash"] == before["cash"]
    assert reloaded["funding_investment"] == before["funding_investment"]
    assert reloaded["cash"]["available_amount"] == "0"
    assert reloaded["funding_investment"]["funded"] is None
    assert reloaded["funding_investment"]["invested"] is False
    latest = second["responses"][1]
    assert latest["cash"]["observation_id"] == corrected[0].content_hash
    assert latest["funding_investment"]["observation_id"] == corrected[1].content_hash
    assert latest["funding_investment"]["funded"] is False
    assert latest["funding_investment"]["invested"] is None


async def test_actual_two_family_statement_snapshot_survives_inflight_head_changes(
    observation_lease, monkeypatch
):
    from sqlalchemy import func, select, text, true

    from src.services.query_control_plane_service.app.application import (
        portfolio_source_observations as application,
    )
    from src.services.query_control_plane_service.app.contracts import (
        portfolio_source_observations as contracts,
    )
    from src.services.query_control_plane_service.app.infrastructure import (
        portfolio_source_observation_sources as sources,
    )

    lease = observation_lease
    cash = lease.cash()
    funding = FundingInvestmentObservation(
        replace(cash.envelope, source_record_id="funding"), None, False
    )
    for fact in (cash, funding):
        await lease.create(fact)
    request = contracts.PortfolioSourceObservationsRequest.model_validate(
        {
            "as_of_date": "2026-01-15",
            "cash": {
                "producer_id": "synthetic-source",
                "source_record_id": "cash",
                "latest_restated": True,
            },
            "funding_investment": {
                "producer_id": "synthetic-source",
                "source_record_id": "funding",
                "latest_restated": True,
            },
        }
    )
    original_statement = sources.observation_snapshot_statement
    # Test-only materialized CTE blocks INSIDE the production statement after its
    # MVCC snapshot exists; no mocked result or call-entry-only barrier.
    key = int(lease.schema[-7:], 16)

    def blocked_statement(**kwargs):
        statement = original_statement(**kwargs)
        barrier = select(func.pg_advisory_xact_lock(key)).cte("owned_snapshot_barrier")
        barrier = barrier.prefix_with("MATERIALIZED")
        return statement.select_from(statement.get_final_froms()[0].join(barrier, true()))

    monkeypatch.setattr(sources, "observation_snapshot_statement", blocked_statement)
    started = asyncio.Event()
    reader_pid = None

    async def query():
        nonlocal reader_pid
        async with lease.sessions() as session:
            reader_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            return await application.PortfolioSourceObservationsService(
                sources.SqlAlchemyPortfolioSourceObservationReader(session)
            ).query(tenant_id=lease.tenant, portfolio_id=lease.portfolio, request=request)

    task = None
    corrected = []
    try:
        async with lease.sessions.begin() as blocker:
            await blocker.execute(select(func.pg_advisory_xact_lock(key)))
            task = asyncio.create_task(query())
            await asyncio.wait_for(started.wait(), timeout=5)

            async def actual_lock_wait():
                async with lease.sessions() as observer:
                    while not await observer.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid "
                            "AND locktype='advisory' AND NOT granted)"
                        ),
                        {"pid": reader_pid},
                    ):
                        await asyncio.sleep(0.02)

            await asyncio.wait_for(actual_lock_wait(), timeout=5)
            assert not task.done()
            for fact in (cash, funding):
                envelope = replace(
                    fact.envelope,
                    source_revision=2,
                    source_cut_id="race-corrected",
                    predecessor_id=fact.content_hash,
                    expected_head_hash=fact.content_hash,
                )
                correction = (
                    replace(fact, envelope=envelope, available=Decimal("7"))
                    if fact is cash
                    else replace(fact, envelope=envelope, funded=False, invested=None)
                )
                await lease.create(correction)
                corrected.append(correction)
            assert not task.done()
        response = await asyncio.wait_for(task, timeout=5)
        assert response.cash.observation_id == cash.content_hash
        assert response.funding_investment.observation_id == funding.content_hash
        assert response.funding_investment.funded is None
        assert response.funding_investment.invested is False
        monkeypatch.setattr(sources, "observation_snapshot_statement", original_statement)
        async with lease.sessions() as session:
            after = await application.PortfolioSourceObservationsService(
                sources.SqlAlchemyPortfolioSourceObservationReader(session)
            ).query(tenant_id=lease.tenant, portfolio_id=lease.portfolio, request=request)
        assert after.cash.observation_id == corrected[0].content_hash
        assert after.funding_investment.observation_id == corrected[1].content_hash
        assert response.compatibility == after.compatibility == "UNAVAILABLE"
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_actual_completed_receipt_get_is_scoped_and_nonreplayable(
    observation_lease, monkeypatch
):
    from src.services.event_replay_service.app.main import app as operations_app
    from src.services.ingestion_service.app import ops_controls

    lease = observation_lease
    await _configure(lease, monkeypatch)
    completed = await lease.create(lease.cash())
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "synthetic-ops-proof")
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_only")
    route = f"/ingestion/jobs/{completed.job.job_id}"
    headers = _headers(lease.tenant, READ_CAP)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=operations_app), base_url="http://test"
    ) as client:
        denied = await client.get(route, headers=headers)
        assert denied.status_code == 401
        headers["X-Lotus-Ops-Token"] = "synthetic-ops-proof"
        response = await client.get(route, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed" and body["completed_at"] is not None
        assert not body["request_payload_replay_eligible"]
        assert body["retry_count"] == 0
        foreign = _headers("foreign", READ_CAP)
        foreign["X-Lotus-Ops-Token"] = "synthetic-ops-proof"
        refused = await client.get(route, headers=foreign)
        assert refused.status_code == 404, refused.text
    assert await lease.counts() == (1, 1, 1)


def _headers(tenant, capability, *, producer="synthetic-source"):
    headers = {
        "X-Actor-Id": "synthetic-operator",
        "X-Tenant-Id": tenant,
        "X-Role": "ops",
        "X-Correlation-Id": "synthetic-correlation",
        "X-Service-Identity": producer,
        "X-Capabilities": capability,
        "X-Enterprise-Auth-Key-Id": "synthetic-key",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        "synthetic-context-secret",
    )
    headers["X-Idempotency-Key"] = "synthetic-http-receipt"
    return headers


def _payload(fact):
    record = asdict(fact.envelope)
    record.pop("tenant_id")
    record["source_system"] = record.pop("producer_id")
    record["source_version"] = record.pop("source_revision")
    record.update(
        currency=fact.currency,
        settled_amount=str(fact.settled),
        encumbered_amount=None,
        available_amount=str(fact.available),
        content_hash=fact.content_hash,
    )
    # DTO serialization is the real HTTP contract, not a hand-built JSON encoder.
    from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
        CashAvailabilityObservationIngestionRequest,
    )

    return CashAvailabilityObservationIngestionRequest.model_validate(
        {"observations": [record]},
    ).model_dump(mode="json")


async def _configure(lease, monkeypatch, *, grants=True, funding=False):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "synthetic-key")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "synthetic-context-secret")

    async def sessions():
        async with lease.sessions() as session:
            yield session

    # Native operational policy reads use this same leased DB, not a shared provider.
    monkeypatch.setattr(jobs, "get_async_db_session", sessions)
    async with lease.sessions.begin() as session:
        if await session.get(IngestionOpsControl, 1) is None:
            session.add(IngestionOpsControl(id=1, mode="normal", updated_by="synthetic-proof"))
    fact = lease.cash()
    if funding:
        fact = FundingInvestmentObservation(
            replace(fact.envelope, source_record_id="funding"), None, False
        )
    grant = ProducerSubmissionGrant(
        lease.tenant, lease.portfolio, fact.envelope.producer_id, fact.family
    )

    def factory(stager):
        return jobs.IngestionJobService(
            job_store=SqlAlchemyIngestionJobStore(
                session_factory=sessions,
                fingerprint_key_id="synthetic-key",
                fingerprint_hmac_secret="synthetic-secret",
                fingerprint_previous_keys={},
                on_created=stager.stage,
            )
        )

    from src.services.ingestion_service.app.infrastructure import (
        ingestion_idempotency_replay_reader as replay_adapter,
    )

    class ReplayReader:
        async def find_matching_job(self, **kwargs):
            async with lease.sessions() as session:
                return await replay_adapter.SqlAlchemyIngestionIdempotencyReplayReader(
                    session, fingerprint_keyring={"synthetic-key": "synthetic-secret"}
                ).find_matching_job(**kwargs)

    commands = PortfolioSourceObservationCommands(
        UnqualifiedProducerAuthority((grant,) if grants else ()),
        factory,
        ReplayReader(),
    )
    monkeypatch.setitem(
        write_app.dependency_overrides, get_portfolio_source_observation_commands, lambda: commands
    )
    monkeypatch.setitem(read_app.dependency_overrides, get_async_db_session, sessions)
    return fact


def _funding_payload(fact):
    from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
        FundingInvestmentObservationIngestionRequest,
    )

    record = asdict(fact.envelope)
    record.pop("tenant_id")
    record["source_system"] = record.pop("producer_id")
    record["source_version"] = record.pop("source_revision")
    record.update(funded=fact.funded, invested=fact.invested, content_hash=fact.content_hash)
    return FundingInvestmentObservationIngestionRequest.model_validate(
        {"observations": [record]}
    ).model_dump(mode="json")


async def test_actual_funding_handlers_persist_nullable_flags_and_original_correction(
    observation_lease, monkeypatch
):
    lease = observation_lease
    original = await _configure(lease, monkeypatch, funding=True)
    correction = replace(
        original,
        funded=False,
        invested=None,
        envelope=replace(
            original.envelope,
            source_revision=2,
            source_cut_id="funding-corrected-cut",
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=write_app), base_url="http://test"
    ) as writer:
        for fact in (original, correction):
            headers = _headers(lease.tenant, FUNDING_CAP)
            headers["X-Idempotency-Key"] = f"funding-revision-{fact.envelope.source_revision}"
            response = await writer.post(
                "/ingest/portfolio-funding-investment-observations",
                headers=headers,
                json=_funding_payload(fact),
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "completed"
            replay = await writer.post(
                "/ingest/portfolio-funding-investment-observations",
                headers=headers,
                json=_funding_payload(fact),
            )
            assert replay.status_code == 200
            assert replay.json()["job_id"] == response.json()["job_id"]
        for tenant, capability in (("foreign", FUNDING_CAP), (lease.tenant, WRITE_CAP)):
            refused_fact = replace(original, envelope=replace(original.envelope, tenant_id=tenant))
            refused = await writer.post(
                "/ingest/portfolio-funding-investment-observations",
                headers=_headers(tenant, capability),
                json=_funding_payload(refused_fact),
            )
            assert refused.status_code == 403, refused.text
    # Fresh SQL sessions exercise reload; this is not a service-process restart.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=read_app), base_url="http://test"
    ) as reader:
        for fact in (original, correction):
            response = await reader.post(
                f"/integration/portfolios/{lease.portfolio}/financial-source-observations/query",
                headers=_headers(lease.tenant, READ_CAP),
                json={
                    "as_of_date": "2026-01-15",
                    "funding_investment": {
                        "producer_id": fact.envelope.producer_id,
                        "source_record_id": "funding",
                        "observation_id": fact.content_hash,
                        "content_hash": fact.content_hash,
                        "source_cut_id": fact.envelope.source_cut_id,
                        "source_version": fact.envelope.source_revision,
                    },
                },
            )
            assert response.status_code == 200, response.text
            evidence = response.json()["funding_investment"]
            assert evidence["observation_id"] == fact.content_hash
            assert evidence["funded"] is fact.funded
            assert evidence["invested"] is fact.invested
            assert evidence["qualification"] == "unqualified"
            assert response.json()["authoritative_state"] == "UNAVAILABLE"
    from portfolio_common.portfolio_source_observation_models import (
        FundingInvestmentObservationHead,
        FundingInvestmentObservationRow,
    )
    from sqlalchemy import func, select

    async with lease.sessions() as session:
        count = await session.scalar(
            select(func.count()).select_from(FundingInvestmentObservationRow)
        )
        assert count == 2
        heads = (await session.scalars(select(FundingInvestmentObservationHead))).all()
        assert len(heads) == 1 and heads[0].observation_id == correction.content_hash


async def test_actual_included_handlers_commit_receipt_and_keep_original_after_correction(
    observation_lease,
    monkeypatch,
):
    lease = observation_lease
    original = await _configure(lease, monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=write_app), base_url="http://test"
    ) as writer:
        response = await writer.post(
            "/ingest/portfolio-cash-availability-observations",
            headers=_headers(lease.tenant, WRITE_CAP),
            json=_payload(original),
        )
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["status"] == "completed" and receipt["completed_at"] is not None
        async with lease.sessions.begin() as session:
            control = await session.get(IngestionOpsControl, 1)
            control.mode = "paused"
        from unittest.mock import Mock

        from src.services.ingestion_service.app.services import (
            portfolio_source_observation_commands as command_module,
        )

        with monkeypatch.context() as replay_controls:
            exhausted_rate = Mock(side_effect=PermissionError("rate exhausted"))
            replay_controls.setattr(
                command_module, "enforce_ingestion_write_rate_limit", exhausted_rate
            )
            replay = await writer.post(
                "/ingest/portfolio-cash-availability-observations",
                headers=_headers(lease.tenant, WRITE_CAP),
                json=_payload(original),
            )
            exhausted_rate.assert_not_called()
        assert replay.status_code == 200 and replay.json()["job_id"] == receipt["job_id"]
        async with lease.sessions.begin() as session:
            control = await session.get(IngestionOpsControl, 1)
            control.mode = "normal"
    correction = replace(
        original,
        available=Decimal("3"),
        envelope=replace(
            original.envelope,
            source_revision=2,
            source_cut_id="corrected-cut",
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    await lease.create(correction)
    # New factory-owned session on each query: no cached original/head objects.
    route = f"/integration/portfolios/{lease.portfolio}/financial-source-observations/query"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=read_app), base_url="http://test"
    ) as reader:
        for fact in (original, correction):
            response = await reader.post(
                route,
                headers=_headers(lease.tenant, READ_CAP),
                json={
                    "as_of_date": "2026-01-15",
                    "cash": {
                        "producer_id": fact.envelope.producer_id,
                        "source_record_id": "cash",
                        "observation_id": fact.content_hash,
                        "content_hash": fact.content_hash,
                        "source_cut_id": fact.envelope.source_cut_id,
                        "source_version": fact.envelope.source_revision,
                    },
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["cash"]["observation_id"] == fact.content_hash
            assert Decimal(body["cash"]["available_amount"]) == fact.available
            assert body["cash"]["encumbered_amount"] is None
            assert body["cash"]["observed_at"][:10] > str(date(2026, 1, 15))
            assert body["authoritative_state"] == body["compatibility"] == "UNAVAILABLE"
            assert body["cash"]["qualification"] == "unqualified"
        latest = await reader.post(
            route,
            headers=_headers(lease.tenant, READ_CAP),
            json={
                "as_of_date": "2026-01-15",
                "cash": {
                    "producer_id": "synthetic-source",
                    "source_record_id": "cash",
                    "latest_restated": True,
                },
            },
        )
        assert latest.status_code == 200
        assert latest.json()["cash"]["latest_restated"] is True
        assert latest.json()["cash"]["observation_id"] == correction.content_hash
    assert await lease.counts() == (2, 2, 1)


@pytest.mark.parametrize(
    "failure",
    ["missing_cap", "read_cap", "wrong_family", "wrong_producer", "wrong_tenant", "default_grants"],
)
async def test_actual_write_admission_refusal_has_no_receipt_fact_or_head(
    observation_lease,
    monkeypatch,
    failure,
):
    lease = observation_lease
    fact = await _configure(lease, monkeypatch, grants=failure != "default_grants")
    capability = {
        "missing_cap": "",
        "read_cap": READ_CAP,
        "wrong_family": "ingestion.portfolio_funding_investment_observations.write",
    }.get(failure, WRITE_CAP)
    headers = _headers(
        "foreign" if failure == "wrong_tenant" else lease.tenant,
        capability,
        producer="foreign" if failure == "wrong_producer" else "synthetic-source",
    )
    # A foreign tenant fact has a valid hash for that tenant, so refusal is permission,
    # not accidental hash failure before the authority check.
    if failure == "wrong_tenant":
        fact = replace(fact, envelope=replace(fact.envelope, tenant_id="foreign"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=write_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/portfolio-cash-availability-observations", headers=headers, json=_payload(fact)
        )
    assert response.status_code == 403, response.text
    assert await lease.counts() == (0, 0, 0)
