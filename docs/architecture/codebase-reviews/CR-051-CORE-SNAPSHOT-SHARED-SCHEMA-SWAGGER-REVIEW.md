# CR-051 Core Snapshot Shared Schema Swagger Review

## Scope
- Shared `query_service` integration DTOs for core snapshot response metadata and nested section payloads
- OpenAPI component quality for reusable control-plane snapshot schemas

## Findings
- The router contract for `POST /integration/portfolios/{portfolio_id}/core-snapshot` was already strong.
- The remaining weakness was in reusable component schemas:
  - governance section lists had descriptions but no concrete examples
  - freshness metadata lacked a timestamp field/example for baseline lineage inspection
  - section payload examples were too thin for baseline/projected/delta inspection in Swagger
- This reduced schema-first usefulness for downstream consumers and API reviewers.

## Actions Taken
- Added concrete examples for `requested_sections`, `applied_sections`, and `dropped_sections` in `CoreSnapshotGovernanceMetadata`.
- Added explicit example content for `policy_provenance`.
- Added `snapshot_timestamp` metadata to `CoreSnapshotFreshnessMetadata` with description/example.
- Deepened section payload examples for:
  - `positions_baseline`
  - `positions_projected`
  - `positions_delta`
  - `instrument_enrichment`
- Added OpenAPI integration assertions to lock the richer component schema contract.

## Follow-up
- Continue the shared-schema depth pass on the next weakest integration or reference DTO surface.
- Prefer enriching reusable component schemas only where router-level docs are already strong.

## Evidence
- `src/services/query_service/app/dtos/core_snapshot_dto.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
