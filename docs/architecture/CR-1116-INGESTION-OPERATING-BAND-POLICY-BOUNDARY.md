# CR-1116: Ingestion Operating-Band Policy Boundary

Date: 2026-06-20

## Scope

`IngestionJobService` still constructed `OPERATING_BAND_POLICY` directly from runtime operating-band
settings. `ingestion_operating_band.py` already owned operating-band classification and response
assembly, so threshold setting mapping belonged in the same module.

## Change

- Added `build_operating_band_policy(...)` to `ingestion_operating_band.py`.
- Kept the service facade constant as a delegate over `_RUNTIME_POLICY.operating_band`.
- Added direct helper coverage proving yellow/orange/red backlog-age and DLQ-pressure thresholds
  map exactly from runtime settings.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_operating_band.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
- `python -m pytest tests/unit/services/ingestion_service/services -q`
- `make lint`
- `make typecheck`
- `make quality-maintainability-gate`
- `make quality-complexity-gate`
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- `git diff --check`
- Radon reports `build_operating_band_policy` is `A (1)`, `IngestionJobService.get_operating_band`
  remains `A (1)`, `ingestion_job_service.py` remains A-ranked at `A (100.00)`, and
  `ingestion_operating_band.py` remains A-ranked at `A (48.91)`.

## Follow-Up

Continue extracting ingestion facade responsibilities only where a focused helper owns the
corresponding policy or read-model boundary and tests can pin operator-facing behavior.
