# CR-1136 Ingestion Write Rate-Limit Boundary

Date: 2026-06-22

## Scope

Privileged ingestion write rate limiting in
`src/services/ingestion_service/app/ops_controls.py`.

## Finding

`enforce_ingestion_write_rate_limit(...)` owned feature-flag handling, record-count flooring,
window eviction, projected request/record usage calculation, budget breach detection, error-message
assembly, and event recording in one B-ranked helper. The behavior was deterministic, but the
helper was security/operability-adjacent and shared by many ingestion write routers.

Radon reported:

- `enforce_ingestion_write_rate_limit`: `B (6)`

## Action Taken

Extracted focused helpers for:

- record-count normalization,
- projected request and record usage calculation,
- budget breach detection,
- rate-limit error message construction,
- write-event recording.

Added direct unit coverage proving disabled mode is a no-op, zero record counts floor to one,
projected record-budget breaches fail without recording a second event, and endpoint buckets remain
isolated.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\ingestion_service\test_ops_controls.py -q`
- Result: `8 passed`

Focused static proof:

- `python -m ruff check src\services\ingestion_service\app\ops_controls.py tests\unit\services\ingestion_service\test_ops_controls.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\ingestion_service\app\ops_controls.py -s`
- Result: `enforce_ingestion_write_rate_limit` is `A (3)`, and every function/class in
  `ops_controls.py` is A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\ingestion_service\app\ops_controls.py -s`
- Result: `A (33.25)`

Measured movement:

- `enforce_ingestion_write_rate_limit`: `B (6)` -> `A (3)`
- `ops_controls.py`: no B-or-worse functions/classes remain

## Residual Risk

This slice does not change API routes, rate-limit configuration names, HTTP error mapping, window
duration semantics, request-budget semantics, record-budget semantics, or endpoint scoping. It keeps
the existing in-process rate-limit store unchanged; distributed rate limiting remains outside this
local helper-boundary refactor.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of ingestion write throttling,
- direct proof for budget and endpoint scoping behavior,
- lower-noise tests for privileged ingestion ops controls.

It does not claim full bank-buyable readiness for `lotus-core`.
