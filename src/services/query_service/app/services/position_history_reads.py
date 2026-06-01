from datetime import date
from typing import Any

from ..dtos.position_dto import PortfolioPositionHistoryResponse
from ..repositories.identifier_normalization import normalize_security_id
from .position_history import portfolio_position_history_response_data


async def position_history_response(
    *,
    repository: Any,
    portfolio_id: str,
    security_id: str,
    start_date: date | None,
    end_date: date | None,
) -> PortfolioPositionHistoryResponse:
    normalized_security_id = normalize_security_id(security_id)
    db_results = await repository.get_position_history_by_security(
        portfolio_id=portfolio_id,
        security_id=normalized_security_id,
        start_date=start_date,
        end_date=end_date,
    )
    return portfolio_position_history_response_data(
        portfolio_id=portfolio_id,
        security_id=normalized_security_id,
        db_results=db_results,
    )
