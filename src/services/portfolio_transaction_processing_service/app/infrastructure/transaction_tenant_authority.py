"""Resolve transaction tenant authority from the durable portfolio root."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from portfolio_common.database_models import Portfolio
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.transaction_tenant_authority import (
    TransactionTenantAuthorityMismatch,
    TransactionTenantAuthorityUnavailable,
)


class SqlAlchemyTransactionTenantAuthority:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(
        self,
        *,
        portfolio_id: str,
        asserted_tenant_id: str | None,
    ) -> str:
        async with self._session_factory() as session:
            source_tenant_id = (
                await session.execute(
                    select(Portfolio.tenant_id).where(Portfolio.portfolio_id == portfolio_id)
                )
            ).scalar_one_or_none()
        if source_tenant_id is None:
            raise TransactionTenantAuthorityUnavailable(
                f"Portfolio {portfolio_id!r} has no durable tenant authority"
            )
        resolved_tenant_id = TenantId(source_tenant_id).value
        if (
            asserted_tenant_id is not None
            and TenantId(asserted_tenant_id).value != resolved_tenant_id
        ):
            raise TransactionTenantAuthorityMismatch(
                f"Transaction tenant does not own portfolio {portfolio_id!r}"
            )
        return cast(str, resolved_tenant_id)
