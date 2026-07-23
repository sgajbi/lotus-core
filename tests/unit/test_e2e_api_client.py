"""Unit proof for deterministic E2E API polling ownership."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.e2e.api_client import E2EApiClient


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
