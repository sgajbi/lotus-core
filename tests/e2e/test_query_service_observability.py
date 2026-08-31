from .api_client import E2EApiClient


def test_query_service_preserves_incoming_correlation_id(e2e_api_client: E2EApiClient):
    response = e2e_api_client.session.get(
        f"{e2e_api_client.query_url}/openapi.json",
        headers={"X-Correlation-ID": "e2e-corr-123"},
        timeout=10,
    )

    response.raise_for_status()
    assert response.headers["X-Correlation-ID"] == "e2e-corr-123"


def test_query_service_generates_correlation_id_when_missing(e2e_api_client: E2EApiClient):
    response = e2e_api_client.session.get(
        f"{e2e_api_client.query_url}/openapi.json",
        timeout=10,
    )

    response.raise_for_status()
    assert response.headers["X-Correlation-ID"].startswith("QRY:")
