import pytest

from src.services.query_service.app.dtos.analytics_input_dto import (
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesResponse,
)
from src.services.query_service.app.dtos.position_dto import PortfolioPositionsResponse
from src.services.query_service.app.dtos.reporting_dto import (
    ActivitySummaryResponse,
    CashBalancesResponse,
    HoldingsSnapshotResponse,
    IncomeSummaryResponse,
)
from src.services.query_service.app.dtos.transaction_dto import PaginatedTransactionResponse


@pytest.mark.parametrize(
    ("response_model", "product_name"),
    [
        (PortfolioAnalyticsTimeseriesResponse, "PortfolioTimeseriesInput"),
        (PositionAnalyticsTimeseriesResponse, "PositionTimeseriesInput"),
        (PortfolioPositionsResponse, "HoldingsAsOf"),
        (CashBalancesResponse, "HoldingsAsOf"),
        (HoldingsSnapshotResponse, "HoldingsAsOf"),
        (PaginatedTransactionResponse, "TransactionLedgerWindow"),
        (IncomeSummaryResponse, "TransactionLedgerWindow"),
        (ActivitySummaryResponse, "TransactionLedgerWindow"),
    ],
)
def test_query_service_product_responses_declare_product_identity_defaults(
    response_model, product_name
) -> None:
    assert response_model.model_fields["product_name"].default == product_name
    assert response_model.model_fields["product_version"].default == "v1"
