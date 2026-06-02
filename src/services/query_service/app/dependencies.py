# services/query-service/app/dependencies.py
from typing import Dict, Optional

from fastapi import Query


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
