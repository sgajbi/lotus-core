# CR-1299 Performance Economics Source-Data Builder Split

## Scope

Issue cluster: GitHub issue #663, with supporting coverage for umbrella mapping issue #661.

This slice refactors `PerformanceComponentEconomics:v1` into explicit row mapping,
source-evidence policy, and response-envelope assembly modules.

## Objective

Reduce design-time complexity in the high-value performance-economics source-data product by
separating repository orchestration, typed row-to-DTO mapping, component/supportability policy,
lineage/runtime metadata, and final API response assembly.

## Changes

1. Added `performance_component_economics_rows.py` for typed
   `PerformanceEconomicsTransactionReadRecord` to `PerformanceComponentEconomicsRow` mapping.
2. Added `performance_component_economics_policy.py` for source lineage, component-family
   coverage, supportability state/reason, data-quality status, returned-page totals, and latest
   evidence timestamp policy.
3. Added `performance_component_economics_response.py` for final response assembly, request
   fingerprinting, page metadata, runtime metadata, supportability DTOs, lineage, and component
   totals.
4. Kept `performance_component_economics.py` as the orchestration and compatibility module so
   existing imports, route behavior, and tests remain stable.
5. Added direct policy tests for source-evidence classification, empty/partial page state, data
   quality, component-family coverage, and lineage.
6. Updated the implementation-backed methodology with field provenance and assembly-boundary truth.

## Behavior And Compatibility

This is a design-modularity slice inside the existing `query_service` deployable. It is not a
runtime service split.

No route path, request DTO, response DTO, OpenAPI schema, database query, pagination token,
sort-key, supportability value, data-quality value, lineage field, runtime metadata field,
component-total calculation, or row value changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py -q`
   - 21 passed.
2. `python scripts/test_manifest.py --suite boundary-mapping-conformance --quiet`
   - 6 passed.
3. `python -m ruff check src\services\query_service\app\services\performance_component_economics.py src\services\query_service\app\services\performance_component_economics_policy.py src\services\query_service\app\services\performance_component_economics_rows.py src\services\query_service\app\services\performance_component_economics_response.py tests\unit\services\query_service\services\test_performance_component_economics.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py`
   - passed.

4. `python -m ruff format --check src\services\query_service\app\services\performance_component_economics.py src\services\query_service\app\services\performance_component_economics_policy.py src\services\query_service\app\services\performance_component_economics_rows.py src\services\query_service\app\services\performance_component_economics_response.py tests\unit\services\query_service\services\test_performance_component_economics.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py`
   - passed.
5. `make quality-wiki-docs-gate`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.

## Documentation, Wiki, Context, And Skill Decision

Updated the implementation-backed methodology, mapping/anti-corruption boundary, codebase review
ledger, and repo-local engineering context.

No wiki update is required because no operator command, API route behavior, runtime support
workflow, or user-facing capability changed.

No central Lotus skill change is required. The reusable pattern is now documented in repo-local
mapping guidance: high-value source-data builders should split row mapping, source-evidence policy,
and response-envelope assembly before adding new behavior.

## Remaining Work

GitHub issue #663 is locally fixed for the required representative product pending PR CI/QA and
issue closure. Apply the same source-data builder split to additional products opportunistically
when they change, especially older `reference_data_mappers.py` functions that still combine row
adaptation and source-evidence defaults.
