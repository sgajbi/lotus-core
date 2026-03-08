from scripts.openapi_quality_gate import evaluate_schema


def test_evaluate_schema_flags_missing_contract_fields() -> None:
    schema = {
        "paths": {
            "/api/v1/positions": {
                "get": {
                    "operationId": "get_positions",
                    "summary": "Get positions",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }

    errors = evaluate_schema(schema, service_name="query_service")
    assert any("missing description" in error for error in errors)
    assert any("missing tags" in error for error in errors)
    assert any("missing error response" in error for error in errors)


def test_evaluate_schema_flags_duplicate_operation_ids() -> None:
    schema = {
        "paths": {
            "/api/v1/a": {
                "get": {
                    "operationId": "dup_op",
                    "summary": "A",
                    "description": "A",
                    "tags": ["t"],
                    "responses": {"200": {"description": "ok"}, "400": {"description": "bad"}},
                }
            },
            "/api/v1/b": {
                "get": {
                    "operationId": "dup_op",
                    "summary": "B",
                    "description": "B",
                    "tags": ["t"],
                    "responses": {"200": {"description": "ok"}, "400": {"description": "bad"}},
                }
            },
        }
    }

    errors = evaluate_schema(schema, service_name="query_service")
    assert any("duplicate operationId" in error for error in errors)


def test_evaluate_schema_accepts_documented_operation() -> None:
    schema = {
        "paths": {
            "/api/v1/positions": {
                "get": {
                    "operationId": "get_positions",
                    "summary": "Get positions",
                    "description": "Returns latest positions.",
                    "tags": ["positions"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"example": {"items": []}}},
                        },
                        "400": {"description": "bad request"},
                    },
                    "parameters": [{"name": "portfolio_id", "in": "query", "example": "PORT-1"}],
                }
            }
        }
    }

    assert evaluate_schema(schema, service_name="query_service") == []


def test_evaluate_schema_flags_missing_schema_field_description_and_example() -> None:
    schema = {
        "paths": {
            "/api/v1/positions": {
                "get": {
                    "operationId": "get_positions",
                    "summary": "Get positions",
                    "description": "Returns latest positions.",
                    "tags": ["positions"],
                    "responses": {
                        "200": {"description": "ok"},
                        "400": {"description": "bad request"},
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Position": {
                    "type": "object",
                    "properties": {
                        "securityId": {"type": "string"},
                    },
                }
            }
        },
    }

    errors = evaluate_schema(schema, service_name="query_service")
    assert any("missing schema field metadata" in error for error in errors)
    assert any("Position.securityId: missing description" in error for error in errors)
    assert any("Position.securityId: missing example" in error for error in errors)


def test_evaluate_schema_flags_missing_operation_examples() -> None:
    schema = {
        "paths": {
            "/api/v1/reconcile": {
                "post": {
                    "operationId": "run_reconcile",
                    "summary": "Run reconcile",
                    "description": "Run controls.",
                    "tags": ["reconcile"],
                    "parameters": [
                        {"name": "portfolio_id", "in": "query", "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "portfolio_id": {
                                            "type": "string",
                                            "example": "PORT-1",
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        },
                        "400": {"description": "bad request"},
                    },
                }
            }
        }
    }

    errors = evaluate_schema(schema, service_name="query_service")
    assert any("missing request example" in error for error in errors)
    assert any("missing parameter example" in error for error in errors)
    assert any("missing success response example" in error for error in errors)
