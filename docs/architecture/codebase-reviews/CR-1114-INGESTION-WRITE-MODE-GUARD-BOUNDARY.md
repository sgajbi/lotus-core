# CR-1114: Ingestion Write-Mode Guard Boundary

Date: 2026-06-20

## Scope

`IngestionJobService.assert_ingestion_writable()` still owned ingestion-mode metric mapping and
paused/drain write-denial policy inline. Ops-mode persistence already lived in
`ingestion_ops_mode.py`, so write-mode assertion belonged with the same operating-control boundary.

## Change

- Added `assert_ingestion_writable_mode(...)` to `ingestion_ops_mode.py`.
- Kept `IngestionJobService.assert_ingestion_writable()` as a thin delegate over the existing
  `get_ops_mode` loader and `INGESTION_MODE_STATE` metric.
- Added direct helper tests proving normal-mode metric state and paused-mode denial behavior.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_ops_mode.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_ops_mode.py tests/unit/services/ingestion_service/services/test_ingestion_ops_mode.py`
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_ops_mode.py tests/unit/services/ingestion_service/services/test_ingestion_ops_mode.py`
- Radon reports `IngestionJobService.assert_ingestion_writable` reduced from `A (2)` to `A (1)`.
  `ingestion_ops_mode.py` remains A-ranked maintainability at `A (58.59)`, with the new helper
  A-ranked by cyclomatic complexity.

## Follow-Up

Continue extracting ingestion facade responsibilities only when the target helper owns the
corresponding policy boundary and the slice keeps operator-facing behavior directly tested.
