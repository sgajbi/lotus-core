# RFC 060 - Ingestion API Idempotency and Async Job Contract Hardening

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-27 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core ingestion and operations maintainers |
| Depends On | RFC 065 throughput/operability controls |
| Related Standards | RFC-0067 OpenAPI quality and vocabulary governance; durability/consistency standards |
| Scope | In repo |

## Executive Summary
RFC 060 started as a phased hardening plan for ingestion acknowledgment contracts, idempotency signaling, and async job tracking. Current code has progressed beyond early slices: canonical ack DTOs, idempotency-header propagation, durable ingestion jobs, status/failure/retry APIs, and idempotency diagnostics are implemented.

The RFC document was stale; this revision aligns it with current implementation reality.

## Original Requested Requirements (Preserved)
1. Canonical acceptance contract for ingestion endpoints.
2. Optional `X-Idempotency-Key` contract.
3. `job_id` returned for asynchronous batch ingestion.
4. Preserve observability lineage (`correlation_id`, `request_id`, `trace_id`).
5. Future slices for persistent dedupe store and job-status APIs.

## Current Implementation Reality
1. Canonical ack DTOs exist: `IngestionAcceptedResponse` and `BatchIngestionAcceptedResponse`.
2. Routers generate `job_id` for batch paths and include lineage fields and optional idempotency key.
3. Kafka publish headers include propagated `idempotency_key`.
4. Durable ingestion job model and operations APIs are implemented (`/ingestion/jobs/*`).
5. Replay/retry and idempotency diagnostics APIs are implemented.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Canonical acceptance DTOs | Implemented | `src/services/ingestion_service/app/DTOs/ingestion_ack_dto.py`; `src/services/ingestion_service/app/ack_response.py` |
| Idempotency header acceptance/propagation | Implemented | `src/services/ingestion_service/app/request_metadata.py`; `src/services/ingestion_service/app/services/ingestion_service.py`; `tests/unit/services/ingestion_service/services/test_ingestion_service.py` |
| Batch `job_id` contract | Implemented | ingestion routers (`portfolios.py`, `transactions.py`, `instruments.py`, `business_dates.py`, etc.) |
| Job status/query API | Implemented (beyond original early slices) | `src/services/ingestion_service/app/routers/ingestion_jobs.py`; `src/services/ingestion_service/app/services/ingestion_job_service.py` |
| Persistent job/idempotency storage | Implemented | `src/libs/portfolio-common/portfolio_common/database_models.py` (`ingestion_jobs`, related entities) |
| Idempotency diagnostics and replay governance | Implemented | `src/services/ingestion_service/app/routers/ingestion_jobs.py` (`/ingestion/idempotency/diagnostics`, replay endpoints) |

## Design Reasoning and Trade-offs
1. Early contract normalization improved external integration safety without waiting for full ops stack.
2. Extending into durable job/replay APIs improved incident response and eliminated DB-first troubleshooting dependence.
3. Expanded ingestion-ops surface increases complexity but provides stronger operational control and auditable recovery.

## Gap Assessment
1. RFC narrative previously reflected only slices 1-2; this revision captures current operational scope.
2. No blocking implementation gap remains for semantic clarity after adding endpoint-level idempotency matrix below.

## Deviations and Evolution Since Original RFC
1. Original non-goal excluded job-status API; implementation now includes full job-status/retry suite.
2. Original future slices for persistent tracking are already delivered.

## Proposed Changes
1. Rebaseline RFC 060 as implemented ingestion contract + operations hardening record.
2. Keep endpoint-level semantic matrix in this RFC synchronized with ingestion router/repository behavior.

## Endpoint Idempotency Semantics Matrix
| Endpoint Family | Idempotency Header Accepted | Persistence Deduplication Guarantee | Notes |
| --- | --- | --- | --- |
| `/ingest/portfolios` | Yes (`X-Idempotency-Key`) | Deterministic upsert by business key (`portfolio_id`) | Duplicate requests converge to same portfolio state. |
| `/ingest/instruments` | Yes (`X-Idempotency-Key`) | Deterministic upsert by business key (`security_id`) | Duplicate requests converge to same instrument state. |
| `/ingest/transactions` | Yes (`X-Idempotency-Key`) | Deterministic upsert by business key (`transaction_id`) + consumer idempotency guard | Replay-safe for both transaction row and consumer processing stage. |
| `/ingest/market-prices` | Yes (`X-Idempotency-Key`) | Deterministic upsert by (`security_id`, `price_date`) | Same key/date payloads are idempotent. |
| `/ingest/fx-rates` | Yes (`X-Idempotency-Key`) | Deterministic upsert by (`from_currency`, `to_currency`, `rate_date`) | Same pair/date payloads are idempotent. |
| `/ingest/business-dates` | Yes (`X-Idempotency-Key`) | Deterministic upsert by (`calendar_code`, `date`) | Safe replay for calendar/day ingestion. |
| `/ingestion/jobs/*` operations | Job-scoped controls (not payload idempotency header) | Idempotent read/retry semantics via durable `job_id` and replay audit identifiers | Control-plane idempotency is job-context based. |

## Test and Validation Evidence
1. `tests/integration/services/ingestion_service/test_ingestion_routers.py`
2. `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
3. `tests/unit/services/ingestion_service/services/test_ingestion_service.py`
4. `src/services/ingestion_service/app/routers/ingestion_jobs.py`
5. `src/services/ingestion_service/app/services/ingestion_job_service.py`

## Original Acceptance Criteria Alignment
1. Canonical ack responses: aligned.
2. Batch `job_id`: aligned.
3. Idempotency header propagation: aligned.
4. Job status and async contract hardening: aligned and extended beyond original phase.

## Rollout and Backward Compatibility
1. Existing `202` acceptance behavior is preserved with stronger typed payloads.
2. Added operations endpoints are additive and improve operability without breaking ingestion producers.

## Open Questions
1. Should strict dedupe guarantees become mandatory for all ingestion entity types, or stay endpoint-specific with diagnostics?
2. Should replay-policy controls be codified as platform-wide standards to align all Lotus apps?

## Next Actions
1. Keep ingestion-ops API contract tests as required gate for future ingestion changes.
2. Update this matrix whenever endpoint semantics change.
