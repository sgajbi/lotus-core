"""Synthetic receipt authority across native TCP HTTP and distinct OS processes."""

import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from portfolio_common.database_models import IngestionOpsControl

from scripts.development.repository_python import repository_environment
from tests.integration.services.ingestion_service import (
    test_portfolio_source_verification_postgresql as verification,
)
from tests.integration.services.query_control_plane_service import (
    test_portfolio_source_observation_router_postgresql as routes,
)

observation_schema = routes.observation_schema
preverification_observation_schema = routes.preverification_observation_schema
observation_lease = routes.observation_lease
pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


@asynccontextmanager
async def http_generation(lease, environment):
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.test_support.portfolio_source_http_process"],
        env=repository_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        process.stdin.write(
            json.dumps(
                {
                    "database_url": lease.sessions.kw["bind"].url.render_as_string(
                        hide_password=False
                    ),
                    "schema": lease.schema,
                    "tenant": lease.tenant,
                    "portfolio": lease.portfolio,
                    "environment": environment,
                }
            )
            + "\n"
        )
        process.stdin.flush()
        line = await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), timeout=30)
        # Never publish connection, trust configuration or request payload on failure.
        assert line.startswith("OWNED_HTTP="), "native HTTP process did not report readiness"
        identity = json.loads(line.removeprefix("OWNED_HTTP="))
        assert identity["pid"] == process.pid
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{identity['port']}", timeout=10, trust_env=False
        ) as client:
            yield client, identity["pid"]
        process.stdin.write("stop\n")
        process.stdin.flush()
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=15)
        assert process.returncode == 0, "native HTTP process failed during shutdown"
    finally:
        if process.poll() is None:
            process.terminate()
            await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        assert process.poll() is not None


def deployment(facts):
    keys, cuts, signed = [], [], []
    for fact in facts:
        authority, receipt, key = verification.registered(fact)
        keys.append(
            {
                "issuer_id": key.issuer_id,
                "key_id": key.key_id,
                "scope": key.scope.model_dump(mode="json"),
                "valid_from": key.valid_from.isoformat(),
                "valid_to": key.valid_to.isoformat(),
                "secret_env": "LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_SYNTHETIC_HTTP",
            }
        )
        cuts.append(
            {
                "scope": authority.cuts[0].scope.model_dump(mode="json"),
                "source_cut_id": fact.envelope.source_cut_id,
                "manifest_hash": authority.cuts[0].manifest_hash,
            }
        )
        signed.append(receipt.model_dump(mode="json"))
    # Original and correction use one identical key scope; only the cuts differ.
    environment = {
        "ENTERPRISE_ENFORCE_AUTHZ": "true",
        "ENTERPRISE_PRIMARY_KEY_ID": "synthetic-key",
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET": "synthetic-context-secret",
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS": json.dumps(keys[:1]),
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS": json.dumps(cuts),
        "LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_SYNTHETIC_HTTP": verification.SECRET,
    }
    return environment, signed


async def test_registered_receipt_http_restart_keeps_original_and_corrected_pins(observation_lease):
    lease = observation_lease
    original = lease.cash()
    correction = replace(
        original,
        available=Decimal("3"),
        envelope=replace(
            original.envelope,
            source_revision=2,
            source_cut_id="corrected-http-cut",
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    environment, signed = deployment((original, correction))
    async with lease.sessions.begin() as session:
        session.add(IngestionOpsControl(id=1, mode="normal", updated_by="synthetic-http-proof"))
    query = f"/integration/portfolios/{lease.portfolio}/financial-source-observations/query"

    async def read(client, fact, *, tenant=None, consumer=verification.CONSUMER):
        response = await client.post(
            query,
            headers=routes._headers(tenant or lease.tenant, routes.READ_CAP, producer=consumer),
            json={"as_of_date": "2026-03-01", "cash": routes._pin(fact)},
        )
        assert response.status_code == 200
        return response.json()

    async with http_generation(lease, environment) as (client, first_pid):
        before = []
        for index, fact in enumerate((original, correction)):
            payload = routes._payload(fact)
            payload["observations"][0]["verification_receipt"] = signed[index]
            headers = routes._headers(lease.tenant, routes.WRITE_CAP)
            headers["X-Idempotency-Key"] = f"synthetic-receipt-http-{index}"
            response = await client.post(
                "/ingest/portfolio-cash-availability-observations", headers=headers, json=payload
            )
            assert response.status_code == 200
            assert response.json()["status"] == "completed"
            before.append(await read(client, fact))
        # Original pins stay readable after a supported correction in the same process.
        assert (await read(client, original))["cash"] == before[0]["cash"]
    async with http_generation(lease, environment) as (client, second_pid):
        assert len({os.getpid(), first_pid, second_pid}) == 3
        for index, fact in enumerate((original, correction)):
            result = await read(client, fact)
            assert result["cash"] == before[index]["cash"]
            assert result["cash"]["verification_receipt"] == signed[index]
            assert result["fact_verification_status"] == "FACT_VERIFIED"
            assert result["authoritative_state"] == result["compatibility"] == "UNAVAILABLE"
            foreign = await read(client, fact, consumer="foreign-consumer")
            # Legacy HTTP omits unverified extension fields rather than adding defaults.
            assert "fact_verification_status" not in foreign
            assert "verification_receipt" not in foreign["cash"]
            assert foreign["cash"]["content_hash"] == fact.content_hash
        foreign = await read(client, original, tenant="foreign-tenant")
        assert foreign["cash"] is None and "fact_verification_status" not in foreign
    keys = json.loads(environment["LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS"])
    keys[0]["revoked_at"] = datetime.now(UTC).isoformat()
    environment["LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS"] = json.dumps(keys)
    async with http_generation(lease, environment) as (client, revoked_pid):
        for index, fact in enumerate((original, correction)):
            refused = await read(client, fact)
            assert "fact_verification_status" not in refused
            assert "verification_receipt" not in refused["cash"]
            economic = dict(before[index]["cash"])
            economic.pop("verification_receipt")
            assert refused["cash"] == economic
    environment["LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS"] = "[]"
    environment["LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS"] = "[]"
    async with http_generation(lease, environment) as (client, unconfigured_pid):
        for index, fact in enumerate((original, correction)):
            unavailable = await read(client, fact)
            assert "fact_verification_status" not in unavailable
            economic = dict(before[index]["cash"])
            economic.pop("verification_receipt")
            assert unavailable["cash"] == economic
    pids = (first_pid, second_pid, revoked_pid, unconfigured_pid)
    assert len({os.getpid(), *pids}) == 5
    print(f"receipt HTTP generations={pids}; all exited=0")
