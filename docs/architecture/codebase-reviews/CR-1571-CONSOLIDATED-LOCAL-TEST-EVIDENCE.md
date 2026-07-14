# CR-1571: Consolidated Local Test Evidence

## Objective

Remove duplicate complete-suite execution from local parity while preserving fail-closed warning,
test-selection, coverage, and critical-path evidence.

## Finding

`make ci-local` previously ran the unit suite through `warning_budget_gate.py`, ran
integration-lite directly, and then ran both suites again through `coverage_gate.py`. The repeated
pytest-asyncio loop workload reproduced Windows `WinError 10055` after otherwise green tests and
made the normal local gate materially slower. The warning-runner unit test also lived below Query
Service even though the runner is repository-wide quality automation.

## Change

1. Added a reusable `run_suite_with_warning_budget` entrypoint that preserves manifest-owned suite
   selection and accepts the existing coverage options.
2. Made `coverage_gate.py` collect unit warning and coverage evidence from one process, with the
   warning budget still fixed at zero.
3. Removed standalone warning and integration-lite prerequisites from `ci-local`; the coverage
   gate already owns those exact executions.
4. Retained `warning-gate` in hosted `CI_GATES` so Linux lanes keep their early, isolated warning
   failure signal.
5. Moved the warning-runner test from Query Service to mirrored quality-script ownership and added
   coverage-runner plus local/hosted lane-composition guards.

## Measurable Improvement

- complete local unit-suite executions: two to one;
- local integration-lite executions: two to one;
- warning budget: unchanged at zero;
- aggregate coverage threshold: unchanged at 98%;
- source scope, marker exclusions, runtime profiles, coverage files, reports, and critical-path
  enforcement: unchanged.

Issue #755 recorded a 137.40-second standalone warning run and a 214.89-second covered unit run in
the prior passing gate. The new composition removes the standalone complete unit run and one
integration-lite run rather than masking resource exhaustion with sleep or retry behavior.

## Compatibility

No application source, API, OpenAPI schema, event, database, image, deployable service, or runtime
topology changed. The standalone `make warning-gate`, `make coverage-gate`, and hosted CI contracts
remain available. Only local parity orchestration and internal quality-runner composition changed.

## Validation

- warning, coverage, and local/hosted lane contract tests: `8 passed`;
- quality-runner, lane-governance, and script-organization tests: `16 passed`;
- `make -n ci-local` shows one unit-DB entrypoint and one coverage entrypoint, with no standalone
  unit warning or integration-lite execution;
- standalone combined coverage gate: `4,471` unit tests, `10` deselected, zero warnings, `136`
  integration-lite tests, 97.79% aggregate coverage, and 91.27% branch coverage passed in 311.88
  seconds; Windows `TIME_WAIT` moved from 204 to 393 without resource exhaustion;
- immediately following full `make ci-local`: all static/type/architecture/API gates, `10` unit-DB
  tests, the same `4,471` zero-warning unit tests, `136` integration-lite tests, and coverage gates
  passed in 541.37 seconds; `TIME_WAIT` moved from 308 to 343 without `WinError 10055`;
- focused Ruff lint/format and `git diff --check`: passed.

The exact-head Remote Feature Lane remains the pre-PR proof for this slice.

## Documentation Decision

README, testing wiki, automation README, repository context, and this review ledger changed because
the repo-native local validation contract changed. OpenAPI, supported-features, client capability,
and product wiki content require no change because application behavior did not change.
