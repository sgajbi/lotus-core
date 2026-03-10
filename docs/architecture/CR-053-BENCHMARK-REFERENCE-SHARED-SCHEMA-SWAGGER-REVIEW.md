# CR-053 Benchmark Reference Shared Schema Swagger Review

## Scope
- Shared benchmark, index, risk-free, coverage, and classification DTOs in `reference_integration_dto.py`

## Findings
- The integration router for benchmark/reference data had become materially stronger in CR-052.
- The shared component schemas underneath it still had thin example coverage for catalog, lineage, and coverage metadata.
- That left Swagger stronger at the operation layer than at the reusable component layer.

## Actions Taken
- Added schema-level examples for:
  - benchmark and index catalog responses
  - market-series lineage and quality summary
  - index, benchmark, and risk-free lineage metadata
  - coverage observed/expected dates and quality distribution
  - classification taxonomy response records
- Added OpenAPI integration assertions to lock those component contracts in place.

## Follow-up
- Continue the same schema-depth pass on the next weakest active shared DTO surface.

## Evidence
- `src/services/query_service/app/dtos/reference_integration_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
