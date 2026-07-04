# services/query-service/app/dependencies.py
from typing import Dict, Optional

from fastapi import Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from .services.buy_state_service import BuyStateService
from .services.cash_account_service import CashAccountService
from .services.cash_balance_service import CashBalanceService
from .services.cash_movement_service import CashMovementService
from .services.cashflow_projection_service import CashflowProjectionService
from .services.liquidity_ladder_service import PortfolioLiquidityLadderService
from .services.portfolio_service import PortfolioService
from .services.position_service import PositionService
from .services.reporting_service import ReportingService
from .services.sell_state_service import SellStateService


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
        None, description="Field to sort by (e.g., 'transaction_date')."
    ),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'."),
) -> Dict[str, Optional[str]]:
    """
    A dependency that provides standardized sorting query parameters.
    - sort_by: The field to sort the results on.
    - sort_order: The direction of the sort (ascending or descending).
    """
    return {"sort_by": sort_by, "sort_order": sort_order}


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


def get_liquidity_ladder_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioLiquidityLadderService:
    return PortfolioLiquidityLadderService(db)


def get_portfolio_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioService:
    return PortfolioService(db)


def get_position_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionService:
    return PositionService(db)


def get_reporting_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReportingService:
    return ReportingService(db)


def get_sell_state_service(db: AsyncSession = Depends(get_async_db_session)) -> SellStateService:
    return SellStateService(db)
