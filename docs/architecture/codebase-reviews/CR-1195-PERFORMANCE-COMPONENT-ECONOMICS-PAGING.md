# CR-1195: Performance Component Economics Paging

Date: 2026-06-30

## Objective

Address GitHub issue #682 by making `PerformanceComponentEconomics:v1` row-level evidence bounded
and cursor-pageable. The endpoint should not materialize every transaction, cashflow, and cost row
for a portfolio/window when consumers only need a bounded response page.

## Change

- Added optional `page` controls to `PerformanceComponentEconomicsRequest` using the existing signed
  query-control-plane page-token codec.
- Added response `page` metadata and explicit `component_totals_scope="returned_page"`.
- Added request-scoped keyset cursor validation over normalized
  `(security_id, transaction_date, transaction_id)` and HTTP 400 mapping for malformed or
  cross-scope page tokens.
- Changed the repository read to accept `after_key` and `limit`, order deterministically by the
  published keyset, and read `page_size + 1` rows to determine whether another page exists.
- Marked non-terminal pages `DEGRADED` with reason `PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL`
  and `data_quality_status="PARTIAL"` so downstream consumers cannot mistake a single page for the
  full requested window.

## Expected Improvement

Large performance-component-economics windows now scale row materialization with the requested page
size instead of the full matched transaction window. The endpoint remains deterministic and resumable
while making page-scoped totals explicit, reducing memory pressure, response size, timeout risk, and
downstream ambiguity.

## Tests Added

- Service tests prove page-size orchestration calls the repository with `limit=page_size + 1`,
  returns only the requested page, emits next-page token payloads, and marks partial pages as
  degraded.
- Service tests reject cross-scope and malformed page tokens before repository access.
- Repository SQL-shape tests prove normalized keyset ordering, `after_key` predicates, filters, and
  `LIMIT`.
- Router tests prove malformed page-token/service validation errors map to HTTP 400.
- OpenAPI schema coverage continues to prove the performance-component-economics schema family is
  fully documented.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/services/query_service/dtos/test_reference_integration_dto.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_performance_component_economics_success_path tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_performance_component_economics_maps_missing_portfolio_to_404 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_performance_component_economics_maps_bad_token_to_400 tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_performance_component_economics_schema_family -q`
  passed with 67 tests.
- `python -m ruff check src/services/query_service/app/dtos/reference_integration_performance_component_economics_dto.py src/services/query_service/app/services/performance_component_economics.py src/services/query_service/app/services/integration_service.py src/services/query_service/app/repositories/transaction_repository.py src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/services/query_service/dtos/test_reference_integration_dto.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py`
  passed.
- `python -m ruff format --check src/services/query_service/app/dtos/reference_integration_performance_component_economics_dto.py src/services/query_service/app/services/performance_component_economics.py src/services/query_service/app/services/integration_service.py src/services/query_service/app/repositories/transaction_repository.py src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/services/query_service/dtos/test_reference_integration_dto.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py`
  passed.

## Downstream Compatibility

Route path, existing filter fields, row fields, component amount formulas, lineage fields,
source-owner declaration, and existing no-evidence behavior are preserved. Existing consumers that
do not provide `page` receive the default page size and the same response shape plus new additive
page metadata.

The intentional contract change is that `rows` and `component_totals` are explicitly page-scoped.
Consumers that require full-window totals must follow `page.next_page_token` until exhausted or wait
for a future aggregate contract. Non-terminal pages now report `DEGRADED` and `PARTIAL` rather than
claiming full-window readiness.

## Documentation

- Updated the performance-component-economics methodology.
- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.
- Updated repo-local wiki source for the mesh data product description because the consumer-visible
  paging and page-scoped totals contract changed.

## Follow-Up

Issue #682 remains open for PR/CI/QA evidence, downstream consumer rollout review, and production
query-plan/index review against large performance evidence books. A future full-window aggregate
contract can be added separately if `lotus-performance` needs totals without iterating row pages.
