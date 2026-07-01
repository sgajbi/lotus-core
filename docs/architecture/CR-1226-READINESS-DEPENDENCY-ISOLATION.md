# CR-1226 Readiness Dependency Isolation

Date: 2026-07-01

## Objective

Fix GitHub issue #599 by making shared `/health/ready` dependency checks bounded and
failure-isolated. The slice promotes the reusable platform pattern that readiness endpoints should
classify dependency failure modes instead of letting one slow or unexpected dependency check
dominate the whole readiness request.

## Change

- Added per-dependency readiness timeout handling to `portfolio_common.health.create_health_router`.
- Added `DependencyReadinessResult` and explicit readiness statuses:
  `ok`, `unavailable`, `timeout`, and `error`.
- Changed readiness orchestration to run dependency probes with `asyncio.gather(...,
  return_exceptions=True)` and a per-check `asyncio.wait_for(...)` budget.
- Preserved the existing top-level response shape:
  - ready responses still return `{"status": "ready", "dependencies": {...}}`,
  - not-ready responses still raise HTTP 503 with `detail.status="not_ready"` and the dependency
    map.
- Added tests for DB timeout, Kafka timeout, dependency exception isolation, cached ready, cached
  not-ready, unknown dependencies, and mixed dependency states.

## Expected Improvement

Readiness is now a bounded orchestration surface. A slow database, Kafka, or future dependency
probe cannot hang the entire endpoint until the dependency's own lower-level timeout expires.
Operators can distinguish dependency `timeout`, `unavailable`, and unexpected `error` states while
clients retain the existing top-level ready/not-ready contract.

## Tests Added

- DB timeout classification.
- Kafka timeout classification.
- Dependency exception classification.
- Cached not-ready result reuse.
- Mixed dependency state response.

Existing health tests continue to cover unknown dependency filtering, empty dependency readiness,
cached ready results, and cache expiry.

## Validation Evidence

- Focused health tests passed with 9 tests:
  `python -m pytest tests\unit\libs\portfolio-common\test_health.py -q`.
- Scoped Ruff lint passed:
  `python -m ruff check src\libs\portfolio-common\portfolio_common\health.py tests\unit\libs\portfolio-common\test_health.py`.
- Scoped Ruff format check passed:
  `python -m ruff format --check src\libs\portfolio-common\portfolio_common\health.py tests\unit\libs\portfolio-common\test_health.py`.
- Repository lint gate passed:
  `make lint`.
- Type checking passed:
  `make typecheck`.
- Wiki/documentation gate passed:
  `make quality-wiki-docs-gate`.
- Whitespace diff check passed:
  `git diff --check`.

## Downstream Compatibility

The route path, HTTP status behavior, and top-level response shape are preserved. The intentional
contract expansion is that dependency status values can now include `timeout` and `error` in
addition to the existing `ok` and `unavailable` values.

No database schema, Kafka topic, runtime service topology, OpenAPI generation command, or client
success DTO changed.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, operations runbook, repository
context, quality scorecard, and refactor health report. No repo-local wiki update is required
because health/readiness operator truth is currently summarized in `docs/operations-runbook.md` and
the API route remains unchanged.

## Remaining Follow-Up

- Keep issue #599 open for PR/CI/QA evidence and Docker-backed service readiness proof.
- Extend the same bounded-dependency pattern if future readiness checks add additional dependency
  types beyond database and Kafka.
