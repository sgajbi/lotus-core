# CR-1106: Ingestion Replay-Audit Boundary

Date: 2026-06-17

## Scope

Move consumer-DLQ replay-audit persistence, duplicate lookup, and metric side effects out of
`ingestion_job_service.py` without changing API behavior, retry/replay semantics, database schema,
metric names, metric labels, or router contracts.

## Finding

`IngestionJobService` still owned successful replay-audit fingerprint lookup, replay-audit row
creation, duplicate-blocked metric accounting, and replay-failure metric accounting inline, while
`ingestion_replay_audits.py` already owned replay-audit response mapping and listing. The public
methods were A-ranked, but the service remained the current ingestion maintainability target and
mixed replay-audit persistence policy with ingestion lifecycle orchestration.

## Action

Expanded `ingestion_replay_audits.py` with:

- `find_successful_replay_audit_by_fingerprint_response`
- `record_consumer_dlq_replay_audit_response`
- `get_replay_audit_response`
- replay-audit status sets and metric recording policy

`IngestionJobService` now keeps the public method signatures while delegating replay-audit lookup,
single-audit read, audit write, and metric side effects to the helper module. Added direct unit
coverage for successful fingerprint lookup, missing lookup, audit persistence, completed timestamp
posture, and duplicate/failure metric routing.

## Result

`ingestion_job_service.py` improved from the last recorded `A (22.62)` / 762 SLOC to `A (25.65)` /
726 SLOC under Radon. The expanded replay-audit helper reports `A (52.41)`, and the service's
replay-audit public methods are now thin `A (1)` delegates.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_replay_audits.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py -q`
  => 21 passed
- `python -m pytest tests\unit\services\ingestion_service\services -q`
  => 79 passed
- `python -m ruff check src\services\ingestion_service\app\services\ingestion_replay_audits.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\unit\services\ingestion_service\services\test_ingestion_replay_audits.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_replay_audits.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\unit\services\ingestion_service\services\test_ingestion_replay_audits.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_guardrails.py`
  => 4 files already formatted
- `python -m radon mi src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py -s`
  => service `A (25.65)`, helper `A (52.41)`
- `python -m radon raw src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py`
  => service 726 SLOC, helper 137 SLOC
- `python -m radon cc src\services\ingestion_service\app\services\ingestion_job_service.py src\services\ingestion_service\app\services\ingestion_replay_audits.py -s -a`
  => all service replay-audit methods `A (1)`; helper average complexity `A (1.90)`

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, metric contracts, OpenAPI contracts, retry/replay semantics, and
operator-facing documentation truth.
