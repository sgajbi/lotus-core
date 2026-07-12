# CR-045 Capabilities Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared capability and workflow DTO schemas used by `query_control_plane_service` for
`/integration/capabilities`.

Reviewed schemas:

- `FeatureCapability`
- `WorkflowCapability`

## Findings

The capabilities endpoint itself already had strong query-parameter documentation after CR-033, but
its nested capability/workflow component schemas still lacked schema-level examples. That made the
contract usable in Swagger only if the consumer inspected the top-level endpoint example instead of
its reusable component models.

## Actions Taken

- Added field-level examples to the nested capability and workflow component schemas.
- Added an OpenAPI integration assertion that verifies the richer component-schema descriptions are
  present in the published spec.

## Follow-up

Continue the same schema-depth pass on other shared control-plane DTOs where endpoint contracts are
already strong but nested components are still thin.

## Evidence

- `src/services/query_service/app/dtos/capabilities_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
