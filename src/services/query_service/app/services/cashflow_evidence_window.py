from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..repositories.cashflow_repository import CashflowRepository


@dataclass(frozen=True)
class CashflowEvidenceWindow:
    booked_rows: list[tuple[date, Decimal]]
    projected_rows: list[tuple[date, Decimal]]
    latest_evidence_timestamp: datetime | None


async def read_cashflow_evidence_window(
    *,
    repo: CashflowRepository,
    portfolio_id: str,
    start_date: date,
    end_date: date,
    include_projected: bool,
) -> CashflowEvidenceWindow:
    booked_evidence = await repo.get_portfolio_cashflow_series_with_evidence(
        portfolio_id=portfolio_id,
        start_date=start_date,
        end_date=end_date,
    )
    if include_projected:
        projected_evidence = await repo.get_projected_settlement_cashflow_series_with_evidence(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        projected_rows = projected_evidence.rows
        latest_projected_evidence = projected_evidence.latest_evidence_timestamp
    else:
        projected_rows = []
        latest_projected_evidence = None

    return CashflowEvidenceWindow(
        booked_rows=booked_evidence.rows,
        projected_rows=projected_rows,
        latest_evidence_timestamp=max(
            (
                timestamp
                for timestamp in (
                    booked_evidence.latest_evidence_timestamp,
                    latest_projected_evidence,
                )
                if timestamp
            ),
            default=None,
        ),
    )
