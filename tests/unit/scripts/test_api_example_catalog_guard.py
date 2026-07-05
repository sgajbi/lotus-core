from pathlib import Path

from scripts.api_example_catalog_guard import (
    find_api_example_catalog_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _registry() -> str:
    return """
{
  "routes": {
    "query_service": {
      "Operational Read": ["GET /portfolios/{portfolio_id}/positions"]
    }
  }
}
"""


def test_api_example_catalog_guard_accepts_verified_catalog(tmp_path: Path) -> None:
    _write(tmp_path / "docs/standards/route-contract-family-registry.json", _registry())
    _write(
        tmp_path / "docs/standards/verified-api-examples.v1.json",
        """
{
  "routeFamilyLinks": [
    {
      "service": "query_service",
      "family": "Operational Read",
      "exampleIds": [
        "success-example",
        "validation-example",
        "auth-example",
        "not-found-example",
        "conflict-example",
        "timeout-example",
        "degraded-example",
        "pagination-example"
      ]
    }
  ],
  "examples": [
    {
      "id": "success-example",
      "category": "success",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"correlation_id": "corr"} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "validation-example",
      "category": "validation_error",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"code": "VALIDATION_ERROR", "message": "invalid", "correlation_id": "corr", "details": {}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "auth-example",
      "category": "auth_permission_denial",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"code": "DENIED", "message": "denied", "correlation_id": "corr", "details": {}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "not-found-example",
      "category": "not_found",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"code": "NOT_FOUND", "message": "missing", "correlation_id": "corr", "details": {}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "conflict-example",
      "category": "conflict_idempotency",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"code": "CONFLICT", "message": "conflict", "correlation_id": "corr", "idempotency_key": "idem", "details": {}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "timeout-example",
      "category": "dependency_timeout",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"code": "TIMEOUT", "message": "timeout", "correlation_id": "corr", "details": {}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "degraded-example",
      "category": "degraded_source_data",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {},
      "response": {"body": {"correlation_id": "corr", "data_quality": {"state": "SOURCE_LIMITED"}} },
      "sensitivity": {"syntheticOnly": true}
    },
    {
      "id": "pagination-example",
      "category": "pagination_filtering_sorting",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/portfolios/{portfolio_id}/positions",
      "sourceTests": ["tests/unit/example.py"],
      "request": {"body": {"limit": 10}},
      "response": {"body": {"correlation_id": "corr", "page": {"next_page_token": "next"}} },
      "sensitivity": {"syntheticOnly": true}
    }
  ]
}
""",
    )

    assert find_api_example_catalog_findings(tmp_path) == []


def test_api_example_catalog_guard_rejects_missing_contract_metadata(tmp_path: Path) -> None:
    _write(tmp_path / "docs/standards/route-contract-family-registry.json", _registry())
    _write(
        tmp_path / "docs/standards/verified-api-examples.v1.json",
        """
{
  "routeFamilyLinks": [],
  "examples": [
    {
      "id": "bad-example",
      "category": "conflict_idempotency",
      "service": "query_service",
      "family": "Operational Read",
      "method": "GET",
      "path": "/unknown",
      "sourceTests": [],
      "request": {},
      "response": {"body": {"code": "CONFLICT", "message": "conflict"}},
      "sensitivity": {"syntheticOnly": false}
    }
  ]
}
""",
    )

    rules = {finding.rule for finding in find_api_example_catalog_findings(tmp_path)}

    assert "missing-required-api-example-category" in rules
    assert "missing-route-family-example-link" in rules
    assert "example-route-not-registered" in rules
    assert "missing-source-test-reference" in rules
    assert "missing-correlation-id" in rules
    assert "missing-problem-field" in rules
    assert "missing-idempotency-conflict-field" in rules
    assert "missing-synthetic-only-claim" in rules
