"""Registered HTTP admission with real signed context, synthetic server configuration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from portfolio_common.fx_cut_authorization import authenticate_fx_cut_authorization
from portfolio_common.fx_source_configuration import load_fx_source_policies

from src.services.ingestion_service.app import main
from src.services.ingestion_service.app.dependencies import get_ingestion_publish_command_handler
from src.services.ingestion_service.app.services.ingestion_publish_commands import (
    IngestionCommandResult,
)
from tests.test_support.fx_source_fixtures import (
    configure_synthetic_fx_source,
    signed_headers,
    submission,
    synthetic_cut,
    synthetic_revision,
)

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.contract]


@pytest.fixture
def registered_http(monkeypatch):
    configure_synthetic_fx_source(monkeypatch)
    producer = MagicMock()
    producer.flush.return_value = 0
    monkeypatch.setattr(main, "get_kafka_producer", lambda: producer)
    handler = MagicMock()
    handler.ingest_fx_source_cut = AsyncMock(
        return_value=IngestionCommandResult(
            "One complete FX source cut accepted for asynchronous retention.",
            "fx_source_cut",
            1,
            "synthetic-fx-cut-command",
            "synthetic-fx-job",
        )
    )
    monkeypatch.setitem(
        main.app.dependency_overrides, get_ingestion_publish_command_handler, lambda: handler
    )
    with TestClient(main.app) as client:
        yield client, handler


def test_registered_http_constructs_one_signed_cut_and_member_cost(registered_http):
    client, handler = registered_http
    cut = synthetic_cut()
    response = client.post(
        "/ingest/fx-rates", headers=signed_headers(), json=submission(cut).model_dump(mode="json")
    )
    assert response.status_code == 202, response.text
    assert response.json()["accepted_count"] == 1
    assert response.json()["entity_type"] == "fx_source_cut"
    command = handler.ingest_fx_source_cut.await_args.args[0]
    assert command.admission_record_count == len(cut.revisions)
    assert len(command.records) == 1
    event = command.records[0]
    assert event.source_cut() == cut
    _, digest = authenticate_fx_cut_authorization(
        event.authorization, cut, relay_policy=load_fx_source_policies().relay
    )
    assert len(digest) == 64
    assert event.authorization.claims.tenant_id == command.tenant_context.tenant_id_text
    assert command.tenant_context.identity_verified is True


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "signature",
        "foreign-tenant",
        "ordinary-capability",
        "revoked",
        "empty",
        "pair",
    ],
)
def test_bypass_never_admits_missing_or_foreign_authority(registered_http, monkeypatch, fault):
    client, handler = registered_http
    headers = signed_headers(
        tenant="FOREIGN_TENANT" if fault == "foreign-tenant" else "SYNTHETIC_TENANT",
        capability="ingestion.fx_rates.write"
        if fault == "ordinary-capability"
        else "ingestion.fx_rates.source_cut.submit",
    )
    body = submission(synthetic_cut()).model_dump(mode="json")
    if fault == "missing":
        headers = {"X-Tenant-Id": "SYNTHETIC_TENANT"}
    elif fault == "signature":
        headers["X-Enterprise-Auth-Signature"] = "0" * 64
    elif fault == "revoked":
        configure_synthetic_fx_source(monkeypatch, active=False)
    elif fault == "empty":
        monkeypatch.setenv("LOTUS_FX_SOURCE_ENROLLMENTS", "[]")
    elif fault == "pair":
        body["members"][0]["to_currency"] = "EUR"
        # Membership is deliberately inconsistent too; neither should reach publication.
    response = client.post("/ingest/fx-rates", headers=headers, json=body)
    assert response.status_code in (403, 422), response.text
    handler.ingest_fx_source_cut.assert_not_awaited()


@pytest.mark.parametrize("extra", ["tenant_id", "cut_id", "authorization", "enrollment_version"])
def test_caller_authority_fields_refused_before_submission(registered_http, extra):
    client, handler = registered_http
    body = submission(synthetic_cut()).model_dump(mode="json") | {extra: "caller-override"}
    response = client.post("/ingest/fx-rates", headers=signed_headers(), json=body)
    assert response.status_code == 422
    handler.ingest_fx_source_cut.assert_not_awaited()


@pytest.mark.parametrize("fault", ["missing-member", "count", "hash", "compact-numeric"])
def test_incomplete_or_unrepresentable_cut_refuses_before_job(registered_http, fault):
    client, handler = registered_http
    body = submission(synthetic_cut()).model_dump(mode="json")
    if fault == "missing-member":
        body["members"] = []
    elif fault == "count":
        body["declared_member_count"] = 2
    elif fault == "hash":
        body["declared_membership_hash"] = "0" * 64
    else:
        body["members"][0]["rate"] = "1e100000"
    response = client.post("/ingest/fx-rates", headers=signed_headers(), json=body)
    assert response.status_code == 422
    handler.ingest_fx_source_cut.assert_not_awaited()


def test_malformed_server_config_safe_error_without_secret(registered_http, monkeypatch):
    client, handler = registered_http
    monkeypatch.setenv("LOTUS_FX_SOURCE_RELAY_KEYS", "SECRET_CONFIG_NOT_JSON")
    response = client.post(
        "/ingest/fx-rates",
        headers=signed_headers(),
        json=submission(synthetic_cut()).model_dump(mode="json"),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "FX_SOURCE_CONFIGURATION_UNAVAILABLE"
    assert "SECRET_CONFIG" not in response.text
    handler.ingest_fx_source_cut.assert_not_awaited()


def test_encoded_cut_size_refuses_before_job_or_publication(registered_http):
    client, handler = registered_http
    # Individually valid bounded Unicode IDs still exceed the actual Kafka encoding ceiling.
    cut = synthetic_cut(
        *(
            synthetic_revision(source_record_id=str(index), source_revision="\U0001f642" * 128)
            for index in range(512)
        )
    )
    response = client.post(
        "/ingest/fx-rates", headers=signed_headers(), json=submission(cut).model_dump(mode="json")
    )
    assert response.status_code == 413, response.text
    assert response.json()["detail"]["code"] == "FX_SOURCE_CUT_ENCODED_SIZE_EXCEEDED"
    handler.ingest_fx_source_cut.assert_not_awaited()
