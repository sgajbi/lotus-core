"""Synthetic authority controls through real owning PostgreSQL/UOW/read adapters."""

import hashlib
import hmac
import runpy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.api_contract.portfolio_source_verification import (
    ObservationVerificationClaims,
    ObservationVerificationScope,
    ObservationVerificationSubject,
    SignedObservationVerificationReceipt,
)
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAdmission,
)
from portfolio_common.portfolio_source_observation_verification import (
    ObservationCutRegistration,
    ObservationReceiptVerifier,
    ObservationVerificationAuthority,
    ObservationVerificationKey,
    observation_verification_claims_bytes,
)
from portfolio_common.portfolio_source_verification_store import PortfolioSourceVerificationStore
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.services.ingestion_service.app.infrastructure import (
    portfolio_source_observation_unit_of_work as observation_uow,
)
from src.services.query_control_plane_service.app.application.portfolio_source_observations import (
    PortfolioSourceObservationsService,
)
from src.services.query_control_plane_service.app.contracts.portfolio_source_observations import (
    ObservationSelector,
    PortfolioSourceObservationsRequest,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_source_observation_sources as source_reader,
)
from tests.integration.services.ingestion_service import (
    test_portfolio_source_observation_admission_postgresql as lease_support,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
CONSUMER = "synthetic-manage-consumer"
SECRET = "synthetic-pg-only-key-not-provider-qualification"
observation_lease = lease_support.observation_lease
observation_schema = lease_support.observation_schema


def migration(connection):
    module = runpy.run_path(
        str(
            Path(__file__).resolve().parents[4]
            / "alembic/versions/c181b2c3d542_add_portfolio_source_fact_verifications.py"
        )
    )
    assert module["down_revision"] == "c179b2c3d540"
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def apply_migration(owned, operation="upgrade"):
    engine, _, schema, _ = owned
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        migration(connection)[operation]()


def registered(fact):
    now = datetime.now(UTC)
    subject = ObservationVerificationSubject.from_observation(
        fact, source_cut_manifest_hash="a" * 64, consumer_id=CONSUMER, as_of_date=date(2026, 3, 1)
    )
    scope = ObservationVerificationScope.from_subject(subject)
    key = ObservationVerificationKey(
        "synthetic-verifier",
        "key-v1",
        scope,
        now - timedelta(days=1),
        now + timedelta(days=1),
        SECRET,
    )
    authority = ObservationVerificationAuthority(
        ObservationReceiptVerifier((key,)),
        (ObservationCutRegistration(scope, fact.envelope.source_cut_id, "a" * 64),),
    )
    claims = ObservationVerificationClaims(
        issuer_id=key.issuer_id,
        key_id=key.key_id,
        artifact_revision="synthetic-v1",
        subject=subject,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    receipt = SignedObservationVerificationReceipt(
        claims=claims,
        signature=hmac.new(
            SECRET.encode(), observation_verification_claims_bytes(claims), hashlib.sha256
        ).hexdigest(),
    )
    return authority, receipt, key


def stager(fact, authority, receipt):
    admission = UnqualifiedProducerAdmission(
        ProducerSubmissionGrant(
            fact.envelope.tenant_id,
            fact.envelope.portfolio_id,
            fact.envelope.producer_id,
            fact.family,
        )
    )
    return observation_uow.PortfolioSourceObservationStager(
        (fact,), (admission,), (receipt,), authority
    )


async def test_native_atomic_receipt_restart_projection_and_current_revocation(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    fact = lease.cash()
    authority, signed, key = registered(fact)
    await lease.create(fact, callback=stager(fact, authority, signed).stage)
    # A new session rehydrates durable original facts and receipts, not an in-memory wrapper.
    request = PortfolioSourceObservationsRequest(
        as_of_date=date(2026, 3, 1),
        cash=ObservationSelector(
            producer_id=fact.envelope.producer_id,
            source_record_id=fact.envelope.source_record_id,
            observation_id=fact.content_hash,
            content_hash=fact.content_hash,
            source_cut_id=fact.envelope.source_cut_id,
            source_version=1,
        ),
    )
    async with lease.sessions() as session:
        stored = await PortfolioSourceVerificationStore(session).receipts(
            fact, consumer_id=CONSUMER
        )
        assert stored == (signed,)
        service = PortfolioSourceObservationsService(
            source_reader.SqlAlchemyPortfolioSourceObservationReader(session), authority
        )
        result = await service.query(
            tenant_id=lease.tenant,
            portfolio_id=lease.portfolio,
            request=request,
            consumer_id=CONSUMER,
        )
        assert result.fact_verification_status == "FACT_VERIFIED"
        assert result.cash.verification_receipt == signed
        assert result.cash.content_hash == fact.content_hash
        assert (
            result.cash.source_version == 1
            and result.cash.source_cut_id == fact.envelope.source_cut_id
        )
        assert result.cash.qualification == "unqualified"
        revoked = ObservationVerificationAuthority(
            ObservationReceiptVerifier((replace(key, revoked_at=datetime.now(UTC)),)),
            authority.cuts,
        )
        service.verification_authority = revoked
        result = await service.query(
            tenant_id=lease.tenant,
            portfolio_id=lease.portfolio,
            request=request,
            consumer_id=CONSUMER,
        )
        assert (
            result.fact_verification_status == "UNAVAILABLE"
            and result.cash.verification_receipt is None
        )
    for operation in (
        "UPDATE portfolio_source_fact_verifications SET consumer_id='other'",
        "DELETE FROM portfolio_source_fact_verifications",
        "TRUNCATE portfolio_source_fact_verifications",
    ):
        async with lease.sessions() as session:
            with pytest.raises(DBAPIError):
                await session.execute(text(operation))
            await session.rollback()
    with pytest.raises(DBAPIError):
        apply_migration(observation_schema, "downgrade")


async def test_invalid_attestation_rolls_back_native_job_fact_and_head(
    observation_lease, observation_schema
):
    lease = observation_lease
    apply_migration(observation_schema)
    fact = lease.cash()
    authority, signed, _ = registered(fact)
    before = await lease.counts()
    forged = signed.model_copy(update={"signature": "0" * 64})
    with pytest.raises(ObservationConflict, match="SIGNATURE_INVALID"):
        await lease.create(fact, callback=stager(fact, authority, forged).stage)
    assert await lease.counts() == before
    async with lease.sessions() as session:
        assert (
            await session.scalar(text("SELECT count(*) FROM portfolio_source_fact_verifications"))
            == 0
        )


async def test_empty_downgrade_upgrade_preserves_existing_unqualified_fact(
    observation_lease, observation_schema
):
    lease = observation_lease
    fact = lease.cash()
    await lease.create(fact)
    before = await lease.counts()
    apply_migration(observation_schema)
    apply_migration(observation_schema, "downgrade")
    apply_migration(observation_schema)
    assert await lease.counts() == before
    async with lease.sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT content_hash, source_revision, source_cut_id, qualification "
                    "FROM portfolio_cash_availability_observations"
                )
            )
        ).one()
        assert tuple(row) == (fact.content_hash, 1, fact.envelope.source_cut_id, "unqualified")
