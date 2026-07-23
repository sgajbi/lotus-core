import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.quality.api_vocabulary_inventory import (
    _build_attribute_catalog,
    _extract_request_fields,
    main,
    validate_committed_inventory_parity,
    validate_inventory,
)


def _minimal_inventory() -> dict[str, Any]:
    return {
        "generatedAt": "2026-07-23T00:00:00+00:00",
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
        "scripts.quality.api_vocabulary_inventory.generate_inventory", _minimal_inventory
    )

    assert main() == 0
    assert capsys.readouterr().out == "Inventory validation passed.\n"


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
