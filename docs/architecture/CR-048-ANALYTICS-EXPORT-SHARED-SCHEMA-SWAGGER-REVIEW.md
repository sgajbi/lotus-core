# CR-048 Analytics Export Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared paging and export-result DTO schemas used by `query_control_plane_service` analytics input
contracts.

Reviewed schemas:

- `PageMetadata`
- `AnalyticsExportJobResponse`
- `AnalyticsExportJsonResultResponse`

## Findings

The analytics-input router already had strong request parameter and error documentation after
CR-031, but the reusable paging and export-result component models were still lighter than the
endpoint layer. That weakened schema-first inspection of export contracts.

## Actions Taken

- Added an explicit example for `PageMetadata.next_page_token`.
- Added a concrete result-row example for `AnalyticsExportJsonResultResponse.data`.
- Added an OpenAPI integration assertion that locks these richer component-schema descriptions in
  place.

## Follow-up

Continue the same schema-depth pass on the next weakest shared analytics-input DTO surface.

## Evidence

- `src/services/query_service/app/dtos/analytics_input_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
