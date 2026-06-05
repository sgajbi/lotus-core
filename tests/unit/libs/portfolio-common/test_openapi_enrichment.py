from portfolio_common.openapi_enrichment import enrich_openapi_schema
from portfolio_common.openapi_examples import build_schema_example, infer_description, infer_example


def test_infer_example_preserves_ordered_fallback_policy() -> None:
    assert infer_example("portfolioId", {"type": "string"}) == "DEMO_DPM_EUR_001"
    assert infer_example("status", {"enum": ["BLOCKED", "ACTIVE"]}) == "ACTIVE"
    assert infer_example("reviewStatus", {"enum": ["BLOCKED", "ACTIVE"]}) == "BLOCKED"
    assert infer_example("tags", {"type": "array", "items": {"type": "string"}}) == [
        "example_tags_item"
    ]
    assert infer_example("isActive", {"type": "boolean"}) is True
    assert infer_example("ttlHours", {"type": "integer"}) == 24
    assert infer_example("targetWeight", {"type": "number"}) == 0.125
    assert infer_example("effectiveDate", {"type": "string", "format": "date"}) == "2026-02-27"
    assert (
        infer_example("completedAt", {"type": "string", "format": "date-time"})
        == "2026-02-27T10:30:00Z"
    )


def test_infer_description_preserves_domain_rule_precedence() -> None:
    assert infer_description("PositionRecord", "portfolioId", {"type": "string"}) == (
        "Unique portfolio identifier."
    )
    assert (
        infer_description(
            "PositionRecord",
            "asOfDate",
            {"type": "string", "format": "date"},
        )
        == "Business date for as of date."
    )
    assert (
        infer_description(
            "PositionRecord",
            "updatedAt",
            {"type": "string", "format": "date-time"},
        )
        == "Timestamp for updated at."
    )
    assert infer_description("PositionRecord", "baseCurrency", {"type": "string"}) == (
        "ISO currency code for base currency."
    )
    assert infer_description("PositionRecord", "marketValue", {"type": "number"}) == (
        "Monetary value for market value."
    )
    assert infer_description("PositionRecord", "quantity", {"type": "number"}) == (
        "Quantity value for quantity."
    )
    assert infer_description("PositionRecord", "price", {"type": "number"}) == (
        "Rate/price value for price."
    )
    assert infer_description("PositionRecord", "lifecycleStatus", {"type": "string"}) == (
        "Current status for lifecycle status."
    )


def test_build_schema_example_merges_all_of_object_variants() -> None:
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {"portfolio_id": {"type": "string"}},
                "required": ["portfolio_id"],
            },
            {
                "type": "object",
                "properties": {"business_date": {"type": "string", "format": "date"}},
                "required": ["business_date"],
            },
        ]
    }

    assert build_schema_example(schema, root_schema={}) == {
        "portfolio_id": "example_value",
        "business_date": "2026-02-27",
    }


def test_build_schema_example_uses_first_available_one_of_variant() -> None:
    schema = {
        "oneOf": [
            {"type": "string", "title": "status", "enum": ["PENDING", "DONE"]},
            {"type": "integer", "title": "version"},
        ]
    }

    assert build_schema_example(schema, root_schema={}) == "ACTIVE"


def test_enrich_openapi_schema_populates_missing_operation_docs() -> None:
    schema = {
        "paths": {
            "/health/live": {"get": {"responses": {"200": {"description": "ok"}}}},
            "/metrics": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
        "components": {"schemas": {}},
    }

    enriched = enrich_openapi_schema(schema, service_name="query_service")
    assert enriched["paths"]["/health/live"]["get"]["summary"]
    assert enriched["paths"]["/health/live"]["get"]["description"]
    assert enriched["paths"]["/health/live"]["get"]["tags"] == ["Health"]
    assert enriched["paths"]["/metrics"]["get"]["tags"] == ["Monitoring"]


def test_enrich_openapi_schema_populates_schema_field_description_and_example() -> None:
    schema = {
        "paths": {},
        "components": {
            "schemas": {
                "PositionRecord": {
                    "type": "object",
                    "properties": {
                        "portfolioId": {"type": "string"},
                        "asOfDate": {"type": "string", "format": "date"},
                        "marketValue": {"type": "number"},
                    },
                }
            }
        },
    }

    enriched = enrich_openapi_schema(schema, service_name="query_service")
    props = enriched["components"]["schemas"]["PositionRecord"]["properties"]
    assert props["portfolioId"]["description"]
    assert props["portfolioId"]["example"] == "DEMO_DPM_EUR_001"
    assert props["asOfDate"]["example"] == "2026-02-27"
    assert isinstance(props["marketValue"]["example"], float)


def test_enrich_openapi_schema_populates_request_response_and_parameter_examples() -> None:
    schema = {
        "paths": {
            "/api/v1/reconcile/{portfolio_id}": {
                "post": {
                    "parameters": [
                        {"name": "portfolio_id", "in": "path", "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReconciliationRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ReconciliationResponse"
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "ReconciliationRequest": {
                    "type": "object",
                    "properties": {
                        "portfolio_id": {"type": "string", "example": "PORT-1"},
                        "business_date": {"type": "string", "format": "date"},
                    },
                    "required": ["portfolio_id", "business_date"],
                },
                "ReconciliationResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "example": "completed"},
                        "finding_count": {"type": "integer", "example": 0},
                    },
                    "required": ["status", "finding_count"],
                },
            }
        },
    }

    enriched = enrich_openapi_schema(schema, service_name="financial_reconciliation_service")
    operation = enriched["paths"]["/api/v1/reconcile/{portfolio_id}"]["post"]

    assert operation["parameters"][0]["example"] == "DEMO_DPM_EUR_001"
    assert operation["requestBody"]["content"]["application/json"]["example"] == {
        "portfolio_id": "PORT-1",
        "business_date": "2026-02-27",
    }
    assert operation["responses"]["200"]["content"]["application/json"]["example"] == {
        "status": "completed",
        "finding_count": 0,
    }


def test_enrich_openapi_schema_populates_error_response_examples() -> None:
    schema = {
        "paths": {
            "/api/v1/reconcile/{portfolio_id}": {
                "post": {
                    "summary": "Run reconcile",
                    "description": "Run controls.",
                    "tags": ["reconcile"],
                    "responses": {
                        "422": {
                            "description": "Validation error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "HTTPValidationError": {
                    "type": "object",
                    "properties": {
                        "detail": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/ValidationError"},
                        }
                    },
                    "required": ["detail"],
                },
                "ValidationError": {
                    "type": "object",
                    "properties": {
                        "loc": {"type": "array", "items": {"type": "string"}},
                        "msg": {"type": "string", "example": "Field required"},
                        "type": {"type": "string", "example": "missing"},
                    },
                    "required": ["loc", "msg", "type"],
                },
            }
        },
    }

    enriched = enrich_openapi_schema(schema, service_name="financial_reconciliation_service")
    example = enriched["paths"]["/api/v1/reconcile/{portfolio_id}"]["post"]["responses"]["422"][
        "content"
    ]["application/json"]["example"]

    assert example["detail"][0]["msg"] == "Field required"
    assert example["detail"][0]["type"] == "missing"
