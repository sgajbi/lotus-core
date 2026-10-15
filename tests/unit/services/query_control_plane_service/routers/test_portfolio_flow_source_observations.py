"""Both registered flow reads preserve every opaque identity and exact authority."""

import logging
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.page_tokens import PageTokenCodec

from src.services.query_control_plane_service.app.application import (
    portfolio_flow_source_observations as flow_application,
)
from src.services.query_control_plane_service.app.contracts import (
    portfolio_flow_source_observations as contracts,
)
from src.services.query_control_plane_service.app.exception_mappers import (
    register_query_control_plane_exception_handlers,
)
from src.services.query_control_plane_service.app.ports.portfolio_flow_source_observations import (
    PersistedFlowCut,
    PersistedFlowEvent,
)
from src.services.query_control_plane_service.app.routers import (
    portfolio_flow_source_observations as routes,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, event

pytestmark = pytest.mark.unit
PREFIX = "/integration/financial-source-observations/flow-events/"
CANONICAL = PREFIX + "versions/{flow_source_record_revision}"
WINDOW = PREFIX + "query"


class Reader:
    def __init__(self, record):
        self.record = record
        self.calls = []
        self.cut_record = None
        self.cut_calls = []

    async def read_event(self, **selection):
        self.calls.append(selection)
        return self.record

    async def read_cut(self, **selection):
        self.cut_calls.append(selection)
        return self.cut_record


def application(
    source_system="producer",
    source_record_id="record",
    *,
    verified=True,
    tenant="tenant-synthetic",
    missing=False,
    portfolio="portfolio-synthetic",
    source_cut="source-cut",
):
    fact = event(source_record_id)
    fact = replace(
        fact,
        envelope=replace(
            fact.envelope,
            producer_id=source_system,
            portfolio_id=portfolio,
            source_cut_id=source_cut,
        ),
    )
    record = PersistedFlowEvent(fact, datetime(2026, 10, 16, tzinfo=UTC), "synthetic-receipt")
    reader = Reader(None if missing else record)
    manifest = cut(
        fact, portfolio_id=portfolio, source_system=source_system, source_cut_id=source_cut
    )
    reader.cut_record = (
        None
        if missing
        else PersistedFlowCut(manifest, record.received_at, "cut-receipt", (record,))
    )
    service = flow_application.PortfolioFlowObservationsService(
        reader, PageTokenCodec(secret="synthetic-route")
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_portfolio_flow_observations_service] = lambda: service
    register_query_control_plane_exception_handlers(app, logger=logging.getLogger(__name__))

    @app.middleware("http")
    async def authority(request, call_next):
        request.state.tenant_context = TenantContext(TenantId(tenant), identity_verified=verified)
        return await call_next(request)

    return app, reader, record


def lookup_path(source_system, source_record_id, *, revision=1, portfolio="portfolio-synthetic"):
    # Exercise the actual registered endpoint on both sides of the regression.
    path = next(route.path for route in routes.router.routes if "GET" in route.methods)
    return path.format(
        portfolio_id=quote(portfolio, safe=""),
        flow_source_record_revision=revision,
        source_system=quote(source_system, safe=""),
        source_record_id=quote(source_record_id, safe=""),
    )


@pytest.mark.parametrize(
    "portfolio,source_system,source_record_id",
    [
        ("portfolio-synthetic", "producer", "record"),
        ("desk/feed", "producer", "record"),
        ("portfolio-synthetic", "desk/feed", "record"),
        ("portfolio-synthetic", "producer", "batch/42"),
        ("portfolio/a", "desk/feed", "batch/42"),
        ("portfolio%2Fa", "desk%2Ffeed", "batch%2F42"),
        ("portfolio%252Fa", "desk%252Ffeed", "batch%252F42"),
        ("portfolio / + & ? # %2F", "desk team+east&query?=#", "record / + & ? # %2F"),
        ("口座/é", "組織/市場", "取引/é"),
    ],
)
def test_admissible_opaque_identities_reach_registered_revision_and_preserve_pins(
    portfolio, source_system, source_record_id
):
    require_observation_identity(source_system, "source_system")
    require_observation_identity(source_record_id, "source_record_id")
    require_observation_identity(portfolio, "portfolio_id")
    app, reader, record = application(source_system, source_record_id, portfolio=portfolio)
    with TestClient(app) as client:
        response = client.get(
            lookup_path(source_system, source_record_id, portfolio=portfolio),
            params={
                "portfolio_id": portfolio,
                "source_system": source_system,
                "source_record_id": source_record_id,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_system"] == source_system and body["source_record_id"] == source_record_id
    assert body["flow_source_record_revision"] == 1
    assert body["observation_id"] == body["content_hash"] == record.fact.content_hash
    assert body["receipt_job_id"] == "synthetic-receipt"
    assert datetime.fromisoformat(body["received_at"]) == record.received_at
    assert body["qualification"] == "unqualified" and body["degradation"]["status"] == "UNAVAILABLE"
    assert reader.calls == [
        {
            "tenant_id": "tenant-synthetic",
            "portfolio_id": portfolio,
            "source_system": source_system,
            "source_record_id": source_record_id,
            "flow_source_record_revision": 1,
        }
    ]


@pytest.mark.parametrize("field", ["portfolio_id", "source_system", "source_record_id"])
@pytest.mark.parametrize(
    "value", [None, "", " ", " leading", "trailing ", "x" * 129, "control\x00value"]
)
def test_missing_or_invalid_query_identity_refuses_before_source_read(field, value):
    app, reader, _ = application()
    params = {
        "portfolio_id": "portfolio-synthetic",
        "source_system": "producer",
        "source_record_id": "record",
    }
    if value is None:
        params.pop(field)
    else:
        params[field] = value
    with TestClient(app) as client:
        response = client.get(
            CANONICAL.format(portfolio_id="portfolio-synthetic", flow_source_record_revision=1),
            params=params,
        )
    assert response.status_code == 422, response.text
    assert reader.calls == []


@pytest.mark.parametrize("revision", [0, -1, "not-an-integer"])
def test_invalid_revision_refuses_before_source_read(revision):
    app, reader, _ = application()
    with TestClient(app) as client:
        response = client.get(
            CANONICAL.format(
                portfolio_id="portfolio-synthetic", flow_source_record_revision=revision
            ),
            params={
                "portfolio_id": "portfolio-synthetic",
                "source_system": "producer",
                "source_record_id": "record",
            },
        )
    assert response.status_code == 422
    assert reader.calls == []


@pytest.mark.parametrize(
    "verified,tenant,status,code",
    [
        (False, "tenant-synthetic", 403, "QCP_TENANT_SCOPE_FORBIDDEN"),
        (True, "foreign-tenant", 409, "QCP_FLOW_SOURCE_INCOMPATIBLE"),
    ],
)
def test_admitted_tenant_authority_is_preserved(verified, tenant, status, code):
    app, reader, _ = application(verified=verified, tenant=tenant)
    with TestClient(app) as client:
        response = client.get(
            CANONICAL.format(portfolio_id="portfolio-synthetic", flow_source_record_revision=1),
            params={
                "portfolio_id": "portfolio-synthetic",
                "source_system": "producer",
                "source_record_id": "record",
            },
        )
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == code
    assert len(reader.calls) == int(verified)


@pytest.mark.parametrize(
    "field,value",
    [
        ("portfolio_id", "foreign"),
        ("source_system", "foreign"),
        ("source_record_id", "foreign"),
        ("flow_source_record_revision", 2),
    ],
)
def test_wrong_returned_scope_cannot_be_substituted(field, value):
    app, reader, _ = application()
    selection = {
        "portfolio_id": "portfolio-synthetic",
        "flow_source_record_revision": 1,
        "source_system": "producer",
        "source_record_id": "record",
    }
    selection[field] = value
    with TestClient(app) as client:
        response = client.get(
            CANONICAL.format(**selection),
            params={
                key: selection[key] for key in ("portfolio_id", "source_system", "source_record_id")
            },
        )
    assert response.status_code == 409
    assert response.json()["error_code"] == "QCP_FLOW_SOURCE_INCOMPATIBLE"
    assert len(reader.calls) == 1


def test_absent_exact_revision_never_falls_back_to_latest():
    app, reader, _ = application(missing=True)
    with TestClient(app) as client:
        response = client.get(
            CANONICAL.format(portfolio_id="portfolio-synthetic", flow_source_record_revision=2),
            params={
                "portfolio_id": "portfolio-synthetic",
                "source_system": "producer",
                "source_record_id": "record",
            },
        )
    assert response.status_code == 404
    assert response.json()["error_code"] == "QCP_FLOW_SOURCE_NOT_FOUND"
    assert len(reader.calls) == 1 and reader.calls[0]["flow_source_record_revision"] == 2


def test_openapi_and_registered_lookup_are_canonical_required_query_identities():
    app, _, _ = application()
    paths = app.openapi()["paths"]
    lookups = [path for path, item in paths.items() if "get" in item]
    assert lookups == [CANONICAL]
    params = {p["name"]: p for p in paths[CANONICAL]["get"]["parameters"]}
    for name in ("portfolio_id", "source_system", "source_record_id"):
        assert params[name]["in"] == "query" and params[name]["required"]
        assert params[name]["schema"]["type"] == "string"
        assert (
            params[name]["schema"]["minLength"] == 1 and params[name]["schema"]["maxLength"] == 128
        )
    assert {p["name"] for p in params.values() if p["in"] == "path"} == {
        "flow_source_record_revision"
    }
    assert params["flow_source_record_revision"]["in"] == "path"
    assert params["flow_source_record_revision"]["schema"]["minimum"] == 1
    with TestClient(app) as client:
        old = client.get(
            "/integration/portfolios/portfolio-synthetic/financial-source-observations/flow-events/producer/record/versions/1"
        )
    assert old.status_code == 404


def window_request(reader):
    manifest = reader.cut_record.cut
    return contracts.PortfolioFlowObservationsRequest.model_validate(
        {
            "source_system": manifest.source_system,
            "source_cut_id": manifest.source_cut_id,
            "cut_revision": manifest.cut_revision,
            "manifest_hash": manifest.content_hash,
            "currency": manifest.currency,
            "window": {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            "page": {"page_size": 1, "page_token": None},
        }
    ).model_dump(mode="json")


def window_path(portfolio="portfolio-synthetic"):
    path = next(route.path for route in routes.router.routes if "POST" in route.methods)
    return path.format(portfolio_id=quote(portfolio, safe=""))


@pytest.mark.parametrize(
    "portfolio,producer,record_id,cut_id",
    [
        ("portfolio-synthetic", "producer", "record", "cut"),
        ("portfolio/a", "producer", "record", "cut"),
        ("portfolio-synthetic", "desk/feed", "record", "cut"),
        ("portfolio-synthetic", "producer", "record/a", "cut"),
        ("portfolio-synthetic", "producer", "record", "cut/a"),
        ("portfolio/a", "desk/feed", "record/a", "cut/a"),
        ("portfolio%2Fa", "desk%2Ffeed", "record%2Fa", "cut%2Fa"),
        ("portfolio%252Fa", "desk%252Ffeed", "record%252Fa", "cut%252Fa"),
        ("portfolio / + & ? # %2F", "desk + & ? # %2F", "record / + & ? #", "cut / + %2F"),
        ("口座/é", "組織/市場", "取引/é", "期間/é"),
    ],
)
def test_admissible_window_identities_reach_real_service_without_body_mutation(
    portfolio, producer, record_id, cut_id
):
    app, reader, record = application(producer, record_id, portfolio=portfolio, source_cut=cut_id)
    payload = window_request(reader)
    with TestClient(app) as client:
        response = client.post(
            window_path(portfolio), params={"portfolio_id": portfolio}, json=payload
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["portfolio_id"], body["source_system"], body["source_cut_id"]) == (
        portfolio,
        producer,
        cut_id,
    )
    assert body["manifest_hash"] == reader.cut_record.cut.content_hash
    assert body["events"][0]["source_record_id"] == record_id
    assert body["events"][0]["content_hash"] == record.fact.content_hash
    assert body["events"][0]["amount"] == str(record.fact.amount)
    assert body["window"] == payload["window"] and body["currency"] == payload["currency"]
    assert body["receipt_job_id"] == "cut-receipt" and body["qualification"] == "unqualified"
    assert body["pagination"]["total_count"] == body["pagination"]["returned_count"] == 1
    assert body["pagination"]["next_page_token"] is None
    assert len(reader.cut_calls) == 1
    forwarded = reader.cut_calls[0]
    assert forwarded["tenant_id"] == "tenant-synthetic" and forwarded["portfolio_id"] == portfolio
    assert forwarded["request"].model_dump(mode="json") == payload


@pytest.mark.parametrize("field", ["portfolio_id", "source_system", "source_cut_id"])
@pytest.mark.parametrize(
    "value", [None, "", " ", " leading", "trailing ", "x" * 129, "control\x00value"]
)
def test_window_invalid_query_or_body_identity_refuses_before_read(field, value):
    app, reader, _ = application()
    payload = window_request(reader)
    params = {"portfolio_id": "portfolio-synthetic"}
    target = params if field == "portfolio_id" else payload
    if value is None:
        target.pop(field)
    else:
        target[field] = value
    with TestClient(app) as client:
        response = client.post(WINDOW, params=params, json=payload)
    assert response.status_code == 422, response.text
    assert reader.cut_calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("portfolio_id", "foreign/portfolio"),
        ("source_system", "foreign/producer"),
        ("source_cut_id", "foreign/cut"),
        ("cut_revision", 2),
        ("manifest_hash", "0" * 64),
        ("currency", "USD"),
        ("window", {"from_date": "2026-01-02", "to_date": "2026-01-31"}),
        ("page", {"page_size": 1, "page_token": "tampered"}),
    ],
)
def test_window_wrong_scope_pins_window_and_cursor_are_refused(field, value):
    app, reader, _ = application()
    payload = window_request(reader)
    params = {"portfolio_id": "portfolio-synthetic"}
    (params if field == "portfolio_id" else payload)[field] = value
    with TestClient(app) as client:
        response = client.post(WINDOW, params=params, json=payload)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "QCP_FLOW_SOURCE_INCOMPATIBLE"
    assert len(reader.cut_calls) == 1


@pytest.mark.parametrize(
    "verified,tenant,status,code",
    [
        (False, "tenant-synthetic", 403, "QCP_TENANT_SCOPE_FORBIDDEN"),
        (True, "foreign-tenant", 409, "QCP_FLOW_SOURCE_INCOMPATIBLE"),
    ],
)
def test_window_tenant_authority_is_preserved(verified, tenant, status, code):
    app, reader, _ = application(verified=verified, tenant=tenant)
    with TestClient(app) as client:
        response = client.post(
            WINDOW, params={"portfolio_id": "portfolio-synthetic"}, json=window_request(reader)
        )
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == code
    assert len(reader.cut_calls) == int(verified)


@pytest.mark.parametrize("revision", [None, 0, -1, "not-an-integer"])
def test_window_missing_or_invalid_exact_cut_revision_refuses_before_read(revision):
    app, reader, _ = application()
    payload = window_request(reader)
    if revision is None:
        payload.pop("cut_revision")
    else:
        payload["cut_revision"] = revision
    with TestClient(app) as client:
        response = client.post(WINDOW, params={"portfolio_id": "portfolio-synthetic"}, json=payload)
    assert response.status_code == 422
    assert reader.cut_calls == []


def test_absent_cut_and_revision_do_not_select_latest_or_alias():
    app, reader, _ = application()
    payload = window_request(reader)
    reader.cut_record = None
    with TestClient(app) as client:
        missing = client.post(WINDOW, params={"portfolio_id": "portfolio-synthetic"}, json=payload)
        absent_revision = client.get(
            PREFIX + "versions", params={"portfolio_id": "portfolio-synthetic"}
        )
        old_window = client.post(
            "/integration/portfolios/portfolio-synthetic/financial-source-observations/flow-events/query",
            json=payload,
        )
        old_revision = client.get(
            "/integration/portfolios/portfolio-synthetic/financial-source-observations/flow-events/versions/1",
            params={"source_system": "producer", "source_record_id": "record"},
        )
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "QCP_FLOW_SOURCE_NOT_FOUND"
    assert absent_revision.status_code == old_window.status_code == old_revision.status_code == 404
    assert len(reader.cut_calls) == 1 and reader.calls == []


def test_both_flow_operations_have_only_required_opaque_query_scope_and_revision_path():
    app, _, _ = application()
    paths = app.openapi()["paths"]
    assert set(paths) == {CANONICAL, WINDOW}
    assert set(paths[CANONICAL]) == {"get"} and set(paths[WINDOW]) == {"post"}
    params = paths[WINDOW]["post"]["parameters"]
    assert len(params) == 1
    assert (params[0]["name"], params[0]["in"], params[0]["required"]) == (
        "portfolio_id",
        "query",
        True,
    )
    assert params[0]["schema"]["minLength"] == 1 and params[0]["schema"]["maxLength"] == 128


@pytest.mark.parametrize(
    "method,path",
    [("GET", CANONICAL.format(flow_source_record_revision=1)), ("POST", WINDOW)],
)
def test_effective_capability_matching_preserves_flow_authority_and_legacy_boundary(
    monkeypatch, method, path
):
    from portfolio_common.source_data_security import required_source_data_capability

    from src.services.query_control_plane_service.app import enterprise_readiness

    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)
    assert enterprise_readiness._required_capability(
        method, path
    ) == required_source_data_capability("PortfolioFinancialFlowObservations")
    old_prefix = "/integration/portfolios/portfolio-synthetic/financial-source-observations/"
    assert (
        enterprise_readiness._required_capability(method, old_prefix + "flow-events/query") is None
    )
    assert enterprise_readiness._required_capability(
        "POST", old_prefix + "query"
    ) == required_source_data_capability("PortfolioFinancialSourceObservations")
