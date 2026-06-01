from typing import Any


async def ensure_portfolio_exists(
    *,
    repository: Any,
    portfolio_id: str,
) -> None:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")
