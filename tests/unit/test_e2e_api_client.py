"""Unit proof for deterministic E2E API polling ownership."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.e2e.api_client import E2EApiClient


def _client() -> E2EApiClient:
    return E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
    )


def test_e2e_client_binds_request_and_portfolio_to_one_tenant() -> None:
    client = _client()
    response = SimpleNamespace(raise_for_status=lambda: None)
    client.session.post = Mock(return_value=response)

    client.ingest(
        "/ingest/portfolios",
        {"portfolios": [{"portfolio_id": "P1"}]},
    )

    assert client.session.headers["X-Tenant-Id"] == client.tenant_id
    assert client.session.post.call_args.kwargs["json"] == {
        "portfolios": [{"portfolio_id": "P1", "tenant_id": client.tenant_id}]
    }


def test_e2e_client_refuses_portfolio_outside_admitted_tenant() -> None:
    client = _client()
    client.session.post = Mock()

    with pytest.raises(ValueError, match="must match the admitted tenant"):
        client.ingest(
            "/ingest/portfolios",
            {"portfolios": [{"portfolio_id": "P1", "tenant_id": "other-tenant"}]},
        )

    client.session.post.assert_not_called()


def test_poll_for_data_routes_control_plane_readiness_to_control_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    calls: list[str] = []

    def control_response(endpoint: str) -> SimpleNamespace:
        calls.append(endpoint)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "publish_allowed": True,
                "controls_blocking": False,
            },
        )

    monkeypatch.setattr(client, "query_control", control_response)
    monkeypatch.setattr(
        client,
        "query",
        lambda _endpoint: pytest.fail("query data-plane client must not be used"),
    )

    payload = client.poll_for_data(
        "/support/portfolios/P1/overview",
        lambda data: data["publish_allowed"] is True,
        control_plane=True,
    )

    assert payload == {"publish_allowed": True, "controls_blocking": False}
    assert calls == ["/support/portfolios/P1/overview"]
