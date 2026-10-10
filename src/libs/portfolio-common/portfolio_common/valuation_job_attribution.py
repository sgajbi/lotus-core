"""Qualify valuation scheduling against exact, source-owned portfolio roots."""

from dataclasses import fields

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import Portfolio
from .domain.tenant import TenantId
from .infrastructure.persistence.statement_batching import iter_statement_chunks
from .valuation_job_contracts import AttributedValuationJobUpsert, ValuationJobUpsert


async def attribute_valuation_jobs(
    db: AsyncSession, jobs: list[ValuationJobUpsert]
) -> list[AttributedValuationJobUpsert]:
    """Bind global fan-out requests to owners without normalizing portfolio identities.

    Root locks keep owner attribution stable until the caller's job transaction commits.
    A missing or conflicting root refuses the entire batch before any job is staged.
    """

    owners: dict[str, TenantId] = {}
    for portfolio_ids in iter_statement_chunks(
        sorted({job.portfolio_id for job in jobs}), binds_per_row=1
    ):
        result = await db.execute(
            select(Portfolio.portfolio_id, Portfolio.tenant_id)
            .where(Portfolio.portfolio_id.in_(portfolio_ids))
            .order_by(Portfolio.portfolio_id)
            .with_for_update(read=True, key_share=True)
        )
        for portfolio_id, tenant_text in result.all():
            tenant_id = TenantId(tenant_text)
            if tenant_id.value != tenant_text:
                raise ValueError("valuation scheduling requires canonical persisted ownership")
            if portfolio_id in owners and owners[portfolio_id] != tenant_id:
                raise ValueError("valuation scheduling found ambiguous portfolio ownership")
            owners[portfolio_id] = tenant_id
    if any(job.portfolio_id not in owners for job in jobs):
        raise ValueError("valuation scheduling requires an authoritative portfolio owner")
    if any(
        isinstance(job, AttributedValuationJobUpsert) and job.tenant_id != owners[job.portfolio_id]
        for job in jobs
    ):
        raise ValueError("valuation scheduling tenant conflicts with persisted ownership")
    return [
        AttributedValuationJobUpsert(
            **{field.name: getattr(job, field.name) for field in fields(ValuationJobUpsert)},
            tenant_id=owners[job.portfolio_id],
        )
        for job in jobs
    ]
