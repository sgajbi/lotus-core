# CR-1113: Ingestion Operating-Band Boundary

Date: 2026-06-20

## Scope

`IngestionJobService.get_operating_band(...)` still assembled SLO status, error-budget pressure,
operating-band classifier signals, and `IngestionOperatingBandResponse` directly in the service
facade. The operating-band classifier already lived in `ingestion_operating_band.py`, so response
assembly belonged with that policy boundary rather than in the public service facade.

## Change

- Added `load_operating_band_response(...)` to `ingestion_operating_band.py`.
- Kept `IngestionJobService.get_operating_band(...)` as a thin delegate that supplies configured
  thresholds, policy, and the existing SLO/error-budget loaders.
- Updated tests so operating-band classifier imports come from the helper module instead of the
  service facade.
- Added direct helper coverage proving loader arguments, red-band decisioning, and response DTO
  fields.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
- Radon reports `ingestion_job_service.py` improved from `A (48.85)` / 512 lines to `A (49.41)` /
  490 lines. `ingestion_operating_band.py` remains A-ranked maintainability at `A (49.28)` /
  156 lines, with the new response loader A-ranked by cyclomatic complexity.

## Follow-Up

Continue reducing `IngestionJobService` only by cohesive public-facade responsibilities that have
direct helper tests and measurable maintainability movement.
