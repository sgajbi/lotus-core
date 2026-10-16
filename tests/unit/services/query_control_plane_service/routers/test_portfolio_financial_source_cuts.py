"""Registered HTTP collection, real signature admission and source-safe failures."""

import json
import logging
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import (
    VerifiedServicePrincipal,
    _enterprise_auth_context_signature,
    _normalize_headers,
    verify_service_principal,
)
from portfolio_common.source_data_security import (
    parse_neutral_source_read_grants,
    required_source_data_capability,
)

from src.services.query_control_plane_service.app.dependencies import (
    get_neutral_source_read_grants,
    get_portfolio_financial_source_cuts_service,
)
from src.services.query_control_plane_service.app.exception_mappers import (
    register_query_control_plane_exception_handlers,
)
from src.services.query_control_plane_service.app.routers import (
    portfolio_financial_source_cuts as routes,
)
from src.services.query_control_plane_service.app.settings import load_query_control_plane_settings
from tests.unit.services.query_control_plane_service.application import (
    test_portfolio_financial_source_cuts as read_tests,
)

pytestmark = pytest.mark.unit
financial_fixture = read_tests.financial_fixture
registry_fixture = read_tests.registry_fixture
retained_service = read_tests.retained_service
SECRET = "synthetic-neutral-http-signature-key"
REGISTRY = "PortfolioHistoricalRegistry"
PATH = "/integration/portfolio-historical-registries/query"


def signed_headers(tenant="tenant", service="lotus-manage", product=REGISTRY):
    headers = {
        "X-Tenant-Id": tenant,
        "X-Service-Identity": service,
        "X-Actor-Id": "synthetic",
        "X-Role": "system",
        "X-Correlation-Id": "synthetic-neutral-read",
        "X-Capabilities": required_source_data_capability(product),
        "X-Enterprise-Auth-Key-Id": "synthetic-key",
        "X-Enterprise-Auth-Timestamp": str(int(time.time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers), SECRET
    )
    return headers


def application(monkeypatch, *, enabled=True, grants=True):
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", SECRET)
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "synthetic-key")
    monkeypatch.setenv("LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED", str(enabled).lower())
    monkeypatch.setenv("LOTUS_CORE_CAP_FINANCIAL_SOURCE_CUT_READ_ENABLED", str(enabled).lower())
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)
    reader, query, _, _ = registry_fixture(0)
    service = retained_service(reader)
    service.query = AsyncMock(wraps=service.query)
    app = FastAPI()
    app.include_router(routes.router)
    register_query_control_plane_exception_handlers(
        app, logger=logging.getLogger("synthetic-read-test")
    )
    app.dependency_overrides[get_portfolio_financial_source_cuts_service] = lambda: service
    grant_rows = (
        [
            {
                "service_identity": "lotus-manage",
                "tenant_id": "tenant",
                "source_system": "producer",
                "registry_scope_id": "registry",
                "products": [REGISTRY, "PortfolioFinancialSourceCut"],
            }
        ]
        if grants
        else []
    )
    app.dependency_overrides[get_neutral_source_read_grants] = lambda: (
        parse_neutral_source_read_grants(json.dumps(grant_rows))
    )

    @app.middleware("http")
    async def admitted_context(request, call_next):
        principal = verify_service_principal(
            dict(request.headers), load_query_control_plane_settings()
        )
        request.state.tenant_context = TenantContext(
            TenantId(request.headers.get("X-Tenant-Id", "tenant")),
            service_identity=principal.service_identity
            if isinstance(principal, VerifiedServicePrincipal)
            else None,
            identity_verified=isinstance(principal, VerifiedServicePrincipal),
        )
        return await call_next(request)

    return app, service, query.model_copy(update={"view": "CUT"}).model_dump(mode="json")


def test_both_collections_are_registered_in_actual_qcp_and_openapi():
    from src.services.query_control_plane_service.app.main import app

    registered = {route.path: route for route in app.routes if getattr(route, "methods", None)}
    for path, product in [
        (PATH, REGISTRY),
        ("/integration/financial-source-cuts/query", "PortfolioFinancialSourceCut"),
    ]:
        assert "POST" in registered[path].methods
        assert (
            registered[path].openapi_extra["x-lotus-source-data-product"]["product_name"] == product
        )
        assert (
            registered[path].openapi_extra["x-lotus-source-data-security"]["tenant_required"]
            is True
        )


@pytest.mark.parametrize("financial", [False, True])
def test_registered_route_refuses_a_valid_response_of_the_other_product(monkeypatch, financial):
    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )
    from tests.unit.services.query_control_plane_service.contracts import (
        test_portfolio_financial_source_cuts as fixtures,
    )

    app, service, body = application(monkeypatch)
    if financial:
        _, query, _, _ = financial_fixture()
        body = query.model_copy(update={"view": "CUT"}).model_dump(mode="json")
        path, product = "/integration/financial-source-cuts/query", "PortfolioFinancialSourceCut"
        wrong = contracts.SourceCutReadResponse.model_validate(fixtures.empty_registry_response())
    else:
        path, product = PATH, REGISTRY
        wrong = fixtures.financial_header_response()
    service.query.side_effect = None
    service.query.return_value = wrong
    with TestClient(app) as client:
        response = client.post(path, json=body, headers=signed_headers(product=product))
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "QCP_SOURCE_CUT_INCOMPATIBLE"


def test_registered_collection_returns_original_completed_empty_manifest(monkeypatch):
    app, service, body = application(monkeypatch)
    with TestClient(app) as client:
        response = client.post(PATH, json=body, headers=signed_headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["rows"]) == result["pagination"]["root_item_count"] == 1
    assert result["rows"][0]["manifest"]["supplied_count"] == 0
    assert result["content_hash"] == "sha256:" + body["content_hash"]
    assert result["qualification"] == "UNQUALIFIED" and not result["authoritative_use_available"]
    assert service.query.call_args.kwargs["tenant_id"] == "tenant"
    assert service.query.call_args.kwargs["service_identity"] == "lotus-manage"


@pytest.mark.parametrize(
    "mutation", ["missing", "unsigned", "spoofed_service", "foreign_tenant", "no_capability"]
)
def test_real_signature_tenant_and_service_authorization_precede_retained_reads(
    monkeypatch, mutation
):
    app, service, body = application(monkeypatch)
    headers = signed_headers()
    if mutation == "missing":
        headers = {}
    elif mutation == "unsigned":
        headers.pop("X-Enterprise-Auth-Signature")
    elif mutation == "spoofed_service":
        headers["X-Service-Identity"] = "lotus-gateway"
    elif mutation == "foreign_tenant":
        headers = signed_headers(tenant="foreign")
    else:
        headers["X-Capabilities"] = ""
        headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
            _normalize_headers(headers), SECRET
        )
    with TestClient(app) as client:
        response = client.post(PATH, json=body, headers=headers)
    assert response.status_code == 403, response.text
    service.query.assert_not_called()


@pytest.mark.parametrize("enabled,grants,status", [(False, True, 503), (True, False, 403)])
def test_availability_flag_is_independent_of_registry_access(monkeypatch, enabled, grants, status):
    app, service, body = application(monkeypatch, enabled=enabled, grants=grants)
    with TestClient(app) as client:
        response = client.post(PATH, json=body, headers=signed_headers())
    assert response.status_code == status, response.text
    service.query.assert_not_called()


def test_invalid_server_grant_configuration_fails_unavailable_without_exposing_payload(monkeypatch):
    app, service, body = application(monkeypatch)
    app.dependency_overrides.pop(get_neutral_source_read_grants)
    monkeypatch.setenv("PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON", '{"private-config":true}')
    with TestClient(app) as client:
        response = client.post(PATH, json=body, headers=signed_headers())
    assert response.status_code == 503 and "private-config" not in response.text
    service.query.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "foreign"},
        {"revision": True},
        {"content_hash": "sha256:" + "a" * 64},
        {"page": {"page_size": 501}},
        {"view": "latest"},
    ],
)
def test_closed_body_refuses_alias_offsets_or_caller_tenant(monkeypatch, change):
    app, service, body = application(monkeypatch)
    with TestClient(app) as client:
        response = client.post(PATH, json=body | change, headers=signed_headers())
    assert response.status_code == 422, response.text
    service.query.assert_not_called()


@pytest.mark.parametrize(
    "error,status", [(LookupError("private-selector"), 404), (ValueError("private-selector"), 409)]
)
def test_source_failures_are_distinct_and_details_do_not_echo_selectors(monkeypatch, error, status):
    app, service, body = application(monkeypatch)
    service.query.side_effect = error
    with TestClient(app) as client:
        response = client.post(PATH, json=body, headers=signed_headers())
    assert response.status_code == status and "private-selector" not in response.text


def test_registered_financial_collection_exposes_selected_graph_and_body_portfolio(monkeypatch):
    app, _, _ = application(monkeypatch)
    reader, query, _, row = financial_fixture()
    app.dependency_overrides[get_portfolio_financial_source_cuts_service] = lambda: (
        retained_service(reader)
    )
    with TestClient(app) as client:
        response = client.post(
            "/integration/financial-source-cuts/query",
            json=query.model_dump(mode="json"),
            headers=signed_headers(product="PortfolioFinancialSourceCut"),
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["portfolio_id"] == "portfolio/opaque"
    assert result["rows"][0]["graph_content_hash"] == row.graph_content_hash
    assert result["batch_manifest_hash"] == query.content_hash != row.graph_content_hash


def test_registered_native_capture_collection_uses_admitted_catalog_without_qualifying_vectors(
    monkeypatch,
):
    import base64

    from src.services.query_control_plane_service.app.infrastructure import (
        portfolio_financial_source_cuts as retained,
    )
    from tests.unit.services.query_control_plane_service.infrastructure import (
        test_portfolio_financial_source_cuts as captures,
    )

    app, _, _ = application(monkeypatch)
    reader, query, _, _, rows = captures.native_vector_fixture()
    service = retained_service(reader, capture_verifier=retained.RetainedSourceCaptureVerifier())
    app.dependency_overrides[get_portfolio_financial_source_cuts_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(
            "/integration/financial-source-cuts/query",
            json=query.model_copy(
                update={"page": query.page.model_copy(update={"page_size": 500})}
            ).model_dump(mode="json"),
            headers=signed_headers(product="PortfolioFinancialSourceCut"),
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["pagination"]["root_item_count"] == result["pagination"]["total_count"] == 5
    assert (
        result["qualification"] == "UNQUALIFIED"
        and result["population_verification"] == "UNVERIFIED"
    )
    assert result["authoritative_use_available"] is False
    cash = next(row for row in result["rows"] if row["role"] == "CASH")
    assert base64.b64decode(cash["bytes_base64"]) == base64.b64decode(
        captures.NATIVE_CAPTURE_VECTORS["CASH"]["bytes_base64"]
    )
    assert [row["capture_id"] for row in result["rows"]] == [row.capture_id for row in rows]


def test_default_read_dependency_wires_admitted_ingress_and_native_catalogs():
    from src.services.query_control_plane_service.app.infrastructure import (
        portfolio_financial_source_cuts as retained,
    )

    service = get_portfolio_financial_source_cuts_service(db=object())
    assert isinstance(service.capture_verifier, retained.RetainedSourceCaptureVerifier)
