# CR-1254 Ingestion Gateway Rate-Limit Policy

Date: 2026-07-01

## Objective

Close the remaining local implementation gap for GitHub issue #684 by making the production
gateway-owned ingestion write rate-limit control a concrete, repo-owned contract instead of a
narrative follow-up. CR-1196 declared local versus gateway-backed scope, and CR-1225 made that
scope truth regression-blocking. This slice adds the governed gateway policy artifact and endpoint
coverage guard needed to keep scaled-service rate-limit evidence synchronized with the active
ingestion write surface.

## Change

- Added
  `contracts/operational-controls/ingestion-write-rate-limit-gateway-policy.v1.json`.
- Declared governed policy ID `lotus-core-ingestion-write-global-v1`.
- Declared the policy owner as `lotus-platform-gateway` and the effective scope as
  `global_service`.
- Required gateway-backed runtime scopes:
  `upstream_gateway` and `local_process_with_upstream_gateway`.
- Captured the default rolling-window budgets already used by the local limiter:
  60 seconds, 120 requests, and 10000 records.
- Listed every locally rate-limited ingestion write endpoint template that the upstream gateway
  policy must cover.
- Added `scripts/ingestion_gateway_rate_limit_policy_guard.py`.
- Added `make ingestion-gateway-rate-limit-policy-guard` and wired it into `make lint`.
- Added focused guard tests proving current truth passes and endpoint/docs drift fails.

## Expected Improvement

The scaled-deployment abuse-protection pattern is now machine-readable and CI-enforced:

- local-process limiting remains explicitly local,
- gateway-backed global enforcement requires a concrete policy ID,
- the policy endpoint set must stay in sync with route-level limiter usage,
- default budgets must stay aligned with the service settings,
- denial observability remains bounded to `endpoint`, `reason`, and `enforcement_scope`,
- platform runtime validation remains explicit instead of being implied by Core documentation.

This reduces the chance that future agent or operator changes reintroduce the original defect class:
claiming global rate-limit protection from local process state or from undocumented gateway intent.

## Tests Added

- `tests/unit/scripts/test_ingestion_gateway_rate_limit_policy_guard.py`
  - accepts current repository truth,
  - rejects a missing guarded endpoint template,
  - rejects missing documentation anchors for the governed policy ID.

## Validation Evidence

Validation recorded before commit:

- `python scripts\ingestion_gateway_rate_limit_policy_guard.py` passed.
- `python -m pytest tests\unit\scripts\test_ingestion_gateway_rate_limit_policy_guard.py tests\unit\scripts\test_ingestion_rate_limit_scope_guard.py tests\unit\services\ingestion_service\test_ops_controls.py tests\unit\services\ingestion_service\test_settings.py -q --tb=short`
  passed with 28 tests.
- `python -m ruff check scripts\ingestion_gateway_rate_limit_policy_guard.py tests\unit\scripts\test_ingestion_gateway_rate_limit_policy_guard.py --ignore E501,I001`
  passed.
- `python -m ruff format --check scripts\ingestion_gateway_rate_limit_policy_guard.py tests\unit\scripts\test_ingestion_gateway_rate_limit_policy_guard.py`
  passed.
- `make ingestion-rate-limit-scope-guard` passed.
- `make ingestion-gateway-rate-limit-policy-guard` passed.
- `make lint` passed, including the new gateway policy guard.
- `make typecheck` passed with no issues in 50 source files.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.
- Stranded-truth reconciliation found only active Dependabot branches for GitHub Actions and
  Python runtime dependency maintenance; neither contains unique durable #684 contract truth.

## Downstream Compatibility

No route path, request DTO, response DTO, HTTP status, OpenAPI schema, database schema, Kafka topic,
event payload, default rate-limit budget, or local-process runtime behavior changed.

This slice is a contract and CI-enforcement improvement. Production deployments that select
gateway-backed scopes still require platform ingress configuration for
`lotus-core-ingestion-write-global-v1`; Core now owns the source contract and guard that platform
runtime validation must consume.

## Documentation And Wiki Decision

- Updated `docs/operations/ingestion-api-gold-standard.md`.
- Updated the codebase review ledger.
- Updated `REPOSITORY-ENGINEERING-CONTEXT.md`.
- Updated `quality/quality_scorecard.md`.
- Updated `quality/refactor_health_report.md`.
- No repo-local wiki update is required because ingestion rate-limit operator truth is authored in
  `docs/operations/ingestion-api-gold-standard.md`, and this slice does not change a wiki-sourced
  operator workflow.

## Remaining Follow-Up

- PR/CI/QA must validate this branch before #684 can be closed.
- `lotus-platform` must provide runtime ingress proof for the
  `lotus-core-ingestion-write-global-v1` policy ID before Lotus claims the gateway control is live
  in an environment.
- A Redis or other shared-store token bucket remains a separate future option if Lotus chooses
  service-owned global enforcement instead of gateway-owned global enforcement.
