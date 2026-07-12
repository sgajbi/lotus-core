# CR-043 Event Replay Shared Schema Swagger Review

Date: 2026-03-10  
Status: Hardened

## Scope

Shared replay and ingestion-operations DTO schemas surfaced by `event_replay_service` via
components imported from `ingestion_service`.

Reviewed schemas:

- `IngestionOpsModeResponse`
- `IngestionOpsModeUpdateRequest`
- `ConsumerDlqReplayRequest`
- `IngestionReplayAuditListResponse`
- `IngestionIdempotencyDiagnosticsResponse`

## Findings

The router layer for `event_replay_service` was already strong after CR-028. The remaining Swagger
quality gap was in shared DTO components: field descriptions on replay and operations payloads were
thinner than the surrounding router contracts, which made `/openapi.json` less useful once the user
navigated into the component schemas.

## Actions Taken

- Tightened field-level descriptions for the highest-value shared replay and operations DTOs.
- Added an OpenAPI integration assertion that verifies the richer component-schema descriptions are
  present in the published spec.
- Left the existing router-level request/response examples intact; this slice was about shared
  schema depth, not changing endpoint behavior.

## Follow-up

Continue the same schema-depth pass on shared DTOs used by other active HTTP services where router
contracts are already strong but component schemas are still thin.

## Evidence

- `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`
- `tests/integration/services/event_replay_service/test_event_replay_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
