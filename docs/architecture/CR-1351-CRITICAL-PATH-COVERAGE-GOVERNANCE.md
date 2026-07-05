# CR-1351 Critical-Path Coverage Governance

Date: 2026-07-05

Related issue: `sgajbi/lotus-core#612`

## Objective

Separate aggregate coverage, changed-code coverage, and high-risk critical-path coverage evidence so
the PR gate cannot rely only on one repository-wide percentage.

## Expected Improvement

- Keeps the existing branch-aware 98% aggregate threshold.
- Adds a governed contract for critical transaction lifecycle, calculation, state-transition,
  security, ingestion/replay/outbox, repository, and API-contract module families.
- Writes machine-readable changed-code and critical-path coverage evidence under `output/coverage/`.
- Ties each critical path to expected test families and existing repo-native test suites.

## Implementation

- Added `docs/standards/critical-path-coverage.v1.json`.
- Added `scripts/critical_path_coverage_guard.py`.
- Updated `scripts/coverage_gate.py` to emit `output/coverage/coverage.json` and
  `output/coverage/critical-path-coverage-report.json`.
- Added `make critical-path-coverage-guard` and lint/docs evidence wiring.
- Updated PR and main coverage jobs to fetch base history and pass changed-code base context.
- Fixed same-pattern drift surfaced while validating the gate:
  - stale reducer constant imports in transaction registry tests,
  - stale runtime-boundary guard expectations for direct Kafka publishes,
  - stale time-provider guard expectations after the clock provider extraction,
  - canonical advisory simulation execution failures now return the documented
    `application/problem+json` contract response instead of falling through to the generic JSON 500.

## Tests Added

- `tests/unit/scripts/test_critical_path_coverage_guard.py`
  - validates the current contract,
  - rejects unknown manifest suites,
  - classifies measured and unmeasured changed critical files,
  - fails low measured critical-path coverage,
  - proves explicit changed-file report generation.
- `tests/integration/services/query_service/test_advisory_simulation_router.py`
  - covers canonical advisory simulation execution-failure problem details.

## Downstream Compatibility

No success-path API, OpenAPI schema, DTO, database schema, Kafka, metric, Docker image, or deployment
contract changed. One error-path behavior was restored to the documented contract:
`POST /integration/advisory/proposals/simulate-execution` execution failures now return
`application/problem+json` with `CANONICAL_SIMULATION_EXECUTION_FAILED` instead of the generic JSON
500.

## Documentation And Context

- Updated `README.md`.
- Updated `wiki/Validation-and-CI.md`.
- Updated `REPOSITORY-ENGINEERING-CONTEXT.md`.
- No central platform context or skill source changed; the existing CI-enforcement skill already
  covers this pattern.

## Validation Evidence

Planned and recorded before commit:

- `python -m pytest tests/unit/scripts/test_critical_path_coverage_guard.py -q`
- `python scripts/critical_path_coverage_guard.py --contract-only`
- `python -m pytest tests/integration/services/query_service/test_advisory_simulation_router.py::test_advisory_simulation_execution_router_returns_problem_details_on_execution_failure -q`
- scoped Ruff lint/format for the new guard and tests
- `make docs-evidence-pack`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`
