"""Real PostgreSQL ownership, collision and replay controls for valuation jobs."""

import asyncio
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    Transaction,
)
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_async_database_engine
from portfolio_common.domain.tenant import TenantId
from portfolio_common.valuation_job_contracts import (
    ValuationJobClaim,
    ValuationJobTransitionOutcome,
)
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.valuation_repository_base import ValuationRepositoryBase
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
DAY = date(2026, 10, 9)
OWNERS = (("VALUATION_OWNER", "tenant-a"), (" VALUATION_OWNER ", "tenant-b"))


@pytest_asyncio.fixture
async def tenant_sessions(db_engine, clean_db):
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=db_engine.url.render_as_string(hide_password=False).replace(
            "postgresql://", "postgresql+asyncpg://"
        ),
        pool_mode=DatabasePoolMode.NULL,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        session.add_all(
            [
                Portfolio(
                    tenant_id=tenant,
                    portfolio_id=portfolio,
                    base_currency="USD",
                    open_date=DAY,
                    risk_exposure="balanced",
                    investment_time_horizon="long",
                    portfolio_type="advisory",
                    booking_center_code="SG",
                    client_id=f"client-{tenant}",
                    status="ACTIVE",
                )
                for portfolio, tenant in OWNERS
            ]
        )
    yield factory
    await engine.dispose()


async def _stage(session, portfolio: str, epoch: int = 1, **controls):
    return await ValuationJobRepository(session).upsert_job(
        portfolio_id=portfolio,
        security_id="SEC",
        valuation_date=DAY,
        epoch=epoch,
        correlation_id="same-transport-correlation",
        **controls,
    )


async def _terminal(repository, job, tenant: str, token: str):
    return await repository.update_job_status(
        job.portfolio_id,
        job.security_id,
        job.valuation_date,
        job.epoch,
        "COMPLETE",
        tenant_id=TenantId(tenant),
        expected_claim_token=token,
    )


async def test_staging_derives_exact_owners_and_never_cross_supersedes(tenant_sessions):
    async with tenant_sessions.begin() as session:
        for portfolio, _tenant in OWNERS:
            assert await _stage(session, portfolio) == 1
            assert await _stage(session, portfolio) == 0
        assert await _stage(session, OWNERS[0][0], epoch=3) == 1
    async with tenant_sessions() as session:
        jobs = (await session.execute(select(PortfolioValuationJob))).scalars().all()
        assert {(job.tenant_id, job.portfolio_id, job.epoch, job.status) for job in jobs} == {
            ("tenant-a", OWNERS[0][0], 1, "SKIPPED_SUPERSEDED"),
            ("tenant-a", OWNERS[0][0], 3, "PENDING"),
            ("tenant-b", OWNERS[1][0], 1, "PENDING"),
        }
    async with tenant_sessions() as session:
        with pytest.raises(ValueError, match="authoritative portfolio owner"):
            async with session.begin():
                await _stage(session, "VALUATION_OWNER  ")
    async with tenant_sessions() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    PortfolioValuationJob(
                        tenant_id="tenant-b",
                        portfolio_id=OWNERS[0][0],
                        security_id="FOREIGN",
                        valuation_date=DAY,
                        epoch=1,
                    )
                )
                await session.flush()


async def test_owned_claim_terminal_recovery_and_stale_replay(tenant_sessions):
    async with tenant_sessions.begin() as session:
        for portfolio, _tenant in OWNERS:
            await _stage(session, portfolio)
        jobs = await ValuationRepositoryBase(session).find_and_claim_eligible_jobs(
            2, lease_owner="tenant-proof", lease_duration_seconds=900
        )
        assert {(job.tenant_id, job.portfolio_id) for job in jobs} == {
            (tenant, portfolio) for portfolio, tenant in OWNERS
        }
    owner_a = next(job for job in jobs if job.tenant_id == "tenant-a")
    owner_b = next(job for job in jobs if job.tenant_id == "tenant-b")
    async with tenant_sessions.begin() as session:
        repository = ValuationRepositoryBase(session)
        assert not await repository.owns_valuation_claim(
            tenant_id=TenantId("tenant-b"),
            portfolio_id=owner_a.portfolio_id,
            security_id="SEC",
            valuation_date=DAY,
            epoch=1,
            claim_token=owner_a.valuation_claim_token,
        )
        assert await _terminal(repository, owner_a, "tenant-b", owner_a.valuation_claim_token) == (
            ValuationJobTransitionOutcome.NOT_OWNED
        )
        assert await repository.recover_dispatch_failed_jobs(
            [ValuationJobClaim(TenantId("tenant-b"), owner_a.id, owner_a.valuation_claim_token)],
            max_attempts=3,
            failure_reason="foreign-recovery",
        ) == {"pending_count": 0, "failed_count": 0}
        assert await _terminal(repository, owner_a, "tenant-a", owner_a.valuation_claim_token) == (
            ValuationJobTransitionOutcome.TERMINAL_APPLIED
        )
        assert await _terminal(repository, owner_a, "tenant-a", owner_a.valuation_claim_token) == (
            ValuationJobTransitionOutcome.NOT_OWNED
        )
        await session.execute(
            text(
                "UPDATE portfolio_valuation_jobs SET valuation_lease_expires_at = "
                "clock_timestamp() - interval '1 second' WHERE tenant_id = :tenant AND id = :id"
            ),
            {"tenant": "tenant-b", "id": owner_b.id},
        )
    async with tenant_sessions.begin() as session:
        repository = ValuationRepositoryBase(session)
        assert await repository.find_and_reset_stale_jobs(max_attempts=3) == 1
        reclaimed = await repository.find_and_claim_eligible_jobs(2, lease_owner="reclaimed")
        assert len(reclaimed) == 1
        current = reclaimed[0]
        assert current.id == owner_b.id and current.tenant_id == "tenant-b"
        assert current.valuation_claim_token != owner_b.valuation_claim_token
        assert await _terminal(repository, owner_b, "tenant-b", owner_b.valuation_claim_token) == (
            ValuationJobTransitionOutcome.NOT_OWNED
        )
        assert await _terminal(repository, current, "tenant-b", current.valuation_claim_token) == (
            ValuationJobTransitionOutcome.TERMINAL_APPLIED
        )


async def test_concurrent_claims_retain_disjoint_owner_authority(tenant_sessions):
    async with tenant_sessions.begin() as session:
        for portfolio, _tenant in OWNERS:
            await _stage(session, portfolio)

    async def claim(owner):
        async with tenant_sessions.begin() as session:
            jobs = await ValuationRepositoryBase(session).find_and_claim_eligible_jobs(
                1, lease_owner=owner
            )
            return [(job.id, job.tenant_id, job.valuation_claim_token) for job in jobs]

    claimed = await asyncio.gather(claim("runner-a"), claim("runner-b"))
    receipts = [receipt for cohort in claimed for receipt in cohort]
    assert len(receipts) == 2
    assert len({receipt[0] for receipt in receipts}) == 2
    assert {receipt[1] for receipt in receipts} == {"tenant-a", "tenant-b"}


async def test_worker_reads_preserve_exact_portfolio_owner_and_holdings(tenant_sessions):
    quantities = {"tenant-a": Decimal("10"), "tenant-b": Decimal("30")}
    async with tenant_sessions.begin() as session:
        for portfolio, tenant in OWNERS:
            session.add(
                Transaction(
                    transaction_id=f"TX-{tenant}",
                    portfolio_id=portfolio,
                    instrument_id="I-SEC",
                    security_id="SEC",
                    transaction_date=DAY,
                    transaction_type="BUY",
                    quantity=quantities[tenant],
                    price=100,
                    gross_transaction_amount=quantities[tenant] * 100,
                    trade_currency="USD",
                    currency="USD",
                )
            )
        await session.flush()
        for portfolio, tenant in OWNERS:
            session.add(
                PositionHistory(
                    transaction_id=f"TX-{tenant}",
                    portfolio_id=portfolio,
                    security_id="SEC",
                    position_date=DAY,
                    epoch=1,
                    quantity=quantities[tenant],
                    cost_basis=quantities[tenant] * 100,
                    cost_basis_local=quantities[tenant] * 100,
                )
            )
    async with tenant_sessions() as session:
        repository = ValuationRepositoryBase(session)
        for portfolio, tenant in OWNERS:
            owner = TenantId(tenant)
            selected_root = await repository.get_portfolio(portfolio, tenant_id=owner)
            assert selected_root.portfolio_id == portfolio
            assert selected_root.tenant_id == tenant
            selected = await repository.get_last_position_history_before_date(
                portfolio, "SEC", DAY, 1, tenant_id=owner
            )
            assert selected.portfolio_id == portfolio
            assert selected.quantity == quantities[tenant]
            assert selected.cost_basis == quantities[tenant] * 100
            foreign = TenantId("tenant-b" if tenant == "tenant-a" else "tenant-a")
            assert await repository.get_portfolio(portfolio, tenant_id=foreign) is None
            assert (
                await repository.get_last_position_history_before_date(
                    portfolio, "SEC", DAY, 1, tenant_id=foreign
                )
                is None
            )
