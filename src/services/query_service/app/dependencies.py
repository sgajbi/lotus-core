# services/query-service/app/dependencies.py
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from .application.transaction_sorting import (
    DEFAULT_TRANSACTION_SORT_ORDER,
    TRANSACTION_SORT_FIELDS,
    TRANSACTION_SORT_ORDERS,
    TransactionSortValidationError,
    normalize_transaction_sort,
)
from .services.buy_state_service import BuyStateService
from .services.cash_account_service import CashAccountService
from .services.cash_balance_service import CashBalanceService
from .services.cash_movement_service import CashMovementService
from .services.cashflow_projection_service import CashflowProjectionService
from .services.fx_rate_service import FxRateService
from .services.instrument_service import InstrumentService
from .services.liquidity_ladder_service import PortfolioLiquidityLadderService
from .services.lookup_catalog_service import LookupCatalogService
from .services.portfolio_service import PortfolioService
from .services.position_service import PositionService
from .services.price_service import MarketPriceService
from .services.reporting_service import ReportingService
from .services.sell_state_service import SellStateService
from .services.transaction_service import TransactionService


def pagination_params(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> Dict[str, int]:
    """
    A dependency that provides standardized pagination query parameters.
    - skip: The starting offset.
    - limit: The number of items to return.
    """
    return {"skip": skip, "limit": limit}


def sorting_params(
    sort_by: Optional[str] = Query(
        None,
        description=(
            "Transaction ledger sort field. Defaults to transaction_date. "
            "Results always use transaction id as a deterministic tie-breaker."
        ),
        json_schema_extra={"enum": list(TRANSACTION_SORT_FIELDS)},
        examples=["transaction_date"],
    ),
    sort_order: Optional[str] = Query(
        DEFAULT_TRANSACTION_SORT_ORDER,
        description="Transaction ledger sort direction.",
        json_schema_extra={"enum": list(TRANSACTION_SORT_ORDERS)},
        examples=["desc"],
    ),
) -> Dict[str, Optional[str]]:
    """
    A dependency that provides standardized sorting query parameters.
    - sort_by: The field to sort the results on.
    - sort_order: The direction of the sort (ascending or descending).
    """
    try:
        _, normalized_sort_order = normalize_transaction_sort(
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except TransactionSortValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TRANSACTION_SORT_PARAMETER",
                "message": str(exc),
                "field": exc.field_name,
                "rejected_value": exc.rejected_value,
                "allowed_values": list(exc.allowed_values),
            },
        ) from exc
    return {"sort_by": sort_by, "sort_order": normalized_sort_order}


def get_buy_state_service(db: AsyncSession = Depends(get_async_db_session)) -> BuyStateService:
    return BuyStateService(db)


def get_cash_account_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashAccountService:
    return CashAccountService(db)


def get_cash_balance_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashBalanceService:
    return CashBalanceService(db)


def get_cash_movement_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashMovementService:
    return CashMovementService(db)


def get_cashflow_projection_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashflowProjectionService:
    return CashflowProjectionService(db)


def get_fx_rate_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> FxRateService:
    return FxRateService(db)


def get_instrument_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> InstrumentService:
    return InstrumentService(db)


def get_liquidity_ladder_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioLiquidityLadderService:
    return PortfolioLiquidityLadderService(db)


def get_portfolio_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioService:
    return PortfolioService(db)


def get_lookup_catalog_service(
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    instrument_service: InstrumentService = Depends(get_instrument_service),
) -> LookupCatalogService:
    return LookupCatalogService(
        portfolio_service=portfolio_service,
        instrument_service=instrument_service,
    )


def get_position_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionService:
    return PositionService(db)


def get_market_price_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> MarketPriceService:
    return MarketPriceService(db)


def get_reporting_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReportingService:
    return ReportingService(db)


def get_sell_state_service(db: AsyncSession = Depends(get_async_db_session)) -> SellStateService:
    return SellStateService(db)


def get_transaction_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> TransactionService:
    return TransactionService(db)
