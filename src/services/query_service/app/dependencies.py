# services/query-service/app/dependencies.py
from typing import Dict, Optional

from fastapi import Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from .services.buy_state_service import BuyStateService
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


def get_sell_state_service(db: AsyncSession = Depends(get_async_db_session)) -> SellStateService:
    return SellStateService(db)
