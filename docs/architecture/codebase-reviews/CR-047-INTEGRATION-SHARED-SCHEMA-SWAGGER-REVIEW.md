# CR-047 Integration Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared policy and instrument-enrichment DTO schemas used by `query_control_plane_service`
integration endpoints.

Reviewed schemas:

- `EffectiveIntegrationPolicyResponse`
- `PolicyProvenanceMetadata`
- `InstrumentEnrichmentBulkRequest`
- `InstrumentEnrichmentBulkResponse`

## Findings

The integration router already had strong parameter and error documentation after CR-032, but the
shared policy-provenance and instrument-enrichment component schemas still needed stronger schema-
level examples and more explicit request wording.

## Actions Taken

- Added reusable examples for `policy_provenance` on the effective-policy response.
- Tightened the request description for bulk instrument enrichment.
- Added an OpenAPI integration assertion that verifies the richer component-schema descriptions are
  present in the published spec.

## Follow-up

Continue the same schema-depth pass on the next weakest shared integration DTO surface.

## Evidence

- `src/services/query_service/app/dtos/integration_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
