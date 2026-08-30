from typing import Any


async def ensure_portfolio_owned(
    *,
    repository: Any,
    tenant_id: str,
    portfolio_id: str,
) -> None:
    """Fail closed unless the portfolio belongs to the admitted tenant."""

    if not await repository.portfolio_exists(
        tenant_id=tenant_id,
        portfolio_id=portfolio_id,
    ):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")


async def get_owned_portfolio(
    *,
    repository: Any,
    tenant_id: str,
    portfolio_id: str,
) -> Any:
    """Return a tenant-owned portfolio without exposing foreign ownership."""

    portfolio = await repository.get_portfolio_by_id(
        tenant_id=tenant_id,
        portfolio_id=portfolio_id,
    )
    if portfolio is None:
        raise LookupError(f"Portfolio with id {portfolio_id} not found")
    return portfolio
