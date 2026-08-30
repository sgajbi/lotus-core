from typing import Any


async def ensure_portfolio_exists(
    *,
    repository: Any,
    portfolio_id: str,
) -> None:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")


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
