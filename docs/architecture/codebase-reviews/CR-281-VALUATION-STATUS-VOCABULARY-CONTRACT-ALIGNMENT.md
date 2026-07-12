# CR-281 Valuation Status Vocabulary Contract Alignment

## Summary

The query-service lineage and support DTO examples still advertised valuation/support completion
status as `DONE`, while the durable runtime and repository-backed tests use `COMPLETE`.

## Finding

- Class: API vocabulary / contract drift
- Consequence: client developers and operators could be taught the wrong status vocabulary from
  OpenAPI examples and query-service test fixtures, which increases the risk of brittle client-side
  parsing and documentation drift across services.

## Action Taken

- updated query-service DTO examples in
  `src/services/query_service/app/dtos/operations_dto.py`
- updated query-service unit and router dependency tests to use `COMPLETE` for valuation lineage
  status examples
- kept the support-job operational-state helper tolerant of completion statuses, but aligned the
  published contract and tests to the durable vocabulary actually used by the runtime

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py -q`
  - `80 passed`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
  - passed
- `python scripts/openapi_quality_gate.py`
  - passed

## Follow-up

- keep watching for vocabulary drift where query-service examples, router tests, and durable
  service state can quietly diverge even when the behavior still “works”
