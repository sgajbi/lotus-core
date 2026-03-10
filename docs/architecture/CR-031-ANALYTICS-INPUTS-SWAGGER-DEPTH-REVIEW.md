# CR-031 Analytics Inputs Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the control-plane Swagger/OpenAPI contract for analytics-input endpoints.

## Findings

- The shared analytics DTOs were already relatively mature.
- The main remaining weakness was router-level contract depth in
  `query_control_plane_service/app/routers/analytics_inputs.py`:
  - portfolio and export path parameters lacked explicit descriptions/examples
  - common `400`, `404`, and `422` error responses had no concrete examples
  - downstream consumers would get a valid schema, but not an operator-grade API contract

## Actions Taken

- Added path parameter descriptions/examples for:
  - `portfolio_id`
  - `job_id`
- Added concrete response examples for:
  - invalid analytics request
  - portfolio not found
  - insufficient analytics source data
  - export job not found
  - export job incomplete
- Added an OpenAPI integration assertion covering:
  - analytics-input path parameter docs
  - export result path parameter docs
  - representative error examples

## Follow-up

- Continue the same depth pass on the next weakest active HTTP surface.
- Favor router-local response examples where the behavior is service-owned, even when DTOs are
  shared.

## Evidence

- `src/services/query_control_plane_service/app/routers/analytics_inputs.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
