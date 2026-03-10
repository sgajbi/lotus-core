# CR-028 Event Replay Swagger Depth Review

## Scope

Raise the highest-value operational endpoints in `event_replay_service` from
baseline OpenAPI compliance to stronger operator-grade Swagger quality.

## Finding

The service already had operation-level examples, but several core operational
endpoints still under-documented:

- path identifiers
- query filters
- common not-found and conflict responses

This was especially visible on:

- `GET /ingestion/jobs/{job_id}`
- `GET /ingestion/jobs`
- `GET /ingestion/jobs/{job_id}/failures`
- `GET /ingestion/jobs/{job_id}/records`
- `POST /ingestion/jobs/{job_id}/retry`
- `POST /ingestion/dlq/consumer-events/{event_id}/replay`
- `GET /ingestion/audit/replays`

## Action Taken

1. Added descriptions and examples for the main path/query parameters.
2. Added explicit `404` and `409` response examples for the core replay/job
   remediation endpoints.
3. Added an OpenAPI integration test that asserts these richer parameters and
   error examples are present.

## Result

The event replay control-plane surface is now materially clearer for operators:

- identifiers are described
- filters are explained
- the primary error responses are documented with real payload shapes

## Evidence

- `src/services/event_replay_service/app/routers/ingestion_operations.py`
- `tests/integration/services/event_replay_service/test_event_replay_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
