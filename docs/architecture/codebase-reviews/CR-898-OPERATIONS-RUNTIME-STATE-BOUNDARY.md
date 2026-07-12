# CR-898: Operations Runtime State Boundary

Date: 2026-06-04

## Scope

Reduce `OperationsService` maintainability debt by moving reusable runtime metadata and
operational-state policy out of the service orchestration class without changing public service
methods, router contracts, repository reads, or response DTOs.

## Finding

`OperationsService` remained a C-ranked maintainability hotspot and still mixed operational
workflow orchestration with reusable source-data runtime metadata assembly, reconciliation status
aggregation, analytics export status normalization, export stale-running detection, and export
operational-state classification.

Those helpers are service policy, not repository access or router behavior, so keeping them in the
large orchestration class made the module harder to scan and harder to reuse.

## Action

Extracted focused runtime-state helpers into `operations_runtime_state.py`:

- `evidence_product_runtime_metadata(...)` builds source-data product runtime metadata.
- `aggregate_reconciliation_statuses(...)` owns reconciliation status precedence.
- `normalize_analytics_export_status(...)` and `normalize_analytics_export_status_filter(...)`
  own export status normalization.
- `analytics_export_operational_state(...)` and `is_analytics_export_job_stale(...)` own export
  runtime-state classification.

`OperationsService` keeps compatibility wrappers for existing tests and callers, but the policy
logic now lives in the focused helper module.

## Result

`OperationsService._evidence_product_runtime_metadata`,
`OperationsService._aggregate_statuses`, and
`OperationsService._get_analytics_export_operational_state` now each report `A (1)` under Radon
cyclomatic complexity.

`operations_service.py` improved from `C (5.44)` to `B (9.91)` under Radon maintainability. The
new `operations_runtime_state.py` helper module reports `A (46.40)`. This removes
`operations_service.py` from the current C-ranked maintainability list and reduces the source
C-hotspot count from 8 to 7.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\services\test_operations_service.py -q`
  => `57 passed`
- `python -m ruff check src\services\query_service\app\services\operations_service.py src\services\query_service\app\services\operations_runtime_state.py`
- `python -m ruff format src\services\query_service\app\services\operations_service.py src\services\query_service\app\services\operations_runtime_state.py`
- `python -m radon cc src\services\query_service\app\services\operations_service.py src\services\query_service\app\services\operations_runtime_state.py -s`
- `python -m radon mi src\services\query_service\app\services\operations_service.py src\services\query_service\app\services\operations_runtime_state.py -s`
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`

No integration selection was run for this slice. The change is an internal service-helper
extraction covered by focused operations-service unit tests.

## Wiki Decision

No wiki source update is required. This is an internal service-helper refactor and does not change
an operator-facing contract, API contract, or runbook.
