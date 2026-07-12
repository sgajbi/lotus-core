# CR-065 Ingestion Job Shared Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`
- `tests/integration/services/event_replay_service/test_event_replay_app.py`

## Findings

- The event-replay and ingestion-operations router surfaces were already documented well enough operationally.
- The weaker part was the shared ingestion-job DTO layer:
  - list wrappers still lacked concrete examples
  - backlog summary metadata was thinner than the surrounding control-plane routes
  - policy metadata was missing an explicit replay dry-run capability flag in the shared schema

## Actions taken

- Added example-backed shared schema depth for:
  - `IngestionJobListResponse.jobs`
  - `IngestionJobFailureListResponse.failures`
  - `IngestionReprocessingQueueHealthResponse.queues`
- Added explicit shared operational metadata for:
  - `IngestionHealthSummaryResponse.oldest_backlog_job_id`
  - `IngestionOpsPolicyResponse.replay_dry_run_supported`
- Added event-replay app OpenAPI assertions to lock the richer shared-schema behavior in place.

## Result

- The ingestion-job shared DTO family now reads as a reusable control-plane contract instead of a thin support schema behind stronger routers.

## Evidence

- `python -m pytest tests/integration/services/event_replay_service/test_event_replay_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
