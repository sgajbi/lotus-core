"""The retired Core portfolio-review route must stay unavailable to callers."""

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status


def test_portfolio_review_endpoint_is_disabled(e2e_api_client: E2EApiClient) -> None:
    # Review belongs to lotus-report; no Core valuation pipeline is a prerequisite.
    path = "/portfolios/E2E_RETIRED_REVIEW/review"
    response = e2e_api_client.post_query(
        path,
        {
            "as_of_date": "2025-08-31",
            "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"],
        },
        raise_for_status=False,
    )

    assert_legacy_endpoint_status(
        response,
        target_service="lotus-report",
        target_endpoint="/reports/portfolios/{portfolio_id}/review",
    )
    if response.status_code == 404:
        get_response = e2e_api_client.query(path, raise_for_status=False)
        assert get_response.status_code in (404, 410)
