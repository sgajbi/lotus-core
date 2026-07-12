from scripts.quality.api_vocabulary_inventory import (
    _build_attribute_catalog,
    _extract_request_fields,
    validate_inventory,
)


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
    inventory = {
        "application": "lotus-core",
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
                "method": "GET",
                "path": "/portfolios/{portfolio_id}",
                "summary": "Get portfolio",
                "description": "Returns portfolio details.",
                "request": {
                    "fields": [
                        {
                            "name": "portfolio_id",
                            "semanticId": "lotus.portfolio_id",
                        }
                    ]
                },
                "response": {
                    "fields": [
                        {
                            "name": "portfolio_id",
                            "semanticId": "lotus.portfolio_id",
                        }
                    ]
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

    errors = validate_inventory(inventory)
    assert errors == []


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
