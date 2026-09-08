from typing import Any

from portfolio_common.domain.tenant import TenantId


async def ensure_portfolio_exists(
    *,
    repository: Any,
    portfolio_id: str,
    tenant_id: TenantId,
) -> None:
    """Refuse a portfolio the admitted tenant does not own, as if it were absent.

    The tenant is required rather than defaulted. This helper is the existence
    gate for eleven routes across six services, and a default would have left
    every call site not updated by hand answering "does this portfolio exist
    anywhere" -- which is how the gate came to admit foreign portfolios in the
    first place.

    The message is identical for an absent portfolio and one owned by another
    tenant, so the gate cannot be used to discover that an unreadable identifier
    is real.
    """
    if not await repository.portfolio_exists(portfolio_id, tenant_id=tenant_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")
