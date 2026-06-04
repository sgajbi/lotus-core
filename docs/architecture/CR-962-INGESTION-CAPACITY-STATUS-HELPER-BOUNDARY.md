# CR-962: Ingestion Capacity Status Helper Boundary

Date: 2026-06-05

## Scope

Move ingestion capacity-status query orchestration and per-group capacity calculations into a
dedicated helper module without changing response fields, capacity formulas, saturation thresholds,
replica defaults, or the public `IngestionJobService.get_capacity_status` service method.

## Finding

`IngestionJobService.get_capacity_status` mixed time-window setup, capacity default resolution,
SQL aggregate construction, grouped row normalization, per-group capacity calculations, and
response assembly in one B-ranked service method. The service remained the only active
non-generated C-ranked source hotspot after CR-961.

## Action

Added `ingestion_capacity_status.py` with:

- `_derive_capacity_group`
- `load_capacity_status_response`

`IngestionJobService.get_capacity_status` now delegates to the helper while passing the service
module's session factory, preserving existing monkeypatch seams and behavior tests. The original
`_derive_capacity_group` import surface remains available from `ingestion_job_service.py` for
existing tests and callers.

## Result

`IngestionJobService.get_capacity_status` improved from `B (9)` to `A (1)`. The extracted helper
module reports `A (43.64)` maintainability. `ingestion_job_service.py` shrank from 1,420 SLOC to
1,304 SLOC and improved from `C (2.32)` to `C (5.70)`, but remains the remaining active
non-generated C-ranked source hotspot.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py -q`
  => 20 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_capacity_status.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 4 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_capacity_status.py`
  => `ingestion_job_service.py` 1,304 SLOC; `ingestion_capacity_status.py` 142 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_capacity_status.py -s`
  => `ingestion_job_service.py` `C (5.70)`; `ingestion_capacity_status.py` `A (43.64)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal service/helper extraction that preserves
public API contracts, operational capacity semantics, and operator-facing documentation truth.
