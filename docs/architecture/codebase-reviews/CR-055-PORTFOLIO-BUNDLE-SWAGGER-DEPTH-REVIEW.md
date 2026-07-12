# CR-055 Portfolio Bundle Swagger Depth Review

## Scope
- Portfolio bundle ingestion router and shared portfolio-bundle request DTO

## Findings
- The portfolio-bundle endpoint already had a strong high-level description, but its operational error responses were still thin.
- The shared `PortfolioBundleIngestionRequest` schema relied too heavily on one large example and lacked field-level descriptions/examples for each entity collection.
- That left Swagger weaker for schema-first onboarding than the already-hardened upload endpoints.

## Actions Taken
- Added field-level descriptions/examples for each entity collection in `PortfolioBundleIngestionRequest`.
- Added explicit `410`, `429`, and `503` response examples to the portfolio-bundle router.
- Added an OpenAPI integration assertion to lock the richer bundle contract in place.

## Follow-up
- Continue the write-plane Swagger pass on the next weakest ingestion DTO or router surface.

## Evidence
- `src/services/ingestion_service/app/DTOs/portfolio_bundle_dto.py`
- `src/services/ingestion_service/app/routers/portfolio_bundle.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
