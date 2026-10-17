"""Source semantics for the opt-in overlay; native Docker proof is separate."""

from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import (
    VerifiedServicePrincipal,
    _enterprise_auth_context_signature,
    _normalize_headers,
    load_default_enterprise_settings,
    verify_service_principal,
)
from portfolio_common.http_app_bootstrap import configure_standard_http_app
from portfolio_common.portfolio_financial_source_cut_admission import parse_registry_source_grants
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
    parse_submission_grants,
)
from portfolio_common.source_data_security import (
    parse_neutral_source_read_grants,
    require_neutral_source_read_grant,
)

ROOT = Path(__file__).resolve().parents[3]
OVERLAY = ROOT / "docker-compose.source-custody.yml"
SERVICES = ("ingestion_service", "query_control_plane_service")
AUTH_INPUTS = {
    "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET": "synthetic-unit-test-secret",
    "ENTERPRISE_PRIMARY_KEY_ID": "synthetic-unit-test-key",
}
AUTH_KEYS = {*AUTH_INPUTS, "ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS"}
GRANT_KEYS = {
    "ingestion_service": {
        "LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON",
        "LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON",
    },
    "query_control_plane_service": {"PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON"},
}
FEATURE_KEYS = {
    "LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED",
    "LOTUS_CORE_CAP_FINANCIAL_SOURCE_CUT_READ_ENABLED",
}
ENFORCEMENT_KEYS = {
    "ingestion_service": {"ENTERPRISE_ENFORCE_AUTHZ"},
    "query_control_plane_service": {"ENTERPRISE_ENFORCE_AUTHZ", "ENTERPRISE_ENFORCE_READ_AUTHZ"},
}


@pytest.fixture(autouse=True)
def _fixed_auth_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("portfolio_common.enterprise_readiness.time.time", lambda: 1_700_000_000)


def _overlay() -> dict:
    return yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))


def _environment(service: str, supplied: dict[str, str]) -> dict[str, str]:
    """Project only the overlay's required/default interpolation for source checks."""
    result = {}
    for key, expression in _overlay()["services"][service]["environment"].items():
        match = re.fullmatch(r"\$\{([A-Z_]+):([?-])(.*)\}", expression)
        if match is None:
            assert expression in {"300", "true"}
            result[key] = expression
            continue
        name, operation, default = match.groups()
        assert name == key
        value = supplied.get(name, "")
        if operation == "?" and not value:
            raise ValueError(f"operator input required: {name}")
        result[key] = value or default
    return result


def _headers() -> dict[str, str]:
    headers = {
        "X-Actor-Id": "synthetic-maker",
        "X-Tenant-Id": "synthetic-tenant",
        "X-Role": "operator",
        "X-Correlation-Id": "synthetic-correlation",
        "X-Service-Identity": "synthetic-producer",
        "X-Capabilities": "ingestion.portfolio_financial_source_cuts.write",
        "X-Enterprise-Auth-Key-Id": AUTH_INPUTS["ENTERPRISE_PRIMARY_KEY_ID"],
        "X-Enterprise-Auth-Timestamp": "1700000000",
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers), AUTH_INPUTS["ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET"]
    )
    return headers


def test_overlay_changes_only_two_service_environment_maps() -> None:
    overlay = _overlay()
    assert set(overlay) == {"services"}
    assert set(overlay["services"]) == set(SERVICES)
    base = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    merged = copy.deepcopy(base)
    for service, definition in overlay["services"].items():
        assert set(definition) == {"environment"}
        expected = AUTH_KEYS | GRANT_KEYS[service] | ENFORCEMENT_KEYS[service]
        if service == "query_control_plane_service":
            expected |= FEATURE_KEYS
        assert set(definition["environment"]) == expected
        merged["services"][service]["environment"].update(definition["environment"])
    for service, original in base["services"].items():
        if service not in SERVICES:
            assert merged["services"][service] == original
            continue
        assert {k: v for k, v in merged["services"][service].items() if k != "environment"} == {
            k: v for k, v in original.items() if k != "environment"
        }
        assert {
            k: v
            for k, v in merged["services"][service]["environment"].items()
            if k not in overlay["services"][service]["environment"]
        } == {
            k: v
            for k, v in original["environment"].items()
            if k not in overlay["services"][service]["environment"]
        }
    assert {k: v for k, v in merged.items() if k != "services"} == {
        k: v for k, v in base.items() if k != "services"
    }


def test_base_stack_does_not_require_or_distribute_overlay_credentials() -> None:
    base = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for service in base["services"].values():
        environment = service.get("environment", {})
        keys = (
            set(environment)
            if isinstance(environment, dict)
            else {entry.split("=", maxsplit=1)[0] for entry in environment}
        )
        assert not set(AUTH_INPUTS) & keys


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("key", AUTH_INPUTS)
@pytest.mark.parametrize("missing", (None, ""))
def test_overlay_requires_each_operator_auth_input(service, key, missing) -> None:
    expression = _overlay()["services"][service]["environment"][key]
    assert expression.startswith("${" + key + ":?") and expression.endswith("}")
    supplied = dict(AUTH_INPUTS)
    if missing is None:
        supplied.pop(key)
    else:
        supplied[key] = missing
    with pytest.raises(ValueError, match=f"operator input required: {key}"):
        _environment(service, supplied)


@pytest.mark.parametrize("service", SERVICES)
def test_operator_auth_context_reaches_existing_native_verifier(monkeypatch, service) -> None:
    environment = _environment(service, AUTH_INPUTS)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    settings = load_default_enterprise_settings(service_name=service)
    assert settings.enterprise_auth_context_max_age_seconds == 300
    assert verify_service_principal(_headers(), settings) == VerifiedServicePrincipal(
        service_identity="synthetic-producer",
        capabilities=frozenset({"ingestion.portfolio_financial_source_cuts.write"}),
    )


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize(
    ("changed", "value", "reason"),
    (
        ("X-Enterprise-Auth-Key-Id", "foreign-key", "invalid_auth_context_key_id"),
        ("X-Enterprise-Auth-Signature", "forged", "invalid_auth_context_signature"),
        ("X-Enterprise-Auth-Timestamp", "0", "stale_auth_context"),
    ),
)
def test_wired_context_still_refuses_bad_native_identity(
    monkeypatch, service, changed, value, reason
) -> None:
    for key, setting in _environment(service, AUTH_INPUTS).items():
        monkeypatch.setenv(key, setting)
    headers = _headers()
    headers[changed] = value
    assert (
        verify_service_principal(headers, load_default_enterprise_settings(service_name=service))
        == reason
    )


def test_authentication_alone_does_not_admit_a_financial_producer() -> None:
    environment = _environment("ingestion_service", AUTH_INPUTS)
    grants = parse_submission_grants(environment["LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON"])
    assert grants == ()
    assert (
        parse_registry_source_grants(environment["LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON"])
        == ()
    )
    grant = ProducerSubmissionGrant(
        "synthetic-tenant",
        "synthetic-portfolio",
        "synthetic-producer",
        ObservationFamily.CASH_AVAILABILITY,
    )
    context = TenantContext(
        TenantId("synthetic-tenant"), service_identity="synthetic-producer", identity_verified=True
    )
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED"):
        UnqualifiedProducerAuthority(grants).admit(context, grant)
    supplied = dict(AUTH_INPUTS)
    supplied["LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON"] = json.dumps(
        [
            {
                "tenant_id": grant.tenant_id,
                "portfolio_id": grant.portfolio_id,
                "producer_id": grant.producer_id,
                "family": grant.family.value,
            }
        ]
    )
    configured = _environment("ingestion_service", supplied)
    exact = parse_submission_grants(configured["LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON"])
    assert UnqualifiedProducerAuthority(exact).admit(context, grant).qualification == "unqualified"


def test_read_features_and_consumer_grants_remain_independent_closed_defaults() -> None:
    environment = _environment("query_control_plane_service", AUTH_INPUTS)
    assert (
        parse_neutral_source_read_grants(environment["PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON"])
        == ()
    )
    assert {environment[key] for key in FEATURE_KEYS} == {"false"}
    assert {environment[key] for key in ENFORCEMENT_KEYS["query_control_plane_service"]} == {"true"}


def test_operator_registry_and_read_grants_remain_exact_and_independent() -> None:
    scope = {
        "tenant_id": "synthetic-tenant",
        "source_system": "synthetic-producer",
        "registry_scope_id": "synthetic-scope",
        "products": ["PortfolioFinancialSourceCut"],
    }
    producer = _environment(
        "ingestion_service",
        {**AUTH_INPUTS, "LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON": json.dumps([scope])},
    )
    assert parse_registry_source_grants(producer["LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON"])
    enabled = {**AUTH_INPUTS, **dict.fromkeys(FEATURE_KEYS, "true")}
    no_consumer = _environment("query_control_plane_service", enabled)
    grants = parse_neutral_source_read_grants(
        no_consumer["PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON"]
    )
    selection = dict(
        service_identity="synthetic-observer",
        tenant_id="synthetic-tenant",
        source_system="synthetic-producer",
        registry_scope_id="synthetic-scope",
        product="PortfolioFinancialSourceCut",
    )
    with pytest.raises(PermissionError):
        require_neutral_source_read_grant(grants, **selection)
    row = {"service_identity": "synthetic-observer", **scope}
    configured = _environment(
        "query_control_plane_service",
        {**enabled, "PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON": json.dumps([row])},
    )
    grants = parse_neutral_source_read_grants(
        configured["PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON"]
    )
    require_neutral_source_read_grant(grants, **selection)
    with pytest.raises(PermissionError):
        require_neutral_source_read_grant(grants, **{**selection, "service_identity": "foreign"})


@pytest.mark.parametrize(
    ("service", "key", "parse", "grant"),
    (
        (
            "ingestion_service",
            "LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON",
            parse_submission_grants,
            {
                "tenant_id": "*",
                "portfolio_id": "p",
                "producer_id": "s",
                "family": "cash_availability",
            },
        ),
        (
            "ingestion_service",
            "LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON",
            parse_registry_source_grants,
            {
                "tenant_id": "t",
                "source_system": "s",
                "registry_scope_id": "*",
                "products": ["PortfolioFinancialSourceCut"],
            },
        ),
        (
            "query_control_plane_service",
            "PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON",
            parse_neutral_source_read_grants,
            {
                "service_identity": "*",
                "tenant_id": "t",
                "source_system": "s",
                "registry_scope_id": "r",
                "products": ["PortfolioFinancialSourceCut"],
            },
        ),
    ),
)
def test_operator_grant_wiring_preserves_native_wildcard_refusal(
    service, key, parse, grant
) -> None:
    supplied = {**AUTH_INPUTS, key: json.dumps([grant])}
    with pytest.raises(ValueError):
        parse(_environment(service, supplied)[key])


# These tests install the service-owned middleware and registered custody routers.
# Only persistence/retained storage is replaced; no tenant/principal/context is injected.
BRIDGE_ROLES = ("ingestion-write", "qcp-retained-post", "qcp-get")
BRIDGE_CAPABILITIES = {
    "ingestion-write": "ingestion.portfolio_historical_registries.write",
    "qcp-retained-post": "source_data.portfolio_historical_registry.read",
    "qcp-get": "core.security_audit.read",
}


def _bridge_headers(role: str, case: str = "valid") -> dict[str, str]:
    headers = _headers()
    headers.update(
        {
            "X-Tenant-Id": "tenant",
            "X-Service-Identity": "producer" if role == "ingestion-write" else "lotus-manage",
            "X-Capabilities": BRIDGE_CAPABILITIES[role],
            "X-Idempotency-Key": "synthetic-custody-bridge",
        }
    )
    if case == "wrong-capability":
        headers["X-Capabilities"] = "synthetic.unrelated.read"
    if case == "stale":
        headers["X-Enterprise-Auth-Timestamp"] = "0"
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers), AUTH_INPUTS["ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET"]
    )
    if case == "missing":
        headers.pop("X-Enterprise-Auth-Signature")
    elif case == "forged":
        headers["X-Enterprise-Auth-Signature"] = "forged"
    return headers


def _install_bridge_middleware(app, monkeypatch, role, observed):
    from src.services.ingestion_service.app import enterprise_readiness as ingestion_security
    from src.services.query_control_plane_service.app import enterprise_readiness as qcp_security

    service = "ingestion_service" if role == "ingestion-write" else "query_control_plane_service"
    for key, value in _environment(service, AUTH_INPUTS).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    @app.middleware("http")
    async def observe_native_context(request: Request, call_next):
        observed.append(getattr(request.state, "tenant_context", None))
        return await call_next(request)

    middleware = (
        ingestion_security.build_ingestion_enterprise_audit_middleware(
            max_write_payload_bytes_resolver=None
        )
        if role == "ingestion-write"
        else qcp_security.build_enterprise_audit_middleware()
    )
    app.middleware("http")(middleware)
    configure_standard_http_app(
        app,
        service_name=service,
        service_prefix="SYNTHETIC",
        logger=logging.getLogger("synthetic-custody-context"),
        id_generator=lambda prefix: f"{prefix}:synthetic-id",
    )

    @app.get("/health/ready")
    async def health_probe():
        return {"healthy": True}


def _ingestion_bridge(app, monkeypatch, grants):
    from src.services.ingestion_service.app.dependencies import (
        get_portfolio_financial_source_cut_commands,
    )
    from src.services.ingestion_service.app.routers import portfolio_financial_source_cuts as routes
    from src.services.ingestion_service.app.services import (
        portfolio_financial_source_cut_commands as custody_commands,
    )

    commands = custody_commands.PortfolioFinancialSourceCutCommands(
        parse_registry_source_grants(json.dumps(grants)),
        Mock(return_value=object()),
        Mock(side_effect=AssertionError("Storage must not be used by this context contract")),
    )
    # Native admission runs before this storage receipt lookup boundary.
    commands._original = AsyncMock(
        return_value=SimpleNamespace(
            job_id="synthetic-native-receipt",
            entity_type="portfolio_historical_registry_chunk",
            accepted_count=0,
        )
    )
    commands.submit = AsyncMock(wraps=commands.submit)
    app.include_router(routes.router)
    app.dependency_overrides[get_portfolio_financial_source_cut_commands] = lambda: commands
    payload = {
        "source_system": "producer",
        "registry_scope_id": "registry",
        "source_cut_id": "cut",
        "revision": 1,
        "chunk_index": 0,
        "members": [],
        "typed_content_hash": canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistryChunk:v1", "members": []}
        ),
    }
    return "/ingest/portfolio-historical-registry-chunks", payload, commands


def _retained_read_bridge(app, monkeypatch, grants, enabled):
    from src.services.query_control_plane_service.app.dependencies import (
        get_portfolio_financial_source_cuts_service,
    )
    from src.services.query_control_plane_service.app.exception_mappers import (
        register_query_control_plane_exception_handlers,
    )
    from src.services.query_control_plane_service.app.routers import portfolio_financial_source_cuts
    from tests.unit.services.query_control_plane_service.application import (
        test_portfolio_financial_source_cuts as retained,
    )

    reader, query, _, _ = retained.registry_fixture(0)
    service = retained.retained_service(reader)
    service.query = AsyncMock(wraps=service.query)
    monkeypatch.setenv("PORTFOLIO_NEUTRAL_SOURCE_READ_GRANTS_JSON", json.dumps(grants))
    monkeypatch.setenv("LOTUS_CORE_CAP_HISTORICAL_REGISTRY_READ_ENABLED", str(enabled).lower())
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)
    app.include_router(portfolio_financial_source_cuts.router)
    register_query_control_plane_exception_handlers(
        app, logger=logging.getLogger("synthetic-custody-context")
    )
    app.dependency_overrides[get_portfolio_financial_source_cuts_service] = lambda: service
    return (
        "/integration/portfolio-historical-registries/query",
        (query.model_copy(update={"view": "CUT"}).model_dump(mode="json")),
        service,
    )


def _bridge_application(monkeypatch, role, *, grant=True, enabled=True):
    app, observed = FastAPI(), []
    _install_bridge_middleware(app, monkeypatch, role, observed)
    scope = {
        "tenant_id": "tenant",
        "source_system": "producer",
        "registry_scope_id": "registry",
        "products": ["PortfolioHistoricalRegistry"],
    }
    if role == "ingestion-write":
        path, payload, boundary = _ingestion_bridge(app, monkeypatch, [scope] if grant else [])
    elif role == "qcp-retained-post":
        row = {"service_identity": "lotus-manage", **scope}
        path, payload, boundary = _retained_read_bridge(
            app, monkeypatch, [row] if grant else [], enabled
        )
    else:
        path, payload, boundary = "/support/security-audit/events", None, None

        @app.get(path)
        async def read_context(request: Request):
            context = request.state.tenant_context
            return {"identity_verified": context.identity_verified}

    return app, observed, path, payload, boundary


def _request_bridge(client, role, path, payload, headers):
    if role == "qcp-get":
        return client.get(path, headers=headers)
    return client.post(path, json=payload, headers=headers)


@pytest.mark.parametrize("role", BRIDGE_ROLES)
@pytest.mark.parametrize("case", ("valid", "missing", "forged", "stale", "wrong-capability"))
def test_overlay_installed_service_middleware_propagates_verified_context(monkeypatch, role, case):
    app, observed, path, payload, boundary = _bridge_application(monkeypatch, role)
    with TestClient(app) as client:
        response = _request_bridge(client, role, path, payload, _bridge_headers(role, case))
    if case == "valid":
        assert response.status_code == (202 if role == "ingestion-write" else 200), response.text
        assert len(observed) == 1
        context = observed[0]
        assert context.identity_verified is True
        assert context.tenant_id_text == "tenant"
        assert context.service_identity == (
            "producer" if role == "ingestion-write" else "lotus-manage"
        )
        if role == "ingestion-write":
            submitted = boundary.submit.await_args.args[0]
            assert submitted.tenant_context is context
            boundary._original.assert_awaited_once()
        elif role == "qcp-retained-post":
            boundary.query.assert_awaited_once()
            assert boundary.query.await_args.kwargs["tenant_id"] == "tenant"
            assert boundary.query.await_args.kwargs["service_identity"] == "lotus-manage"
    else:
        assert response.status_code == 403, response.text
        expected = {
            "missing": "missing_auth_context_signature",
            "forged": "invalid_auth_context_signature",
            "stale": "stale_auth_context",
            "wrong-capability": "missing_capability:" + BRIDGE_CAPABILITIES[role],
        }
        assert response.json()["reason"] == expected[case]
        assert observed == []  # Denied before the registered source boundary.
        if role == "ingestion-write":
            boundary.submit.assert_not_awaited()
        elif role == "qcp-retained-post":
            boundary.query.assert_not_awaited()


@pytest.mark.parametrize("role", BRIDGE_ROLES)
def test_disabling_enforcement_reproduces_missing_native_context_bridge(monkeypatch, role):
    app, observed, path, payload, boundary = _bridge_application(monkeypatch, role)
    if role == "qcp-get":
        monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "false")
    else:
        monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
        monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "false")
    with TestClient(app) as client:
        response = _request_bridge(client, role, path, payload, _bridge_headers(role))
    assert len(observed) == 1
    assert observed[0].identity_verified is False
    assert response.status_code == (200 if role == "qcp-get" else 403), response.text
    if role == "ingestion-write":
        boundary._original.assert_not_awaited()
    elif role == "qcp-retained-post":
        boundary.query.assert_not_awaited()


@pytest.mark.parametrize("role", ("ingestion-write", "qcp-retained-post"))
def test_verified_context_does_not_replace_the_native_source_grant(monkeypatch, role):
    app, observed, path, payload, boundary = _bridge_application(monkeypatch, role, grant=False)
    with TestClient(app) as client:
        response = _request_bridge(client, role, path, payload, _bridge_headers(role))
    assert response.status_code == 403, response.text
    assert observed[0].identity_verified is True
    if role == "ingestion-write":
        boundary._original.assert_not_awaited()
    else:
        boundary.query.assert_not_awaited()


def test_verified_consumer_and_grant_still_require_retained_read_feature(monkeypatch):
    role = "qcp-retained-post"
    app, observed, path, payload, boundary = _bridge_application(monkeypatch, role, enabled=False)
    with TestClient(app) as client:
        response = _request_bridge(client, role, path, payload, _bridge_headers(role))
    assert response.status_code == 503, response.text
    assert observed[0].identity_verified is True
    boundary.query.assert_not_awaited()


@pytest.mark.parametrize("role", ("ingestion-write", "qcp-retained-post"))
def test_enforcing_profile_preserves_unauthenticated_health_probe(monkeypatch, role):
    app, _, _, _, _ = _bridge_application(monkeypatch, role)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
