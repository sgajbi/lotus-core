"""Bind portfolio ingestion records to admitted tenant authority."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from portfolio_common.domain.tenant import TenantContext, bind_tenant_authority


class TenantOwnedPortfolio(Protocol):
    tenant_id: str


def bind_portfolio_tenant_authority(
    portfolios: Iterable[TenantOwnedPortfolio],
    tenant_context: TenantContext,
) -> None:
    """Validate the whole batch before stamping the admitted canonical identifier."""

    records = tuple(portfolios)
    admitted_tenant_ids = tuple(
        bind_tenant_authority(portfolio.tenant_id, tenant_context) for portfolio in records
    )
    for portfolio, admitted_tenant_id in zip(records, admitted_tenant_ids, strict=True):
        portfolio.tenant_id = admitted_tenant_id
