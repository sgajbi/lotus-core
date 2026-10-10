"""Source-root attribution and typed recovery admission for valuation work."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.tenant import TenantId
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.valuation_job_attribution import attribute_valuation_jobs
from portfolio_common.valuation_job_contracts import (
    AttributedValuationJobUpsert,
    ValuationJobClaim,
    ValuationJobUpsert,
)
from portfolio_common.valuation_repository_base import ValuationRepositoryBase
from sqlalchemy.dialects.postgresql import dialect


def _request(portfolio_id: str) -> ValuationJobUpsert:
    return ValuationJobUpsert(portfolio_id, "SEC", date(2026, 10, 9), 2)


def _database(rows: list[tuple[str, str]]) -> AsyncMock:
    database = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    database.execute.return_value = result
    return database


@pytest.mark.asyncio
@pytest.mark.parametrize("retained_job_id, expected", [(7, True), (None, False)])
async def test_claim_admission_checks_exact_authority_without_blocking_corrections(
    retained_job_id, expected
) -> None:
    database = _database([])
    database.execute.return_value.scalar_one_or_none.return_value = retained_job_id
    assert (
        await ValuationRepositoryBase(database).owns_valuation_claim(
            tenant_id=TenantId("tenant-a"),
            portfolio_id=" PORT ",
            security_id=" SEC ",
            valuation_date=date(2026, 10, 9),
            epoch=2,
            claim_token="a" * 32,
        )
        is expected
    )
    compiled = database.execute.await_args.args[0].compile(dialect=dialect())
    assert compiled.params["tenant_id_1"] == "tenant-a"
    assert compiled.params["portfolio_id_1"] == " PORT "
    assert compiled.params["security_id_1"] == " SEC "
    assert compiled.params["valuation_claim_token_1"] == "a" * 32
    assert "clock_timestamp()" in str(compiled)
    assert "FOR UPDATE" not in str(compiled)
    assert "trim(" not in str(compiled)


@pytest.mark.asyncio
async def test_exact_portfolio_roots_attribute_distinct_whitespace_identifiers() -> None:
    database = _database([("PORT", "tenant-a"), (" PORT ", "tenant-b")])
    attributed = await attribute_valuation_jobs(database, [_request("PORT"), _request(" PORT ")])
    assert [(job.portfolio_id, job.tenant_id) for job in attributed] == [
        ("PORT", TenantId("tenant-a")),
        (" PORT ", TenantId("tenant-b")),
    ]
    statement = str(database.execute.await_args.args[0].compile(dialect=dialect()))
    assert "FOR KEY SHARE" in statement
    assert "trim(" not in statement


@pytest.mark.asyncio
async def test_one_orphan_refuses_whole_staging_batch() -> None:
    database = _database([("PORT", "tenant-a")])
    with pytest.raises(ValueError, match="authoritative portfolio owner"):
        await attribute_valuation_jobs(database, [_request("PORT"), _request("MISSING")])
    assert database.execute.await_count == 1
    assert "INSERT" not in str(database.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_conflicting_retained_roots_refuse_attribution() -> None:
    with pytest.raises(ValueError, match="ambiguous portfolio ownership"):
        await attribute_valuation_jobs(
            _database([("PORT", "tenant-a"), ("PORT", "tenant-b")]), [_request("PORT")]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", [" tenant-a ", "\u00a0tenant-a", "", None])
async def test_invalid_retained_tenant_is_never_repaired_by_scheduling(tenant) -> None:
    with pytest.raises((ValueError, TypeError)):
        await attribute_valuation_jobs(_database([("PORT", tenant)]), [_request("PORT")])


@pytest.mark.asyncio
async def test_empty_batch_does_not_read_or_write() -> None:
    database = _database([])
    assert await attribute_valuation_jobs(database, []) == []
    database.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_conflicting_attributed_request_is_refused_rather_than_rewritten() -> None:
    database = _database([("PORT", "tenant-a")])
    request = AttributedValuationJobUpsert(
        "PORT", "SEC", date(2026, 10, 9), 2, tenant_id=TenantId("tenant-b")
    )
    with pytest.raises(ValueError, match="conflicts with persisted ownership"):
        await attribute_valuation_jobs(database, [request])


@pytest.mark.parametrize("tenant", [None, "tenant-a", {"value": "tenant-a"}])
def test_recovery_claim_requires_canonical_typed_authority(tenant) -> None:
    with pytest.raises(TypeError, match="TenantId"):
        ValuationJobClaim(tenant, 1, "a" * 32)


@pytest.mark.parametrize("token", ["", "a" * 31, "A" * 32, "g" * 32])
def test_recovery_claim_refuses_malformed_lease_token(token: str) -> None:
    with pytest.raises(ValueError, match="hexadecimal"):
        ValuationJobClaim(TenantId("tenant-a"), 1, token)


@pytest.mark.parametrize("job_id", [0, -1, "1", True])
def test_recovery_claim_refuses_invalid_durable_job_id(job_id) -> None:
    with pytest.raises(ValueError, match="positive"):
        ValuationJobClaim(TenantId("tenant-a"), job_id, "a" * 32)


@pytest.mark.parametrize("tenant", [None, "", "\u00a0\t"])
def test_dispatch_event_requires_retained_tenant_authority(tenant) -> None:
    payload = dict(portfolio_id="PORT", security_id="SEC", valuation_date="2026-10-09", epoch=2)
    if tenant is not None:
        payload["tenant_id"] = tenant
    with pytest.raises(ValueError):
        PortfolioValuationRequiredEvent.model_validate(payload)
    event = PortfolioValuationRequiredEvent.model_validate({**payload, "tenant_id": "tenant-a"})
    assert event.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_conflicting_recovery_receipts_refuse_before_database_access() -> None:
    database = _database([])
    with pytest.raises(ValueError, match="conflicting valuation claim tokens"):
        await ValuationRepositoryBase(database).recover_dispatch_failed_jobs(
            [
                ValuationJobClaim(TenantId("tenant-a"), 1, "a" * 32),
                ValuationJobClaim(TenantId("tenant-a"), 1, "b" * 32),
            ],
            max_attempts=3,
            failure_reason="transport-failed",
        )
    database.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_financial_reads_require_typed_owner_before_database_access() -> None:
    database = _database([])
    repository = ValuationRepositoryBase(database)
    with pytest.raises(TypeError, match="TenantId"):
        await repository.get_portfolio("PORT", tenant_id="tenant-a")
    with pytest.raises(TypeError, match="TenantId"):
        await repository.get_last_position_history_before_date(
            "PORT", "SEC", date(2026, 10, 9), 2, tenant_id="tenant-a"
        )
    database.execute.assert_not_awaited()
