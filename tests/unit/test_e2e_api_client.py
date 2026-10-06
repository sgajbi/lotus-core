"""Unit proof for deterministic E2E API polling ownership."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from tests.e2e.api_client import E2EApiClient


def _client() -> E2EApiClient:
    return E2EApiClient(
        ingestion_url="http://ingestion",
        query_url="http://query",
        query_control_plane_url="http://control",
    )


def test_admitted_portfolio_wait_observes_delayed_tenant_scoped_persistence(monkeypatch):
    client = _client()
    states = iter([{"portfolios": []}, {"portfolios": [{"portfolio_id": "P1"}]}])
    client.query = Mock(
        side_effect=lambda endpoint: SimpleNamespace(
            status_code=200,
            json=lambda: next(states),
        )
    )
    monkeypatch.setattr("tests.e2e.api_client.time.sleep", lambda interval: None)
    assert client.wait_for_admitted_portfolio("P1")["portfolios"] == [{"portfolio_id": "P1"}]
    assert client.query.call_count == 2
    assert client.session.headers["X-Tenant-Id"] == "tenant_e2e"


def test_foreign_tenant_portfolio_is_not_admitted_by_supported_query(monkeypatch):
    client = _client()
    client.query = Mock(side_effect=requests.HTTPError("foreign portfolio absent"))
    clock = iter([0, 0, 61])
    monkeypatch.setattr("tests.e2e.api_client.time.time", lambda: next(clock))
    monkeypatch.setattr("tests.e2e.api_client.time.sleep", lambda interval: None)
    with pytest.raises(pytest.fail.Exception, match="Tenant-owned portfolio did not materialize"):
        client.wait_for_admitted_portfolio("FOREIGN")
    client.query.assert_called_once_with("/portfolios?portfolio_id=FOREIGN")


def test_ingestion_refusal_retains_actual_bounded_body_without_retry():
    client = _client()
    error = requests.HTTPError("403")
    response = SimpleNamespace(
        status_code=403, text='{"code":"actual-refusal"}', raise_for_status=Mock(side_effect=error)
    )
    client.session.post = Mock(return_value=response)
    with pytest.raises(requests.HTTPError) as caught:
        client.ingest("/ingest/transactions", {"transactions": []})
    assert caught.value is error
    assert "actual-refusal" in error.__notes__[0]
    client.session.post.assert_called_once()


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


def test_e2e_client_preserves_malformed_payload_for_server_validation() -> None:
    client = _client()
    response = SimpleNamespace(raise_for_status=lambda: None)
    client.session.post = Mock(return_value=response)
    malformed_payload = [{"transaction_id": "bad-payload"}]

    client.ingest("/ingest/transactions", malformed_payload)

    assert client.session.post.call_args.kwargs["json"] == malformed_payload


def test_query_can_observe_a_retired_route_404_without_masking_normal_errors() -> None:
    client = _client()
    response = SimpleNamespace(
        status_code=404, raise_for_status=Mock(side_effect=RuntimeError("404"))
    )
    client.session.get = Mock(return_value=response)

    assert client.query("/retired", raise_for_status=False) is response
    response.raise_for_status.assert_not_called()
    with pytest.raises(RuntimeError, match="404"):
        client.query("/retired")
    assert client.session.get.call_args.args == ("http://query/retired",)


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


def test_wait_for_admitted_portfolio_uses_tenant_scoped_supported_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    expected = {"portfolios": [{"portfolio_id": "P /1"}]}

    def poll_for_data(
        endpoint: str,
        validation_func,
        timeout: int,
        fail_message: str,
    ):
        assert endpoint == "/portfolios?portfolio_id=P%20%2F1"
        assert timeout == 45
        assert fail_message == (
            "Tenant-owned portfolio did not materialize before transaction admission."
        )
        assert validation_func(expected)
        assert not validation_func({"portfolios": []})
        assert not validation_func({"portfolios": [{"portfolio_id": "other"}]})
        return expected

    monkeypatch.setattr(client, "poll_for_data", poll_for_data)

    assert client.wait_for_admitted_portfolio("P /1", timeout=45) == expected


def test_wait_for_admitted_portfolio_rejects_blank_identity() -> None:
    with pytest.raises(ValueError, match="portfolio_id must be nonblank"):
        _client().wait_for_admitted_portfolio("   ")
