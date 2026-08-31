"""Unit proof for deterministic E2E API polling ownership."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.e2e.api_client import E2EApiClient


def test_e2e_client_binds_http_and_portfolio_tenant_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
        tenant_id="tenant-e2e",
    )
    captured: dict[str, object] = {}

    def post(url: str, *, json: object, timeout: int) -> SimpleNamespace:
        captured.update(url=url, json=json, timeout=timeout)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(client.session, "post", post)

    client.ingest(
        "/ingest/portfolios",
        {"portfolios": [{"portfolio_id": "P1"}]},
    )

    assert client.session.headers["X-Tenant-Id"] == "tenant-e2e"
    assert captured["json"] == {"portfolios": [{"portfolio_id": "P1", "tenant_id": "tenant-e2e"}]}


def test_e2e_client_rejects_portfolio_tenant_mismatch() -> None:
    client = E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
        tenant_id="tenant-e2e",
    )

    with pytest.raises(ValueError, match="must match admitted tenant"):
        client.ingest(
            "/ingest/portfolios",
            {"portfolios": [{"portfolio_id": "P1", "tenant_id": "tenant-other"}]},
        )


def test_poll_for_data_routes_control_plane_readiness_to_control_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
    )
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


def test_wait_for_portfolio_authority_requires_tenant_scoped_portfolio_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
    )
    captured: dict[str, object] = {}

    def poll_for_data(endpoint: str, validation_func, **kwargs):
        captured.update(endpoint=endpoint, **kwargs)
        assert validation_func({"portfolio_id": "P1"}) is True
        assert validation_func({"portfolio_id": "OTHER"}) is False

    monkeypatch.setattr(client, "poll_for_data", poll_for_data)

    client.wait_for_portfolio_authority("P1", timeout=90)

    assert captured == {
        "endpoint": "/portfolios/P1",
        "timeout": 90,
        "fail_message": "Portfolio tenant authority did not become queryable",
    }
