# CR-954: Ingestion Operating Band Policy Boundary

Date: 2026-06-05

## Scope

Move ingestion operating-band classification policy out of `ingestion_job_service.py` without
changing runtime policy thresholds, operating-band response shape, service router contracts, or
operator-facing recommended actions.

## Finding

`classify_operating_band` lived in `ingestion_job_service.py` and mixed red/orange/yellow threshold
evaluation, breach-signal collection, and operator action selection in one C-ranked function. The
function reported `C (19)` complexity and kept runtime policy logic coupled to the broader
ingestion job service.

## Action

Added `ingestion_operating_band.py` with:

- `OperatingBandPolicy`
- `OperatingBandSignals`
- `OperatingBandDecision`
- `classify_operating_band`

`ingestion_job_service.py` still constructs `OPERATING_BAND_POLICY` from runtime settings and now
passes that policy explicitly into the extracted classifier. Existing imports from
`ingestion_job_service.py` remain available through compatibility imports.

## Result

`classify_operating_band` moved out of the service and now reports `B (7)` in an A-ranked helper
module. `ingestion_job_service.py` shrank from 1,633 SLOC to 1,545 SLOC and remains `C (0.00)`
under Radon maintainability, requiring additional focused extractions. The new operating-band
policy module reports `A (50.49)` maintainability.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_operating_band.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 18 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_operating_band.py tests\unit\services\ingestion_service\services\test_ingestion_operating_band.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_operating_band.py tests\unit\services\ingestion_service\services\test_ingestion_operating_band.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 4 files already formatted
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_operating_band.py`
  => `ingestion_job_service.py` 1,545 SLOC; operating-band helper 112 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_operating_band.py -s`
  => service `C (0.00)`, helper `A (50.49)`
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_operating_band.py -s`
  => extracted `classify_operating_band` `B (7)`; the service no longer reports the C-ranked
  classifier
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal policy-helper extraction that preserves
public API behavior, runtime thresholds, operating-band response fields, and operator-facing
recommended actions.
