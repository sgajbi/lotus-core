import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from scripts.quality.api_vocabulary_inventory import (
    _build_attribute_catalog,
    _extract_request_fields,
    _extract_service_inventory,
    _fallback_example,
    _schema_type,
    generate_inventory,
    main,
    validate_committed_inventory_parity,
    validate_inventory,
    validate_service_coverage,
)


def test_request_alternatives_keep_fields_and_variant_requiredness() -> None:
    components = {
        "schemas": {
            "LegacyFx": {
                "type": "object",
                "required": ["fx_rates"],
                "properties": {"fx_rates": {"type": "array", "items": {"type": "string"}}},
            },
            "RetainedCut": {
                "type": "object",
                "required": ["provider_id"],
                "properties": {"provider_id": {"type": "string"}},
            },
        }
    }
    operation = {
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/LegacyFx"},
                            {"$ref": "#/components/schemas/RetainedCut"},
                            {"type": "null"},
                        ]
                    }
                }
            }
        }
    }
    fields, controls = _extract_request_fields(operation, components)
    assert [field["name"] for field in fields] == ["fx_rates", "provider_id"]
    assert [field["schemaAlternative"] for field in fields] == ["LegacyFx", "RetainedCut"]
    assert all(field["requiredWithinAlternative"] and not field["required"] for field in fields)
    assert controls == []


def test_composed_exact_decimal_schema_prefers_lexical_contract() -> None:
    schema = {
        "anyOf": [
            {"type": "string"},
            {"type": "integer", "exclusiveMinimum": 0},
            {"type": "null"},
        ]
    }

    assert _schema_type(schema) == "string"
    assert _fallback_example("contract_rate", schema) == "1.2345"


@pytest.mark.parametrize("composition", ["anyOf", "oneOf"])
@pytest.mark.parametrize("primitive", ["string", "integer", "number", "boolean", "array"])
def test_nullable_primitive_compositions_keep_actual_wire_type(composition, primitive) -> None:
    schema = {composition: [{"type": primitive}, {"type": "null"}]}
    assert _schema_type(schema) == primitive


@pytest.mark.parametrize("composition", ["anyOf", "oneOf"])
def test_composition_type_controls_preserve_lexical_objects_and_references(composition) -> None:
    assert _schema_type({composition: [{"type": "integer"}, {"type": "string"}]}) == "string"
    assert _schema_type({composition: [{"type": "object"}, {"type": "null"}]}) == "object"
    assert _schema_type({composition: [{"type": "boolean"}, {"type": "string"}]}) == "object"
    assert _schema_type({"type": "object", "properties": {"id": {"type": "string"}}}) == "object"
    assert _schema_type({"$ref": "#/components/schemas/SourceIdentity"}) == "SourceIdentity"
    assert (
        _schema_type(
            {composition: [{"$ref": "#/components/schemas/SourceIdentity"}, {"type": "null"}]}
        )
        == "object"
    )


def test_literal_and_source_authority_examples_are_contractual() -> None:
    assert _fallback_example("event_type", {"const": "corporate_action.manifest.received"}) == (
        "corporate_action.manifest.received"
    )
    assert _fallback_example("source_content_hash", {"type": "string"}) == "a" * 64
    assert _fallback_example("source_revision", {"type": "string"}) == "revision-1"
    assert _fallback_example("tenant_id", {"type": "string"}) == "TENANT_SG"
    assert _fallback_example("corporate_action_type", {"type": "string"}) == "SPIN_OFF"


def _minimal_inventory() -> dict[str, Any]:
    return {
        "generatedAt": "2026-07-23T00:00:00+00:00",
        "application": "lotus-core",
        "sourceOpenApi": [
            {"service": "query_service", "version": "1.0.0", "openApiVersion": "3.1.0"}
        ],
        "attributeCatalog": [
            {
                "semanticId": "lotus.portfolio_id",
                "canonicalTerm": "portfolio_id",
                "preferredName": "portfolio_id",
                "description": "Unique portfolio identifier.",
                "example": "DEMO_DPM_EUR_001",
                "type": "string",
            }
        ],
        "endpoints": [
            {
                "operationId": "get_portfolio",
                "serviceGroup": "query",
                "method": "GET",
                "path": "/portfolios/{portfolio_id}",
                "summary": "Get portfolio",
                "description": "Returns portfolio details.",
                "request": {
                    "fields": [{"name": "portfolio_id", "semanticId": "lotus.portfolio_id"}]
                },
                "response": {
                    "fields": [{"name": "portfolio_id", "semanticId": "lotus.portfolio_id"}]
                },
            }
        ],
        "controlsCatalog": [
            {
                "name": "limit",
                "kind": "request_option",
                "description": "Pagination limit.",
                "default": 100,
                "exposure": "consumer_visible",
                "canonicalTerm": "limit",
                "semanticId": "lotus.limit",
            }
        ],
    }


def _write_inventory(path: Path, inventory: dict[str, Any]) -> bytes:
    path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return path.read_bytes()


def test_extract_request_fields_adds_fallback_description_and_example() -> None:
    operation = {
        "parameters": [
            {
                "name": "portfolio_id",
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "limit",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
            },
        ]
    }

    request_fields, controls = _extract_request_fields(operation, components={})

    by_name = {field["name"]: field for field in request_fields}
    assert by_name["portfolio_id"]["description"]
    assert by_name["portfolio_id"]["example"] == "PORTFOLIO_001"
    assert by_name["limit"]["description"]
    assert by_name["limit"]["example"] == 10
    assert len(controls) == 2


def test_validate_inventory_accepts_minimal_complete_structure() -> None:
    inventory = _minimal_inventory()

    errors = validate_inventory(inventory)
    assert errors == []


def _inventory_for_domain_term(term: str) -> dict[str, Any]:
    inventory = _minimal_inventory()
    attribute = inventory["attributeCatalog"][0]
    attribute.update(
        semanticId=f"lotus.{term}",
        canonicalTerm=term,
        preferredName=term,
        description="Source-owned business relationship or ingestion disposition.",
    )
    for section in ("request", "response"):
        inventory["endpoints"][0][section]["fields"] = [
            {"name": term, "semanticId": f"lotus.{term}"}
        ]
    return inventory


@pytest.mark.parametrize("term", ["ingestion_job_id", "ingestion_outcome"])
def test_exact_domain_qualified_business_terms_are_accepted(term: str) -> None:
    assert validate_inventory(_inventory_for_domain_term(term)) == []


@pytest.mark.parametrize(
    "term",
    [
        "ingestion_service_job_id",
        "ingestion_job_id_debug",
        "ingestion_portfolio_id",
        "ingestion_service_outcome",
        "ingestion_outcome_internal",
        "query_ingestion_outcome",
        "query_portfolio_id",
        "dto_job_id",
        "db_owner",
    ],
)
def test_domain_qualification_does_not_exempt_prefixes_or_near_misses(term: str) -> None:
    errors = validate_inventory(_inventory_for_domain_term(term))
    assert any("uses implementation-specific prefix" in error for error in errors)


@pytest.mark.parametrize("term", ["ingestion_job_id", "ingestion_outcome"])
def test_domain_qualified_catalog_semantics_cannot_be_rebound_to_another_namespace(
    term: str,
) -> None:
    inventory = _inventory_for_domain_term(term)
    alias = f"another_namespace.{term}"
    inventory["attributeCatalog"][0]["semanticId"] = alias
    for section in ("request", "response"):
        inventory["endpoints"][0][section]["fields"][0]["semanticId"] = alias
    assert (
        f"domain-qualified term '{term}' must retain semanticId 'lotus.{term}'"
        in validate_inventory(inventory)
    )


@pytest.mark.parametrize("term", ["ingestion_job_id", "ingestion_outcome"])
@pytest.mark.parametrize("name", ["job_id", "ingestionJobId"])
def test_domain_qualified_endpoint_links_reject_field_name_aliases(term: str, name: str) -> None:
    inventory = _inventory_for_domain_term(term)
    inventory["endpoints"][0]["response"]["fields"][0]["name"] = name
    assert (
        f"domain-qualified semanticId 'lotus.{term}' must retain name '{term}'"
        in validate_inventory(inventory)
    )


def test_domain_qualified_owner_cannot_alias_the_primary_job_identity() -> None:
    inventory = _inventory_for_domain_term("ingestion_job_id")
    inventory["attributeCatalog"].append(
        {
            **inventory["attributeCatalog"][0],
            "semanticId": "lotus.job_id",
            "canonicalTerm": "job_id",
            "preferredName": "job_id",
        }
    )
    inventory["endpoints"][0]["response"]["fields"][0]["semanticId"] = "lotus.job_id"
    assert (
        "domain-qualified term 'ingestion_job_id' must retain semanticId 'lotus.ingestion_job_id'"
        in validate_inventory(inventory)
    )


def test_domain_qualified_preferred_name_and_canonical_name_tampering_still_fails() -> None:
    inventory = _inventory_for_domain_term("ingestion_job_id")
    inventory["attributeCatalog"][0]["preferredName"] = "job_id"
    assert (
        "attribute 'lotus.ingestion_job_id' preferredName must match canonicalTerm"
        in validate_inventory(inventory)
    )
    inventory["attributeCatalog"][0].update(canonicalTerm="job_id", preferredName="job_id")
    assert (
        "domain-qualified semanticId 'lotus.ingestion_job_id' must retain name 'ingestion_job_id'"
        in validate_inventory(inventory)
    )


def test_domain_qualified_names_follow_actual_dto_and_openapi_relationships() -> None:
    from src.services.event_replay_service.app.main import app
    from src.services.event_replay_service.app.routers.ingestion_operations_examples import (
        INGESTION_EVIDENCE_BUNDLE_RESPONSE_EXAMPLE,
    )
    from src.services.ingestion_service.app.DTOs.ingestion_job_lifecycle_dto import (
        IngestionEvidenceBundleResponse,
        IngestionJobResponse,
    )
    from src.services.ingestion_service.app.DTOs.ingestion_job_replay_dto import (
        ConsumerDlqEventResponse,
    )

    owner_field = ConsumerDlqEventResponse.model_fields["ingestion_job_id"]
    assert get_args(owner_field.annotation) == (str, type(None))
    assert owner_field.default is None
    event_payload = copy.deepcopy(
        INGESTION_EVIDENCE_BUNDLE_RESPONSE_EXAMPLE["consumer_dlq_events"][0]
    )
    event_payload.update(ingestion_job_id=None, correlation_id="observability-only")
    event = ConsumerDlqEventResponse.model_validate(event_payload)
    assert event.ingestion_job_id is None and event.correlation_id == "observability-only"
    assert event.event_id == event_payload["event_id"]
    with pytest.raises(ValidationError):
        TypeAdapter(owner_field.annotation).validate_python(42)
    assert "job_id" in IngestionJobResponse.model_fields
    assert "ingestion_job_id" not in IngestionJobResponse.model_fields

    outcomes = ("accepted", "partially_accepted", "rejected", "quarantined", "empty")
    outcome_field = IngestionEvidenceBundleResponse.model_fields["ingestion_outcome"]
    assert get_args(outcome_field.annotation) == outcomes
    adapter = TypeAdapter(outcome_field.annotation)
    assert tuple(adapter.validate_python(value) for value in outcomes) == outcomes
    for execution_or_recovery_status in ("queued", "completed", "replayed", "repaired", ""):
        with pytest.raises(ValidationError):
            adapter.validate_python(execution_or_recovery_status)

    schema = app.openapi()
    models = schema["components"]["schemas"]
    owner_schema = models["ConsumerDlqEventResponse"]["properties"]["ingestion_job_id"]
    assert owner_schema["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert "ingestion_job_id" not in models["ConsumerDlqEventResponse"].get("required", [])
    assert models["IngestionEvidenceBundleResponse"]["properties"]["ingestion_outcome"][
        "enum"
    ] == list(outcomes)
    assert models["IngestionEvidenceBundleResponse"]["properties"]["consumer_dlq_events"]["items"][
        "$ref"
    ].endswith("/ConsumerDlqEventResponse")
    assert models["ConsumerDlqEventListResponse"]["properties"]["events"]["items"]["$ref"].endswith(
        "/ConsumerDlqEventResponse"
    )
    for path, model in [
        ("/ingestion/jobs/{job_id}/evidence", "IngestionEvidenceBundleResponse"),
        ("/ingestion/dlq/consumer-events", "ConsumerDlqEventListResponse"),
    ]:
        assert schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["$ref"].endswith("/" + model)

    endpoints, _ = _extract_service_inventory("event_replay_service", schema)
    fields = [field for endpoint in endpoints for field in endpoint["response"]["fields"]]
    owner_links = [field for field in fields if field["name"].endswith(".ingestion_job_id")]
    assert len(owner_links) == 2
    assert all(
        field["type"] == "string" and field["semanticId"] == "lotus.ingestion_job_id"
        for field in owner_links
    )
    outcome_links = [field for field in fields if field["name"] == "ingestion_outcome"]
    assert len(outcome_links) == 1 and outcome_links[0]["type"] == "string"
    assert outcome_links[0]["semanticId"] == "lotus.ingestion_outcome"
    inventory = generate_inventory({"event_replay_service": schema})
    assert validate_inventory(inventory) == []
    assert validate_service_coverage(inventory, {"event_replay_service": schema}) == []


def test_committed_inventory_parity_ignores_only_generated_timestamp(tmp_path: Path) -> None:
    generated = _minimal_inventory()
    tracked = copy.deepcopy(generated)
    tracked["generatedAt"] = "2026-07-22T00:00:00+00:00"
    inventory_path = tmp_path / "inventory.json"
    original_bytes = _write_inventory(inventory_path, tracked)

    assert validate_committed_inventory_parity(generated, inventory_path=inventory_path) == []
    assert inventory_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            lambda payload: payload["attributeCatalog"][0].__setitem__(
                "description", "Different portfolio identifier description."
            ),
            "$.attributeCatalog[0].description",
        ),
        (
            lambda payload: payload["attributeCatalog"][0].__setitem__("type", "integer"),
            "$.attributeCatalog[0].type",
        ),
        (
            lambda payload: payload["attributeCatalog"][0].__setitem__(
                "example", "PORTFOLIO_DIFFERENT"
            ),
            "$.attributeCatalog[0].example",
        ),
        (
            lambda payload: payload["endpoints"][0].__setitem__(
                "path", "/portfolios/{portfolio_id}/different"
            ),
            "$.endpoints[0].path",
        ),
    ],
)
def test_committed_inventory_parity_rejects_semantic_drift(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    expected_path: str,
) -> None:
    generated = _minimal_inventory()
    tracked = copy.deepcopy(generated)
    mutate(tracked)
    inventory_path = tmp_path / "inventory.json"
    original_bytes = _write_inventory(inventory_path, tracked)

    errors = validate_committed_inventory_parity(generated, inventory_path=inventory_path)

    assert len(errors) == 1
    assert expected_path in errors[0]
    assert "regenerate" in errors[0]
    assert inventory_path.read_bytes() == original_bytes


def test_committed_inventory_parity_rejects_malformed_json_without_mutation(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text("{not-json", encoding="utf-8")
    original_bytes = inventory_path.read_bytes()

    errors = validate_committed_inventory_parity(
        _minimal_inventory(), inventory_path=inventory_path
    )

    assert len(errors) == 1
    assert "is not valid JSON" in errors[0]
    assert inventory_path.read_bytes() == original_bytes


def test_committed_inventory_parity_rejects_malformed_catalog_shape(
    tmp_path: Path,
) -> None:
    tracked = _minimal_inventory()
    tracked["attributeCatalog"] = "not-a-list"
    inventory_path = tmp_path / "inventory.json"
    original_bytes = _write_inventory(inventory_path, tracked)

    errors = validate_committed_inventory_parity(
        _minimal_inventory(), inventory_path=inventory_path
    )

    assert errors == ["committed inventory.attributeCatalog must be a list"]
    assert inventory_path.read_bytes() == original_bytes


def test_generated_only_cli_does_not_claim_committed_parity(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["api_vocabulary_inventory.py"])
    monkeypatch.setattr(
        "scripts.quality.api_vocabulary_inventory.generate_inventory",
        lambda schemas: _minimal_inventory(),
    )
    monkeypatch.setattr(
        "scripts.quality.api_vocabulary_inventory._load_service_schemas",
        lambda: {"query_service": _service_schema("/portfolios/{portfolio_id}", "get_portfolio")},
    )

    assert main() == 0
    assert capsys.readouterr().out == "Inventory validation passed.\n"


def _service_schema(path: str, operation_id: str) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"version": "1.0.0"},
        "paths": {
            path: {
                "get": {
                    "operationId": operation_id,
                    "summary": "Read retained service evidence",
                    "description": "Returns source-owned retained evidence for this service.",
                    "responses": {"200": {"description": "Retained evidence response."}},
                }
            }
        },
    }


def _coverage_schemas() -> dict[str, dict[str, Any]]:
    return {
        "query_service": _service_schema("/health/live", "health_live"),
        "ingestion_service": _service_schema("/health/live", "health_live"),
        "query_control_plane_service": _service_schema(
            "/integration/financial-source-cuts/query", "query_financial_source_cuts"
        ),
        "event_replay_service": _service_schema("/health/live", "health_live"),
    }


def test_complete_service_inventory_preserves_owners_and_shared_route_identities() -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)

    assert validate_service_coverage(inventory, schemas) == []
    assert inventory["sourceOpenApi"] == [
        {"service": name, "version": "1.0.0", "openApiVersion": "3.1.0"} for name in schemas
    ]
    assert {
        (endpoint["serviceGroup"], endpoint["method"], endpoint["path"], endpoint["operationId"])
        for endpoint in inventory["endpoints"]
    } == {
        ("query", "GET", "/health/live", "health_live"),
        ("ingestion", "GET", "/health/live", "health_live"),
        (
            "query_control_plane_service",
            "GET",
            "/integration/financial-source-cuts/query",
            "query_financial_source_cuts",
        ),
        ("event_replay_service", "GET", "/health/live", "health_live"),
    }


def test_expanded_service_inventory_preserves_established_catalog_metadata_precedence() -> None:
    schemas = _coverage_schemas()
    # The authoritative loader places QCP before ingestion; existing catalog metadata must
    # retain the established query/ingestion first-wins order when other apps join.
    schemas = {
        name: schemas[name]
        for name in (
            "query_service",
            "query_control_plane_service",
            "ingestion_service",
            "event_replay_service",
        )
    }
    for service, description, example in [
        ("ingestion_service", "Existing source-owned custody reference.", "CUSTODY-EXISTING"),
        ("query_control_plane_service", "Control-plane custody reference.", "CUSTODY-CONTROL"),
    ]:
        operation = next(iter(schemas[service]["paths"].values()))["get"]
        operation["parameters"] = [
            {
                "name": "custody_reference",
                "in": "query",
                "description": description,
                "schema": {"type": "string", "example": example},
            }
        ]
    prior = generate_inventory(
        {name: schemas[name] for name in ("query_service", "ingestion_service")}
    )
    complete = generate_inventory(schemas)

    assert complete["attributeCatalog"] == prior["attributeCatalog"]
    assert [source["service"] for source in complete["sourceOpenApi"]] == [
        "query_service",
        "ingestion_service",
        "query_control_plane_service",
        "event_replay_service",
    ]
    assert validate_service_coverage(complete, schemas) == []


def test_generator_uses_shared_authority_without_a_private_service_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schemas = _coverage_schemas()
    schemas["future_operator_service"] = _service_schema("/operations/retained", "read_retained")
    monkeypatch.setattr(
        "scripts.quality.api_vocabulary_inventory._load_service_schemas", lambda: schemas
    )

    inventory = generate_inventory()
    assert validate_service_coverage(inventory, schemas) == []
    assert any(
        endpoint["serviceGroup"] == "future_operator_service"
        and endpoint["path"] == "/operations/retained"
        and endpoint["operationId"] == "read_retained"
        for endpoint in inventory["endpoints"]
    )


@pytest.mark.parametrize("remove_declaration", [False, True])
def test_service_coverage_rejects_omitted_control_plane_even_with_remaining_apps(
    remove_declaration: bool,
) -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    inventory["endpoints"] = [
        endpoint
        for endpoint in inventory["endpoints"]
        if endpoint["serviceGroup"] != "query_control_plane_service"
    ]
    if remove_declaration:
        inventory["sourceOpenApi"] = [
            source
            for source in inventory["sourceOpenApi"]
            if source["service"] != "query_control_plane_service"
        ]

    errors = validate_service_coverage(inventory, schemas)
    assert (
        "inventory missing OpenAPI operation: query_control_plane_service "
        "GET /integration/financial-source-cuts/query" in errors
    )
    assert (
        "inventory missing supported OpenAPI service: query_control_plane_service" in errors
    ) is remove_declaration


def test_service_coverage_rejects_one_missing_operation_in_a_declared_service() -> None:
    schemas = _coverage_schemas()
    schemas["query_service"]["paths"].update(
        _service_schema("/portfolios", "list_portfolios")["paths"]
    )
    inventory = generate_inventory(schemas)
    inventory["endpoints"] = [
        endpoint for endpoint in inventory["endpoints"] if endpoint["path"] != "/portfolios"
    ]

    assert validate_service_coverage(inventory, schemas) == [
        "inventory missing OpenAPI operation: query GET /portfolios"
    ]


def test_service_coverage_rejects_duplicate_source_and_operation_in_one_app() -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    inventory["sourceOpenApi"].append(copy.deepcopy(inventory["sourceOpenApi"][0]))
    inventory["endpoints"].append(copy.deepcopy(inventory["endpoints"][0]))

    assert validate_service_coverage(inventory, schemas) == [
        "duplicate sourceOpenApi service: query_service",
        "duplicate inventory operation: query GET /health/live",
        "duplicate inventory operationId in query: health_live",
    ]


def test_service_coverage_rejects_duplicate_operation_ids_on_distinct_paths_in_one_app() -> None:
    schemas = _coverage_schemas()
    schemas["query_service"]["paths"].update(_service_schema("/portfolios", "health_live")["paths"])
    inventory = generate_inventory(schemas)
    assert validate_service_coverage(inventory, schemas) == [
        "duplicate inventory operationId in query: health_live"
    ]


def test_service_coverage_rejects_a_declared_app_without_operations() -> None:
    schemas = _coverage_schemas()
    schemas["query_control_plane_service"]["paths"] = {}
    inventory = generate_inventory(schemas)
    assert validate_service_coverage(inventory, schemas) == [
        "OpenAPI service has no supported HTTP operations: query_control_plane_service"
    ]


@pytest.mark.parametrize(
    "endpoints, error",
    [
        (None, "inventory.endpoints must be a list"),
        (["not-an-object"], "inventory.endpoints entries must be objects"),
    ],
)
def test_service_coverage_rejects_malformed_operation_records(endpoints: Any, error: str) -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    inventory["endpoints"] = endpoints
    assert error in validate_service_coverage(inventory, schemas)


@pytest.mark.parametrize(
    "field,value,error",
    [
        (
            "operationId",
            "wrong_operation",
            "inventory operationId differs from OpenAPI: query GET /health/live",
        ),
        (
            "path",
            "/not-a-source-route",
            "inventory contains unknown OpenAPI operation: query GET /not-a-source-route",
        ),
        (
            "serviceGroup",
            "query_control_plane_service",
            "inventory contains unknown OpenAPI operation: "
            "query_control_plane_service GET /health/live",
        ),
    ],
)
def test_service_coverage_rejects_misattributed_or_changed_operation(
    field: str,
    value: str,
    error: str,
) -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    inventory["endpoints"][0][field] = value
    assert error in validate_service_coverage(inventory, schemas)


@pytest.mark.parametrize("sources", [None, [], ["not-an-object"], [{"service": "foreign_service"}]])
def test_service_coverage_rejects_empty_malformed_or_unknown_source_declarations(
    sources: Any,
) -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    inventory["sourceOpenApi"] = sources
    assert validate_service_coverage(inventory, schemas)


def test_service_coverage_rejects_empty_authority_and_stale_service_metadata() -> None:
    schemas = _coverage_schemas()
    inventory = generate_inventory(schemas)
    assert validate_service_coverage(inventory, {}) == [
        "OpenAPI service authority must be non-empty"
    ]
    inventory["sourceOpenApi"][0]["version"] = "older-version"
    assert validate_service_coverage(inventory, schemas) == [
        "sourceOpenApi metadata differs from current service: query_service"
    ]


def test_cli_rejects_incomplete_generated_service_coverage_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schemas = _coverage_schemas()
    incomplete = generate_inventory({"query_service": schemas["query_service"]})
    output = tmp_path / "must-not-be-written.json"
    monkeypatch.setattr(sys, "argv", ["api_vocabulary_inventory.py", "--output", str(output)])
    monkeypatch.setattr(
        "scripts.quality.api_vocabulary_inventory._load_service_schemas", lambda: schemas
    )
    monkeypatch.setattr(
        "scripts.quality.api_vocabulary_inventory.generate_inventory", lambda schemas: incomplete
    )

    assert main() == 1
    assert (
        "inventory missing supported OpenAPI service: query_control_plane_service"
        in capsys.readouterr().out
    )
    assert not output.exists()


def test_build_attribute_catalog_documents_semantic_once_without_alias_list() -> None:
    endpoints = [
        {
            "request": {
                "fields": [
                    {
                        "name": "portfolio_id",
                        "location": "path",
                        "type": "string",
                        "description": "Unique portfolio identifier.",
                        "example": "DEMO_DPM_EUR_001",
                        "canonicalTerm": "portfolio_id",
                        "semanticId": "lotus.portfolio_id",
                    }
                ]
            },
            "response": {
                "fields": [
                    {
                        "name": "session.portfolio_id",
                        "location": "body",
                        "type": "string",
                        "description": "Unique portfolio identifier.",
                        "example": "DEMO_DPM_EUR_001",
                        "canonicalTerm": "portfolio_id",
                        "semanticId": "lotus.portfolio_id",
                    }
                ]
            },
        }
    ]

    catalog, drift = _build_attribute_catalog(endpoints)
    assert len(catalog) == 1
    assert catalog[0]["semanticId"] == "lotus.portfolio_id"
    assert "aliases" not in catalog[0]
    assert drift == []
