from __future__ import annotations

from collections.abc import Sequence

from portfolio_common.domain.tenant import TenantContext

from ..ports.portfolio_tenant_ownership import PortfolioTenantOwnershipReader


class TransactionPortfolioOwnershipRejected(Exception):
    def __init__(self, portfolio_ids: Sequence[str]) -> None:
        self.portfolio_ids = tuple(portfolio_ids)
        super().__init__("Transaction portfolios are not owned by the admitted tenant.")


class ValidateTransactionPortfolioOwnership:
    """Fail closed before publishing transactions outside admitted tenant authority."""

    def __init__(self, reader: PortfolioTenantOwnershipReader) -> None:
        self._reader = reader

    async def execute(
        self,
        *,
        tenant_context: TenantContext,
        portfolio_ids: Sequence[str],
    ) -> None:
        required_ids = tuple(dict.fromkeys(portfolio_id.strip() for portfolio_id in portfolio_ids))
        owned_ids = await self._reader.read_owned_portfolio_ids(
            tenant_id=tenant_context.tenant_id_text,
            portfolio_ids=required_ids,
        )
        rejected_ids = tuple(
            portfolio_id for portfolio_id in required_ids if portfolio_id not in owned_ids
        )
        if rejected_ids:
            raise TransactionPortfolioOwnershipRejected(rejected_ids)
