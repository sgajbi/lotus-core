# CR-046 Operations Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared support and lineage DTO schemas used by `query_control_plane_service` operations endpoints.

Reviewed schemas:

- `CalculatorSloResponse`
- `LineageKeyListResponse`
- `SupportJobListResponse`

## Findings

The operations router itself already had strong parameter and error documentation after CR-029, but
its nested SLO and list-wrapper component schemas still lacked reusable examples. That made the
component layer weaker than the operator-facing endpoint descriptions.

## Actions Taken

- Added examples to the nested calculator SLO, lineage-key list, and support-job list schema
  properties.
- Added an OpenAPI integration assertion that verifies the richer component-schema descriptions are
  present in the published spec.

## Follow-up

Continue the same schema-depth pass on the next weakest shared control-plane DTO surface.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
