# CR-966: Ingestion Replay Audit Helper Boundary

Date: 2026-06-05

## Scope

Move replay-audit list filtering, ordering, row mapping, and response construction into a dedicated
helper module without changing public replay-audit service methods, response fields, filter
semantics, or ordering by most recent request time.

## Finding

`IngestionJobService.list_replay_audits` mixed optional audit filters, SQL statement construction,
bounded ordering, database read execution, and DTO mapping in one B-ranked service method. The
method supports incident forensics and replay governance review, so preserving behavior and
testability is more important than changing endpoint behavior.

## Action

Added `ingestion_replay_audits.py` with `list_replay_audit_responses` and
`to_replay_audit_response`. `IngestionJobService.list_replay_audits` now delegates to the helper
while passing the service module's session factory, preserving the existing monkeypatch seam and
public method contract. `get_replay_audit` reuses the shared mapper.

## Result

`IngestionJobService.list_replay_audits` improved from `B (7)` to `A (1)`. The extracted helper
module reports `A (72.80)` maintainability. `ingestion_job_service.py` shrank from 1,137 SLOC to
1,116 SLOC and improved from `B (11.79)` to `B (12.63)`.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 15 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => passed after formatting touched files
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py`
  => `ingestion_job_service.py` 1,116 SLOC; `ingestion_replay_audits.py` 46 SLOC
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py -s`
  => `ingestion_job_service.py` `B (12.63)`; `ingestion_replay_audits.py` `A (72.80)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal replay-audit helper extraction that preserves
public API contracts, filter semantics, and operator-facing documentation truth.
