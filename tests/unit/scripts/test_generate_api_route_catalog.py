from scripts import generate_api_route_catalog as catalog


def _openapi_fixture() -> dict:
    return {
        "ingestion_service": {
            "paths": {
                "/ingest/transactions": {
                    "post": {
                        "operationId": "ingest_transactions",
                        "summary": "Ingest transactions",
                        "description": "Accepts an idempotency key for replay-safe ingestion.",
                        "tags": ["Transactions"],
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/TransactionIngestionRequest"
                                    }
                                }
                            }
                        },
                        "responses": {
                            "202": {
                                "description": "Accepted",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": (
                                                "#/components/schemas/"
                                                "BatchIngestionAcceptedResponse"
                                            )
                                        }
                                    }
                                },
                            },
                            "422": {
                                "description": "Validation Error",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/HTTPValidationError"
                                        }
                                    }
                                },
                            },
                        },
                    }
                }
            }
        },
        "query_service": {
            "paths": {
                "/portfolios/{portfolio_id}/positions/": {
                    "get": {
                        "operationId": "list_positions",
                        "summary": "List positions",
                        "description": "List positions with pagination and sorting.",
                        "tags": ["Positions"],
                        "parameters": [
                            {"name": "portfolio_id", "in": "path"},
                            {"name": "limit", "in": "query"},
                            {"name": "sort", "in": "query"},
                        ],
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/PositionPage"}
                                    }
                                },
                            }
                        },
                    }
                },
                "/health/ready": {
                    "get": {
                        "operationId": "health_ready",
                        "summary": "Readiness",
                        "description": "Readiness probe.",
                        "tags": ["Health"],
                        "responses": {"200": {"description": "OK"}},
                    }
                },
            }
        },
    }


def _registry_fixture() -> dict:
    return {
        "routes": {
            "ingestion_service": {
                "Write Ingress": ["POST /ingest/transactions"],
            },
            "query_service": {
                "Operational Read": ["GET /portfolios/{portfolio_id}/positions"],
            },
        }
    }


def test_generate_api_route_catalog_enriches_openapi_routes_with_route_family() -> None:
    payload = catalog.generate_catalog_payload(_openapi_fixture(), _registry_fixture())

    entries = {
        (entry["service_app"], entry["method"], entry["path"]): entry
        for entry in payload["entries"]
    }

    write_entry = entries[("ingestion_service", "POST", "/ingest/transactions")]
    assert write_entry["route_family"] == "Write Ingress"
    assert write_entry["request_schema"] == "TransactionIngestionRequest"
    assert write_entry["response_schemas"][0]["schema"] == "BatchIngestionAcceptedResponse"
    assert write_entry["error_models"][0]["schema"] == "HTTPValidationError"
    assert write_entry["auth_requirement"] == "governed-enterprise-readiness"
    assert write_entry["audit_requirement"] == "audit-required"
    assert write_entry["idempotency_behavior"] == "idempotency-key-aware"
    assert write_entry["downstream_consumers"] == ["source-adapters", "operations"]

    read_entry = entries[("query_service", "GET", "/portfolios/{portfolio_id}/positions/")]
    assert read_entry["route_family"] == "Operational Read"
    assert read_entry["pagination"] == ["limit"]
    assert read_entry["filtering"] == ["portfolio_id"]
    assert read_entry["sorting"] == ["sort"]
    assert read_entry["idempotency_behavior"] == "safe-read"

    health_entry = entries[("query_service", "GET", "/health/ready")]
    assert health_entry["route_family"] == "Shared Operational"


def test_validate_api_route_catalog_reports_missing_and_stale_routes() -> None:
    generated = catalog.generate_catalog_payload(_openapi_fixture(), _registry_fixture())
    stale_payload = {
        **generated,
        "entries": [
            *generated["entries"][1:],
            {
                **generated["entries"][0],
                "service_app": "old_service",
                "method": "GET",
                "path": "/old",
            },
        ],
    }

    errors = catalog.validate_catalog(stale_payload, generated)

    assert any("missing implemented routes" in error for error in errors)
    assert any("contains stale routes" in error for error in errors)
    assert any("not current" in error for error in errors)
