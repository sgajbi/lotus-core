# CR-1209 Shared Runtime Settings

Date: 2026-06-30

## Objective

Continue GitHub issue #600 by moving query-service and query-control-plane runtime configuration
parsing onto a shared strict/local settings helper instead of preserving duplicated permissive
helpers.

## Change

- Added `portfolio_common.runtime_settings` with shared boolean, integer, string, and JSON-object
  env parsers.
- Added profile-aware strict validation controlled by `LOTUS_CORE_STRICT_CONFIG_VALIDATION=true` or
  non-local `ENVIRONMENT` values.
- Local/development/test profiles preserve explicit warning-backed fallback.
- Query-service and query-control-plane settings now reuse the shared helper while preserving their
  existing public `env_bool`, `env_int`, `env_str`, and `env_json_map` wrapper functions.
- Added lower-bound validation for query/control-plane resilience and enterprise-readiness settings:
  analytics export stale timeout, enterprise secret rotation days, and enterprise maximum write
  payload bytes.
- Added service-specific configuration error aliases so tests and callers can catch the strict
  failure path without coupling to duplicated local exception classes.

## Expected Improvement

Query-service and query-control-plane deployments no longer silently accept malformed enterprise
readiness and resilience settings in strict/non-local profiles. The parser behavior is now reusable
for additional Lotus runtime settings modules, reducing duplicated fallback logic and making future
strictness adoption testable from one shared contract.

## Tests Added

- Shared runtime settings local fallback for invalid bool, int, and JSON object values.
- Shared runtime settings strict rejection for invalid bool, out-of-range int, and invalid JSON.
- Query-service strict rejection for invalid integer, out-of-range payload size, and invalid JSON
  map settings.
- Query-control-plane strict rejection for invalid boolean, out-of-range rotation days, and invalid
  JSON map settings.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_runtime_settings.py tests/unit/services/query_service/test_query_service_settings.py tests/unit/services/query_control_plane_service/test_control_plane_settings.py -q`
  passed with 16 tests.
- Scoped Ruff lint and format checks passed for the changed settings modules and tests.
- `make typecheck` passed with 50 source files checked.
- `make quality-ruff-gate` passed.
- `make quality-ruff-format-gate` passed with 1,238 files already formatted.
- `make quality-complexity-gate` passed.
- `make quality-maintainability-gate` passed.
- `make architecture-guard` passed.
- `make quality-import-boundary-gate` passed with 2 kept contracts.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.

## Downstream Compatibility

Existing public helper names and settings dataclass fields are preserved. Existing unset env
defaults remain unchanged. The intentional behavior change is limited to strict/non-local profiles:
invalid query-service and query-control-plane configuration now raises a runtime configuration error
instead of silently using defaults. No API, OpenAPI, database schema, Kafka contract, or response
shape changed.

## Documentation And Wiki

Repository context, codebase review ledger, quality scorecard, and refactor health report were
updated. No repo-local wiki page changed because this slice did not add or change an operator
command, endpoint, runbook workflow, or published API contract.

## Remaining Follow-Up

Issue #600 remains open for remaining common runtime settings modules that still own local fallback
helpers, and for deciding whether the ingestion settings module should be migrated from its
first-slice local strict parser to `portfolio_common.runtime_settings`.
