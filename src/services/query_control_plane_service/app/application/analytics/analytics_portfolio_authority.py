"""Tenant-owned portfolio authority for analytics input orchestration."""

from ...domain.analytics import PortfolioAnalyticsSource
from ...ports.analytics import AnalyticsTimeseriesReader
from .analytics_errors import AnalyticsInputError


async def require_owned_portfolio(
    reader: AnalyticsTimeseriesReader,
    tenant_id: str,
    portfolio_id: str,
) -> PortfolioAnalyticsSource:
    portfolio = await reader.get_portfolio(tenant_id=tenant_id, portfolio_id=portfolio_id)
    if portfolio is None:
        raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
    return portfolio
