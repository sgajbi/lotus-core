# RFC 060 - Ingestion API Idempotency and Async Job Contract Hardening

## Status
Draft (implemented slices 1-2 in this change set)

## Problem Statement
Current ingestion endpoints are functionally correct but operationally weak:
- batch `202` responses do not provide a stable ingestion job identifier;
- idempotent client retries are not first-class in the API contract;
- response envelopes vary and provide limited request lineage fields.

This makes external system integrations harder to operate safely at scale, and increases ambiguity during replay/retry incidents.

## Goals
- Introduce a canonical ingestion acknowledgment contract across ingestion APIs.
- Add optional request idempotency contract via `X-Idempotency-Key`.
- Return `job_id` for asynchronous batch-style ingestion requests.
- Preserve API-first and observability-first operation patterns.

## Non-Goals
- Persistent idempotency deduplication store (header propagation only in this RFC slice).
- Full ingestion job persistence/status query API.
- Any change to downstream calculator processing semantics.

## Proposed Contract
- Canonical response models:
  - `IngestionAcceptedResponse` (single-entity acceptance)
  - `BatchIngestionAcceptedResponse` (batch acceptance + `job_id`)
- Required lineage fields in responses:
  - `correlation_id`, `request_id`, `trace_id`
- Optional retry safety field:
  - `idempotency_key` from `X-Idempotency-Key`

## Architectural Placement
- API contracts: `src/services/ingestion_service/app/DTOs/ingestion_ack_dto.py`
- Request metadata helpers: `src/services/ingestion_service/app/request_metadata.py`
- Header propagation into Kafka publish path:
  - `src/services/ingestion_service/app/services/ingestion_service.py`
- Endpoint contract application:
  - `src/services/ingestion_service/app/routers/*`

## Incremental Slices
1. Slice 1: Canonical ingestion acknowledgment response models.
2. Slice 2: `X-Idempotency-Key` acceptance and Kafka header propagation.
3. Slice 3: Persistent idempotency store with deterministic replay behavior.
4. Slice 4: Ingestion job repository + `GET /ingestion/jobs/{job_id}` status API.
5. Slice 5: Validation-only mode for all ingestion resources.

## Verification Strategy
- Unit tests for service header propagation and contract behavior.
- Integration tests for router acceptance response shape and status codes.
- OpenAPI quality gate:
  - endpoint summary/description/tags/responses
  - schema field description + examples
  - duplicate `operationId` prevention

## Risks and Mitigations
- Risk: Clients parsing old free-form response payloads.
  - Mitigation: maintain `202` behavior, enrich response with stable schema and descriptive `message`.
- Risk: Idempotency interpreted as guaranteed dedupe.
  - Mitigation: explicit documentation that current slice propagates key; dedupe persistence is a follow-up slice.

## Definition of Done (for this RFC phase)
- Ingestion endpoints return canonical acceptance contract.
- Batch endpoints include `job_id`.
- `X-Idempotency-Key` is accepted and propagated to Kafka headers.
- Tests pass and OpenAPI quality gate passes.

