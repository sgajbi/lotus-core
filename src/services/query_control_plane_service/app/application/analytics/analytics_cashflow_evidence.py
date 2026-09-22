"""Load snapshot-consistent position cashflow evidence for analytics pages."""

from datetime import date

from ...domain.analytics import AnalyticsCashflowEpochEvidenceError, AnalyticsCashflowEvidence
from ...ports.analytics import AnalyticsTimeseriesReader
from .analytics_input_errors import AnalyticsInputError


async def load_position_cashflow_rows(
    reader: AnalyticsTimeseriesReader,
    *,
    portfolio_id: str,
    security_ids: list[str],
    valuation_dates: list[date],
    snapshot_epoch: int,
) -> list[AnalyticsCashflowEvidence]:
    try:
        return await reader.list_position_cashflow_rows(
            portfolio_id=portfolio_id,
            security_ids=security_ids,
            valuation_dates=valuation_dates,
            snapshot_epoch=snapshot_epoch,
        )
    except AnalyticsCashflowEpochEvidenceError as exc:
        raise AnalyticsInputError("INSUFFICIENT_DATA", str(exc)) from exc
