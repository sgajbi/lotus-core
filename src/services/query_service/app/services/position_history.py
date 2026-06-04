from typing import Any

from ..dtos.position_dto import PortfolioPositionHistoryResponse, PositionHistoryRecord


def position_history_record_data(
    *,
    position_history_obj: Any,
    reprocessing_status: str | None,
) -> PositionHistoryRecord:
    return PositionHistoryRecord(
        position_date=position_history_obj.position_date,
        transaction_id=position_history_obj.transaction_id,
        quantity=position_history_obj.quantity,
        cost_basis=position_history_obj.cost_basis,
        cost_basis_local=position_history_obj.cost_basis_local,
        valuation=None,
        reprocessing_status=reprocessing_status,
    )


def portfolio_position_history_response_data(
    *,
    portfolio_id: str,
    security_id: str,
    db_results: list[tuple[Any, str | None]],
) -> PortfolioPositionHistoryResponse:
    return PortfolioPositionHistoryResponse(
        portfolio_id=portfolio_id,
        security_id=security_id,
        positions=[
            position_history_record_data(
                position_history_obj=position_history_obj,
                reprocessing_status=reprocessing_status,
            )
            for position_history_obj, reprocessing_status in db_results
        ],
    )
