# CR-1217 Query-Control-Plane Problem-Details Guard

Date: 2026-07-01

## Objective

Convert the repeated GitHub issue #677 query-control-plane error-contract lesson into a reusable
local and CI guard. QCP means query-control-plane: the
`src/services/query_control_plane_service` backend that owns governed analytics-input,
snapshot/simulation, integration-policy, source-data, and support/control-plane APIs.

## Change

- Added `scripts/qcp_problem_details_guard.py`.
- Added `make qcp-problem-details-guard`.
- Wired the guard into `make lint` so the defect class fails early in the static-quality lane.
- Added focused guard tests for FastAPI and Starlette `HTTPException` imports, direct
  `HTTPException` calls, `detail=str(...)` keyword payloads, and `{"detail": str(...)}` payloads.
- Added a current-state assertion that all active query-control-plane router files pass the guard.

## Expected Improvement

Future query-control-plane router changes can no longer silently reintroduce the issue #677 raw
error pattern after the migrated baseline. Developers and agents now get a deterministic,
source-location-specific failure before expensive integration or OpenAPI gates.

## Tests Added

- `tests/unit/scripts/test_qcp_problem_details_guard.py` covers failing and passing guard behavior.
- The current active query-control-plane router set is scanned by the unit test and the
  repo-native guard command.

## Validation Evidence

- `python -m pytest tests/unit/scripts/test_qcp_problem_details_guard.py -q` passed with 6 tests.
- `make qcp-problem-details-guard` passed.
- `make lint` passed, proving the guard runs inside the Feature Lane, PR Merge Gate, and Main
  Releasability lint target without weakening existing quality gates.
- `python -m ruff check scripts/qcp_problem_details_guard.py tests/unit/scripts/test_qcp_problem_details_guard.py --ignore E501,I001`
  passed.
- `python -m ruff format --check scripts/qcp_problem_details_guard.py tests/unit/scripts/test_qcp_problem_details_guard.py`
  passed.
- `make typecheck` passed with no issues in 50 source files.
- `make quality-unit-collection-gate` passed with 3,255 of 3,265 unit tests collected and 10
  manifest deselects.
- `make quality-wiki-docs-gate` and `git diff --check` passed.

## Downstream Compatibility

No API route, OpenAPI contract, runtime response payload, database schema, Kafka contract, or
downstream source-data envelope changed. This slice adds prevention only.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, repository context, and quality/refactor
scorecards were updated. No wiki update is required because no operator command, runbook, or
published workflow changed.

## Remaining Follow-Up

- Continue issue-backed migration of any future query-control-plane route-family raw-error findings.
- Consider promoting additional problem-details media-type inventory only after OpenAPI false
  positives are fully understood.
