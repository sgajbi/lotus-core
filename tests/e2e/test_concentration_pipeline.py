"""The retired Core concentration route must stay unavailable to callers."""

from .api_client import E2EApiClient
from .assertions import assert_legacy_endpoint_status


def test_concentration_endpoint_is_disabled(e2e_api_client: E2EApiClient) -> None:
    # No portfolio seed is needed: the route is absent independently of portfolio data.
    path = "/portfolios/E2E_RETIRED_CONCENTRATION/concentration"
    response = e2e_api_client.post_query(
        path,
        {
            "scope": {"as_of_date": "2025-08-31"},
            "metrics": ["BULK", "ISSUER"],
            "options": {"bulk_top_n": [2], "issuer_top_n": 5},
        },
        raise_for_status=False,
    )

    assert_legacy_endpoint_status(response)
    if response.status_code == 404:
        # A restored POST route can return 404 for an unknown portfolio, but
        # normally returns 405 for GET. A deliberate 410 compatibility shim
        # already proves the route is disabled and need not support GET.
        get_response = e2e_api_client.query(path, raise_for_status=False)
        assert get_response.status_code in (404, 410)
